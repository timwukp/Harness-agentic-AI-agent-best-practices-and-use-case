# UI Testing Agent — Design Document

## Overview

A Harness AgentCore application that replaces human QA testers in the SDLC. The agent mimics how a human tester works: reads test specifications, navigates the UI, interacts with elements (click, type, scroll), observes results, and produces structured test reports for downstream workflows.

## Why Harness AgentCore

| Requirement | Harness Capability |
|-------------|-------------------|
| Browse and interact with web UI | **AgentCore Browser** (cloud Playwright) |
| Understand test specs and reason about results | **Multi-model** (Claude Sonnet for reasoning) |
| Execute validation scripts | **Code Interpreter** (Python sandbox) |
| Remember test standards across sessions | **Long-term Memory** (semantic strategy) |
| Produce test reports as files | **Filesystem** (session storage) |
| Set up test environment | **Shell** (`InvokeAgentRuntimeCommand`) |
| Hand off to next agent in pipeline | **Inline Function** (workflow integration) |

## Agent Workflow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        UI Testing Agent                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. UNDERSTAND                                                       │
│     ├── Read test plan (from memory or input)                        │
│     ├── Identify test cases, acceptance criteria                     │
│     └── Determine test sequence and priority                         │
│                                                                      │
│  2. NAVIGATE                                                         │
│     ├── Open target URL in AgentCore Browser                         │
│     ├── Wait for page load, verify initial state                     │
│     └── Take baseline screenshot                                     │
│                                                                      │
│  3. INTERACT                                                         │
│     ├── Click buttons, links, menus                                  │
│     ├── Type into input fields, forms                                │
│     ├── Scroll, hover, drag-and-drop                                 │
│     ├── Handle dialogs, popups, modals                               │
│     └── Navigate between pages/routes                                │
│                                                                      │
│  4. OBSERVE                                                          │
│     ├── Capture screenshots after each action                        │
│     ├── Read page content (accessibility tree)                       │
│     ├── Check console errors                                         │
│     ├── Verify network responses                                     │
│     └── Measure response times                                       │
│                                                                      │
│  5. EVALUATE                                                         │
│     ├── Compare actual vs expected results                           │
│     ├── Classify: PASS / FAIL / BLOCKED / SKIPPED                    │
│     ├── Capture evidence (screenshots, logs)                         │
│     └── Calculate pass rate and severity                             │
│                                                                      │
│  6. REPORT                                                           │
│     ├── Generate structured test report (JSON + Markdown)            │
│     ├── Attach screenshots and console logs                          │
│     ├── Summarize findings with severity classification              │
│     └── Output for downstream agent (bug-fix agent)                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Architecture

```
                    ┌──────────────────────┐
                    │   CI/CD Pipeline     │
                    │  (GitHub Actions /   │
                    │   CodePipeline)      │
                    └──────────┬───────────┘
                               │ trigger
                               ▼
                    ┌──────────────────────┐
                    │   Orchestrator       │
                    │  (Lambda / Step Fn)  │
                    └──────────┬───────────┘
                               │ invoke_harness()
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                    AgentCore Harness                               │
│                    "ui-test-agent"                                 │
│                                                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   Browser   │  │    Code     │  │       Memory            │  │
│  │  (Playwright)│  │ Interpreter │  │  - Test standards       │  │
│  │             │  │  (Python)   │  │  - Historical results   │  │
│  │  • click    │  │             │  │  - Known issues         │  │
│  │  • type     │  │  • compare  │  │  - User preferences     │  │
│  │  • scroll   │  │  • validate │  │                         │  │
│  │  • screenshot│ │  • report   │  │                         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│                                                                    │
│  ┌─────────────┐  ┌─────────────────────────────────────────┐    │
│  │    Shell    │  │         Inline Functions                 │    │
│  │             │  │  • notify_test_complete                  │    │
│  │  • env setup│  │  • request_human_review (edge cases)    │    │
│  │  • git clone│  │  • trigger_fix_agent                    │    │
│  └─────────────┘  └─────────────────────────────────────────┘    │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │              Session Storage (/mnt/reports/)                 │  │
│  │  • test-report-{timestamp}.json                             │  │
│  │  • screenshots/                                             │  │
│  │  • console-logs/                                            │  │
│  └─────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                               │
                               │ inline_function: trigger_fix_agent
                               ▼
                    ┌──────────────────────┐
                    │   Bug-Fix Agent      │
                    │  (downstream)        │
                    └──────────────────────┘
```

## Harness Configuration

### Model

- **Default:** `us.anthropic.claude-sonnet-4-5-20250514-v1:0`
- **Reasoning:** Best balance of vision capability (screenshot analysis), reasoning (test evaluation), and cost
- **Override for complex UI:** Claude Opus for edge cases requiring deeper visual reasoning

