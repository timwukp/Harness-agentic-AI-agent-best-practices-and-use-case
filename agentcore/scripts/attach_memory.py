#!/usr/bin/env python3
"""
Issue #24: Attach an existing AgentCore Memory resource to UITestAgentHarness.

Programmatic approach using boto3.update_harness (requires boto3 >= 1.43.18).

The script is **idempotent**:
  - If memory is already attached with the same ARN, prints status and exits 0.
  - If memory is not attached or differs, calls update_harness and polls for READY.

Discovery is by name — no hardcoded IDs:
  - Harness:  by --harness-name (default: UITestAgentHarness)
  - Memory:   by --memory-name-prefix (default: uitestagent_uitestagentMemory)
  - Account:  via sts.get_caller_identity()

For the discovery / API gotchas behind this script, see AGENTS.md §3.

Usage:
  python attach_memory.py [--region us-east-1]
                          [--harness-name UITestAgentHarness]
                          [--memory-name-prefix uitestagent_uitestagentMemory]
                          [--actor-id ci-pipeline]
                          [--messages-count 20]
                          [--top-k 10]
                          [--relevance-score 0.2]
                          [--dry-run]

Exit codes:
  0  Memory attached successfully (or already attached, idempotent)
  1  Discovery failed (harness or memory not found)
  2  boto3 too old (must be >= 1.43.18 for harness operations)
  3  update_harness failed or timed out
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
    print("ERROR: boto3 not installed. Run: pip install --upgrade boto3 botocore", file=sys.stderr)
    sys.exit(2)


MIN_BOTO3 = (1, 43, 18)
MAX_POLL_SECONDS = 180
POLL_INTERVAL = 5


def parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split(".")[:3])


def check_boto3_version() -> None:
    cur = parse_version(boto3.__version__)
    if cur < MIN_BOTO3:
        print(
            f"ERROR: boto3 {boto3.__version__} is too old.\n"
            f"  Harness operations (create_harness, update_harness, etc.) "
            f"require >= {'.'.join(map(str, MIN_BOTO3))}.\n"
            f"  Upgrade: pip install --upgrade boto3 botocore\n"
            f"  Or use a venv:\n"
            f"    python3 -m venv ~/.venvs/agentcore\n"
            f"    ~/.venvs/agentcore/bin/pip install --upgrade boto3 botocore\n"
            f"    ~/.venvs/agentcore/bin/python3 {sys.argv[0]}",
            file=sys.stderr,
        )
        sys.exit(2)


def redact(s: str) -> str:
    """Redact 12-digit account IDs and 10-char resource suffixes for friendly logging."""
    s = re.sub(r"\b\d{12}\b", "<ACCOUNT_ID>", s)
    s = re.sub(r"-[a-zA-Z0-9]{10}\b", "-<ID>", s)
    return s


def find_harness(client: Any, name: str) -> dict:
    """Discover the harness by name. Returns the harness summary."""
    print(f"Searching for harness: {name}")
    paginator = client.get_paginator("list_harnesses") if "list_harnesses" in dir(client) else None
    if paginator:
        all_harnesses = []
        for page in paginator.paginate():
            all_harnesses.extend(page.get("harnesses", []))
    else:
        all_harnesses = client.list_harnesses().get("harnesses", [])
    for h in all_harnesses:
        if h.get("harnessName") == name:
            print(f"  Found: {redact(h['arn'])}  status={h['status']}")
            return h
    available = [h.get("harnessName") for h in all_harnesses]
    print(f"ERROR: Harness '{name}' not found. Available: {available}", file=sys.stderr)
    sys.exit(1)


def find_memory(client: Any, prefix: str) -> dict:
    """Discover the memory resource by name prefix. Returns the full memory."""
    print(f"Searching for memory with name prefix: {prefix}")
    summaries = client.list_memories().get("memories", [])
    for m in summaries:
        full = client.get_memory(memoryId=m["id"])["memory"]
        if full.get("name", "").startswith(prefix):
            print(f"  Found: {redact(full['arn'])}  status={full['status']}")
            print(f"  Strategies ({len(full.get('strategies', []))}):")
            for s in full.get("strategies", []):
                ns = (s.get("namespaces") or ["?"])[0]
                print(f"    - {s['type']:<16} → {ns}  ({s.get('strategyId', '?')})")
            return full
    available = [client.get_memory(memoryId=m['id'])['memory'].get('name') for m in summaries]
    print(f"ERROR: No memory found with name prefix '{prefix}'. Available: {available}", file=sys.stderr)
    sys.exit(1)


def build_retrieval_config(memory: dict, top_k: int, relevance_score: float) -> dict:
    """Build retrievalConfig dict mapping namespace template → {strategyId, topK, relevanceScore}.

    NOTE: Field name is `strategyId`, NOT `memoryStrategyId`. See AGENTS.md §3.2.4.
    """
    cfg = {}
    for s in memory.get("strategies", []):
        if s.get("status") not in (None, "ACTIVE"):
            continue
        namespaces = s.get("namespaces") or []
        if not namespaces:
            continue
        cfg[namespaces[0]] = {
            "strategyId": s["strategyId"],
            "topK": top_k,
            "relevanceScore": relevance_score,
        }
    return cfg


def is_already_attached(harness_detail: dict, memory_arn: str) -> bool:
    """Check whether the harness already has this memory attached."""
    mem = harness_detail.get("memory") or {}
    cur_cfg = mem.get("agentCoreMemoryConfiguration") or {}
    cur_arn = cur_cfg.get("arn")
    return cur_arn == memory_arn


def attach_memory(
    client: Any,
    harness_id: str,
    memory_arn: str,
    actor_id: str,
    messages_count: int,
    retrieval_config: dict,
    dry_run: bool = False,
) -> None:
    """Call update_harness to attach memory. Returns when call completes (not yet READY).

    The payload uses the `optionalValue` wrapper required by HarnessAgentCoreMemoryConfiguration.
    See https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_UpdateHarness.html
    """
    payload = {
        "harnessId": harness_id,
        "memory": {
            "optionalValue": {
                "agentCoreMemoryConfiguration": {
                    "arn": memory_arn,
                    "actorId": actor_id,
                    "messagesCount": messages_count,
                    "retrievalConfig": retrieval_config,
                }
            }
        },
        # clientToken min validated length is 33 chars; token_hex(20) gives 40 chars (safe).
        # token_hex(8) was a latent bug — fails ParamValidationError on a fresh attach.
        # See AGENTS.md §3.2.3 and issue #46.
        "clientToken": secrets.token_hex(20),
    }
    print("\n=== update_harness payload (redacted) ===")
    import json as _json
    print(redact(_json.dumps(payload, indent=2, default=str)))
    print()

    if dry_run:
        print("DRY RUN: not calling update_harness.")
        return

    try:
        client.update_harness(**payload)
        print("✓ update_harness call returned HTTP 200")
    except botocore.exceptions.ClientError as e:
        print(f"ERROR: update_harness failed: {redact(str(e))}", file=sys.stderr)
        sys.exit(3)


def poll_until_ready(client: Any, harness_id: str) -> dict:
    """Poll get_harness until status is terminal. Returns the final detail."""
    print(f"Polling get_harness until status=READY (max {MAX_POLL_SECONDS}s)...")
    deadline = time.time() + MAX_POLL_SECONDS
    while time.time() < deadline:
        detail = client.get_harness(harnessId=harness_id)["harness"]
        status = detail.get("status")
        print(f"  status={status}")
        if status in ("READY",):
            print("✓ Harness is READY")
            return detail
        if status in ("UPDATE_FAILED", "DELETE_FAILED", "FAILED"):
            print(f"ERROR: Harness reached terminal failure status: {status}", file=sys.stderr)
            sys.exit(3)
        time.sleep(POLL_INTERVAL)
    print(f"ERROR: Timed out after {MAX_POLL_SECONDS}s waiting for READY", file=sys.stderr)
    sys.exit(3)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--harness-name", default="UITestAgentHarness")
    parser.add_argument("--memory-name-prefix", default="uitestagent_uitestagentMemory")
    parser.add_argument(
        "--actor-id",
        default="ci-pipeline",
        help="actorId for this harness's memory namespaces. "
        "Convention: 'ci-pipeline' for CI, 'dev-{username}' for ad-hoc",
    )
    parser.add_argument("--messages-count", type=int, default=20)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--relevance-score", type=float, default=0.2)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payload without calling update_harness",
    )
    args = parser.parse_args()

    check_boto3_version()
    print(f"boto3 {boto3.__version__} OK\n")

    session = boto3.Session(region_name=args.region)
    sts = session.client("sts")
    sts.get_caller_identity()  # Validates credentials; account intentionally not printed
    print(f"Region:  {args.region}")
    print(f"Account: <ACCOUNT_ID>")
    print()

    control = session.client("bedrock-agentcore-control")

    harness = find_harness(control, args.harness_name)
    memory = find_memory(control, args.memory_name_prefix)

    # Get full harness details (memory config etc)
    harness_detail = control.get_harness(harnessId=harness["harnessId"])["harness"]

    if is_already_attached(harness_detail, memory["arn"]):
        cur = harness_detail["memory"]["agentCoreMemoryConfiguration"]
        print()
        print("✓ Memory is ALREADY ATTACHED (idempotent — no action taken)")
        print(f"  actorId:       {cur.get('actorId')}")
        print(f"  messagesCount: {cur.get('messagesCount')}")
        print(f"  retrievalConfig namespaces: {len(cur.get('retrievalConfig') or {})}")
        for ns, c in (cur.get("retrievalConfig") or {}).items():
            print(
                f"    - {ns:<40} topK={c.get('topK')}  relevance={c.get('relevanceScore')}"
            )
        # Even if Memory is already attached, verify IAM is still correct (drift check)
        print("\n=== Step 3 of trinity (verify): grant_memory_access_for_harness ===")
        from grant_memory_access import grant_memory_access_for_harness
        grant = grant_memory_access_for_harness(
            harness["harnessId"],
            control_client=control,
            dry_run=args.dry_run,
            verbose=True,
        )
        print(f"  IAM grant action: {grant['action']}")
        return 0

    retrieval_config = build_retrieval_config(memory, args.top_k, args.relevance_score)
    print(f"\nBuilt retrievalConfig with {len(retrieval_config)} namespaces:")
    for ns, c in retrieval_config.items():
        print(f"  - {ns:<40} strategy={c['strategyId']}")

    attach_memory(
        control,
        harness_id=harness["harnessId"],
        memory_arn=memory["arn"],
        actor_id=args.actor_id,
        messages_count=args.messages_count,
        retrieval_config=retrieval_config,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        return 0

    poll_until_ready(control, harness["harnessId"])

    # Trinity step 3: grant Memory data plane IAM perms to harness's role
    # (per AGENTS.md §3.9 — Memory wire requires create + update_harness + IAM grant).
    # Idempotent — no-op if policy already matches.
    print("\n=== Step 3 of trinity: grant_memory_access_for_harness ===")
    from grant_memory_access import grant_memory_access_for_harness
    grant = grant_memory_access_for_harness(
        harness["harnessId"],
        control_client=control,
        dry_run=args.dry_run,
        verbose=True,
    )
    print(f"  IAM grant action: {grant['action']}")
    print("\n=== Done ===")
    print("Re-run this script to confirm idempotency (should print 'ALREADY ATTACHED').")
    return 0


if __name__ == "__main__":
    sys.exit(main())
