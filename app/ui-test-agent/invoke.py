"""
UI Test Agent — Orchestrator Script

Invokes the Harness AgentCore UI testing agent and handles inline function callbacks.

Usage:
    python invoke.py --harness-arn <ARN> --url https://staging.example.com \
        --test-cases "Login with valid credentials" "Login with invalid password"

Version: 0.2.0
"""

__version__ = "0.2.0"

import argparse
import boto3
import json
import uuid
import sys
import time


def invoke_test_agent(
    harness_arn: str,
    target_url: str,
    test_suite: str,
    test_cases: list[str],
    region: str = "us-west-2",
    repository_url: str | None = None,
    branch: str | None = None,
) -> dict | None:
    """Invoke the UI test agent and return the test report."""
    client = boto3.client("bedrock-agentcore", region_name=region)
    session_id = str(uuid.uuid4())
    print(f"🧪 UI Test Agent v{__version__}")
    print(f"   Session: {session_id}")
    print(f"   Target:  {target_url}")
    print(f"   Suite:   {test_suite}")
    print(f"   Cases:   {len(test_cases)}")
    print()

    # Step 1: Set up environment (zero token cost)
    _exec_command(client, harness_arn, session_id, "mkdir -p /mnt/reports/screenshots")

    # Step 2: Build test prompt
    cases_text = "\n".join(f"  {i+1}. {tc}" for i, tc in enumerate(test_cases))
    prompt = f"""Execute the following UI test plan:

Target URL: {target_url}
Test Suite: {test_suite}

Test Cases:
{cases_text}

For each test case:
- Navigate to the relevant page
- Perform interactions as a human tester would
- Take screenshots before and after each action
- Record pass/fail with evidence
- Save the complete report to /mnt/reports/test-report-latest.json
- Save a markdown summary to /mnt/reports/summary.md
- Call notify_test_complete when done
- If there are failures, call trigger_fix_agent with the failure details
"""

    # Step 3: Invoke agent and handle conversation loop
    messages = [{"role": "user", "content": [{"text": prompt}]}]
    max_turns = 10  # Safety limit for inline function round-trips

    for turn in range(max_turns):
        response = client.invoke_harness(
            harnessArn=harness_arn,
            runtimeSessionId=session_id,
            actorId="ci-pipeline",
            messages=messages,
        )

        # Process stream
        result = _process_stream(response)

        if result["stop_reason"] == "end_turn":
            print("\n\n✅ Test run complete.")
            break
        elif result["stop_reason"] == "tool_use" and result["tool_use"]:
            # Handle inline function and send result back
            tool_result = _handle_inline_function(
                result["tool_use"], repository_url, branch
            )
            # Continue conversation with tool result
            messages = [{
                "role": "user",
                "content": [{"toolResult": {
                    "toolUseId": result["tool_use"]["toolUseId"],
                    "content": [{"text": json.dumps(tool_result)}],
                }}]
            }]
        elif result["stop_reason"] in ("max_iterations_exceeded", "timeout_exceeded", "max_output_tokens_exceeded"):
            print(f"\n⚠️  Agent stopped: {result['stop_reason']}")
            break
        else:
            print(f"\n⚠️  Unexpected stop reason: {result['stop_reason']}")
            break

    # Step 4: Retrieve report (zero token cost)
    report = _retrieve_report(client, harness_arn, session_id)
    if report:
        print(f"\n📊 Pass rate: {report['summary']['passRate']*100:.0f}%")
        print(f"   Total: {report['summary']['total']} | Passed: {report['summary']['passed']} | Failed: {report['summary']['failed']}")
    return report


