# UI Test Agent

AI-powered QA tester that replaces human testers in the SDLC. Built on Amazon Bedrock AgentCore.

## What It Does

1. **Understands** test specifications and acceptance criteria
2. **Navigates** web applications using cloud browser
3. **Interacts** with UI elements (click, type, scroll, hover)
4. **Observes** results, console errors, network responses
5. **Evaluates** actual vs expected outcomes (PASS/FAIL/BLOCKED)
6. **Reports** structured JSON + Markdown test reports
7. **Learns** from failures and improves over time
8. **Hands off** failures to the Bug-Fix Agent for auto-remediation (via A2A)

## Quick Start

```bash
# Deploy
cd ../../
agentcore deploy

# Test interactively
agentcore dev

# Run a test
agentcore invoke --session-id "$(uuidgen)" \
  "Test the login page at https://the-internet.herokuapp.com/login"

# Programmatic invocation
python invoke.py \
  --runtime-arn <ARN> \
  --url https://staging.example.com \
  --test-cases "Login with valid credentials" "Login with invalid password"

# Run regression / golden tests after any agent change
python eval_runner.py --harness-arn <ARN>

# Run full E2E pipeline (UI Test → Bug-Fix → patch)
python e2e_pipeline.py
```

## Files

| File | Purpose |
|------|---------|
| `main.py` | Strands agent entry point (AgentCore Runtime, deployed mode) |
| `invoke.py` | Orchestrator script (boto3, streaming, inline function handling) |
| `eval_runner.py` | 6 golden tests for agent regression validation |
| `a2a_handoff.py` | A2A protocol — direct invocation of the Bug-Fix Agent |
| `e2e_pipeline.py` | Full pipeline orchestration: UI Test → A2A → Bug-Fix → patch |
| `harness.json` | Harness declarative configuration (design reference, not the deployed mode for this agent) |
| `deploy.sh` | One-command Runtime deployment |
| `deploy_harness.py` | One-command Harness deployment (used for the Bug-Fix Agent in this project) |
| `pyproject.toml` | Python dependencies |
| `skills/ui-testing/SKILL.md` | Domain knowledge for the agent |
| `memory/` | AgentCore Memory session manager |
| `model/` | Model loader configuration |
| `mcp_client/` | Streamable HTTP MCP client wiring |
| `screenshots/` | Captured during local test runs |

## Tools (actual wiring in `main.py`)

| Tool | Source | Purpose |
|------|--------|---------|
| **Browser** | `strands_tools.browser.AgentCoreBrowser` | Navigate, click, type, scroll, hover, drag, screenshot — connects to remote AgentCore Browser service |
| **execute_code** | Custom `@tool` wrapping `bedrock_agentcore.tools.code_interpreter_client.CodeInterpreterClient` | Run Python in a sandboxed microVM for comparisons, calculations, report generation |
| **file_read** | Custom `@tool` (path-restricted to `/mnt/reports/`) | Read a file under session storage |
| **file_write** | Custom `@tool` (path-restricted to `/mnt/reports/`) | Write a file under session storage |
| **list_files** | Custom `@tool` (path-restricted to `/mnt/reports/`) | List directory contents under session storage |
| **MCP Client** | Streamable HTTP, `mcp_client/client.py` | Optional pluggable external integrations |

The four `file_*` tools enforce a `_safe_resolve` boundary so the agent cannot read or write outside `/mnt/reports/`.

### Bug-Fix Agent handoff (A2A)

`a2a_handoff.py` calls `invoke_agent_runtime` against `BUG_FIX_AGENT_ARN` (env var) when the orchestrator decides to escalate failures. This is the **A2A protocol** documented in [docs/ARCHITECTURE.md §13](../../docs/ARCHITECTURE.md#a2a-protocol--agent-to-agent-communication) — a direct peer-to-peer invocation, not an inline function or orchestrator middleman.

## Memory

- **Short-term:** Current session test progress
- **Episodic:** Past test runs, failure history
- **Semantic:** Testing patterns, known issues, best methods
- **Reflective:** Generalized patterns (举一反三)

## Limits

| Parameter | Value | Reason |
|-----------|-------|--------|
| maxIterations | 100 | UI testing needs many browser interactions |
| timeoutSeconds | 1800 | 30 min max per suite |
| maxTokens | 32768 | Screenshots + reports need larger context |

## Cost

~$0.32 per test suite run (5–10 test cases). See [Architecture — Entire Project Cost Estimation](../../docs/ARCHITECTURE.md#entire-project-cost-estimation) for the full breakdown.

## Test Results

35 tests | 33 PASS | 3 bugs detected (2 in our app + 1 in test target) | 94.3% pass rate

See [TEST_RESULTS.md](../../docs/TEST_RESULTS.md) for the per-run breakdown.

## Documentation

- [Design Document](../../docs/DESIGN_UI_TEST_AGENT.md) — this agent's design and tool wiring
- [Architecture](../../docs/ARCHITECTURE.md) — the wider system (Code Interpreter §6, Eval Runner §10.2, A2A §13)
- [Best Practices (EN)](../../docs/BEST_PRACTICES.md) — Harness best practices, including Browser production features (§7)
- [Best Practices (中文)](../../docs/BEST_PRACTICES_zh-TW.md) — same content, 繁體中文
- [Test Results](../../docs/TEST_RESULTS.md) — per-run pass/fail logs
- [Testing the Agent](../../docs/TESTING_THE_AGENT.md) — how to test the agent itself
- [Bug-Fix Agent](../../docs/BUG_FIX_AGENT.md) — downstream auto-fix agent (A2A target)
- [Development Workflow](../../docs/DEVELOPMENT_WORKFLOW.md) — issue → fix → PR methodology for changes
