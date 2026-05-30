#!/usr/bin/env python3
"""
Issue #24: Attach the existing Memory resource to UITestAgentHarness.

Why this script is read-only:
  Public boto3 (1.42.79) does NOT expose CreateHarness / UpdateHarness yet.
  The control plane refuses UpdateAgentRuntime against harness-managed runtimes:

    "This agent runtime is managed by harness '...' and cannot be updated
     directly. Use UpdateHarness to update this resource."

  So Memory attachment must be done via the AWS console for now. This script:

  1. Verifies the Memory resource exists and lists its strategies
  2. Verifies the Harness exists
  3. Detects whether Memory is already attached (via MEMORY_*_ID env var)
  4. Prints the exact steps to perform in the AWS console

When UpdateHarness ships in public boto3, the manual block at the bottom can
be uncommented to make this script self-applying.

Usage:
  python attach_memory.py [--region us-east-1] [--harness-name UITestAgentHarness]
"""

import argparse
import sys

import boto3


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--harness-name", default="UITestAgentHarness")
    parser.add_argument("--memory-name-prefix", default="uitestagent_uitestagentMemory")
    args = parser.parse_args()

    region = args.region
    harness_runtime_name = f"harness_{args.harness_name}"
    agentcore = boto3.client("bedrock-agentcore-control", region_name=region)

    print(f"Region: {region}\nLooking for harness: {harness_runtime_name}\nLooking for memory:  {args.memory_name_prefix}*\n")

    # Find the harness runtime
    runtimes = {r["agentRuntimeName"]: r for r in agentcore.list_agent_runtimes()["agentRuntimes"]}
    if harness_runtime_name not in runtimes:
        print(f"✗ Harness runtime not found: {harness_runtime_name}")
        return 1
    harness = runtimes[harness_runtime_name]
    details = agentcore.get_agent_runtime(agentRuntimeId=harness["agentRuntimeId"])
    print(f"✓ Found harness (status: {harness['status']})")

    # Find the memory resource
    memories = agentcore.list_memories()["memories"]
    matching_memory = None
    for m in memories:
        m_full = agentcore.get_memory(memoryId=m["id"])["memory"]
        if m_full.get("name", "").startswith(args.memory_name_prefix):
            matching_memory = m_full
            break
    if not matching_memory:
        print(f"✗ Memory not found with name prefix: {args.memory_name_prefix}")
        return 1
    print(f"✓ Found memory: {matching_memory.get('name', '<unnamed>')}")
    print(f"  Status: {matching_memory['status']}")
    print(f"  Event expiry: {matching_memory.get('eventExpiryDuration', 'n/a')} days")
    print(f"  Strategies ({len(matching_memory.get('strategies', []))}):")
    for s in matching_memory.get("strategies", []):
        ns = s.get("namespaces", ["?"])[0]
        print(f"    - {s['type']:<16} → {ns}")
    print()

    # Detect whether memory is already attached via env var
    env_vars = details.get("environmentVariables", {}) or {}
    expected_env_key = f"MEMORY_{matching_memory['name'].upper().replace('_', '').replace('-', '')}_ID"
    # Actually use convention: MEMORY_<MemoryName>_ID with name uppercased and underscore-stripped
    # Fall back to scanning all MEMORY_*_ID keys
    memory_attached = any(
        k.startswith("MEMORY_") and k.endswith("_ID") and v.startswith(matching_memory["name"])
        for k, v in env_vars.items()
    )
    if memory_attached:
        for k, v in env_vars.items():
            if k.startswith("MEMORY_"):
                print(f"✓ Memory already attached via env var: {k}")
        return 0

    # Print attachment instructions
    print("⚠ Memory is NOT yet attached to the harness.\n")
    print("=== How to attach (manual, AWS console) ===\n")
    print("Public boto3 does not yet expose UpdateHarness, so attachment")
    print("must be done via the AWS console. The recommended steps:\n")
    print(f"  1. AWS Console → Bedrock AgentCore → Harness → {args.harness_name}")
    print("  2. Click [Edit]")
    print("  3. In the Memory section, click Edit / Configure")
    print(f"  4. Select existing memory: {matching_memory.get('name', '<unnamed>')}")
    print("  5. Save and wait for status to return to READY (~30-60 seconds)\n")
    print("If the console doesn't expose a Memory selector for this harness,")
    print("alternative: edit Environment variables and add:\n")
    print(f"  MEMORY_{args.memory_name_prefix.upper().replace('_', '')}_ID = {matching_memory['name']}-<MEM_ID>")
    print(f"\nor more precisely (use the actual ID — substitute placeholder):")
    print(f"  MEMORY_<NAME_UPPER>_ID = <memory-id-from-account>")
    print()
    print("After attachment, re-run this script to verify.")
    print()
    print("Future: when UpdateHarness ships in public boto3, this script can")
    print("be extended to programmatically attach the memory (the code path")
    print("is sketched at the bottom of this file).")
    return 2  # not yet attached, exit with non-zero


# === Future implementation when UpdateHarness ships ===
#
# def update_harness_with_memory(region, harness_id, memory_id, ...):
#     control = boto3.client("bedrock-agentcore-control", region_name=region)
#     control.update_harness(
#         harnessId=harness_id,
#         memoryConfiguration={
#             "memoryArn": f"arn:aws:bedrock-agentcore:{region}:{account_id}:memory/{memory_id}",
#         },
#     )

if __name__ == "__main__":
    sys.exit(main())
