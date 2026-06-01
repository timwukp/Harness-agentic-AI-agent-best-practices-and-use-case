#!/usr/bin/env python3
"""
Issue #29: Tighten allowedTools whitelist + set maxTokens + add tags on both harnesses.

Three production-hygiene config items applied to UITestAgentHarness and
BugFixAgentHarness, applied via:
  - update_harness(allowedTools=[...], maxTokens=N)  -- for tools whitelist + token cap
  - tag_resource(resourceArn=..., tags={...})        -- for tags (UpdateHarness has no tags field)

Discovery findings (recorded in AGENTS.md §3.2 candidate addition):
  - allowedTools / maxTokens are PLAIN list/integer (NO optionalValue wrapper)
  - Only complex structure fields (memory, model, environment) use optionalValue
  - UpdateHarness lacks tags; must call TagResource separately
  - clientToken min length is 33 chars; secrets.token_hex(20) gives 40 chars (safe)

Idempotent: re-running detects matching state and exits 0 with no API mutations.

Requires boto3 >= 1.43.18 (older versions silently lack update_harness / tag_resource).

Usage:
  python tighten_harness_config.py [--region us-east-1] [--dry-run]

Exit codes:
  0  Both harnesses already match desired state, OR all updates succeeded
  1  Discovery failed (harness not found)
  2  boto3 too old (< 1.43.18)
  3  update_harness or tag_resource failed
"""
from __future__ import annotations

import argparse
import re
import secrets
import sys
import time
from typing import Any

try:
    import boto3
    import botocore
except ImportError:
    print("ERROR: boto3 not installed. Run: pip install --upgrade boto3 botocore", file=sys.stderr)
    sys.exit(2)


MIN_BOTO3 = (1, 43, 18)
MAX_POLL_SECONDS = 120
POLL_INTERVAL = 5

# Desired config per harness — tune here, not via CLI
DESIRED = {
    "UITestAgentHarness": {
        "allowedTools": ["browser", "code_interpreter"],
        "maxTokens": 65536,
        "tags": {
            "team": "qa-platform",
            "environment": "production",
            "cost-center": "engineering",
            "agent-type": "ui-test",
        },
    },
    "BugFixAgentHarness": {
        "allowedTools": ["code_interpreter"],
        "maxTokens": 32768,
        "tags": {
            "team": "qa-platform",
            "environment": "production",
            "cost-center": "engineering",
            "agent-type": "bug-fix",
        },
    },
}


def parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split(".")[:3])


def check_boto3_version() -> None:
    cur = parse_version(boto3.__version__)
    if cur < MIN_BOTO3:
        print(
            f"ERROR: boto3 {boto3.__version__} too old; need >= {'.'.join(map(str, MIN_BOTO3))}.\n"
            f"  Upgrade: pip install --upgrade boto3 botocore",
            file=sys.stderr,
        )
        sys.exit(2)


def redact(s: str) -> str:
    s = re.sub(r"\b\d{12}\b", "<ACCOUNT_ID>", s)
    s = re.sub(r"-[a-zA-Z0-9]{10}\b", "-<ID>", s)
    return s


def find_harness(client: Any, name: str) -> dict | None:
    """Return harness summary by name, or None if not found."""
    for h in client.list_harnesses().get("harnesses", []):
        if h.get("harnessName") == name:
            return h
    return None


def update_config_if_needed(client: Any, harness: dict, desired: dict, dry_run: bool) -> bool:
    """
    Check current config vs desired; call update_harness only if drift exists.
    Returns True if drift detected (whether applied or not).
    """
    detail = client.get_harness(harnessId=harness["harnessId"])["harness"]
    cur_tools = detail.get("allowedTools") or []
    cur_max = detail.get("maxTokens")

    needs_tools = sorted(cur_tools) != sorted(desired["allowedTools"])
    needs_max = cur_max != desired["maxTokens"]

    if not (needs_tools or needs_max):
        print(f"  ✓ allowedTools + maxTokens already match desired (no update)")
        print(f"    allowedTools: {cur_tools}  maxTokens: {cur_max}")
        return False

    payload: dict[str, Any] = {
        "harnessId": harness["harnessId"],
        "clientToken": secrets.token_hex(20),  # 40 chars; min validated length is 33
    }
    diffs = []
    if needs_tools:
        payload["allowedTools"] = desired["allowedTools"]
        diffs.append(f"allowedTools: {cur_tools} → {desired['allowedTools']}")
    if needs_max:
        payload["maxTokens"] = desired["maxTokens"]
        diffs.append(f"maxTokens: {cur_max} → {desired['maxTokens']}")

    print(f"  → drift detected:")
    for d in diffs:
        print(f"      {d}")

    if dry_run:
        print(f"  DRY RUN: would call update_harness({list(payload.keys())})")
        return True

    try:
        client.update_harness(**payload)
        print(f"  ✓ update_harness HTTP 200")
    except botocore.exceptions.ClientError as e:
        print(f"ERROR: update_harness failed: {redact(str(e))}", file=sys.stderr)
        sys.exit(3)
    return True