def _process_stream(response: dict) -> dict:
    """Process streaming response, return stop_reason and tool_use info."""
    result = {"stop_reason": None, "tool_use": None, "text": ""}
    current_tool_use = {}

    for event in response["stream"]:
        if "contentBlockStart" in event:
            block = event["contentBlockStart"].get("start", {})
            if "toolUse" in block:
                current_tool_use = {
                    "toolUseId": block["toolUse"].get("toolUseId"),
                    "name": block["toolUse"].get("name"),
                    "input": "",
                }
        elif "contentBlockDelta" in event:
            delta = event["contentBlockDelta"].get("delta", {})
            if "text" in delta:
                print(delta["text"], end="", flush=True)
                result["text"] += delta["text"]
            if "toolUse" in delta and "input" in delta["toolUse"]:
                current_tool_use["input"] += delta["toolUse"]["input"]
        elif "contentBlockStop" in event:
            if current_tool_use and current_tool_use.get("input"):
                try:
                    current_tool_use["input"] = json.loads(current_tool_use["input"])
                except json.JSONDecodeError:
                    pass
                result["tool_use"] = current_tool_use
                current_tool_use = {}
        elif "messageStop" in event:
            result["stop_reason"] = event["messageStop"].get("stopReason")
        elif "runtimeClientError" in event:
            error_msg = event["runtimeClientError"].get("message", "Unknown error")
            print(f"\n❌ Runtime error: {error_msg}", file=sys.stderr)
            result["stop_reason"] = "error"

    return result


def _handle_inline_function(tool_use: dict, repository_url: str | None, branch: str | None) -> dict:
    """Handle inline function calls and return result."""
    name = tool_use.get("name", "")
    input_data = tool_use.get("input", {})

    if name == "notify_test_complete":
        pass_rate = input_data.get("pass_rate", 0)
        print(f"\n📋 Test complete. Pass rate: {pass_rate*100:.0f}%")
        print(f"   Report: {input_data.get('report_path')}")
        return {"status": "acknowledged", "message": "Test completion recorded."}

    elif name == "request_human_review":
        print(f"\n⚠️  Human review requested for {input_data.get('test_case_id')}")
        print(f"   Reason: {input_data.get('reason')}")
        # In CI/CD mode, auto-acknowledge; in interactive mode, could prompt user
        return {"status": "acknowledged", "message": "Human review request logged. Continue testing."}

    elif name == "trigger_fix_agent":
        failures = input_data.get("failures", [])
        print(f"\n🔧 Triggering fix agent for {len(failures)} failure(s)")
        for f in failures:
            print(f"   - {f['test_case_id']}: {f['severity']} — {f['actual']}")
        # TODO: Actually invoke the fix agent harness here
        return {
            "status": "triggered",
            "message": f"Fix agent triggered for {len(failures)} failures.",
            "fix_agent_session_id": str(uuid.uuid4()),
        }

    return {"status": "error", "message": f"Unknown inline function: {name}"}


def _exec_command(client, harness_arn: str, session_id: str, command: str) -> str:
    """Execute a shell command on the harness (zero token cost)."""
    response = client.invoke_agent_runtime_command(
        agentRuntimeArn=harness_arn,
        runtimeSessionId=session_id,
        body={"command": command},
    )
    output = ""
    for event in response["stream"]:
        chunk = event.get("chunk", {})
        if "contentDelta" in chunk:
            delta = chunk["contentDelta"]
            if "stdout" in delta:
                output += delta["stdout"]
            if "stderr" in delta:
                output += delta["stderr"]
    return output


def _retrieve_report(client, harness_arn: str, session_id: str) -> dict | None:
    """Retrieve the JSON test report from the harness filesystem."""
    output = _exec_command(client, harness_arn, session_id, "cat /mnt/reports/test-report-latest.json 2>/dev/null")
    if output.strip():
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            print("⚠️  Could not parse test report JSON", file=sys.stderr)
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"UI Test Agent Orchestrator v{__version__}")
    parser.add_argument("--harness-arn", required=True, help="Harness ARN")
    parser.add_argument("--url", required=True, help="Target URL to test")
    parser.add_argument("--test-suite", default="regression", help="Test suite name")
    parser.add_argument("--test-cases", nargs="+", required=True, help="List of test case descriptions")
    parser.add_argument("--region", default="us-west-2", help="AWS region")
    parser.add_argument("--repo", default=None, help="Git repository URL (for fix agent)")
    parser.add_argument("--branch", default=None, help="Git branch being tested")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    report = invoke_test_agent(
        harness_arn=args.harness_arn,
        target_url=args.url,
        test_suite=args.test_suite,
        test_cases=args.test_cases,
        region=args.region,
        repository_url=args.repo,
        branch=args.branch,
    )

    # Exit with non-zero if any critical/high failures
    if report and report.get("summary", {}).get("failed", 0) > 0:
        sys.exit(1)
