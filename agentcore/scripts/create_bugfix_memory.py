#!/usr/bin/env python3
"""
Issue #25: Create BugFixAgent Memory (semantic + episodic) and attach to BugFixAgentHarness.

Two-phase script:
  Phase A: create_memory (semantic + episodic strategies) — idempotent by name
  Phase B: update_harness (attach memory ARN to BugFixAgentHarness) — idempotent by ARN match

Schema discovery (canonical addition to AGENTS.md §3 in a follow-up doc PR):
  - CreateMemory required: name, eventExpiryDuration
  - memoryStrategies is a list-of-structure with UNION variants:
    semanticMemoryStrategy / episodicMemoryStrategy / summaryMemoryStrategy /
    userPreferenceMemoryStrategy / customMemoryStrategy
  - Each variant has: name (required), description, namespaces, namespaceTemplates,
    memoryRecordSchema, plus variant-specific fields
  - episodicMemoryStrategy has reflectionConfiguration with namespaces;
    reflection namespace MUST be a prefix of the episodic namespace
    (otherwise CreateMemory returns ValidationException)
  - Same union pattern as skills.member (PR #51) and as memory's optionalValue at the harness level

Idempotent:
  - If memory by name already exists, skip create
  - If memory is already attached to harness with the same ARN, skip attach
  - Re-run is no-op

Requires boto3 >= 1.43.18.

Usage:
  python create_bugfix_memory.py [--region us-east-1] [--dry-run]

Exit codes:
  0  Memory created+attached, OR already in target state (idempotent)
  1  Discovery failed (harness not found)
  2  boto3 too old (< 1.43.18)
  3  create_memory or update_harness failed
"""
from __future__ import annotations

import argparse
import re
import secrets
import sys
import time
from typing import Any

# Ensure sibling scripts are importable when running from repo root
import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

try:
    import boto3
    import botocore
except ImportError:
    print("ERROR: boto3 not installed.", file=sys.stderr)
    sys.exit(2)


MIN_BOTO3 = (1, 43, 18)
MAX_POLL_SECONDS = 300  # memory creation is slower than harness updates
POLL_INTERVAL = 10

# Desired Memory resource for BugFix
MEMORY_NAME = "bugfixagent_bugfixagentMemory"
EVENT_EXPIRY_DAYS = 30
HARNESS_NAME = "BugFixAgentHarness"

# 2 strategies per the issue body — narrower than UI Test's 4-strategy
# (skip Summarization: Bug-Fix sessions are short)
# (skip UserPreference: no team-specific quirks expected)
DESIRED_STRATEGIES = [
    {
        "semanticMemoryStrategy": {
            "name": "FixPatternStrategy",
            "description": "Fix patterns and root-cause taxonomy "
            "(e.g. 'when error message color is wrong, check `.error-message {color}` first'). "
            "Long-lived, generalizable knowledge.",
            "namespaces": ["/fix-patterns/{actorId}"],
        }
    },
    {
        "episodicMemoryStrategy": {
            "name": "FixHistoryStrategy",
            "description": "Past fix outcomes per session "
            "(e.g. 'On 2026-05-16 fixed error-message: green → red in demo-frontend, PR succeeded'). "
            "Short-lived, session-scoped traces.",
            "namespaces": ["/fix-history/{actorId}/{sessionId}"],
            # Reflection namespace must be a prefix of the episodic namespace per validator
            # (discovered live: omitting this = ValidationException with default
            # /strategies/{memoryStrategyId}/actors/{actorId}/ which doesn't prefix our episodic ns)
            "reflectionConfiguration": {
                "namespaces": ["/fix-history/{actorId}"],
            },
        }
    },
]

# actorId for the harness: per-repo scoping (issue body convention)
ACTOR_ID = "repo-timwukp-Harness-agentic-AI-agent-best-practices-and-use-case"


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


