#!/usr/bin/env python3
"""
Issue #60: Grant Memory data plane permissions to harness execution roles.

Closes the IAM gap where PR #54 wired BugFix Memory to BugFixAgentHarness
but the harness's execution role had no Memory data plane perms for the
new Memory ARN. Every BugFixAgent invocation failed at session-start with
AccessDeniedException on bedrock-agentcore:ListEvents.

This module exposes a reusable function `grant_memory_access_for_harness`
that idempotently ensures one harness's role has the canonical
`<HarnessName>MemoryAccess` inline policy. It also runs as a CLI that
discovers ALL harnesses with Memory wired and applies the grant to each
(useful for drift detection).

Per AGENTS.md §3.9: Memory wiring = create_memory + update_harness + IAM grant.
This module is the third step.

Idempotent — re-running with no IAM drift makes zero API mutations.

Usage as CLI:
  python3 grant_memory_access.py [--dry-run] [--verbose]

Usage as library (issue #63):
  from grant_memory_access import grant_memory_access_for_harness
  result = grant_memory_access_for_harness(harness_id, dry_run=False)
  # → {"action": "apply" | "noop", "policy_name": str, "harness_name": str, ...}
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from typing import Any

import boto3
import botocore

REGION = "us-east-1"
REQUIRED_BOTO3 = (1, 43, 18)


def redact(s: str) -> str:
    """Redact account IDs and short resource suffixes for safe logging."""
    s = re.sub(r"\b\d{12}\b", "<ACCOUNT_ID>", s)
    s = re.sub(r"-[a-zA-Z0-9]{10}\b", "-<ID>", s)
    return s


def check_boto3():
    parts = tuple(int(x) for x in boto3.__version__.split(".")[:3])
    if parts < REQUIRED_BOTO3:
        sys.exit(
            f"boto3 {boto3.__version__} too old. Need >= "
            f"{'.'.join(str(p) for p in REQUIRED_BOTO3)} for harness ops."
        )


def policy_for(memory_arn: str, namespaces: list) -> dict:
    """Build the canonical Memory access policy for one (role, memoryArn)."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "MemoryEvents",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:CreateEvent",
                    "bedrock-agentcore:DeleteEvent",
                    "bedrock-agentcore:DeleteMemoryRecord",
                    "bedrock-agentcore:GetEvent",
                    "bedrock-agentcore:GetMemory",
                    "bedrock-agentcore:GetMemoryRecord",
                    "bedrock-agentcore:ListActors",
                    "bedrock-agentcore:ListEvents",
                    "bedrock-agentcore:ListSessions",
                ],
                "Resource": memory_arn,
            },
            {
                "Sid": "MemoryRetrieval",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:ListMemoryRecords",
                    "bedrock-agentcore:RetrieveMemoryRecords",
                ],
                "Resource": memory_arn,
                "Condition": {
                    "StringLike": {
                        "bedrock-agentcore:namespace": namespaces or ["*"]
                    }
                },
            },
        ],
    }


def normalize_for_compare(p: dict) -> str:
    """JSON-canonical for comparison (handles dict-key ordering, list ordering)."""
    def canonical(obj):
        if isinstance(obj, dict):
            return {k: canonical(obj[k]) for k in sorted(obj)}
        if isinstance(obj, list):
            try:
                return sorted(canonical(x) for x in obj)
            except TypeError:
                return [canonical(x) for x in obj]
        return obj
    return json.dumps(canonical(p), separators=(",", ":"))


def namespaces_from_config(retrieval_config: dict) -> list:
    """Convert retrievalConfig keys (with placeholders) to IAM-condition glob patterns.

    Per AGENTS.md §3.9 namespace conversion rule:
      /fix-patterns/{actorId}                → /fix-patterns/*
      /fix-history/{actorId}/{sessionId}     → /fix-history/*/*
    """
    out = []
    for ns_key in retrieval_config.keys():
        pattern = re.sub(r"\{[^}]+\}", "*", ns_key)
        out.append(pattern)
    return sorted(set(out))


