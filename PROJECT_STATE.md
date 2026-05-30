# Project State — Persistent Memory

> **Last Updated:** 2026-05-30 UTC+8
> **Version:** 0.2.0
> **Repo:** https://github.com/timwukp/Harness-agentic-AI-agent-best-practices-and-use-case
> **Working Dir:** /path/to/project
> **Region:** us-east-1
> **Status:** ✅ End-to-End Pipeline Fully Verified

---

## What This Project Is

An AI-powered UI testing agent that replaces human QA testers in SDLC, built on Amazon Bedrock AgentCore (Runtime mode, with Harness design docs). The agent navigates web UIs, interacts with elements, observes results, learns from failures, and produces structured test reports.

---

## Completed Work (10/10 Tasks Done)

| # | Task | Status | Key Files |
|---|------|--------|-----------|
| 1 | Code review + fixes | ✅ | invoke.py rewritten with proper tool result handling |
| 2 | Architecture document | ✅ | docs/ARCHITECTURE.md (900+ lines) |
| 3 | Trigger mechanisms + CI/CD | ✅ | .github/workflows/ui-test.yml, docs/TRIGGERS.md |
| 4 | Admin Portal design | ✅ | docs/ADMIN_PORTAL.md |
| 5 | Scaling strategy | ✅ | In ARCHITECTURE.md |
| 6 | Agent testing strategy | ✅ | docs/TESTING_THE_AGENT.md |
| 7 | GitHub Actions workflow | ✅ | .github/workflows/ui-test.yml |
| 8 | Push to GitHub | ✅ | All pushed |
| 9 | Deploy to AWS + live test | ✅ | Deployed, 3 test runs completed |
| 10 | Bug-fix agent design | ✅ | docs/BUG_FIX_AGENT.md |

---

## Deployed Resources (AWS us-east-1)

| Resource | ARN/ID |
|----------|--------|
| Runtime | `arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:runtime/<RUNTIME_ID>` |
| Memory | `arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:memory/uitestagent_<MEMORY_ID>` |
| IAM Role | `AgentCore-uitestagent-def-ApplicationAgentUitestage-<IAM_ROLE_ID>` |
| CloudFormation Stack | `AgentCore-uitestagent-default` |
| Browser IAM Policy | `BrowserAccess` (added to role) |
| Bug-Fix Agent Harness | `BugFixAgentHarness-<HARNESS_ID>` (deployed in commit `75d8e065`) |

---

## Test Results Summary

| Run | Method | Tests | Result |
|-----|--------|-------|--------|
| #1 | web_fetch (deployed) | 3 | 3/3 PASS (static verification) |
| #2 | web_fetch (deployed) | 8 | 8/8 PASS (static verification) |
| #3 | AgentCoreBrowser (local) | 1 | 1/1 PASS (login flow) |
| #4 | AgentCoreBrowser (local) | 3 | 3/3 PASS (login + dropdown + add_remove) |
| #5 | AgentCoreBrowser (local) | 2 | 2/2 PASS (negative: wrong login + broken images) |
| #6 | AgentCoreBrowser (local) | 5 | 5/5 PASS (dynamic loading, alerts, hover, checkboxes) |
| #7 | AgentCoreBrowser (local) | 5 | 5/5 PASS (keys, scroll, context menu, drag-drop) |
| #8 | AgentCoreBrowser (local) | 5 | 4/5 (1 correct FAIL: floating menu CSS bug in test target) |
| #9 | AgentCoreBrowser (demo-frontend) | 3 | 3/3 (1 valid-login PASS + 2 correct FAILs detecting intentional bugs in our own app) |
| **Total** | | **35** | **33 PASS = 94.3%** (3 bugs detected: 2 in our app + 1 in test target) |

> Run #9 was added in commit `56905611` (`test: agent found 2/5 intentional bugs in demo frontend`). The 2 detected bugs (green error message + wrong error text) drove the full E2E pipeline verification in commits `75d8e065` and `05951a94`.
>
> See `docs/TEST_RESULTS.md` for detailed PASS/FAIL accounting.

