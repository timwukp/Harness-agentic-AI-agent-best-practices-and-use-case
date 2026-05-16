# Project State — Persistent Memory

> **Last Updated:** 2026-05-16T21:46 UTC+8  
> **Version:** 0.2.0  
> **Repo:** https://github.com/timwukp/Harness-agentic-AI-agent-best-practices-and-use-case  
> **Working Dir:** /path/to/project  
> **AWS Account:** <ACCOUNT_ID> (user: <USERNAME>)  
> **Region:** us-east-1

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
| IAM Role | `AgentCore-uitestagent-def-ApplicationAgentUitestage-mzobm0YQRR1k` |
| CloudFormation Stack | `AgentCore-uitestagent-default` |
| Browser IAM Policy | `BrowserAccess` (added to role) |

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
| #8 | AgentCoreBrowser (local) | 5 | 4/5 (1 correct FAIL: floating menu CSS bug) |
| **Total** | | **32** | **31 PASS + 1 correct FAIL = 96.9%** |

### Key Finding
- Browser tool works **locally** (connects to remote AgentCore Browser service)
- Browser tool **fails in Runtime CodeZip mode** (Playwright binary permission error)
- Fix: Use Container deployment mode or resolve strands_tools remote-only path
- Agent correctly detects real UI bugs (floating menu position:absolute vs fixed)

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
├── app/ui-test-agent/
│   ├── main.py                          # Strands agent (Browser + Code Interpreter + Memory)
│   ├── invoke.py                        # Orchestrator (boto3, streaming, inline functions)
│   ├── eval_runner.py                   # 6 golden tests
│   ├── a2a_handoff.py                   # A2A protocol for Bug-Fix Agent
│   ├── deploy.sh                        # Deployment script
│   ├── harness.json                     # Harness declarative config (design reference)
│   ├── pyproject.toml                   # Dependencies
│   ├── README.md                        # Agent documentation
│   ├── skills/ui-testing/SKILL.md       # Domain knowledge
│   ├── memory/                          # Memory session manager
│   ├── model/                           # Model loader
│   ├── mcp_client/                      # MCP client
│   └── screenshots/                     # Captured during tests
└── docs/
    ├── ARCHITECTURE.md                  # Full system architecture (900+ lines)
    ├── ADMIN_PORTAL.md                  # Admin portal design
    ├── BEST_PRACTICES.md                # Harness best practices (English)
    ├── BEST_PRACTICES_zh-TW.md          # Harness best practices (Chinese)
    ├── BUG_FIX_AGENT.md                 # Downstream bug-fix agent design
    ├── DESIGN_UI_TEST_AGENT.md          # Original design document
    ├── TEST_RESULTS.md                  # All test run results
    ├── TESTING_THE_AGENT.md             # How to test the agent itself
    └── TRIGGERS.md                      # 4 trigger mechanisms
```

---

## Git History (Latest First)

```
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

### Priority 1: Document Consistency Update
- [x] Update CHANGELOG.md with v0.2.0 entries ✅
- [ ] Update ARCHITECTURE.md to include Code Interpreter, A2A, Eval SDK sections
- [ ] Update DESIGN_UI_TEST_AGENT.md to reflect current main.py tools
- [ ] Update BEST_PRACTICES.md with Browser features (profiles, recording, Web Bot Auth)
- [ ] Update BEST_PRACTICES_zh-TW.md to match English version
- [ ] Update app/ui-test-agent/README.md with new tools (execute_code, a2a, eval)

### Priority 2: Code Fixes
- [ ] Fix Browser tool in deployed Runtime (Container mode or remote-only path)
- [x] Run full test suite with Browser tool — 32 tests completed ✅
- [ ] Verify Code Interpreter works in deployed environment
- [ ] Test A2A handoff (needs Bug-Fix Agent deployed)

### Priority 3: Expand Tests (DONE)
- [x] Run golden tests — covered in runs #3-#8 ✅
- [x] Test negative scenarios (wrong password, broken images) ✅
- [x] Test dynamic content (wait for load) ✅
- [x] Test drag-and-drop, alerts ✅
- [ ] Add remaining 10+ pages for full 40+ coverage

### Priority 4: Production Hardening
- [ ] Switch to Container deployment mode (fixes Playwright issue)
- [ ] Add Browser session recording (S3 bucket)
- [ ] Add Browser profiles (persist login state)
- [ ] Configure Web Bot Auth (reduce CAPTCHA)
- [ ] Set up CloudWatch alarms for anomalous behavior
- [ ] Add online eval for continuous quality monitoring

### Priority 4: Production Hardening
- [ ] Switch to Container deployment mode (fixes Playwright issue)
- [ ] Add Browser session recording (S3 bucket)
- [ ] Add Browser profiles (persist login state)
- [ ] Configure Web Bot Auth (reduce CAPTCHA)
- [ ] Set up CloudWatch alarms for anomalous behavior
- [ ] Add online eval for continuous quality monitoring

---

## Key Technical Decisions

1. **Runtime vs Harness:** Deployed as Runtime (Strands agent) because CLI v0.14.0 doesn't support `create harness` non-interactively. Harness config (harness.json) kept as design reference.
2. **Browser:** Uses `strands_tools.browser.AgentCoreBrowser` which connects to remote AWS Browser service (aws.browser.v1). Works locally, fails in CodeZip due to Playwright binary.
3. **Memory:** 4 strategies configured (semantic, episodic, summarization, user_preference).
4. **Model:** Claude Sonnet 4.5 (us.anthropic.claude-sonnet-4-5-20250514-v1:0).
5. **Test target:** the-internet.herokuapp.com (MIT licensed, designed for test automation).
6. **Communication:** Chinese for discussion, English for code/docs.

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

## Next Session TODO: End-to-End Pipeline Test

1. Create a simple frontend app with an intentional CSS bug (similar to floating menu)
2. Deploy to GitHub Pages or S3
3. Set up GitHub OIDC → AWS IAM role for GitHub Actions
4. Configure GitHub Secrets (HARNESS_ARN, AWS_ROLE_ARN, STAGING_URL)
5. Deploy Bug-Fix Agent as second Harness
6. Wire UI Test Agent → Bug-Fix Agent via A2A or inline function
7. Push frontend code to PR → trigger full pipeline
8. Verify: agent finds bug → triggers fix agent → fix agent creates PR → re-test passes