### System Prompt

```
You are an expert QA tester for web applications. Your job is to:

1. Read and understand test specifications
2. Navigate web applications using the browser
3. Interact with UI elements exactly as a human tester would
4. Observe and record the results of each interaction
5. Compare actual results against expected results
6. Produce structured test reports

Rules:
- Always take a screenshot before and after each significant action
- Record console errors and network failures
- Classify each test case as PASS, FAIL, BLOCKED, or SKIPPED
- Include evidence (screenshots, error messages) for every FAIL
- Be thorough but efficient — skip redundant checks
- If a test is blocked by a previous failure, mark it BLOCKED and continue
- Output the final report as JSON to /mnt/reports/
```

### Tools

| Tool | Type | Purpose |
|------|------|---------|
| Browser | `agentcore_browser` | Navigate, click, type, screenshot, observe |
| Code Interpreter | `agentcore_code_interpreter` | Compare results, generate reports, validate data |
| Shell | `@builtin/shell` | Environment setup, file operations |
| File Operations | `@builtin/file_operations` | Write test reports to filesystem |
| `notify_test_complete` | `inline_function` | Signal orchestrator that testing is done |
| `request_human_review` | `inline_function` | Escalate ambiguous results to human |
| `trigger_fix_agent` | `inline_function` | Pass failures to bug-fix agent |

### Allowed Tools

```json
{
  "allowedTools": [
    "@builtin/shell",
    "@builtin/file_operations",
    "agentcore_browser",
    "agentcore_code_interpreter",
    "notify_test_complete",
    "request_human_review",
    "trigger_fix_agent"
  ]
}
```

### Memory

| Strategy | Purpose |
|----------|---------|
| **Semantic** | Store test standards, acceptance criteria, known patterns |
| **Episodic** | Remember past test runs, regression history |
| **User Preference** | Team-specific conventions (naming, severity levels) |

### Limits

```json
{
  "maxIterations": 100,
  "timeoutSeconds": 1800,
  "maxTokens": 32768,
  "idleRuntimeSessionTimeout": 600
}
```

- `maxIterations: 100` — UI testing requires many browser interactions
- `timeoutSeconds: 1800` — 30 min max per test suite run
- `maxTokens: 32768` — screenshots and reports need larger context

### Filesystem

```json
{
  "filesystemConfigurations": [{
    "sessionStorage": {
      "mountPath": "/mnt/reports/"
    }
  }]
}
```

## Test Report Schema

```json
{
  "reportId": "uuid",
  "timestamp": "2026-05-16T18:00:00Z",
  "targetUrl": "https://staging.example.com",
  "testPlan": "Login Flow Regression",
  "environment": {
    "browser": "chromium",
    "viewport": "1456x819"
  },
  "summary": {
    "total": 12,
    "passed": 9,
    "failed": 2,
    "blocked": 1,
    "skipped": 0,
    "passRate": 0.75,
    "duration": "4m 32s"
  },
  "testCases": [
    {
      "id": "TC-001",
      "name": "Login with valid credentials",
      "priority": "P0",
      "status": "PASS",
      "steps": [
        {"action": "Navigate to /login", "expected": "Login form visible", "actual": "Login form visible", "status": "PASS"},
        {"action": "Type 'user@test.com' in email field", "expected": "Email populated", "actual": "Email populated", "status": "PASS"},
        {"action": "Type password and click Submit", "expected": "Redirect to /dashboard", "actual": "Redirect to /dashboard", "status": "PASS"}
      ],
      "screenshots": ["screenshots/TC-001-before.png", "screenshots/TC-001-after.png"],
      "duration": "3.2s"
    },
    {
      "id": "TC-002",
      "name": "Login with invalid password",
      "priority": "P0",
      "status": "FAIL",
      "steps": [
        {"action": "Type wrong password and click Submit", "expected": "Error message: 'Invalid credentials'", "actual": "Page shows 500 Internal Server Error", "status": "FAIL"}
      ],
      "screenshots": ["screenshots/TC-002-error.png"],
      "consoleErrors": ["Uncaught TypeError: Cannot read property 'message' of undefined"],
      "severity": "HIGH",
      "duration": "2.1s"
    }
  ],
  "recommendations": [
    "TC-002: Server returns 500 instead of 401 for invalid credentials. Backend error handling issue.",
    "TC-007: Button click unresponsive on mobile viewport. CSS z-index conflict suspected."
  ]
}
```

## Invocation Patterns

### Pattern 1: CI/CD Triggered (Automated)

