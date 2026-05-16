# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