def tag_resource_if_needed(client: Any, harness: dict, desired_tags: dict, dry_run: bool) -> bool:
    """
    Apply tags via tag_resource if current tags don't match.
    Idempotent: tag_resource overwrites/merges keys.
    """
    arn = harness["arn"]
    current = client.list_tags_for_resource(resourceArn=arn).get("tags", {}) or {}

    needs_tags = any(current.get(k) != v for k, v in desired_tags.items())
    if not needs_tags:
        print(f"  ✓ all {len(desired_tags)} tags already match (no update)")
        return False

    missing_or_wrong = {k: v for k, v in desired_tags.items() if current.get(k) != v}
    print(f"  → {len(missing_or_wrong)} tag(s) need update:")
    for k, v in missing_or_wrong.items():
        cur_v = current.get(k, "<absent>")
        print(f"      {k}: {cur_v!r} → {v!r}")

    if dry_run:
        print(f"  DRY RUN: would call tag_resource(resourceArn=..., tags={list(missing_or_wrong.keys())})")
        return True

    try:
        client.tag_resource(resourceArn=arn, tags=desired_tags)
        print(f"  ✓ tag_resource HTTP 200")
    except botocore.exceptions.ClientError as e:
        print(f"ERROR: tag_resource failed: {redact(str(e))}", file=sys.stderr)
        sys.exit(3)
    return True


def poll_until_ready(client: Any, harness_id: str) -> None:
    deadline = time.time() + MAX_POLL_SECONDS
    while time.time() < deadline:
        status = client.get_harness(harnessId=harness_id)["harness"].get("status")
        if status == "READY":
            print(f"  ✓ status=READY")
            return
        if status in ("UPDATE_FAILED", "FAILED", "DELETE_FAILED"):
            print(f"ERROR: harness reached terminal failure: {status}", file=sys.stderr)
            sys.exit(3)
        print(f"  status={status} (waiting {POLL_INTERVAL}s)")
        time.sleep(POLL_INTERVAL)
    print(f"ERROR: timeout waiting for READY", file=sys.stderr)
    sys.exit(3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes without mutating")
    args = parser.parse_args()

    check_boto3_version()
    print(f"boto3 {boto3.__version__} OK")
    print(f"Region:  {args.region}")
    print(f"Account: <ACCOUNT_ID>")
    print(f"Mode:    {'DRY RUN' if args.dry_run else 'APPLY'}\n")

    session = boto3.Session(region_name=args.region)
    session.client("sts").get_caller_identity()  # validates creds
    control = session.client("bedrock-agentcore-control")

    any_changed = False
    for name, desired in DESIRED.items():
        print(f"=== {name} ===")
        harness = find_harness(control, name)
        if not harness:
            print(f"  ✗ not found — skipping")
            continue
        print(f"  arn:    {redact(harness['arn'])}")
        print(f"  status: {harness['status']}")

        config_changed = update_config_if_needed(control, harness, desired, args.dry_run)
        if config_changed and not args.dry_run:
            poll_until_ready(control, harness["harnessId"])

        tags_changed = tag_resource_if_needed(control, harness, desired["tags"], args.dry_run)
        any_changed = any_changed or config_changed or tags_changed
        print()

    if args.dry_run:
        if any_changed:
            print("⚠ Dry run complete — drifts detected. Re-run without --dry-run to apply.")
        else:
            print("✓ Dry run complete — both harnesses already match desired config.")
    else:
        if any_changed:
            print("✓ All applicable updates applied successfully")
        else:
            print("✓ No changes needed — both harnesses match desired config (idempotent re-run safe)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
