#!/usr/bin/env python3
"""
Issue #60: Grant Memory data plane permissions to harness execution roles.

Closes the IAM gap where PR #54 wired BugFix Memory to BugFixAgentHarness
but the harness's execution role had no Memory data plane perms for the
new Memory ARN. Every BugFixAgent invocation failed at session-start with
AccessDeniedException on bedrock-agentcore:ListEvents.

This script:
  1. Discovers all harnesses
  2. For each harness with Memory wired:
     a. Reads the executionRoleArn from get_harness
     b. Reads the Memory ARN + retrievalConfig namespaces from agentCoreMemoryConfiguration
     c. Generates an inline policy named <HarnessName>MemoryAccess
     d. Compares to existing policy; PutRolePolicy only if changed
     e. Verifies post-apply by reading the policy back
  3. Prints summary; exit 0 on success

Idempotent — re-running with no IAM drift makes zero API mutations.

Usage:
  python3 grant_memory_access.py [--dry-run] [--verbose]

Per AGENTS.md §3.x: Memory wiring = create_memory + update_harness + IAM grant.
This script is the third step.
"""
import argparse
import json
import re
import sys
from collections import defaultdict

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


def policy_for(memory_arn: str, namespaces: list[str]) -> dict:
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


def namespaces_from_config(retrieval_config: dict) -> list[str]:
    """Convert retrievalConfig keys (with placeholders) to IAM-condition glob patterns."""
    out = []
    for ns_key in retrieval_config.keys():
        # /fix-patterns/{actorId} → /fix-patterns/*
        # /fix-history/{actorId}/{sessionId} → /fix-history/*/*
        pattern = re.sub(r"\{[^}]+\}", "*", ns_key)
        out.append(pattern)
    return sorted(set(out))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="print planned changes; no IAM mutations")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    check_boto3()

    control = boto3.client("bedrock-agentcore-control", region_name=REGION)
    iam = boto3.client("iam", region_name=REGION)

    harnesses = control.list_harnesses()["harnesses"]
    print(f"=== Discovered {len(harnesses)} harness(es) ===")

    actions = []  # list of (action, role, policy_name, memory_id, harness_name)

    for h in harnesses:
        name = h["harnessName"]
        detail = control.get_harness(harnessId=h["harnessId"])["harness"]

        mem_cfg = detail.get("memory", {}).get("agentCoreMemoryConfiguration")
        if not mem_cfg:
            if args.verbose:
                print(f"  - {name}: no Memory wired, skipping")
            continue

        role_arn = detail.get("executionRoleArn")
        mem_arn = mem_cfg.get("arn")
        retrieval_cfg = mem_cfg.get("retrievalConfig", {})
        namespaces = namespaces_from_config(retrieval_cfg)

        if not (role_arn and mem_arn):
            print(f"  - {name}: missing role or memory ARN; skip")
            continue

        role_name = role_arn.split("/")[-1]
        policy_name = f"{name}MemoryAccess"
        desired = policy_for(mem_arn, namespaces)

        # Read existing
        try:
            existing = iam.get_role_policy(
                RoleName=role_name, PolicyName=policy_name
            )["PolicyDocument"]
        except iam.exceptions.NoSuchEntityException:
            existing = None

        is_drift = (
            existing is None
            or normalize_for_compare(existing) != normalize_for_compare(desired)
        )

        print(f"\n  {name}:")
        print(f"    role:       {redact(role_name)}")
        print(f"    memory:     {redact(mem_arn)}")
        print(f"    namespaces: {namespaces}")
        print(f"    policy:     {policy_name}")
        print(f"    drift:      {'YES — will apply' if is_drift else 'no — already matches'}")

        if is_drift:
            if args.dry_run:
                print(f"    DRY-RUN: would PutRolePolicy")
            else:
                iam.put_role_policy(
                    RoleName=role_name,
                    PolicyName=policy_name,
                    PolicyDocument=json.dumps(desired),
                )
                # Verify round-trip
                got_back = iam.get_role_policy(
                    RoleName=role_name, PolicyName=policy_name
                )["PolicyDocument"]
                if normalize_for_compare(got_back) != normalize_for_compare(desired):
                    print(f"    ❌ POST-APPLY MISMATCH")
                    sys.exit(1)
                print(f"    ✓ applied + verified")
            actions.append(("apply", role_name, policy_name, mem_arn, name))
        else:
            actions.append(("noop", role_name, policy_name, mem_arn, name))

    print(f"\n=== Summary ===")
    counts = defaultdict(int)
    for a in actions:
        counts[a[0]] += 1
    print(f"  applied:  {counts['apply']}")
    print(f"  no-op:    {counts['noop']}")

    if not actions:
        print(f"  No harnesses with Memory wired — nothing to do.")


if __name__ == "__main__":
    main()
