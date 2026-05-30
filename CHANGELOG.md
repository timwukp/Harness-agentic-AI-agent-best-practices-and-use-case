# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-05-30

A documentation-only release. No code or behaviour changes. Closes a 7-issue
audit (#2, #4, #6, #8, #10, #12, #14) that brought the doc set in sync with
the code that landed on 2026-05-16 and added a project-specific production-
hardening playbook.

### Added

- `docs/DEVELOPMENT_WORKFLOW.md` — issue → fix → PR methodology, templates, and naming conventions used in this audit (PR #3, issue #2)
- `docs/ARCHITECTURE.md §6 Code Interpreter Integration` — purpose, wiring code from `main.py`, sandbox properties, use cases, cost (PR #9, issue #8)
- `docs/ARCHITECTURE.md §13 A2A Protocol — Agent-to-Agent Communication` — orchestrated-vs-A2A diagram, code from `a2a_handoff.py`, IAM trust model, Cedar policy, decision matrix, production hardening (PR #9, issue #8)
- `docs/ARCHITECTURE.md §10.2 Evaluation Runner Implementation` (subsection) — golden tests structure, validation approach, CI integration, limitations, planned LLM-as-judge upgrade (PR #9, issue #8)
- `docs/BEST_PRACTICES.md §7 Browser Tool — Production Features` (EN) — profiles, session recording, Web Bot Auth (PR #11, issue #10)
- `docs/BEST_PRACTICES_zh-TW.md §7 Browser 工具 — 正式環境功能` (zh-TW) — mirror of the EN section (PR #11, issue #10)
- `docs/PRODUCTION_HARDENING.md` — project-specific design playbook for the six Priority 4 hardening items (Container deploy, S3 recording, profiles, Web Bot Auth, CloudWatch alarms, online eval), with sequencing recommendation, cost summary, and master validation checklist (PR #15, issue #14)
- Cross-references throughout the doc set linking the new sections together

### Changed

- `README.md` badges: `tests-32 passed` → `tests-35 passed`; `pass rate-96.9%` → `pass rate-94.3%`. Aligns with the body and architecture status table (PR #5, issue #4)
- `README.md` Documentation table: added rows for `Development Workflow` and `Production Hardening`
- `PROJECT_STATE.md`: synced TODO checkboxes with reality (Priority 2 A2A handoff and demo-frontend bug detection now `[x]` with commit SHAs); test results total updated to 35 / 33 PASS / 94.3% with new run #9 row; "Next Session TODO" replaced with "✅ E2E Pipeline Verification — Complete" status table; new "Current Open Work" section tracking the v0.2.1 audit issues; Bug-Fix Agent Harness `BugFixAgentHarness-<HARNESS_ID>` added to Deployed Resources (PR #7, issue #6; further updates in PR #15, issue #14)
- `docs/DESIGN_UI_TEST_AGENT.md`: rewrote Tools table, System Prompt, Architecture diagram, Invocation Patterns, and Downstream Integration to match the actual `main.py` Strands Runtime implementation (custom `@tool` functions, `invoke_agent_runtime` not `invoke_harness`, real A2A handoff). Added "Validation & E2E Pipeline" subsection covering `eval_runner.py` and `e2e_pipeline.py`. Cost estimate harmonized to ~$0.32/run (PR #13, issue #12)
- `app/ui-test-agent/README.md`: Test Results updated to 35 / 33 PASS / 94.3%. Files table extended with `eval_runner.py`, `a2a_handoff.py`, `e2e_pipeline.py`, `deploy_harness.py`, `mcp_client/`, `pyproject.toml`, `screenshots/`. Tools table replaced with actual wiring from `main.py`. Added "Bug-Fix Agent handoff (A2A)" subsection. Quick Start updated with eval and e2e examples (PR #13, issue #12)
- `VERSION`: `0.2.0` → `0.2.1` (this PR)

### Fixed

- `PROJECT_STATE.md`: removed the duplicated `### Priority 4: Production Hardening` section that appeared twice with identical content (PR #7, issue #6)
- `docs/DESIGN_UI_TEST_AGENT.md`: removed three fictitious inline-function references (`notify_test_complete`, `request_human_review`, `trigger_fix_agent` as inline-function) that were design intent but never implemented in code. Bug-Fix handoff now correctly described as A2A (PR #13, issue #12)
- Internal cross-references between doc files now resolve consistently (every "see ARCHITECTURE.md §N" / "see BEST_PRACTICES.md §N" link points to a section that actually exists)

### Documentation (audit PR list, for traceability)

| Issue | PR | Topic |
|-------|----|-------|
| #2 | #3 | DEVELOPMENT_WORKFLOW.md (methodology) |
| #4 | #5 | README badges 32→35, 96.9%→94.3% |
| #6 | #7 | PROJECT_STATE.md TODO sync, duplicate Priority 4 removal |
| #8 | #9 | ARCHITECTURE.md §6 Code Interpreter, §10.2 Eval Runner, §13 A2A |
| #10 | #11 | BEST_PRACTICES.md §7 Browser features (EN + zh-TW) |
| #12 | #13 | DESIGN_UI_TEST_AGENT.md and app/ui-test-agent/README.md sync |
| #14 | #15 | PRODUCTION_HARDENING.md design playbook |
| #16 | #17 | This release PR (VERSION + CHANGELOG bump) |

## [0.2.0] - 2026-05-16

### Added
- AgentCore Browser tool integration (real UI interaction: click, type, scroll, screenshot)
- AgentCore Code Interpreter tool (`execute_code` for sandboxed Python)
- A2A protocol module (`a2a_handoff.py`) for UI Test Agent → Bug-Fix Agent communication
- Evaluation runner (`eval_runner.py`) with 6 golden test cases
- AgentCore Gateway + Cedar Policy design (docs/ARCHITECTURE.md)
- Complete project cost estimation
- Admin Portal design (docs/ADMIN_PORTAL.md)
- Agent testing strategy (docs/TESTING_THE_AGENT.md)
- CI/CD workflow (.github/workflows/ui-test.yml)
- PROJECT_STATE.md for context continuity

### Changed
- main.py rewritten with Browser + Code Interpreter + self-reflection prompt
- invoke.py rewritten with proper tool result handling and conversation loop
- deploy.sh made idempotent with version display
- System prompt updated for UI testing methodology

### Fixed
- Inline function handling (now properly returns tool results to continue conversation)
- Added runtimeClientError handling in invoke.py
- Added max_turns safety limit to prevent infinite loops
- .gitignore updated to exclude agentcore/.cache/

### Test Results
- Run #1: 3/3 PASS (static verification, deployed)
- Run #2: 8/8 PASS (static verification, deployed)
- Run #3: 1/1 PASS (browser login flow, local)
- Run #4: 3/3 PASS (browser: login + dropdown + add_remove, local)

## [0.1.0] - 2026-05-16

### Added
- Initial project structure
- Best Practices guide (English + Chinese)
- UI Test Agent design document
- Harness configuration (`harness.json`) with Browser, Code Interpreter, and 3 inline functions
- Orchestrator invoke script (`invoke.py`) with streaming and inline function handling
- Deployment script (`deploy.sh`)
- UI Testing skill (`SKILL.md`) with methodology, severity classification, and edge cases
- Version management (VERSION, CHANGELOG.md)
