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
8. **Hands off** failures to the Bug-Fix Agent for auto-remediation

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
  --harness-arn <ARN> \
  --url https://staging.example.com \
  --test-cases "Login with valid credentials" "Login with invalid password"
```

## Files

| File | Purpose |
|------|---------|
| `main.py` | Strands agent entry point (AgentCore Runtime) |
| `harness.json` | Harness declarative configuration |
| `invoke.py` | Orchestrator script (boto3, handles inline functions) |
| `deploy.sh` | One-command deployment |
| `skills/ui-testing/SKILL.md` | Domain knowledge for the agent |
| `memory/` | AgentCore Memory session manager |
| `model/` | Model loader configuration |

## Tools

| Tool | Type | Purpose |
|------|------|---------|
| Browser | AgentCore Browser (remote) | Navigate, click, type, scroll, hover, drag, screenshot |
| Code Interpreter | AgentCore Code Interpreter | Precise calculations, report generation, data comparison |
| Shell | Built-in | Environment setup, git, npm |
| File Operations | Built-in | Write test reports to /mnt/reports |
| `notify_test_complete` | Inline Function | Signal orchestrator |
| `request_human_review` | Inline Function | Escalate ambiguous results |
| `trigger_fix_agent` | Inline Function / A2A | Pass failures to Bug-Fix Agent |

## Additional Scripts

| Script | Purpose |
|--------|---------|
| `invoke.py` | Orchestrator (boto3, streaming, inline function handling) |
| `eval_runner.py` | 6 golden tests for agent validation |
| `a2a_handoff.py` | A2A protocol for Bug-Fix Agent communication |

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

~$0.32 per test suite run (5-10 test cases). See [Architecture](../../docs/ARCHITECTURE.md#entire-project-cost-estimation) for full breakdown.

## Test Results

32 tests executed | 31 PASS | 1 correct FAIL detection | 96.9% pass rate

See [Test Results](../../docs/TEST_RESULTS.md) for details.

## Documentation

- [Design Document](../../docs/DESIGN_UI_TEST_AGENT.md)
- [Architecture](../../docs/ARCHITECTURE.md)
- [Test Results](../../docs/TEST_RESULTS.md)
- [Testing the Agent](../../docs/TESTING_THE_AGENT.md)
