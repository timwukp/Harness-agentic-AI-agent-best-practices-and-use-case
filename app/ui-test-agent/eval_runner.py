"""
Agent Evaluation Runner — Golden Tests

Uses bedrock_agentcore.evaluation to validate the UI Test Agent
produces correct results against known test scenarios.

Usage:
    python eval_runner.py --harness-arn <ARN>
"""

__version__ = "0.2.0"

import argparse
import json

GOLDEN_TESTS = [
    {
        "id": "GT-01",
        "prompt": "Navigate to https://the-internet.herokuapp.com/login. Type 'tomsmith' in username, 'SuperSecretPassword!' in password, click Login. Report PASS if redirected to /secure.",
        "expected_status": "PASS",
        "must_contain": ["secure", "logged in"],
    },
    {
        "id": "GT-02",
        "prompt": "Navigate to https://the-internet.herokuapp.com/login. Type 'wronguser' in username, 'wrongpass' in password, click Login. Report PASS if you see an error message about invalid credentials.",
        "expected_status": "PASS",
        "must_contain": ["invalid"],
    },
    {
        "id": "GT-03",
        "prompt": "Navigate to https://the-internet.herokuapp.com/dropdown. Select 'Option 2' from the dropdown. Report PASS if the selection is confirmed.",
        "expected_status": "PASS",
        "must_contain": ["option 2"],
    },
    {
        "id": "GT-04",
        "prompt": "Navigate to https://the-internet.herokuapp.com/broken_images. Check all images on the page. Report FAIL if any images are broken.",
        "expected_status": "FAIL",
        "must_contain": ["broken"],
    },
    {
        "id": "GT-05",
        "prompt": "Navigate to https://the-internet.herokuapp.com/dynamic_loading/1. Click the Start button. Wait for the element to appear. Report PASS if you see 'Hello World!' text.",
        "expected_status": "PASS",
        "must_contain": ["hello world"],
    },
    {
        "id": "GT-06",
        "prompt": "Navigate to https://the-internet.herokuapp.com/add_remove_elements/. Click 'Add Element' 3 times. Verify 3 'Delete' buttons appear. Report PASS or FAIL.",
        "expected_status": "PASS",
        "must_contain": ["delete"],
    },
]


def run_golden_tests(harness_arn: str, region: str = "us-east-1") -> dict:
    """Run all golden tests and return results."""
    import boto3
    import uuid

    client = boto3.client("bedrock-agentcore", region_name=region)
    results = {"total": len(GOLDEN_TESTS), "passed": 0, "failed": 0, "details": []}

    for test in GOLDEN_TESTS:
        print(f"Running {test['id']}...", end=" ")
        session_id = str(uuid.uuid4())

        try:
            response = client.invoke_agent_runtime(
                agentRuntimeArn=harness_arn,
                runtimeSessionId=session_id,
                body=json.dumps({"prompt": test["prompt"]}).encode(),
            )

            # Collect response
            response_text = ""
            for event in response.get("body", []):
                chunk = event.get("chunk", {}).get("bytes", b"")
                response_text += chunk.decode("utf-8", errors="ignore")

            # Validate
            response_lower = response_text.lower()
            contains_expected = any(kw in response_lower for kw in test["must_contain"])

            if contains_expected:
                results["passed"] += 1
                status = "✅ PASS"
            else:
                results["failed"] += 1
                status = "❌ FAIL"

            print(status)
            results["details"].append({
                "id": test["id"],
                "status": status,
                "response_preview": response_text[:200],
            })

        except Exception as e:
            results["failed"] += 1
            print(f"❌ ERROR: {e}")
            results["details"].append({"id": test["id"], "status": "ERROR", "error": str(e)})

    results["pass_rate"] = results["passed"] / results["total"] if results["total"] > 0 else 0
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"UI Test Agent Evaluation Runner v{__version__}")
    parser.add_argument("--harness-arn", required=True, help="Agent Runtime ARN")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    results = run_golden_tests(args.harness_arn, args.region)
    print(f"\n📊 Results: {results['passed']}/{results['total']} passed ({results['pass_rate']*100:.0f}%)")

    if results["failed"] > 0:
        exit(1)