def find_memory_by_name(client: Any, name: str) -> dict | None:
    """Discover a memory by exact name (not prefix)."""
    for m in client.list_memories().get("memories", []):
        full = client.get_memory(memoryId=m["id"])["memory"]
        if full.get("name") == name:
            return full
    return None


def find_harness(client: Any, name: str) -> dict | None:
    for h in client.list_harnesses().get("harnesses", []):
        if h.get("harnessName") == name:
            return h
    return None


def wait_memory_active(client: Any, memory_id: str) -> dict:
    print(f"  Polling get_memory until status=ACTIVE (max {MAX_POLL_SECONDS}s)...")
    deadline = time.time() + MAX_POLL_SECONDS
    while time.time() < deadline:
        full = client.get_memory(memoryId=memory_id)["memory"]
        status = full.get("status")
        if status == "ACTIVE":
            print(f"  ✓ memory ACTIVE")
            return full
        if status in ("FAILED", "CREATING_FAILED", "DELETE_FAILED"):
            print(f"ERROR: memory failed: {status}", file=sys.stderr)
            sys.exit(3)
        print(f"    status={status} (waiting {POLL_INTERVAL}s)")
        time.sleep(POLL_INTERVAL)
    print(f"ERROR: timeout waiting for memory ACTIVE", file=sys.stderr)
    sys.exit(3)


def create_memory(client: Any, dry_run: bool) -> dict:
    """Phase A: create the memory if it doesn't exist."""
    existing = find_memory_by_name(client, MEMORY_NAME)
    if existing:
        print(f"  ✓ memory '{MEMORY_NAME}' already exists (status={existing['status']})")
        if existing["status"] != "ACTIVE":
            return wait_memory_active(client, existing["id"])
        return existing

    print(f"  → memory '{MEMORY_NAME}' not found — creating with {len(DESIRED_STRATEGIES)} strategies")
    payload = {
        "clientToken": secrets.token_hex(20),  # AGENTS.md §3.2.3 (#46/PR #50)
        "name": MEMORY_NAME,
        "description": "Bug-Fix Agent memory for fix patterns + past outcomes (issue #25)",
        "eventExpiryDuration": EVENT_EXPIRY_DAYS,
        "memoryStrategies": DESIRED_STRATEGIES,
    }

    if dry_run:
        print(f"  DRY RUN: would call create_memory(name={MEMORY_NAME}, ...)")
        return {"status": "ACTIVE", "name": MEMORY_NAME, "arn": "<dry-run-arn>", "strategies": []}

    try:
        resp = client.create_memory(**payload)
        print(f"  ✓ create_memory HTTP 200")
    except botocore.exceptions.ClientError as e:
        print(f"ERROR: create_memory failed: {redact(str(e))}", file=sys.stderr)
        sys.exit(3)

    memory_id = resp["memory"]["id"]
    return wait_memory_active(client, memory_id)


def is_memory_already_attached(harness_detail: dict, memory_arn: str) -> bool:
    mem = harness_detail.get("memory") or {}
    cur_cfg = mem.get("agentCoreMemoryConfiguration") or {}
    return cur_cfg.get("arn") == memory_arn


def build_retrieval_config(memory: dict, top_k: int = 5, relevance_score: float = 0.3) -> dict:
    """Map each strategy's namespace → retrievalConfig entry.

    Uses `strategyId` (NOT `memoryStrategyId`) per AGENTS.md §3.2.4.
    """
    cfg = {}
    for s in memory.get("strategies", []) or []:
        if s.get("status") not in (None, "ACTIVE"):
            continue
        ns = (s.get("namespaces") or [None])[0]
        if not ns:
            continue
        cfg[ns] = {
            "strategyId": s["strategyId"],
            "topK": top_k,
            "relevanceScore": relevance_score,
        }
    return cfg