```python
import boto3
import uuid
import json

client = boto3.client("bedrock-agentcore", region_name="us-west-2")

# Prepare test context
test_plan = {
    "target_url": "https://staging.example.com",
    "test_suite": "login-flow-regression",
    "specs_url": "https://wiki.internal/test-specs/login-flow.md"
}

response = client.invoke_harness(
    harnessArn=HARNESS_ARN,
    runtimeSessionId=str(uuid.uuid4()) + "-" + "ci-run-1234",
    actorId="ci-pipeline",
    messages=[{
        "role": "user",
        "content": [{"text": f"""
Execute the following test plan:

Target URL: {test_plan['target_url']}
Test Suite: {test_plan['test_suite']}

Test Cases:
1. Login with valid credentials → expect redirect to /dashboard
2. Login with invalid password → expect error message "Invalid credentials"
3. Login with empty fields → expect validation errors on both fields
4. Forgot password link → expect redirect to /reset-password
5. Remember me checkbox → expect session persists after browser close

For each test case:
- Navigate to the page
- Perform the actions as a human would
- Take screenshots before and after
- Record pass/fail with evidence
- Save report to /mnt/reports/
"""}]
    }],
)

# Process streaming response
for event in response["stream"]:
    if "contentBlockDelta" in event:
        delta = event["contentBlockDelta"].get("delta", {})
        if "text" in delta:
            print(delta["text"], end="", flush=True)
    elif "messageStop" in event:
        stop_reason = event["messageStop"].get("stopReason")
        if stop_reason == "tool_use":
            # Handle inline function (notify_test_complete or trigger_fix_agent)
            pass
```

### Pattern 2: Pre-Setup with Shell (Optimized)

```python
# Step 1: Set up environment (zero token cost)
client.invoke_agent_runtime_command(
    agentRuntimeArn=HARNESS_ARN,
    runtimeSessionId=SESSION_ID,
    body={"command": "mkdir -p /mnt/reports/screenshots && echo 'ready'"},
)

# Step 2: Invoke agent for actual testing
client.invoke_harness(
    harnessArn=HARNESS_ARN,
    runtimeSessionId=SESSION_ID,
    messages=[{"role": "user", "content": [{"text": "Execute test plan..."}]}],
)

# Step 3: Retrieve report (zero token cost)
result = client.invoke_agent_runtime_command(
    agentRuntimeArn=HARNESS_ARN,
    runtimeSessionId=SESSION_ID,
    body={"command": "cat /mnt/reports/test-report-latest.json"},
)
```

### Pattern 3: CLI for Development

```bash
# Create and deploy
agentcore create --name ui-test-agent --model-provider bedrock
agentcore add tool --harness ui-test-agent --type agentcore_browser --name browser
agentcore add tool --harness ui-test-agent --type agentcore_code_interpreter --name code-interpreter
agentcore deploy

# Test interactively
agentcore dev

# Run a test
agentcore invoke --harness ui-test-agent \
  --session-id "$(uuidgen)" \
  "Test the login page at https://staging.example.com/login. 
   Verify: valid login redirects to dashboard, invalid shows error message."
```

## Downstream Integration

### Handoff to Bug-Fix Agent

When tests fail, the inline function `trigger_fix_agent` returns control to the orchestrator:

```python
# Orchestrator receives tool_use with trigger_fix_agent
# Extract the test report and pass to fix agent
fix_payload = {
    "failures": [
        {
            "test_case": "TC-002",
            "expected": "Error message: 'Invalid credentials'",
            "actual": "500 Internal Server Error",
            "screenshot": "s3://reports/screenshots/TC-002-error.png",
            "console_error": "TypeError: Cannot read property 'message' of undefined",
            "file_hint": "src/api/auth.controller.ts"
        }
    ],
    "repository": "https://github.com/org/frontend-app",
    "branch": "feature/login-redesign"
}

# Invoke the fix agent with failure context
fix_client.invoke_harness(
    harnessArn=FIX_AGENT_ARN,
    runtimeSessionId=str(uuid.uuid4()) + "-fix-session",
    messages=[{"role": "user", "content": [{"text": json.dumps(fix_payload)}]}],
)
```

## Security Considerations

- **Target URL allowlist:** Only test against staging/dev environments, never production
- **Network isolation:** Deploy in VPC with access only to staging environments
- **No credential storage in prompts:** Use environment variables for test account credentials
- **Session isolation:** Each test run gets a fresh microVM — no cross-contamination
- **Report access:** Session storage is scoped to the session; use S3 Files for persistent access

## Cost Estimation

| Component | Per Test Suite Run | Notes |
|-----------|-------------------|-------|
| Model tokens | ~$0.05–0.15 | Depends on test complexity |
| Browser sessions | ~$0.01 | Per-minute billing |
| Code Interpreter | ~$0.005 | Report generation |
| Total | ~$0.07–0.17 | vs. $50–100/hr human QA tester |

**ROI:** A single human QA tester costs ~$50–100/hr. This agent can run 500+ test suites per hour at <$0.20 each.

---

*Last updated: 2026-05-16*
