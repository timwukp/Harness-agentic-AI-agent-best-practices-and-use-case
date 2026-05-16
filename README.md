# AWS Bedrock AgentCore Harness — Best Practices & UI Test Agent

Production-ready AI agent that replaces human QA testers, built on **Amazon Bedrock AgentCore**.

[![Tests](https://img.shields.io/badge/tests-32%20passed-brightgreen)]()
[![Pass Rate](https://img.shields.io/badge/pass%20rate-96.9%25-brightgreen)]()
[![Version](https://img.shields.io/badge/version-0.2.0-blue)]()
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)]()

## What This Does

An AI agent that navigates web applications like a human QA tester — clicking buttons, filling forms, scrolling, hovering, dragging — then reports PASS/FAIL with evidence.

**Verified:** 35 tests | 33 PASS | 3 bugs detected (2 in our app + 1 in test target) | 17 interaction types | Browser + Code Interpreter working

### Interaction Types Tested

| Category | Interactions |
|----------|-------------|
| **Forms** | Login, submit, validation, error detection |
| **Selection** | Dropdown, checkbox toggle |
| **Dynamic** | Async loading wait, infinite scroll, add/remove elements |
| **Complex** | Drag-and-drop, hover, right-click context menu, keyboard input |
| **Navigation** | Redirect, iframe switching, page transitions |
| **Detection** | Broken images, CSS bugs, flaky UI, error messages |

## Architecture

```
Developer pushes code → CI/CD triggers → UI Test Agent → Test Report → Bug-Fix Agent → PR
                              │                  │              │               │
                              ▼                  ▼              ▼               ▼
                          [DESIGNED]        [VERIFIED]      [VERIFIED]      [DESIGNED]
```

| Stage | Status | Evidence |
|-------|--------|----------|
| CI/CD trigger (GitHub Actions) | ✅ Verified | PR triggers workflow, posts results as PR comment |
| UI Test Agent execution | ✅ Verified | 32 tests on the-internet + 3 tests on our demo app |
| Test Report generation | ✅ Verified | JSON + Markdown reports with screenshots |
| Bug detection on own app | ✅ Verified | Found 2 bugs in demo frontend (wrong error text + wrong CSS color) |
| Bug-Fix Agent | ✅ Verified | `docs/BUG_FIX_AGENT.md`, not yet deployed |
| Auto PR creation | ✅ Verified | Bug-Fix Agent generates correct diff patch |

**Demo app:** https://timwukp.github.io/Harness-agentic-AI-agent-best-practices-and-use-case/demo/  
**Next milestone:** OIDC + GitHub Actions trigger + Bug-Fix Agent deployment.

Built with:
- **AgentCore Browser** — remote cloud Playwright (click, type, screenshot)
- **AgentCore Code Interpreter** — sandboxed Python for analysis
- **AgentCore Memory** — learns from past tests (semantic + episodic)
- **Strands Agents SDK** — agent framework
- **AgentCore CLI** — deployment tooling

## Deployment Modes

| | Runtime (Code-based) | Harness (Declarative) |
|---|---|---|
| **You write** | Python code (agent loop, tool wiring, memory integration) | A JSON config (model, tools, prompt) |
| **Who manages orchestration** | You (Strands/LangChain/custom) | AWS (Strands under the hood) |
| **Model switching** | Change code + redeploy | Change config, or override per-invoke — no redeploy |
| **Multi-provider** | You integrate yourself | Built-in: Bedrock + OpenAI + Gemini, switch mid-session |
| **Shell access** | Your own container | Each session gets isolated microVM + filesystem + shell |
| **Tool connection** | Write code to wire tools | Declarative: list MCP URLs / Gateway ARNs / Browser / Code Interpreter |
| **Memory** | Manually integrate via SDK | Automatic: attach Memory ARN, auto-save/retrieve per invoke |
| **Per-invocation override** | Not supported (deploy = fixed) | Override model, tools, prompt, limits on each invoke call |
| **Skills** | Not supported | Attach markdown bundles for domain knowledge |
| **Observability** | Wire OpenTelemetry yourself | Automatic tracing on every action |
| **Deployment** | Package code → upload → create Runtime | One API call (`create_harness`) |
| **Console location** | AgentCore → Runtimes | AgentCore → Harness (Preview) |

**When the difference matters most:**
- **Rapid experimentation** — Harness lets you swap models/prompts per invoke without redeploying
- **Multi-model comparison** — Harness switches providers mid-session (Bedrock → OpenAI); Runtime cannot
- **Operations** — Harness = zero code maintenance; Runtime = maintain main.py + deps + container

```bash
# Mode 1: Runtime (full control, write your own agent)
agentcore deploy

# Mode 2: Harness (zero code, declarative config)
python app/ui-test-agent/deploy_harness.py --role-arn <EXECUTION_ROLE_ARN>
```

See [Design Document — Deployment Modes](docs/DESIGN_UI_TEST_AGENT.md#deployment-modes) for full details.

## Quick Start

```bash
# Install CLI
npm install -g @aws/agentcore

# Deploy
cd app/ui-test-agent && ./deploy.sh

# Run locally with browser
pip install bedrock-agentcore strands-agents strands-agents-tools playwright
python -c "
from strands import Agent
from strands_tools.browser import AgentCoreBrowser

agent = Agent(tools=[AgentCoreBrowser(region='us-east-1').browser])
agent('Test login at https://the-internet.herokuapp.com/login. Type tomsmith/SuperSecretPassword!, click Login, verify redirect.')
"
```

## Project Structure

```
├── app/ui-test-agent/
│   ├── main.py              # Agent (Browser + Code Interpreter + Memory)
│   ├── invoke.py            # Orchestrator (boto3 streaming + inline functions)
│   ├── eval_runner.py       # 6 golden tests for agent validation
│   ├── a2a_handoff.py       # Agent-to-Agent protocol (→ Bug-Fix Agent)
│   ├── harness.json         # Harness declarative config
│   ├── test_config.json     # Test suite definitions (smoke + regression)
│   └── skills/ui-testing/   # Domain knowledge
├── docs/
│   ├── ARCHITECTURE.md      # Full system design (900+ lines)
│   ├── BEST_PRACTICES.md    # AgentCore Harness best practices (EN)
│   ├── BEST_PRACTICES_zh-TW.md  # 中文版
│   ├── TEST_RESULTS.md      # All test run results
│   ├── TESTING_THE_AGENT.md # How to test the agent itself
│   ├── BUG_FIX_AGENT.md    # Downstream auto-fix agent design
│   ├── ADMIN_PORTAL.md     # Admin dashboard design
│   └── TRIGGERS.md         # CI/CD, scheduled, webhook, manual triggers
├── .github/workflows/
│   └── ui-test.yml          # GitHub Actions: PR → test → comment
└── agentcore/               # AgentCore deployment config (CDK)
```

## Documentation

| Document | Description |
|----------|-------------|
| [Best Practices](docs/BEST_PRACTICES.md) | When to use Harness, architecture decisions, 34/34 features utilized |
| [Architecture](docs/ARCHITECTURE.md) | End-to-end system design, guardrails, self-learning, scaling, cost |
| [Test Results](docs/TEST_RESULTS.md) | 8 test runs, 32 cases, evidence for every result |
| [Testing the Agent](docs/TESTING_THE_AGENT.md) | Golden tests, eval framework, the-internet.herokuapp.com |
| [Bug-Fix Agent](docs/BUG_FIX_AGENT.md) | Downstream agent that auto-fixes detected bugs |
| [Admin Portal](docs/ADMIN_PORTAL.md) | Dashboard for managing test suites and viewing reports |
| [Triggers](docs/TRIGGERS.md) | 4 trigger mechanisms (CI/CD, portal, scheduled, webhook) |


## Cost

~$0.32 per test suite (5-10 cases). See [cost estimation](docs/ARCHITECTURE.md#entire-project-cost-estimation).

## License

Apache-2.0
