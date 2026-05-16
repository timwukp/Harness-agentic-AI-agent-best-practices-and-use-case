"""
Deploy UI Test Agent as AgentCore Harness (declarative mode).

This creates a Harness resource — no agent code needed.
The Harness manages orchestration, model, tools, and memory automatically.

Usage:
    python deploy_harness.py --region us-east-1 --role-arn <EXECUTION_ROLE_ARN>
"""

import argparse
import boto3
import json
import time


def deploy_harness(region: str, role_arn: str):
    client = boto3.client("bedrock-agentcore-control", region_name=region)

    system_prompt = """You are an expert QA tester for web applications.

Your job:
1. Navigate to target URLs using the browser
2. Interact with UI elements as a human would (click, type, scroll, hover)
3. Take screenshots before and after significant actions
4. Compare actual vs expected behavior
5. Report PASS/FAIL with evidence for each test case

Rules:
- Always take screenshots as evidence
- Classify severity: CRITICAL, HIGH, MEDIUM, LOW
- If blocked by a previous failure, mark as BLOCKED and continue
- Never navigate outside the target domain
- Never submit real PII or payment data"""

    print("Creating Harness...")
    client.create_harness(
        harnessName="UITestAgentHarness",
        executionRoleArn=role_arn,
        systemPrompt=[{"text": system_prompt}],
        tools=[
            {"type": "agentcore_browser", "name": "browser"},
            {"type": "agentcore_code_interpreter", "name": "code_interpreter"},
        ],
        maxIterations=100,
        timeoutSeconds=1800,
    )

    # Wait for READY
    for _ in range(30):
        resp = client.list_harnesses()
        for h in resp.get("harnesses", []):
            if h["harnessName"] == "UITestAgentHarness":
                if h["status"] == "READY":
                    print(f"✅ Harness READY: {h['harnessId']}")
                    print(f"   ARN: {h['arn']}")
                    return h
                print(f"   Status: {h['status']}...")
        time.sleep(2)

    print("⚠️ Timeout waiting for READY")
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy UI Test Agent as Harness")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--role-arn", required=True, help="IAM execution role ARN")
    args = parser.parse_args()
    deploy_harness(args.region, args.role_arn)