def grant_memory_access_for_harness(
    harness_id: str,
    *,
    control_client: Any = None,
    iam_client: Any = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """Idempotently grant Memory data plane perms to one harness's execution role.

    Args:
        harness_id: harnessId (e.g. "BugFixAgentHarness-<ID>")
        control_client: optional pre-created bedrock-agentcore-control client
        iam_client: optional pre-created iam client
        dry_run: if True, print planned change but don't mutate IAM
        verbose: if True, print extra detail

    Returns:
        dict with keys: action ("apply"|"noop"|"skip"), policy_name, harness_name,
                         memory_arn (or None if no memory wired), namespaces.
        action="skip" means the harness has no Memory wired.

    Raises:
        ClientError: if iam:PutRolePolicy or iam:GetRolePolicy fails
        botocore.exceptions.ClientError: if get_harness fails
    """
    if control_client is None:
        control_client = boto3.client("bedrock-agentcore-control", region_name=REGION)
    if iam_client is None:
        iam_client = boto3.client("iam", region_name=REGION)

    detail = control_client.get_harness(harnessId=harness_id)["harness"]
    name = detail.get("harnessName")

    mem_cfg = detail.get("memory", {}).get("agentCoreMemoryConfiguration")
    if not mem_cfg:
        return {
            "action": "skip",
            "policy_name": None,
            "harness_name": name,
            "memory_arn": None,
            "namespaces": [],
            "reason": "no Memory wired to this harness",
        }

    role_arn = detail.get("executionRoleArn")
    mem_arn = mem_cfg.get("arn")
    retrieval_cfg = mem_cfg.get("retrievalConfig", {})
    namespaces = namespaces_from_config(retrieval_cfg)

    if not (role_arn and mem_arn):
        raise ValueError(f"{name}: missing role or memory ARN")

    role_name = role_arn.split("/")[-1]
    policy_name = f"{name}MemoryAccess"
    desired = policy_for(mem_arn, namespaces)

    try:
        existing = iam_client.get_role_policy(
            RoleName=role_name, PolicyName=policy_name
        )["PolicyDocument"]
    except iam_client.exceptions.NoSuchEntityException:
        existing = None

    is_drift = (
        existing is None
        or normalize_for_compare(existing) != normalize_for_compare(desired)
    )

    result = {
        "policy_name": policy_name,
        "harness_name": name,
        "memory_arn": mem_arn,
        "role_name": role_name,
        "namespaces": namespaces,
    }

    if verbose:
        print(f"    role:       {redact(role_name)}")
        print(f"    memory:     {redact(mem_arn)}")
        print(f"    namespaces: {namespaces}")
        print(f"    policy:     {policy_name}")
        print(f"    drift:      {'YES — will apply' if is_drift else 'no — already matches'}")

    if not is_drift:
        result["action"] = "noop"
        return result

    if dry_run:
        result["action"] = "dry-run"
        return result

    iam_client.put_role_policy(
        RoleName=role_name,
        PolicyName=policy_name,
        PolicyDocument=json.dumps(desired),
    )
    got_back = iam_client.get_role_policy(
        RoleName=role_name, PolicyName=policy_name
    )["PolicyDocument"]
    if normalize_for_compare(got_back) != normalize_for_compare(desired):
        raise RuntimeError(f"{name}: post-apply mismatch on {policy_name}")

    result["action"] = "apply"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="print planned changes; no IAM mutations")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    check_boto3()

    control = boto3.client("bedrock-agentcore-control", region_name=REGION)
    iam = boto3.client("iam", region_name=REGION)

    harnesses = control.list_harnesses()["harnesses"]
    print(f"=== Discovered {len(harnesses)} harness(es) ===")

    actions = defaultdict(int)

    for h in harnesses:
        result = grant_memory_access_for_harness(
            h["harnessId"],
            control_client=control,
            iam_client=iam,
            dry_run=args.dry_run,
            verbose=False,
        )
        action = result["action"]
        actions[action] += 1

        if action == "skip":
            if args.verbose:
                print(f"\n  - {result['harness_name']}: {result['reason']}, skipping")
            continue

        print(f"\n  {result['harness_name']}:")
        print(f"    role:       {redact(result['role_name'])}")
        print(f"    memory:     {redact(result['memory_arn'])}")
        print(f"    namespaces: {result['namespaces']}")
        print(f"    policy:     {result['policy_name']}")
        if action == "noop":
            print(f"    drift:      no — already matches")
        elif action == "dry-run":
            print(f"    drift:      YES — would PutRolePolicy")
        elif action == "apply":
            print(f"    drift:      YES — applied + verified")

    print(f"\n=== Summary ===")
    print(f"  applied:  {actions['apply']}")
    print(f"  no-op:    {actions['noop']}")
    if args.dry_run:
        print(f"  dry-run:  {actions['dry-run']}")
    if actions["skip"]:
        print(f"  skipped:  {actions['skip']} (no Memory wired)")


if __name__ == "__main__":
    main()
