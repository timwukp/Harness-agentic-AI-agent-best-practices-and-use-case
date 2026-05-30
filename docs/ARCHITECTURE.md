# UI Test Agent — Complete Use Case Architecture

> **Version:** 0.2.0
> **Last Updated:** 2026-05-30
> **Status:** Design + Implementation reference

---

## Table of Contents

1. [Overview](#overview)
2. [Why AgentCore Harness](#why-agentcore-harness)
3. [End-to-End Workflow](#end-to-end-workflow)
4. [System Architecture](#system-architecture)
5. [Trigger Mechanisms](#trigger-mechanisms)
6. [Code Interpreter Integration](#code-interpreter-integration)
7. [Agent Guardrails & Safety](#agent-guardrails--safety)
8. [Self-Learning & Memory Architecture](#self-learning--memory-architecture)
9. [Scaling Strategy](#scaling-strategy)
10. [Agent Testing Strategy](#agent-testing-strategy)
11. [Admin Portal Design](#admin-portal-design)
12. [Downstream Bug-Fix Agent](#downstream-bug-fix-agent)
13. [A2A Protocol — Agent-to-Agent Communication](#a2a-protocol--agent-to-agent-communication)
14. [Security Design](#security-design)
15. [Cost Model](#cost-model)
16. [AgentCore Gateway & Policy Integration](#agentcore-gateway--policy-integration)
17. [Entire Project Cost Estimation](#entire-project-cost-estimation)

---

## Overview

The UI Test Agent is an AI-powered QA automation system that replaces human testers in the SDLC. It operates within Amazon Bedrock AgentCore Harness, using cloud browser automation to interact with web applications exactly as a human would — clicking, typing, scrolling, observing, and evaluating results.

**Key differentiator from traditional test automation (Selenium/Cypress):**
- No brittle selectors or hardcoded test scripts
- Adapts to UI changes without code updates
- Understands intent, not just DOM structure
- Learns from failures and improves over time
- Produces human-readable reports with reasoning

---

## Why AgentCore Harness

| Requirement | Harness Capability | Alternative (DIY) Cost |
|-------------|-------------------|----------------------|
| Browser interaction | Built-in AgentCore Browser (cloud Playwright) | Set up Playwright infra, manage browser pools |
| Reasoning about UI | Multi-model (Claude Sonnet vision) | Build custom vision pipeline |
| Test report generation | Code Interpreter (Python) | Deploy separate compute |
| Remember test patterns | Long-term Memory (semantic + episodic) | Build vector DB + retrieval |
| Environment setup | Shell (InvokeAgentRuntimeCommand) | Manage container lifecycle |
| Workflow integration | Inline Functions | Build custom webhook system |
| Isolation per test run | Firecracker microVM per session | Manage container orchestration |
| Zero infra management | Fully managed | Weeks of DevOps work |

**Estimated build-vs-buy:** 6-8 weeks of engineering to build equivalent DIY vs. 1 day with Harness.

---

## End-to-End Workflow

```
Developer pushes code
        │
        ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  GitHub Actions  │────▶│  Orchestrator    │────▶│  AgentCore      │
│  (trigger)       │     │  (Lambda/script) │     │  Harness        │
└─────────────────┘     └──────────────────┘     │  "ui-test-agent"│
                                                   └────────┬────────┘
                                                            │
                              ┌──────────────────────────────┼──────────────────────────────┐
                              │                              │                               │
                              ▼                              ▼                               ▼
                    ┌─────────────────┐          ┌─────────────────┐            ┌─────────────────┐
                    │  1. UNDERSTAND   │          │  2. EXECUTE      │            │  3. REPORT       │
                    │  - Load test plan│          │  - Browse UI     │            │  - Compare       │
                    │  - Recall memory │          │  - Click/Type    │            │  - Classify      │
                    │  - Plan sequence │          │  - Screenshot    │            │  - Generate JSON │
                    └─────────────────┘          │  - Observe       │            │  - Self-reflect  │
                                                  └─────────────────┘            └────────┬────────┘
                                                                                          │
                              ┌────────────────────────────────────────────────────────────┤
                              │                              │                              │
                              ▼                              ▼                              ▼
                    ┌─────────────────┐          ┌─────────────────┐            ┌─────────────────┐
                    │  4. LEARN        │          │  5. HANDOFF      │            │  6. NOTIFY       │
                    │  - Store patterns│          │  - trigger_fix   │            │  - PR comment    │
                    │  - Update memory │          │    _agent        │            │  - Slack/Teams   │
                    │  - Refine methods│          │  - Pass evidence │            │  - Dashboard     │
                    └─────────────────┘          └─────────────────┘            └─────────────────┘
```

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              TRIGGER LAYER                                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐    │
│  │ GitHub Actions│   │ Admin Portal │   │  Scheduled   │   │  API Gateway │    │
│  │ (PR trigger) │   │ (manual run) │   │  (cron/EB)   │   │ (webhook)    │    │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘    │
│         └──────────────────┬┴──────────────────┴──────────────────┘             │
│                            ▼                                                     │
└────────────────────────────┬─────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────────────────────┐
│                         ORCHESTRATION LAYER                                       │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                    AWS Step Functions                                     │    │
│  │                                                                           │    │
│  │  ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐             │    │
│  │  │ Fan-out │──▶│ Invoke   │──▶│ Collect  │──▶│ Aggregate│             │    │
│  │  │ (split  │   │ Harness  │   │ Reports  │   │ & Notify │             │    │
│  │  │  tests) │   │ (parallel│   │          │   │          │             │    │
│  │  └─────────┘   │ sessions)│   └──────────┘   └──────────┘             │    │
│  │                 └──────────┘                                             │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                   │
└────────────────────────────┬─────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────────────────────┐
│                         EXECUTION LAYER (AgentCore Harness)                        │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                 │
│  │  Session A       │  │  Session B       │  │  Session N       │                 │
│  │  (Login tests)   │  │  (Cart tests)    │  │  (Checkout tests)│                 │
│  │                   │  │                   │  │                   │                 │
│  │  ┌────┐ ┌─────┐ │  │  ┌────┐ ┌─────┐ │  │  ┌────┐ ┌─────┐ │                 │
│  │  │ 🌐 │ │ 🐍  │ │  │  │ 🌐 │ │ 🐍  │ │  │  │ 🌐 │ │ 🐍  │ │                 │
│  │  │Brws│ │Code │ │  │  │Brws│ │Code │ │  │  │Brws│ │Code │ │                 │
│  │  └────┘ └─────┘ │  │  └────┘ └─────┘ │  │  └────┘ └─────┘ │                 │
│  │  ┌────┐ ┌─────┐ │  │  ┌────┐ ┌─────┐ │  │  ┌────┐ ┌─────┐ │                 │
│  │  │ 🧠 │ │ 💾  │ │  │  │ 🧠 │ │ 💾  │ │  │  │ 🧠 │ │ 💾  │ │                 │
│  │  │Mem │ │File │ │  │  │Mem │ │File │ │  │  │Mem │ │File │ │                 │
│  │  └────┘ └─────┘ │  │  └────┘ └─────┘ │  │  └────┘ └─────┘ │                 │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘                 │
│         (isolated Firecracker microVMs)                                           │
└────────────────────────────┬─────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────────────────────┐
│                         OUTPUT LAYER                                               │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐    │
│  │ Test Reports │   │ PR Comments  │   │ Bug-Fix Agent│   │ Admin Portal │    │
│  │ (S3/JSON)    │   │ (GitHub API) │   │ (downstream) │   │ (dashboard)  │    │
│  └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘    │
│                                                                                   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Trigger Mechanisms

### 1. CI/CD Trigger (Primary — GitHub Actions)

```yaml
# .github/workflows/ui-test.yml
on:
  pull_request:
    paths: ['src/frontend/**', 'src/components/**', '*.tsx', '*.css']

jobs:
  ui-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy preview
        run: npm run deploy:preview
      - name: Run UI Test Agent
        run: |
          python app/ui-test-agent/invoke.py \
            --harness-arn ${{ secrets.HARNESS_ARN }} \
            --url ${{ steps.deploy.outputs.preview_url }} \
            --test-suite pr-regression \
            --test-cases "Login flow" "Navigation" "Form validation" \
            --repo ${{ github.repository }} \
            --branch ${{ github.head_ref }}
      - name: Post results to PR
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            // Read report and post as PR comment
```

**When:** Developer pushes front-end code to a PR
**What:** Deploys preview → runs agent → posts results as PR comment
**Block merge:** If any CRITICAL or HIGH severity failures

### 2. Admin Portal Trigger (Manual)

```
POST /api/test-runs
{
  "target_url": "https://staging.example.com",
  "test_suite": "full-regression",
  "triggered_by": "qa-lead@company.com"
}
```

**When:** QA lead wants to run a specific test suite on demand
**What:** Admin portal calls orchestrator API → invokes harness

### 3. Scheduled Trigger (Cron)

```yaml
# EventBridge rule: run nightly regression
{
  "schedule": "cron(0 2 * * ? *)",
  "target": "arn:aws:lambda:...:ui-test-orchestrator",
  "input": {
    "target_url": "https://staging.example.com",
    "test_suite": "nightly-full-regression"
  }
}
```

**When:** Every night at 2 AM UTC
**What:** Full regression suite against staging

### 4. Webhook Trigger (External)

```
POST /api/webhook/test
Headers: X-Webhook-Secret: <secret>
{
  "event": "deployment_complete",
  "environment": "staging",
  "url": "https://staging.example.com",
  "commit_sha": "abc123"
}
```

**When:** External deployment system notifies that a new version is live
**What:** Triggers smoke test suite

---

## Code Interpreter Integration

### Why the agent needs code execution

Browser interaction alone is not enough for high-quality QA. Many test verifications need precise computation that an LLM cannot reliably do in its head:

- **JSON / response payload comparison** — diff two API responses to find which field changed
- **Numerical assertions** — does cart total match the sum of line items + tax + shipping (with rounding)?
- **Date and time math** — was the "expires in 24h" badge calculated correctly?
- **Pixel-level layout checks** — extract bounding-box coordinates from screenshots and assert geometry
- **Test report generation** — produce structured JSON / Markdown reports deterministically
- **Statistical roll-ups** — aggregate pass / fail rates across runs

Doing these via prompt-only reasoning is unreliable: the model can hallucinate calculations or report inconsistent numbers between runs. Running them through Code Interpreter gives a **deterministic, auditable execution path** in a sandbox.

### Wiring in the agent

`app/ui-test-agent/main.py` registers Code Interpreter as a Strands tool:

```python
from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreterClient
from strands import tool

REGION = os.environ.get("AWS_REGION", "us-east-1")
code_interpreter = CodeInterpreterClient(region=REGION)

@tool
def execute_code(code: str, language: str = "python") -> str:
    """Execute code in a secure sandbox.

    Use for calculations, data analysis, report generation, and comparisons.
    """
    try:
        result = code_interpreter.execute(code=code, language=language)
        return result.get("output", "") or result.get("error", "No output")
    except Exception as e:
        return f"Code execution error: {str(e)}"

# Registered alongside Browser, file tools, MCP clients
tools = [browser_tool.browser, execute_code, file_read, file_write, list_files]
```

The agent's system prompt tells it explicitly when to reach for this tool:

> Use code interpreter for data analysis, JSON generation, and calculations.

### Sandbox properties

| Property | Value |
|---|---|
| Isolation | Firecracker microVM (hardware-level), separate from the agent's own VM |
| Languages supported | Python (default), JavaScript, TypeScript |
| Filesystem | Ephemeral; resets per session unless attached to Session Storage / EFS / S3 Files |
| Network egress | Disabled by default; can be enabled for fetching external data |
| Persistent state | None across `execute()` calls unless the agent saves to mounted storage |
| Pre-installed libraries | Standard Python stdlib + common data libs (pandas, numpy, json) |
| Failure mode | Errors returned as a string; no exception leaks to the agent |

### Use cases in this project

| Use case | Example code the agent might run |
|---|---|
| Compare expected vs actual JSON | `json.loads(actual) == json.loads(expected)` |
| Roll up pass / fail counts | `pass_count = sum(1 for t in tests if t['status']=='PASS')` |
| Generate Markdown report | Format test results into a structured `report.md` |
| Calculate cart totals | `sum(line_items) * (1 + tax_rate) + shipping == cart_total` |
| Decode encoded form values | `urllib.parse.parse_qs(form_data)` |

### When NOT to use Code Interpreter

- **Trivial arithmetic** the model can do reliably in prose (e.g. "is 5 > 3?")
- **String matching** that a regex in the system prompt can express
- **Anything the Browser tool can do directly** — don't write JavaScript via Code Interpreter to click an element when `browser.click()` exists

The agent's per-iteration cost is much lower without spinning up a sandbox call, so reserve it for genuinely deterministic-compute tasks.

### Cost characteristics

- ~$0.001 per session-second (see [Cost Model](#cost-model))
- Typical UI Test Agent usage: 30–60 seconds total per test run, contributing ~$0.03 of the ~$0.32 per-run cost
- Cold start of a fresh microVM is included; reuse of an active session is faster

---

## Agent Guardrails & Safety

### Defense-in-Depth Model

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: INPUT GUARDRAILS                                   │
│  - URL allowlist (only staging/dev, never production)        │
│  - Test case validation (reject malicious prompts)           │
│  - Max test cases per run (prevent resource exhaustion)      │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│  Layer 2: EXECUTION GUARDRAILS                               │
│  - maxIterations: 100 (hard cap on reasoning loops)          │
│  - timeoutSeconds: 1800 (30 min max per run)                 │
│  - maxTokens: 32768 (budget cap)                             │
│  - allowedTools: explicit whitelist (no wildcard)            │
│  - Network: VPC with egress restricted to target URLs        │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│  Layer 3: BEHAVIORAL GUARDRAILS (System Prompt)              │
│  - Never modify the application under test                   │
│  - Never submit real payment or PII data                     │
│  - Never navigate away from the target domain                │
│  - Never execute destructive actions (delete, drop)          │
│  - Stop and escalate if uncertain (request_human_review)     │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│  Layer 4: OUTPUT GUARDRAILS                                  │
│  - Report schema validation before output                    │
│  - Screenshot sanitization (redact PII if detected)          │
│  - Severity classification review (prevent false CRITICALs)  │
│  - Human review gate for ambiguous results                   │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│  Layer 5: INFRASTRUCTURE GUARDRAILS                          │
│  - Firecracker microVM isolation (no cross-session access)   │
│  - IAM least-privilege execution role                        │
│  - Session storage scoped (no persistent data leakage)       │
│  - CloudWatch alarms on anomalous behavior                   │
└─────────────────────────────────────────────────────────────┘
```

### URL Allowlist Implementation

```python
# In orchestrator — validate before invoking harness
ALLOWED_DOMAINS = [
    "staging.example.com",
    "dev.example.com",
    "preview-*.example.com",
]

def validate_target_url(url: str) -> bool:
    from urllib.parse import urlparse
    import fnmatch
    host = urlparse(url).hostname
    return any(fnmatch.fnmatch(host, pattern) for pattern in ALLOWED_DOMAINS)
```

### Behavioral Guardrails in System Prompt

Added to system prompt:
```
Safety Rules (NEVER violate):
- NEVER navigate outside the target domain
- NEVER submit forms with real credit card numbers, SSNs, or PII
- NEVER click "Delete", "Drop", "Destroy" buttons unless explicitly in the test plan
- NEVER modify application state that cannot be easily reversed
- If you encounter a login wall, use ONLY the test credentials from environment variables
- If you are unsure whether an action is safe, call request_human_review BEFORE acting
- If you detect you are on a production URL (no "staging", "dev", "preview" in hostname), STOP immediately
```

### Anomaly Detection

Monitor via CloudWatch:
- **Token usage spike** → possible infinite loop → auto-terminate
- **Session duration > 80% of timeout** → warn orchestrator
- **Repeated identical actions** → possible stuck state → escalate
- **Navigation to unexpected domain** → security alert → terminate

---

## Self-Learning & Memory Architecture

### Learning Loop

The agent continuously improves through a structured learning cycle:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SELF-LEARNING LOOP                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐     │
│  │ EXECUTE  │───▶│ REFLECT  │───▶│ EXTRACT  │───▶│  STORE   │     │
│  │          │    │          │    │          │    │          │     │
│  │ Run test │    │ Analyze  │    │ Identify │    │ Save to  │     │
│  │ cases    │    │ what went│    │ patterns │    │ long-term│     │
│  │          │    │ well/bad │    │ & methods│    │ memory   │     │
│  └──────────┘    └──────────┘    └──────────┘    └────┬─────┘     │
│       ▲                                                │           │
│       │          ┌──────────┐    ┌──────────┐         │           │
│       │          │ GENERALIZE│◀──│  RECALL  │◀────────┘           │
│       │          │          │    │          │                      │
│       └──────────│ Apply to │    │ Retrieve │                      │
│                  │ new cases│    │ relevant │                      │
│                  │ (举一反三)│    │ experience│                      │
│                  └──────────┘    └──────────┘                      │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Memory Architecture (4 Layers)

```
┌─────────────────────────────────────────────────────────────────┐
│                     MEMORY LAYERS                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Layer 1: SHORT-TERM MEMORY (within session)             │    │
│  │  - Current test plan and progress                        │    │
│  │  - Screenshots taken this session                        │    │
│  │  - Errors encountered this run                           │    │
│  │  - Decisions made and reasoning                          │    │
│  │  Lifetime: Single session                                │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Layer 2: EPISODIC MEMORY (cross-session)                │    │
│  │  - "Last time I tested login, the submit button was      │    │
│  │    unresponsive due to z-index CSS conflict"             │    │
│  │  - "The cart page always loads slowly on first visit"    │    │
│  │  - "Form validation errors appear after 500ms delay"    │    │
│  │  Lifetime: 30 days (configurable)                        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Layer 3: SEMANTIC MEMORY (permanent knowledge)          │    │
│  │  - Testing patterns: "SPA route changes don't trigger    │    │
│  │    full page reload — wait for content, not navigation"  │    │
│  │  - Known issues: "React hydration causes brief flash"    │    │
│  │  - Best methods: "For dropdown menus, click trigger      │    │
│  │    first, then wait for aria-expanded=true"              │    │
│  │  Lifetime: Permanent (until explicitly removed)          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Layer 4: REFLECTIVE MEMORY (meta-learning)              │    │
│  │  - Patterns extracted from multiple episodes:            │    │
│  │    "When element not found after click, check if a       │    │
│  │     modal overlay is blocking — 70% of the time this     │    │
│  │     is the root cause"                                   │    │
│  │  - Method refinements:                                   │    │
│  │    "For date pickers, using keyboard input is more       │    │
│  │     reliable than clicking calendar UI (learned from     │    │
│  │     3 failures across different frameworks)"             │    │
│  │  Lifetime: Permanent, periodically refined               │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Self-Reflection Protocol

After each test run, the agent performs a structured self-reflection:

```
REFLECTION PROMPT (appended after test execution):

Now reflect on this test run:

1. WHAT WENT WELL?
   - Which test cases passed smoothly?
   - What interaction patterns worked reliably?

2. WHAT WENT WRONG?
   - Which actions failed or were unexpected?
   - What was the root cause?
   - Could you have predicted this from prior experience?

3. WHAT DID YOU LEARN?
   - New patterns discovered (e.g., "this framework renders async")
   - New failure modes (e.g., "toast notifications block click targets")
   - Better methods (e.g., "wait for network idle before asserting")

4. GENERALIZATION (举一反三)
   - Can this learning apply to other test cases?
   - Can this pattern predict future issues?
   - What similar scenarios should you watch for?

Store your learnings as structured knowledge for future sessions.
```

### Memory Storage Implementation

```python
# How learnings are stored in AgentCore Memory

# Episodic: specific events
{
    "namespace": "/episodes/{actorId}/{sessionId}/",
    "content": "Login test TC-002 failed because error handler returned 500 instead of 401. Root cause: backend missing null check on user.message property.",
    "metadata": {"test_case": "TC-002", "app": "example.com", "date": "2026-05-16"}
}

# Semantic: permanent knowledge
{
    "namespace": "/knowledge/{actorId}/patterns/",
    "content": "When testing error handling flows, always verify both the HTTP status code AND the error message content. Backend may return correct status but wrong message body.",
    "metadata": {"source": "TC-002 failure analysis", "confidence": 0.9}
}

# Reflective: meta-patterns
{
    "namespace": "/knowledge/{actorId}/methods/",
    "content": "For SPA applications using React Router, navigation between routes does not trigger page load events. Use browser_wait_for with text content instead of URL change to confirm navigation.",
    "metadata": {"derived_from": ["session-abc", "session-def", "session-ghi"], "success_rate": 0.95}
}
```

### Learning Triggers

| Trigger | What Gets Stored | Memory Layer |
|---------|-----------------|--------------|
| Test case FAILS | Failure details + root cause analysis | Episodic |
| Agent retries an action successfully | "Retry pattern X works for situation Y" | Semantic |
| Same failure occurs 3+ times | Generalized pattern + prevention method | Reflective |
| Agent discovers new interaction method | Method description + when to apply | Semantic |
| Agent encounters unknown UI component | Component behavior + how to interact | Semantic |
| Test suite pass rate improves | What changed + why it helped | Reflective |

### Generalization Engine (举一反三)

The agent generalizes from specific experiences to broader principles:

```
SPECIFIC EXPERIENCE:
  "On example.com, the dropdown menu required clicking the trigger,
   waiting 200ms, then clicking the option. Direct click on option failed."

GENERALIZED PATTERN:
  "Dropdown menus with CSS transitions require a wait between trigger
   click and option click. The wait duration equals the CSS transition
   duration (check computed styles)."

APPLICATION TO NEW CASES:
  - Accordion menus (same transition pattern)
  - Tooltip hovers (same timing issue)
  - Modal open animations (same wait requirement)
  - Tab switching with fade effects (same pattern)
```

### Memory Retrieval at Test Start

Before executing any test, the agent retrieves relevant memories:

```python
# Automatic retrieval (configured in harness memory)
# retrievalConfig with topK=10, relevanceScore=0.3

# The agent receives context like:
"""
Relevant past experiences for this test:
1. [Episodic] Last run on example.com/login: submit button had z-index issue
2. [Semantic] SPA navigation: wait for content, not URL change
3. [Reflective] Form validation: always test both client-side and server-side
4. [Semantic] React apps: hydration causes brief content flash, wait 500ms
"""
```

---

## Scaling Strategy

### How to Run Many Agents in Parallel

```
┌─────────────────────────────────────────────────────────────┐
│              Step Functions Fan-Out Pattern                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Input: 50 test cases                                        │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────┐                                            │
│  │   Splitter   │  Split into groups of 5-10 cases          │
│  └──────┬──────┘                                            │
│         │                                                    │
│    ┌────┼────┬────┬────┬────┐                               │
│    ▼    ▼    ▼    ▼    ▼    ▼                               │
│  ┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐  Each = 1 Harness session │
│  │S1 ││S2 ││S3 ││S4 ││S5 ││S6 │  (independent microVM)    │
│  └─┬─┘└─┬─┘└─┬─┘└─┬─┘└─┬─┘└─┬─┘                          │
│    └────┬┴────┴────┴────┴────┘                              │
│         ▼                                                    │
│  ┌─────────────┐                                            │
│  │  Aggregator  │  Merge reports, calculate overall metrics  │
│  └─────────────┘                                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Scaling Dimensions

| Dimension | Method | Limit |
|-----------|--------|-------|
| **Concurrent sessions** | Each `invoke_harness` with unique `runtimeSessionId` | Service quota (request increase) |
| **Test cases per session** | Split large suites into groups | 5-10 cases per session optimal |
| **Parallel test suites** | Step Functions Map state | 100+ concurrent executions |
| **Cross-region** | Deploy harness in multiple regions | 4 preview regions available |

### Cost at Scale

| Scale | Sessions | Est. Cost/Run | Time |
|-------|----------|---------------|------|
| Small (10 tests) | 1-2 | $0.15-0.30 | 5 min |
| Medium (50 tests) | 5-10 | $0.75-1.50 | 5 min (parallel) |
| Large (200 tests) | 20-40 | $3.00-6.00 | 8 min (parallel) |
| Enterprise (1000 tests) | 100-200 | $15-30 | 10 min (parallel) |

### Session Grouping Strategy

```python
# Optimal grouping: related tests in same session (shares browser state)
groups = {
    "login-flow": ["Login valid", "Login invalid", "Forgot password", "MFA"],
    "cart-flow": ["Add item", "Remove item", "Update quantity", "Apply coupon"],
    "checkout-flow": ["Address form", "Payment form", "Order confirmation"],
}
# Each group = 1 harness session, all groups run in parallel
```

---

## Agent Testing Strategy

### How to Test the Test Agent Itself

```
┌─────────────────────────────────────────────────────────────┐
│              AGENT TESTING PYRAMID                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│                    ┌─────────┐                               │
│                    │  E2E    │  Full agent against real app  │
│                   ┌┴─────────┴┐                              │
│                   │ Integration│  Agent + Browser + Memory   │
│                  ┌┴───────────┴┐                             │
│                  │  Golden Tests │  Known inputs → expected  │
│                 ┌┴─────────────┴┐    outputs                │
│                 │   Eval Framework │  LLM-as-Judge scoring   │
│                ┌┴───────────────┴┐                           │
│                │  Config Validation │  harness.json schema   │
│                └─────────────────┘                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 1. Golden Test Cases — design

Pre-built test app with known bugs → agent must find them:

```python
# Golden test: agent should detect the broken login
golden_tests = [
    {
        "app_url": "https://golden-test-app.internal/v1",  # App with known bug
        "test_case": "Login with invalid password shows error",
        "expected_agent_result": "FAIL",
        "expected_finding": "500 error instead of 401",
    },
    {
        "app_url": "https://golden-test-app.internal/v2",  # App with fixed bug
        "test_case": "Login with invalid password shows error",
        "expected_agent_result": "PASS",
    },
]
```

### 2. Evaluation Runner Implementation

The conceptual golden-tests pattern above is implemented concretely in `app/ui-test-agent/eval_runner.py`. It runs a fixed suite of 6 prompts against the deployed agent and verifies that the response contains expected keywords.

**Test definition format (from `eval_runner.py`):**

```python
GOLDEN_TESTS = [
    {
        "id": "GT-01",
        "prompt": "Navigate to https://the-internet.herokuapp.com/login. "
                  "Type 'tomsmith' in username, 'SuperSecretPassword!' in password, "
                  "click Login. Report PASS if redirected to /secure.",
        "expected_status": "PASS",
        "must_contain": ["secure", "logged in"],
    },
    # ... GT-02 through GT-06
]
```

The 6 golden tests cover:

| ID | Scenario | Verifies |
|---|---|---|
| GT-01 | Valid login | Agent can drive a happy-path login flow |
| GT-02 | Invalid login | Agent correctly reports an error message |
| GT-03 | Dropdown selection | Agent handles `<select>` elements |
| GT-04 | Broken images | Agent detects HTTP 4xx image responses |
| GT-05 | Dynamic loading | Agent waits for async content to appear |
| GT-06 | Add/remove elements | Agent handles dynamic DOM mutation |

**Validation approach (current):**

```python
def run_golden_tests(harness_arn: str, region: str = "us-east-1") -> dict:
    client = boto3.client("bedrock-agentcore", region_name=region)
    results = {"total": len(GOLDEN_TESTS), "passed": 0, "failed": 0, "details": []}

    for test in GOLDEN_TESTS:
        response = client.invoke_agent_runtime(
            agentRuntimeArn=harness_arn,
            runtimeSessionId=str(uuid.uuid4()),
            body=json.dumps({"prompt": test["prompt"]}).encode(),
        )
        # Stream response into a single string
        response_text = "".join(
            chunk.decode("utf-8", errors="ignore")
            for event in response.get("body", [])
            for chunk in [event.get("chunk", {}).get("bytes", b"")]
        )
        # Keyword-based pass/fail
        if any(kw in response_text.lower() for kw in test["must_contain"]):
            results["passed"] += 1
        else:
            results["failed"] += 1
    return results
```

**CI integration:**

```bash
python app/ui-test-agent/eval_runner.py --harness-arn "$RUNTIME_ARN"
# Exit code 0 if all pass, 1 if any fail (suitable for GitHub Actions)
```

**Limitations of the current approach:**

- **Keyword matching is brittle.** A response that says "login attempt secured by MFA" would falsely pass GT-01's `"secure"` keyword.
- **No semantic verification.** The runner cannot tell that the agent reasoned correctly — only that the right substring appeared.
- **No partial credit.** A test either fully passes or fully fails.

**Planned upgrade:** LLM-as-judge replacement that scores each response against the test's intent (1–5 scale) plus a structured rubric (correctness, evidence quality, severity classification). Tracked separately from this issue.

### 3. Regression Testing

After every agent update (prompt change, model change, skill update):
1. Run `eval_runner.py` against the deployed agent
2. Compare results to baseline
3. Alert if pass rate drops or false positives increase

---

## Admin Portal Design

### Scope

A web dashboard for QA leads and managers to manage the UI test agent fleet.

### Features

| Feature | Priority | Description |
|---------|----------|-------------|
| **Test Suite Manager** | P0 | CRUD test suites, define test cases, set acceptance criteria |
| **Run Dashboard** | P0 | View active/completed runs, pass rates, trends |
| **Manual Trigger** | P0 | Start a test run with one click |
| **Report Viewer** | P0 | View detailed reports with screenshots inline |
| **Schedule Manager** | P1 | Configure cron schedules for recurring tests |
| **Agent Memory Viewer** | P1 | See what the agent has learned, edit/delete memories |
| **Cost Dashboard** | P1 | Track spend per test suite, per team |
| **Comparison View** | P2 | Compare results across runs (regression detection) |
| **Agent Config Editor** | P2 | Edit system prompt, tools, limits without CLI |

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Admin Portal (React + Vite)                             │
│  - Test Suite Manager                                    │
│  - Run Dashboard                                         │
│  - Report Viewer (with screenshot gallery)               │
│  - Schedule Manager                                      │
│  - Memory Inspector                                      │
└────────────────────────┬────────────────────────────────┘
                         │ API calls
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Backend API (API Gateway + Lambda)                      │
│  - POST /test-runs (trigger)                             │
│  - GET  /test-runs (list)                                │
│  - GET  /test-runs/:id/report (get report)               │
│  - GET  /schedules (list schedules)                      │
│  - POST /schedules (create schedule)                     │
│  - GET  /memory (view agent memories)                    │
│  - DELETE /memory/:id (remove a memory)                  │
└────────────────────────┬────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  DynamoDB    │ │  AgentCore   │ │  S3          │
│  (runs,      │ │  Harness API │ │  (reports,   │
│   schedules) │ │  (invoke)    │ │   screenshots│
└──────────────┘ └──────────────┘ └──────────────┘
```

---

## Downstream Bug-Fix Agent

### Concept

When the UI Test Agent finds failures, it passes structured failure data to a Bug-Fix Agent that:
1. Reads the failure report (expected vs actual, console errors, screenshots)
2. Clones the repository and checks out the relevant branch
3. Analyzes the source code to identify the root cause
4. Proposes a fix and creates a PR
5. Re-triggers the UI Test Agent to verify the fix

### Architecture

```
UI Test Agent                    Bug-Fix Agent
     │                                │
     │  trigger_fix_agent             │
     │  {failures, repo, branch}      │
     ├───────────────────────────────▶│
     │                                │
     │                                ├── Clone repo
     │                                ├── Analyze failure + code
     │                                ├── Write fix
     │                                ├── Run unit tests
     │                                ├── Create PR
     │                                │
     │  Re-test the fix               │
     │◀───────────────────────────────┤
     │                                │
     ├── Run same test cases          │
     ├── Verify PASS                  │
     ├── Approve PR (if all pass)     │
     │                                │
```

### Bug-Fix Agent Harness Config (Preview)

```json
{
  "name": "bug-fix-agent",
  "model": {"bedrockModelConfig": {"modelId": "us.anthropic.claude-sonnet-4-5-20250514-v1:0"}},
  "systemPrompt": [{"text": "You are an expert frontend developer. Given test failure reports, analyze the code, identify root causes, and propose minimal fixes."}],
  "tools": [
    {"type": "agentcore_code_interpreter", "name": "code_interpreter"},
    {"type": "remote_mcp", "name": "github", "config": {"remoteMcp": {"url": "https://mcp.github.com/sse"}}}
  ],
  "maxIterations": 50,
  "timeoutSeconds": 900
}
```

The Bug-Fix Agent has been deployed in this project as `BugFixAgentHarness-<HARNESS_ID>`. The handoff from UI Test Agent to Bug-Fix Agent uses the [A2A protocol](#a2a-protocol--agent-to-agent-communication).

---

## A2A Protocol — Agent-to-Agent Communication

### What "A2A" means here

A2A (agent-to-agent) is the pattern of one agent invoking another agent **directly**, peer-to-peer, instead of going through an intermediate orchestrator (Step Functions / Lambda / SQS).

```
ORCHESTRATED HANDOFF                          A2A HANDOFF
────────────────────                          ───────────

  UI Test Agent                                UI Test Agent
        │                                            │
        │ emit failure event                         │ invoke_agent_runtime(
        ▼                                            │   target = Bug-Fix ARN,
  ┌─────────────┐                                    │   payload = failures
  │ Step Funcs  │                                    │ )
  │   /Lambda   │                                    │
  └─────┬───────┘                                    ▼
        │ invoke                                Bug-Fix Agent
        ▼
  Bug-Fix Agent

  + Easy retry / DLQ                          + Lower latency
  + Visible in workflow                       + No orchestrator infra
  + Buffers bursty traffic                    + Direct trust path
  − Extra cost & latency                      − Caller owns retries
                                              − No buffering
```

### Implementation in this project

`app/ui-test-agent/a2a_handoff.py` is a thin wrapper around `boto3.invoke_agent_runtime`:

```python
import boto3, json, os

REGION = os.environ.get("AWS_REGION", "us-east-1")
BUG_FIX_AGENT_ARN = os.environ.get("BUG_FIX_AGENT_ARN", "")

def trigger_fix_agent_a2a(
    failures: list[dict],
    repository_url: str = "",
    branch: str = "",
) -> dict:
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
```

The orchestrator (`e2e_pipeline.py`) calls `trigger_fix_agent_a2a()` after collecting failure data, and the Bug-Fix Agent (`BugFixAgentHarness-<HARNESS_ID>`) parses the JSON-encoded payload from its prompt to extract failures, repo URL, and branch.

### IAM trust model

For A2A to work, the **caller's** execution role must have `bedrock-agentcore:InvokeAgentRuntime` permission scoped to the **target's** ARN:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "bedrock-agentcore:InvokeAgentRuntime",
    "Resource": "arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:runtime/BugFixAgentHarness-<HARNESS_ID>"
  }]
}
```

Without this, the call fails with `AccessDenied`. Always scope `Resource` to specific target ARNs — never `*`.

### Recommended Cedar policy (when using Gateway)

If A2A is wired through AgentCore Gateway, scope it with Cedar:

```cedar
// UI Test Agent may invoke ONLY the Bug-Fix Agent, not other runtimes
permit(
  principal == AgentCore::Agent::"ui-test-agent",
  action == Action::"InvokeAgentRuntime",
  resource == AgentCore::Runtime::"BugFixAgentHarness-<HARNESS_ID>"
);

// Deny invocation of any agent that has write access to production repos
forbid(
  principal == AgentCore::Agent::"ui-test-agent",
  action == Action::"InvokeAgentRuntime",
  resource
) when {
  resource.tags.environment == "production"
};
```

### A2A vs orchestrator decision matrix

| Scenario | Use A2A | Use Step Functions / SQS |
|---|---|---|
| Synchronous handoff in same session | ✅ | |
| Need retry with backoff | | ✅ |
| Fan-out to many agents | | ✅ |
| Audit trail required (compliance) | | ✅ |
| Latency-sensitive (< 1s overhead) | ✅ | |
| Long-lived async workflow (hours/days) | | ✅ |
| Need DLQ for failures | | ✅ |
| Two-agent linear pipeline (this project) | ✅ | |

### Production considerations

- **Pass `runtimeSessionId`** when invoking — propagate the parent session ID so traces in CloudWatch/X-Ray correlate across agents.
- **Bound the payload size.** `invoke_agent_runtime` has request-size limits; for large failure dumps, write to S3 and pass a URI in the payload instead.
- **Idempotency.** If the caller retries, the target should detect duplicate `runtimeSessionId` + payload and not re-process. The target agent's prompt should explicitly say "if you've already started a fix for this exact failure set, return your previous result."
- **Circuit breaker.** Add a counter (e.g. CloudWatch metric) of consecutive A2A failures. After N failures, fall back to file-based handoff (write failure JSON to S3, file an issue manually) instead of invoking the target.
- **Audit logging.** Log every A2A call: caller, target ARN, session ID, payload hash, result. CloudTrail captures the API call automatically; supplement with structured app-level logs.

---

## Security Design

### Threat Model

| Threat | Mitigation |
|--------|-----------|
| Agent navigates to production | URL allowlist + system prompt guardrail + domain check in orchestrator |
| Agent submits real PII | System prompt prohibition + test data only in env vars |
| Prompt injection via UI content | Agent instructed to treat page content as data, not instructions |
| Cross-session data leakage | Firecracker microVM isolation (hardware-level) |
| Credential exposure in reports | Screenshots sanitized, credentials never in prompts |
| Runaway cost | Hard limits (maxIterations, timeout, maxTokens) + CloudWatch alarms |
| Unauthorized invocation | IAM dual-permission + optional OAuth inbound |
| Unauthorized A2A invocation | Caller IAM scoped to specific target ARN; Cedar policy when via Gateway |

### Data Flow Security

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│ Orchestrator │──SigV4──│  AgentCore  │──TLS───│  Target App │
│ (IAM auth)   │         │  Harness    │         │  (staging)  │
└─────────────┘         └─────────────┘         └─────────────┘
                              │
                              │ Encrypted at rest
                              ▼
                        ┌─────────────┐
                        │  Reports    │
                        │  (S3 + KMS) │
                        └─────────────┘
```

- All API calls: SigV4 or OAuth JWT
- All data in transit: TLS 1.2+
- Reports at rest: S3 with KMS encryption
- Memory at rest: AgentCore managed encryption
- No PII in test data: synthetic data only

---

## Cost Model

### Per-Component Pricing

| Component | Unit | Est. Cost |
|-----------|------|-----------|
| Claude Sonnet 4.5 (input) | per 1M tokens | $3.00 |
| Claude Sonnet 4.5 (output) | per 1M tokens | $15.00 |
| AgentCore Browser | per minute | ~$0.01 |
| AgentCore Code Interpreter | per session-second | ~$0.001 |
| AgentCore Memory | per 1K read/write | ~$0.001 |
| Step Functions | per state transition | $0.000025 |
| S3 (reports) | per GB/month | $0.023 |

### Typical Run Costs

| Scenario | Tokens (in/out) | Browser | Total |
|----------|----------------|---------|-------|
| 5 test cases, simple | 20K/5K | 3 min | ~$0.10 |
| 10 test cases, moderate | 50K/15K | 8 min | ~$0.35 |
| 20 test cases, complex | 120K/40K | 15 min | ~$1.00 |

### Monthly Budget Examples

| Team Size | Runs/Day | Monthly Cost | vs. Human QA |
|-----------|----------|--------------|--------------|
| Small (1 app) | 5 | ~$50 | Saves $8K/mo (1 QA) |
| Medium (5 apps) | 25 | ~$250 | Saves $40K/mo (5 QA) |
| Enterprise (20 apps) | 100 | ~$1,000 | Saves $160K/mo (20 QA) |

---

## AgentCore Gateway & Policy Integration

### Why Gateway

Instead of connecting directly to GitHub MCP with raw API keys, route through AgentCore Gateway for:
- **Credential rotation** — Gateway manages OAuth token refresh
- **Policy enforcement** — Cedar policies control what the agent can do
- **Audit trail** — Every tool call logged through Gateway
- **Access control** — Different agents get different permissions

### Gateway Configuration

```json
{
  "type": "agentcore_gateway",
  "name": "github-gateway",
  "config": {
    "agentCoreGateway": {
      "gatewayArn": "arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:gateway/github-gateway",
      "outboundAuth": {
        "oauth": {
          "credentialProviderName": "github-oauth-provider",
          "scopes": ["repo", "pull_requests:write"]
        }
      }
    }
  }
}
```

### Cedar Policies

**UI Test Agent — read-only access:**

```cedar
permit(
  principal == AgentCore::Agent::"ui-test-agent",
  action in [Action::"web_search", Action::"web_fetch"],
  resource
);

// Deny any write operations
forbid(
  principal == AgentCore::Agent::"ui-test-agent",
  action in [Action::"create_pull_request", Action::"push_files"],
  resource
);
```

**Bug-Fix Agent — scoped write access:**

```cedar
// Allow PR creation only on specific repos
permit(
  principal == AgentCore::Agent::"bug-fix-agent",
  action in [Action::"create_pull_request", Action::"push_files"],
  resource
) when {
  resource.repository in ["org/frontend-app", "org/backend-api"]
};

// Deny force push and branch deletion
forbid(
  principal == AgentCore::Agent::"bug-fix-agent",
  action in [Action::"delete_branch", Action::"force_push"],
  resource
);

// Deny access to main/production branches
forbid(
  principal == AgentCore::Agent::"bug-fix-agent",
  action == Action::"push_files",
  resource
) when {
  resource.branch in ["main", "master", "production"]
};
```

### Benefits

| Without Gateway | With Gateway |
|----------------|-------------|
| Raw API key in header | OAuth with auto-refresh |
| No access control | Cedar policies per agent |
| No audit trail | Every call logged |
| Agent can do anything | Scoped to specific repos/branches |
| Key rotation = redeploy | Key rotation = automatic |

---

## Entire Project Cost Estimation

### One-Time Setup Costs

| Item | Cost | Notes |
|------|------|-------|
| AgentCore Harness creation | $0 | No charge for creating the harness resource |
| IAM Role creation | $0 | Free |
| AgentCore CLI | $0 | Open source (npm) |
| GitHub repo | $0 | Free tier |
| GitHub Actions | $0 | 2,000 min/month free for public repos |

### Per-Run Costs (Single Test Suite)

| Component | Usage | Unit Price | Cost |
|-----------|-------|-----------|------|
| **Claude Sonnet 4.5 (input tokens)** | ~30K tokens | $3.00/1M | $0.09 |
| **Claude Sonnet 4.5 (output tokens)** | ~10K tokens | $15.00/1M | $0.15 |
| **AgentCore Browser** | ~5 min | ~$0.01/min | $0.05 |
| **AgentCore Code Interpreter** | ~30 sec | ~$0.001/sec | $0.03 |
| **AgentCore Memory (read/write)** | ~20 ops | ~$0.001/1K | $0.001 |
| **S3 (report storage)** | ~1 MB | $0.023/GB | $0.00003 |
| **Total per run** | | | **~$0.32** |

### Monthly Cost Scenarios

| Scenario | Runs/Day | Runs/Month | Monthly Cost | Notes |
|----------|----------|------------|--------------|-------|
| **Developer (solo)** | 2 | 60 | ~$20 | Manual + PR triggers |
| **Small team (5 devs)** | 10 | 300 | ~$100 | CI/CD on every PR |
| **Medium team (20 devs)** | 40 | 1,200 | ~$400 | CI/CD + nightly regression |
| **Enterprise (100 devs)** | 200 | 6,000 | ~$2,000 | Full automation + scheduled |

### Cost Comparison: Agent vs Human QA

| | UI Test Agent | Human QA Tester |
|---|---|---|
| **Hourly cost** | ~$0.32/run (5 min) = $3.84/hr equivalent | $50–100/hr |
| **Availability** | 24/7, instant | Business hours, scheduling needed |
| **Consistency** | 100% repeatable | Variable (fatigue, oversight) |
| **Scale** | 100+ parallel sessions | 1 person = 1 test at a time |
| **Monthly (medium team)** | ~$400 | ~$16,000 (2 QA × $8K) |
| **Annual savings** | | **~$187,000/year** |

### Cost Optimization Tips

| Tip | Savings |
|-----|---------|
| Use `--exec` for env setup (zero tokens) | ~10% per run |
| Group related tests in one session (share browser state) | ~20% per suite |
| Use Claude Haiku for simple validation checks | ~80% on those runs |
| Set `idleRuntimeSessionTimeout: 300` (5 min) | Reduce idle VM cost |
| Cache test plans in memory (avoid re-reading) | ~5% on repeat runs |

### AWS Free Tier Applicability

| Service | Free Tier | Applies? |
|---------|-----------|----------|
| Lambda (orchestrator) | 1M requests/month | ✅ Likely covered |
| DynamoDB (admin portal) | 25 GB + 25 WCU/RCU | ✅ Likely covered |
| S3 (reports) | 5 GB | ✅ Likely covered |
| CloudWatch (logs) | 5 GB ingest | ✅ Likely covered |
| AgentCore Harness | No free tier | ❌ Pay per use |
| Bedrock (model tokens) | No free tier | ❌ Pay per use |

### First Test Run Cost Estimate

For our initial deployment test against the-internet.herokuapp.com:
- 3 test cases (login, dropdown, add/remove elements)
- Estimated: ~$0.15–0.20
- Duration: ~3 minutes

---

*End of Architecture Document*
