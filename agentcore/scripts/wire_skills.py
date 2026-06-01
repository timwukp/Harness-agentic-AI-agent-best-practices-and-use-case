#!/usr/bin/env python3
"""
Issue #26: Wire UITestAgentHarness to existing skills/ui-testing/SKILL.md via update_harness.

The `skills` field on UpdateHarness accepts a list of skill source items, each picking ONE of:
  - path: string                     (local container path; needs container or volume mount)
  - s3:   {uri}                       (S3-hosted skill bundle)
  - git:  {url, path?, auth?}         (Git-hosted; AgentCore fetches at session start)

This script uses the GIT source so we don't need #21 (Container) or a separate S3 upload —
the harness fetches the SKILL.md directly from this repo at session start.

Discovery findings (candidate addition to AGENTS.md §3.2 in a follow-up doc PR):
  - skills.member is a structure with mutually-exclusive sources (path / s3 / git)
  - Only `git.url` is required; `git.path` and `git.auth` are optional
  - For public repos no auth needed
  - skills is plain list-of-structure (NO optionalValue wrapper per AGENTS.md §3.2.1)

Idempotent: re-run detects matching skills and exits 0 with no API mutations.

Requires boto3 >= 1.43.18.

Usage:
  python wire_skills.py [--region us-east-1] [--dry-run]

Exit codes:
  0  Already match desired state, OR all updates succeeded
  1  Discovery failed (harness not found)
  2  boto3 too old
  3  update_harness failed
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

REPO_URL = "https://github.com/timwukp/Harness-agentic-AI-agent-best-practices-and-use-case"

# Desired skills config per harness — tune here, not via CLI.
# Each item picks ONE source: git / s3 / path.
DESIRED = {
    "UITestAgentHarness": {
        "skills": [
            {
                "git": {
                    "url": REPO_URL,
                    "path": "app/ui-test-agent/skills/ui-testing",
                }
            }
        ]
    },
    # BugFixAgentHarness is handled by issue #27 (skill file doesn't exist yet).
}


def parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split(".")[:3])


def check_boto3_version() -> None:
    cur = parse_version(boto3.__version__)
    if cur < MIN_BOTO3:
        print(
            f"ERROR: boto3 {boto3.__version__} too old; need >= {'.'.join(map(str, MIN_BOTO3))}.",
            file=sys.stderr,
        )
        sys.exit(2)


def redact(s: str) -> str:
    s = re.sub(r"\b\d{12}\b", "<ACCOUNT_ID>", s)
    s = re.sub(r"-[a-zA-Z0-9]{10}\b", "-<ID>", s)
    return s


def find_harness(client: Any, name: str) -> dict | None:
    for h in client.list_harnesses().get("harnesses", []):
        if h.get("harnessName") == name:
            return h
    return None


def normalize_skill(skill: dict) -> tuple:
    """Convert a skill dict into a hashable tuple for comparison.

    Handles all 3 source types: path / s3 / git.
    """
    if "git" in skill:
        g = skill["git"]
        return ("git", g.get("url"), g.get("path"), tuple(sorted((g.get("auth") or {}).items())))
    if "s3" in skill:
        return ("s3", skill["s3"].get("uri"))
    if "path" in skill:
        return ("path", skill["path"])
    return ("?", str(skill))


def skills_match(current: list, desired: list) -> bool:
    """Order-insensitive skill list comparison."""
    return sorted(normalize_skill(s) for s in current) == sorted(normalize_skill(s) for s in desired)


def update_skills_if_needed(client: Any, harness: dict, desired_skills: list, dry_run: bool) -> bool:
    detail = client.get_harness(harnessId=harness["harnessId"])["harness"]
    current = detail.get("skills") or []

    if skills_match(current, desired_skills):
        print(f"  ✓ skills already match desired ({len(current)} skill(s), no update)")
        for s in current:
            src_kind = "git" if "git" in s else ("s3" if "s3" in s else "path")
            src_summary = (
                s["git"].get("url", "") + ":" + (s["git"].get("path") or "")
                if src_kind == "git"
                else s.get(src_kind, "?")
            )
            print(f"    - {src_kind}: {redact(str(src_summary))}")
        return False

    print(f"  → drift detected:")
    print(f"      current  ({len(current)} skill(s)): {[normalize_skill(s) for s in current]}")
    print(f"      desired ({len(desired_skills)} skill(s)): {[normalize_skill(s) for s in desired_skills]}")

    payload = {
        "harnessId": harness["harnessId"],
        "skills": desired_skills,
        # clientToken min validated length is 33 chars; token_hex(20) gives 40 (safe).
        # See AGENTS.md §3.2.3 and issue #46.
        "clientToken": secrets.token_hex(20),
    }

    if dry_run:
        print(f"  DRY RUN: would call update_harness(skills=[...], len={len(desired_skills)})")
        return True

    try:
        client.update_harness(**payload)
        print(f"  ✓ update_harness HTTP 200")
    except botocore.exceptions.ClientError as e:
        print(f"ERROR: update_harness failed: {redact(str(e))}", file=sys.stderr)
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
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    check_boto3_version()
    print(f"boto3 {boto3.__version__} OK")
    print(f"Region:  {args.region}")
    print(f"Account: <ACCOUNT_ID>")
    print(f"Mode:    {'DRY RUN' if args.dry_run else 'APPLY'}\n")

    session = boto3.Session(region_name=args.region)
    session.client("sts").get_caller_identity()
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

        changed = update_skills_if_needed(control, harness, desired["skills"], args.dry_run)
        if changed and not args.dry_run:
            poll_until_ready(control, harness["harnessId"])
        any_changed = any_changed or changed
        print()

    if args.dry_run:
        print("⚠ Dry run complete — drifts detected. Re-run without --dry-run to apply." if any_changed
              else "✓ Dry run complete — already match desired config.")
    else:
        print("✓ All applicable updates applied successfully" if any_changed
              else "✓ No changes needed (idempotent re-run safe)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