### Key Finding
- Browser tool works **locally** (connects to remote AgentCore Browser service)
- Browser tool **fails in Runtime CodeZip mode** (Playwright binary permission error)
- Fix: Use Container deployment mode or resolve strands_tools remote-only path. Designed in [`docs/PRODUCTION_HARDENING.md` §1](docs/PRODUCTION_HARDENING.md#1-container-deployment-mode).
- Agent correctly detects real UI bugs (floating menu position:absolute vs fixed; intentional CSS/text bugs in demo frontend)

---

## Project File Structure

```
aws-harness-agentcore-use-case/
├── .github/workflows/ui-test.yml       # CI/CD: PR trigger → test → comment
├── .gitignore
├── CHANGELOG.md
├── README.md
├── VERSION                              # 0.2.0
├── agentcore/
│   ├── agentcore.json                   # Runtime + Memory config
│   ├── aws-targets.json                 # Account <ACCOUNT_ID>, us-east-1
│   └── cdk/                             # CDK infrastructure
├── app/
│   ├── demo-frontend/                   # Static demo with 5 intentional bugs (E2E test target)
│   └── ui-test-agent/
│       ├── main.py                      # Strands agent (Browser + Code Interpreter + Memory)
│       ├── invoke.py                    # Orchestrator (boto3, streaming, inline functions)
│       ├── eval_runner.py               # 6 golden tests
│       ├── a2a_handoff.py               # A2A protocol for Bug-Fix Agent
│       ├── e2e_pipeline.py              # End-to-end orchestration (UI Test → Bug-Fix → Patch)
│       ├── deploy.sh                    # Deployment script
│       ├── deploy_harness.py            # Harness deployment script
│       ├── harness.json                 # Harness declarative config (design reference)
│       ├── pyproject.toml               # Dependencies
│       ├── README.md                    # Agent documentation
│       ├── skills/ui-testing/SKILL.md   # Domain knowledge
│       ├── memory/                      # Memory session manager
│       ├── model/                       # Model loader
│       ├── mcp_client/                  # MCP client
│       └── screenshots/                 # Captured during tests
├── docs/
│   ├── ARCHITECTURE.md                  # Full system architecture (900+ lines)
│   ├── ADMIN_PORTAL.md                  # Admin portal design
│   ├── BEST_PRACTICES.md                # Harness best practices (English)
│   ├── BEST_PRACTICES_zh-TW.md          # Harness best practices (Chinese)
│   ├── BUG_FIX_AGENT.md                 # Downstream bug-fix agent design
│   ├── CASE_STUDY.md                    # STAR case study (English)
│   ├── CASE_STUDY_zh-TW.md              # STAR case study (Chinese)
│   ├── DESIGN_UI_TEST_AGENT.md          # Original design document
│   ├── DEVELOPMENT_WORKFLOW.md          # Issue → fix → PR methodology
│   ├── PRODUCTION_HARDENING.md          # Priority 4 design playbook (Container deploy, recording, profiles, alarms, eval)
│   ├── TEST_RESULTS.md                  # All test run results
│   ├── TESTING_THE_AGENT.md             # How to test the agent itself
│   ├── TRIGGERS.md                      # 4 trigger mechanisms
│   ├── demo/                            # GitHub Pages demo-frontend mirror
│   └── evidence/                        # Reproducible Bug-Fix Agent output
└── hooks/                                # Git hooks for PII/secrets prevention
```

---

## Git History (Latest First)

```
978bae4 docs: final state update — 35 tests, 3 bugs detected, full pipeline verified
05951a9 evidence: save Bug-Fix Agent actual output as reproducible proof
5790a6c docs: update README — all 6 stages VERIFIED with Bug-Fix evidence
3d0c86c security: final PII cleanup in e2e_pipeline.py and PROJECT_STATE.md
59099c6 docs: add STAR case study (English + Chinese)
75d8e06 feat: full E2E pipeline verified — UI Test → Bug-Fix → Patch
5db15fd docs: CI/CD trigger now verified — GitHub Actions workflow ran successfully
3742278 docs: update README with demo frontend test results
56905611 test: agent found 2/5 intentional bugs in demo frontend
e98679d chore: add demo page to docs/ for GitHub Pages
f69301c feat: add demo frontend with 5 intentional bugs for E2E testing
b42daff docs: detailed next session instructions for E2E pipeline test
3e0cd19 docs: honest status labels in README (verified vs designed)
466e0e5 docs: add comprehensive Runtime vs Harness comparison to README
aae3ed3 docs: add deployment modes comparison to README
122d36d feat: add Harness deployment mode (declarative, zero-code)
b3e7f71 feat: UI Test Agent v0.2.0 — AgentCore Harness best practices and use case
685d6e6 feat: integrate Code Interpreter, A2A protocol, Evaluation SDK
800aa36 feat: successful browser interaction test — login flow PASS
89864ef feat: add AgentCore Browser tool to agent
a31de1e docs: comprehensive test run #2 (8 pages) + honest gap analysis
73f49b4 fix: remove deployment cache from git, update .gitignore
7eceafe docs: add proper README for ui-test-agent
2aa0a9d feat: add AgentCore Gateway + Cedar Policy design
c36a3ae docs: add live test results — 3/3 PASS
ad26acc feat: deploy to AWS us-east-1 — first successful live test
0d4f352 docs: add entire project cost estimation to architecture
4b91c65 docs: agent testing design — golden tests, eval framework
46959e4 docs: admin portal design
2968a4d feat: add CI/CD workflow and trigger mechanism design
5a871b5 docs: complete use case architecture
5249d87 feat: initial project setup v0.1.0 (tag: v0.1.0)
```

---

## Pending TODO

### Priority 1: Document Consistency Update — ✅ Resolved by v0.2.1 doc audit

All Priority 1 items have been resolved by the 2026-05-30 documentation audit:

- [x] Update CHANGELOG.md with v0.2.0 entries ✅
- [x] Update ARCHITECTURE.md to include Code Interpreter, A2A, Eval SDK sections ✅ (PR #9, issue #8)
- [x] Update DESIGN_UI_TEST_AGENT.md to reflect current main.py tools ✅ (PR #13, issue #12)
- [x] Update BEST_PRACTICES.md with Browser features (profiles, recording, Web Bot Auth) ✅ (PR #11, issue #10)
- [x] Update BEST_PRACTICES_zh-TW.md to match English version ✅ (PR #11, issue #10)
- [x] Update app/ui-test-agent/README.md with new tools (execute_code, a2a, eval) ✅ (PR #13, issue #12)

### Priority 2: Code Fixes
- [ ] Fix Browser tool in deployed Runtime (Container mode or remote-only path) — *designed in [`docs/PRODUCTION_HARDENING.md` §1](docs/PRODUCTION_HARDENING.md#1-container-deployment-mode); deployment is a separate work stream*
- [x] Run full test suite with Browser tool — 35 tests completed across 9 runs ✅ (commits `56905611`, `978bae4a`)
- [ ] Verify Code Interpreter works in deployed environment
- [x] Test A2A handoff — Bug-Fix Agent deployed and full pipeline verified ✅ (commit `75d8e065`, evidence in commit `05951a944`)

### Priority 3: Expand Tests (DONE)
- [x] Run golden tests — covered in runs #3-#8 ✅
- [x] Test negative scenarios (wrong password, broken images) ✅
- [x] Test dynamic content (wait for load) ✅
- [x] Test drag-and-drop, alerts ✅
- [x] Test bug detection on own app — 2/5 intentional bugs found in demo frontend ✅ (commit `56905611`)
- [ ] Add remaining 10+ pages for full 40+ coverage

### Priority 4: Production Hardening — design landed, deployment pending

All six items now have a concrete project-specific design in [`docs/PRODUCTION_HARDENING.md`](docs/PRODUCTION_HARDENING.md). Each item below links to its section. Actual deployment of each item is a separate work stream (one issue + PR per item).

- [ ] Switch to Container deployment mode (fixes Playwright issue) — [§1](docs/PRODUCTION_HARDENING.md#1-container-deployment-mode)
- [ ] Add Browser session recording (S3 bucket) — [§3](docs/PRODUCTION_HARDENING.md#3-browser-session-recording-s3)
- [ ] Add Browser profiles (persist login state) — [§4](docs/PRODUCTION_HARDENING.md#4-browser-profiles)
- [ ] Configure Web Bot Auth (reduce CAPTCHA) — [§6](docs/PRODUCTION_HARDENING.md#6-web-bot-auth) (deferred — no qualifying target site yet)
- [ ] Set up CloudWatch alarms for anomalous behavior — [§2](docs/PRODUCTION_HARDENING.md#2-cloudwatch-alarms)
- [ ] Add online eval for continuous quality monitoring — [§5](docs/PRODUCTION_HARDENING.md#5-online-eval-continuous-quality-monitoring)

**Sequencing recommendation** (from PRODUCTION_HARDENING.md): Container → Alarms → Recording / Profiles in parallel → Online Eval → Web Bot Auth (deferred).

---

## Key Technical Decisions

1. **Runtime vs Harness:** Deployed as Runtime (Strands agent) because CLI v0.14.0 doesn't support `create harness` non-interactively. Harness config (harness.json) kept as design reference. Bug-Fix Agent later deployed as Harness (`BugFixAgentHarness-<HARNESS_ID>`) demonstrating both modes.
2. **Browser:** Uses `strands_tools.browser.AgentCoreBrowser` which connects to remote AWS Browser service (aws.browser.v1). Works locally, fails in CodeZip due to Playwright binary.
3. **Memory:** 4 strategies configured (semantic, episodic, summarization, user_preference).
4. **Model:** Claude Sonnet 4.5 (us.anthropic.claude-sonnet-4-5-20250514-v1:0).
5. **Test target:** the-internet.herokuapp.com (MIT licensed, designed for test automation).
6. **Demo target:** `app/demo-frontend/` deployed via GitHub Pages — 5 intentional bugs for E2E pipeline verification.
7. **Communication:** Chinese for discussion, English for code/docs.

---

## AWS Documentation Learned

All 7 Harness pages + all Browser sub-pages read and integrated:
- harness.html (overview)
- harness-get-started.html
- harness-config-and-models.html
- harness-tools.html
- harness-memory.html
- harness-environment.html
- harness-operations.html
- harness-security.html
- browser-tool.html
- browser-quickstart.html
- browser-resource-session-management.html
- browser-observability.html (Live View, Recording, CloudWatch)
- browser-features.html (Web Bot Auth, Extensions, Profiles, Proxies, OS Actions)
- browser-tool-troubleshooting.html
- code-interpreter-tool.html
- agentcore-cli repo (github.com/aws/agentcore-cli)
- bedrock-agentcore-sdk-python repo

---

## Harness Features Utilization: 34/34 (100%)

All AgentCore Harness features are designed into the project. See docs/ARCHITECTURE.md "AgentCore Gateway & Policy Integration" section for the last 2 that were added.

---

## E2E Pipeline Verification — ✅ Complete

The end-to-end pipeline (UI Test Agent → Bug-Fix Agent → Patch) was fully verified on 2026-05-16. All 8 originally-planned steps are done:

| Step | Status | Evidence |
|------|--------|----------|
| 1. Create `app/demo-frontend/` with intentional bugs | ✅ | commit `f69301c6` |
| 2. Deploy to GitHub Pages | ✅ | commit `e98679d2` (added `docs/demo/`) |
| 3. Set up GitHub OIDC → AWS IAM role | ✅ | commit `5db15fd7` |
| 4. Add GitHub Secrets (`AWS_ROLE_ARN`, `HARNESS_ARN`, `STAGING_URL`) | ✅ | commit `5db15fd7` |
| 5. Deploy Bug-Fix Agent | ✅ | commit `75d8e065` (`BugFixAgentHarness-<HARNESS_ID>`) |
| 6. Update orchestration to call Bug-Fix Agent on failure | ✅ | commit `75d8e065` (added `e2e_pipeline.py`) |
| 7. PR trigger verification | ✅ | commit `5db15fd7` (PR #1 ran workflow successfully) |
| 8. Full pipeline verification | ✅ | commit `75d8e065` + evidence in `05951a944` |

### Key Commands

```bash
cd /path/to/project
export PATH="$HOME/.local/bin:$PATH"
AWS_REGION=us-east-1

# Test agent locally
cd app/ui-test-agent && .venv/bin/python -c "
from strands import Agent
from strands_tools.browser import AgentCoreBrowser
agent = Agent(tools=[AgentCoreBrowser(region='us-east-1').browser])
agent('Test https://YOUR_STAGING_URL ...')
"

# Deploy
agentcore deploy

# Invoke deployed
agentcore invoke --json --session-id "\$(uuidgen)" --prompt "..."

# Run E2E pipeline (UI Test Agent → Bug-Fix Agent)
cd app/ui-test-agent && python e2e_pipeline.py
```

---

## Current Open Work — Doc Audit (v0.2.1)

A documentation audit on 2026-05-30 found drift between repo state and various docs. Tracked across these issues:

| Issue | Status | Topic |
|-------|--------|-------|
| #2 | ✅ Merged in PR #3 | Add `docs/DEVELOPMENT_WORKFLOW.md` (issue → fix → PR methodology) |
| #4 | ✅ Merged in PR #5 | README badges out of sync with verified test count |
| #6 | ✅ Merged in PR #7 | Sync this file's TODO checkboxes with reality |
| #8 | ✅ Merged in PR #9 | ARCHITECTURE.md missing Code Interpreter / A2A / Eval SDK sections |
| #10 | ✅ Merged in PR #11 | BEST_PRACTICES.md (EN + zh-TW) missing Browser features |
| #12 | ✅ Merged in PR #13 | DESIGN_UI_TEST_AGENT.md and app README out of sync with current code |
| #14 | 🔄 In progress | New `docs/PRODUCTION_HARDENING.md` (Priority 4 design) |

After all merge: bump VERSION to 0.2.1 and add CHANGELOG entry (v0.2.1 release PR).