def attach_memory_to_harness(client: Any, memory: dict, harness: dict, dry_run: bool) -> bool:
    """Phase B: attach memory to harness if not already."""
    detail = client.get_harness(harnessId=harness["harnessId"])["harness"]
    if is_memory_already_attached(detail, memory["arn"]):
        print(f"  ✓ memory already attached to {HARNESS_NAME} (no update)")
        return False

    retrieval_config = build_retrieval_config(memory)
    payload = {
        "harnessId": harness["harnessId"],
        # memory uses optionalValue wrapper (structure field per AGENTS.md §3.2.1)
        "memory": {
            "optionalValue": {
                "agentCoreMemoryConfiguration": {
                    "arn": memory["arn"],
                    "actorId": ACTOR_ID,
                    "messagesCount": 20,
                    "retrievalConfig": retrieval_config,
                }
            }
        },
        "clientToken": secrets.token_hex(20),  # AGENTS.md §3.2.3
    }

    print(f"  → attaching memory to {HARNESS_NAME}")
    print(f"    actorId: {ACTOR_ID}")
    print(f"    retrievalConfig namespaces: {len(retrieval_config)}")
    for ns, c in retrieval_config.items():
        print(f"      - {ns}  topK={c['topK']}  relevance={c['relevanceScore']}")

    if dry_run:
        print(f"  DRY RUN: would call update_harness(memory=...)")
        return True

    try:
        client.update_harness(**payload)
        print(f"  ✓ update_harness HTTP 200")
    except botocore.exceptions.ClientError as e:
        print(f"ERROR: update_harness failed: {redact(str(e))}", file=sys.stderr)
        sys.exit(3)
    return True


def poll_harness_ready(client: Any, harness_id: str) -> None:
    deadline = time.time() + 120
    while time.time() < deadline:
        status = client.get_harness(harnessId=harness_id)["harness"].get("status")
        if status == "READY":
            print(f"  ✓ harness READY")
            return
        if status in ("UPDATE_FAILED", "FAILED", "DELETE_FAILED"):
            print(f"ERROR: harness terminal failure: {status}", file=sys.stderr)
            sys.exit(3)
        print(f"    status={status} (waiting 5s)")
        time.sleep(5)
    print(f"ERROR: harness timeout", file=sys.stderr)
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

    print(f"=== Phase A: Memory '{MEMORY_NAME}' ===")
    memory = create_memory(control, args.dry_run)
    print(f"  ARN: {redact(memory.get('arn', '<unknown>'))}")
    print(f"  strategies: {len(memory.get('strategies', []))}")
    for s in memory.get("strategies", []):
        ns = (s.get("namespaces") or ["?"])[0]
        sid = s.get("strategyId", "?")
        print(f"    - {s.get('type', '?'):<16} → {ns}  (id={redact(sid)})")
    print()

    print(f"=== Phase B: Attach to {HARNESS_NAME} ===")
    harness = find_harness(control, HARNESS_NAME)
    if not harness:
        print(f"  ✗ {HARNESS_NAME} not found", file=sys.stderr)
        sys.exit(1)
    print(f"  arn:    {redact(harness['arn'])}")
    print(f"  status: {harness['status']}")

    changed = attach_memory_to_harness(control, memory, harness, args.dry_run)
    if changed and not args.dry_run:
        poll_harness_ready(control, harness["harnessId"])
    print()

    # Trinity step 3: grant Memory data plane IAM perms to harness's role
    # (per AGENTS.md §3.9 — Memory wire requires create + update_harness + IAM grant).
    # Idempotent — no-op if policy already matches; runs even on no-update branches
    # so a script re-run also verifies IAM hasn't drifted.
    print(f"=== Step 3 of trinity: grant_memory_access_for_harness ===")
    from grant_memory_access import grant_memory_access_for_harness
    grant = grant_memory_access_for_harness(
        harness["harnessId"],
        control_client=control,
        dry_run=args.dry_run,
        verbose=True,
    )
    print(f"  IAM grant action: {grant['action']}")
    print()

    if args.dry_run:
        print("⚠ Dry run complete.")
    else:
        print("✓ Done — re-run for idempotency confirmation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
