"""
Agent-to-Agent (A2A) integration for UI Test Agent → Bug-Fix Agent handoff.

Uses the A2A protocol to pass test failures directly to the Bug-Fix Agent
without going through an orchestrator.
"""

import boto3
import json
import os


REGION = os.environ.get("AWS_REGION", "us-east-1")
BUG_FIX_AGENT_ARN = os.environ.get("BUG_FIX_AGENT_ARN", "")


def trigger_fix_agent_a2a(failures: list[dict], repository_url: str = "", branch: str = "") -> dict:
    """Send test failures to the Bug-Fix Agent via A2A protocol."""
    if not BUG_FIX_AGENT_ARN:
        return {"status": "skipped", "reason": "BUG_FIX_AGENT_ARN not configured"}

    client = boto3.client("bedrock-agentcore", region_name=REGION)

    payload = {
        "prompt": json.dumps({
            "action": "fix_failures",
            "failures": failures,
            "repository_url": repository_url,
            "branch": branch,
        })
    }

    try:
        response = client.invoke_agent_runtime(
            agentRuntimeArn=BUG_FIX_AGENT_ARN,
            body=json.dumps(payload).encode(),
        )
        return {"status": "triggered", "response": "Fix agent invoked via A2A"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
