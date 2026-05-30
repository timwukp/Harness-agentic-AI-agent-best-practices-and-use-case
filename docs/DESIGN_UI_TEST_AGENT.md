# UI Testing Agent — Design Document

> **Version:** 0.2.0
> **Last Updated:** 2026-05-30
> **Status:** Design + implementation reference (matches `app/ui-test-agent/main.py` v0.2.0)

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
| Hand off to next agent in pipeline | **A2A protocol** (`invoke_agent_runtime` peer-to-peer) |

> See [ARCHITECTURE.md §13 — A2A Protocol](ARCHITECTURE.md#a2a-protocol--agent-to-agent-communication) for the handoff design.

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
│     ├── Compare actual vs expected results (Code Interpreter)        │
│     ├── Classify: PASS / FAIL / BLOCKED / SKIPPED                    │
│     ├── Capture evidence (screenshots, logs)                         │
│     └── Calculate pass rate and severity                             │
│                                                                      │
│  6. REPORT                                                           │
│     ├── Generate structured test report (JSON + Markdown)            │
│     ├── Attach screenshots and console logs                          │
│     ├── Summarize findings with severity classification              │
│     └── Hand off failures to Bug-Fix Agent via A2A                   │
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
                    │  (e2e_pipeline.py /  │
                    │   Lambda / Step Fn)  │
                    └──────────┬───────────┘
                               │ invoke_agent_runtime()
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                    AgentCore Runtime                                │
│                    "ui-test-agent" (Strands)                        │
│                                                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   Browser   │  │ execute_code│  │       Memory            │  │
│  │  (Strands   │  │  (custom    │  │  - Test standards       │  │
│  │  AgentCore  │  │  @tool      │  │  - Historical results   │  │
│  │  Browser)   │  │  wrapping   │  │  - Known issues         │  │
│  │             │  │  Code       │  │  - User preferences     │  │
│  │  • click    │  │  Interpreter│  │                         │  │
│  │  • type     │  │  Client)    │  │                         │  │
│  │  • scroll   │  │             │  │                         │  │
│  │  • screenshot│ │  • compare  │  │                         │  │
│  │             │  │  • validate │  │                         │  │
│  │             │  │  • report   │  │                         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│                                                                    │
│  ┌─────────────────────┐  ┌──────────────────────────────────┐  │
│  │  file_* @tools      │  │      Streamable HTTP             │  │
│  │                     │  │      MCP Client                  │  │
│  │  • file_read        │  │  (optional, configured           │  │
│  │  • file_write       │  │   via mcp_client/client.py)      │  │
│  │  • list_files       │  │                                  │  │
│  │  (scoped to /mnt/   │  │                                  │  │
│  │   reports)          │  │                                  │  │
│  └─────────────────────┘  └──────────────────────────────────┘  │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │              Session Storage (/mnt/reports/)                 │  │
│  │  • test-report-{timestamp}.json                             │  │
│  │  • screenshots/                                             │  │
│  │  • console-logs/                                            │  │
│  └─────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                               │
                               │ a2a_handoff.py: invoke_agent_runtime
                               │ (target = BUG_FIX_AGENT_ARN)
                               ▼
                    ┌──────────────────────┐
                    │   Bug-Fix Agent      │
                    │   (Harness, deployed │
                    │   as BugFixAgent-    │
                    │   Harness-<HARNESS_ID>)│
                    └──────────────────────┘
```

## Harness Configuration

### Model

- **Default:** `us.anthropic.claude-sonnet-4-5-20250514-v1:0`
- **Reasoning:** Best balance of vision capability (screenshot analysis), reasoning (test evaluation), and cost
- **Override for complex UI:** Claude Opus for edge cases requiring deeper visual reasoning

### System Prompt

The actual prompt lives in `app/ui-test-agent/main.py` as `DEFAULT_SYSTEM_PROMPT`:

```
You are an expert QA tester for web applications. You have a real browser and a code interpreter.

Your job:
1. Navigate to target URLs using the browser tool
2. Interact with UI elements as a human would (click, type, scroll)
3. Take screenshots before and after significant actions
4. Observe results, console errors, and network responses
5. Compare actual vs expected behavior
6. Use code interpreter for precise comparisons, calculations, and report generation
7. Report PASS/FAIL with evidence for each test case
8. Save reports to /mnt/reports/

Rules:
- Always use the browser tool to navigate and interact
- Use code interpreter for data analysis, JSON generation, and calculations
- Take screenshots as evidence for every FAIL
- Classify severity: CRITICAL, HIGH, MEDIUM, LOW
- If blocked by a previous failure, mark as BLOCKED and continue
- Never navigate outside the target domain
- Never submit real PII or payment data

After each test run, reflect on what you learned:
- What patterns did you discover?
- What interaction methods worked or failed?
- Store useful patterns for future sessions.

You have persistent storage at /mnt/reports. Use file tools to save test reports.
```

### Tools (actual wiring in `main.py`)

| Tool | Source | Purpose |
|------|--------|---------|
| **Browser** | `strands_tools.browser.AgentCoreBrowser(region).browser` | Navigate, click, type, scroll, hover, drag-and-drop, screenshot |
| **execute_code** | Custom `@tool` wrapping `bedrock_agentcore.tools.code_interpreter_client.CodeInterpreterClient` | Run Python in a sandboxed microVM for comparisons, calculations, report generation. See [ARCHITECTURE.md §6](ARCHITECTURE.md#code-interpreter-integration) |
| **file_read** | Custom `@tool` (path-restricted) | Read a file under `/mnt/reports/` (resolves safely, refuses paths outside the boundary) |
| **file_write** | Custom `@tool` (path-restricted) | Write a file under `/mnt/reports/` (creates parent dirs as needed) |
| **list_files** | Custom `@tool` (path-restricted) | List directory contents under `/mnt/reports/` |
| **Streamable HTTP MCP Client** | `mcp_client/client.py` | Optional — pluggable external integrations via MCP |

The four `file_*` tools enforce a `_safe_resolve` boundary so the agent cannot read or write outside `/mnt/reports/`.

The three "inline functions" referenced in earlier drafts (`notify_test_complete`, `request_human_review`, `trigger_fix_agent`) were design-stage ideas that were not implemented as inline functions. Bug-Fix Agent handoff is now implemented as **A2A** (see "Downstream Integration" below).

### Memory

| Strategy | Purpose |
|----------|---------|
| **Semantic** | Store test standards, acceptance criteria, known patterns |
| **Episodic** | Remember past test runs, regression history |
| **Summarization** | Session summaries |
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

The agent's `file_*` tools all operate under this mount path with a safety boundary check.

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

The UI Test Agent is deployed as an **AgentCore Runtime** (Strands), so callers use `invoke_agent_runtime` against the Runtime ARN. (The Bug-Fix Agent is deployed as a **Harness** — both modes are demonstrated in this project.)

### Pattern 1: CI/CD Triggered (Automated)

```python
import boto3
import uuid
import json

client = boto3.client("bedrock-agentcore", region_name="us-east-1")

session_id = str(uuid.uuid4())
prompt = """
Execute the following test plan:

Target URL: https://staging.example.com
Test Suite: login-flow-regression

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
"""

response = client.invoke_agent_runtime(
    agentRuntimeArn=UI_TEST_AGENT_ARN,
    runtimeSessionId=session_id,
    body=json.dumps({"prompt": prompt}).encode(),
)

# Stream response
for event in response.get("body", []):
    chunk = event.get("chunk", {}).get("bytes", b"")
    print(chunk.decode("utf-8", errors="ignore"), end="", flush=True)
```

### Pattern 2: Pre-Setup with Shell (Optimized)

```python
# Step 1: Set up environment (zero token cost)
client.invoke_agent_runtime_command(
    agentRuntimeArn=UI_TEST_AGENT_ARN,
    runtimeSessionId=SESSION_ID,
    body={"command": "mkdir -p /mnt/reports/screenshots && echo 'ready'"},
)

# Step 2: Invoke agent for actual testing
client.invoke_agent_runtime(
    agentRuntimeArn=UI_TEST_AGENT_ARN,
    runtimeSessionId=SESSION_ID,
    body=json.dumps({"prompt": "Execute test plan..."}).encode(),
)

# Step 3: Retrieve report (zero token cost)
result = client.invoke_agent_runtime_command(
    agentRuntimeArn=UI_TEST_AGENT_ARN,
    runtimeSessionId=SESSION_ID,
    body={"command": "cat /mnt/reports/test-report-latest.json"},
)
```

### Pattern 3: CLI for Development

```bash
# Create and deploy via the project's deploy.sh
cd app/ui-test-agent && ./deploy.sh

# Test interactively
agentcore dev

# Run a test
agentcore invoke --session-id "$(uuidgen)" \
  "Test the login page at https://staging.example.com/login.
   Verify: valid login redirects to dashboard, invalid shows error message."
```

## Validation & E2E Pipeline

The agent ships with two helper scripts that exercise it end-to-end:

### `eval_runner.py` — golden-test regression suite

Six pre-defined prompts (GT-01 … GT-06) covering valid login, invalid login, dropdowns, broken images, dynamic loading, and add/remove element flows. After every change to `main.py` (system prompt, model, tool list), run:

```bash
python app/ui-test-agent/eval_runner.py --harness-arn $UI_TEST_AGENT_ARN
```

Exit code is `0` if all pass, `1` if any fail — suitable for GitHub Actions regression. See [ARCHITECTURE.md §10.2 — Evaluation Runner Implementation](ARCHITECTURE.md#agent-testing-strategy) for the validation methodology and limitations (current: keyword matching; planned: LLM-as-judge).

### `e2e_pipeline.py` — full pipeline orchestration

Demonstrates the full automated QA flow against the demo frontend:

1. Invoke UI Test Agent (Runtime) against the demo URL
2. Detect any FAIL results
3. Send the failure context to the Bug-Fix Agent (Harness) via `invoke_harness`
4. Bug-Fix Agent generates a unified diff patch
5. (Optional) git branch + PR creation

```bash
python app/ui-test-agent/e2e_pipeline.py
```

This script is the integration that proved the architecture end-to-end on 2026-05-16 (commit `75d8e065`, evidence in `05951a944`).

## Downstream Integration

### Handoff to Bug-Fix Agent — A2A

When tests fail, the orchestrator (or `e2e_pipeline.py`) calls `trigger_fix_agent_a2a` from `app/ui-test-agent/a2a_handoff.py`:

```python
# app/ui-test-agent/a2a_handoff.py
import boto3, json, os

REGION = os.environ.get("AWS_REGION", "us-east-1")
BUG_FIX_AGENT_ARN = os.environ.get("BUG_FIX_AGENT_ARN", "")

def trigger_fix_agent_a2a(failures, repository_url="", branch=""):
    if not BUG_FIX_AGENT_ARN:
        return {"status": "skipped", "reason": "BUG_FIX_AGENT_ARN not configured"}

    client = boto3.client("bedrock-agentcore", region_name=REGION)
    payload = {"prompt": json.dumps({
        "action": "fix_failures",
        "failures": failures,
        "repository_url": repository_url,
        "branch": branch,
    })}

    response = client.invoke_agent_runtime(
        agentRuntimeArn=BUG_FIX_AGENT_ARN,
        body=json.dumps(payload).encode(),
    )
    return {"status": "triggered", "response": "Fix agent invoked via A2A"}
```

This is **direct agent-to-agent invocation** (A2A pattern) — no orchestrator middleman. The full design rationale, IAM model, Cedar policy example, and decision matrix (A2A vs Step Functions) live in [ARCHITECTURE.md §13](ARCHITECTURE.md#a2a-protocol--agent-to-agent-communication).

The Bug-Fix Agent that receives this call is `BugFixAgentHarness-<HARNESS_ID>` (deployed in commit `75d8e065`).

## Security Considerations

- **Target URL allowlist:** Only test against staging/dev environments, never production
- **Network isolation:** Deploy in VPC with access only to staging environments
- **No credential storage in prompts:** Use environment variables for test account credentials
- **Session isolation:** Each test run gets a fresh microVM — no cross-contamination
- **Filesystem boundary:** `file_*` tools enforce `/mnt/reports/` boundary via `_safe_resolve` to prevent path traversal
- **A2A scoping:** When invoking the Bug-Fix Agent, the caller IAM role must scope `bedrock-agentcore:InvokeAgentRuntime` to the specific target ARN — never `*`. See [BEST_PRACTICES.md §10](BEST_PRACTICES.md#security)
- **Browser features in production:** for profile-per-tenant scoping, S3 recording with KMS, and Web Bot Auth, see [BEST_PRACTICES.md §7](BEST_PRACTICES.md#browser-tool--production-features)

## Cost Estimation

| Component | Per Test Suite Run | Notes |
|-----------|-------------------|-------|
| Claude Sonnet 4.5 input + output | ~$0.24 | ~30K in / ~10K out |
| AgentCore Browser | ~$0.05 | ~5 min |
| AgentCore Code Interpreter | ~$0.03 | ~30 sec |
| AgentCore Memory | ~$0.001 | ~20 read/write ops |
| S3 (report storage) | ~$0.00003 | ~1 MB |
| **Total per run** | **~$0.32** | vs. $50–100/hr human QA tester |

See [ARCHITECTURE.md — Entire Project Cost Estimation](ARCHITECTURE.md#entire-project-cost-estimation) for the full breakdown including monthly scenarios and free-tier applicability.

**ROI:** A single human QA tester costs ~$50–100/hr. This agent runs 100+ test suites in parallel at ~$0.32 each.

---

## Deployment Modes

This project supports **two deployment modes**. Both are functionally equivalent but differ in how they're managed:

### Mode 1: AgentCore Runtime (Code-based) — primary mode for the UI Test Agent

You write `main.py` with Strands SDK, deploy via `agentcore deploy`.

```bash
agentcore create --name uitestagent --framework strands --model-provider bedrock --memory longAndShortTerm
agentcore deploy
agentcore invoke --session-id "$(uuidgen)" "Test the login page..."
```

**Pros:** Full control over agent logic, custom tools, complex orchestration
**Cons:** Must write and maintain Python code
**Console location:** AgentCore → Runtimes
**Files:** `main.py`, `pyproject.toml`, `memory/`, `model/`, `mcp_client/`

### Mode 2: AgentCore Harness (Declarative) — used for the Bug-Fix Agent

No agent code. Define model, tools, and prompt via API or CLI.

```python
import boto3
client = boto3.client("bedrock-agentcore-control", region_name="us-east-1")
client.create_harness(
    harnessName="UITestAgentHarness",
    executionRoleArn="<ROLE_ARN>",
    systemPrompt=[{"text": "You are an expert QA tester..."}],
    tools=[
        {"type": "agentcore_browser", "name": "browser"},
        {"type": "agentcore_code_interpreter", "name": "code_interpreter"},
    ],
    maxIterations=100,
    timeoutSeconds=1800,
)
```

**Pros:** Zero code, config-driven, switch models/tools without redeploy
**Cons:** Less control over orchestration logic
**Console location:** AgentCore → Harness (Preview)
**Files:** `deploy_harness.py` (one-time setup script)

### When to Use Which

| Scenario | Use |
|----------|-----|
| Need custom tool logic (like our path-bounded `file_*` tools) or multi-agent coordination | Runtime |
| Want fastest setup, no code maintenance | Harness |
| Need to experiment with different models/prompts quickly | Harness |
| Need to embed agent in existing application | Runtime |
| Production with minimal ops overhead | Harness |

This project uses **Runtime** for the UI Test Agent (which needs the custom path-restricted file tools and MCP client wiring) and **Harness** for the Bug-Fix Agent (`BugFixAgentHarness-<HARNESS_ID>`, which only needs Code Interpreter + GitHub MCP).

### Deployment Scripts

| Script | Mode | Command |
|--------|------|---------|
| `deploy.sh` | Runtime | `./deploy.sh` |
| `deploy_harness.py` | Harness | `python deploy_harness.py --role-arn <ARN>` |
