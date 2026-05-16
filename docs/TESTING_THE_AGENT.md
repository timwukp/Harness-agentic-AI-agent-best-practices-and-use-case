# Testing the UI Test Agent — Design Document

> **Version:** 0.2.0  
> **Status:** Design

---

## Purpose

This document defines how we validate that the UI Test Agent itself works correctly. The agent is our QA tool — but who tests the tester?

---

## Test Target: the-internet.herokuapp.com

### What Is It

A purpose-built demo web application designed for automated testing practice.

| Item | Detail |
|------|--------|
| **URL** | https://the-internet.herokuapp.com |
| **Author** | Dave Haeffner (Selenium community leader) |
| **Source Code** | https://github.com/saucelabs/the-internet |
| **Maintainer** | Sauce Labs (acquired the project) |
| **Hosting** | Heroku (Salesforce PaaS) |
| **License** | MIT |
| **Community Usage** | Thousands of Selenium/Playwright tutorials worldwide |

### Why We Use It

1. **Designed for test automation** — explicit purpose is to be tested by bots
2. **Known behaviors** — every page has documented expected behavior
3. **No legal risk** — MIT licensed, intended for public automated access
4. **No real data** — test credentials are public (`tomsmith` / `SuperSecretPassword!`)
5. **Diverse UI patterns** — login, dropdowns, drag-and-drop, dynamic content, alerts, frames
6. **Stable** — maintained since 2015, widely relied upon
7. **Free** — no API keys or accounts needed

### Risk Assessment

| Risk | Level | Mitigation |
|------|-------|-----------|
| Site goes offline (Heroku cold start) | 🟡 Low | Retry logic; agent marks tests BLOCKED if site unavailable |
| Site changes behavior without notice | 🟡 Low | Our golden tests detect this; we update expected results |
| Legal/ToS violation | 🟢 None | Site explicitly designed for automated testing |
| Data privacy | 🟢 None | No real PII; test credentials are public |
| Our agent causes harm to the site | 🟢 None | Read-only interactions; no destructive actions |
| Heroku blocks our IP | 🟡 Low | AgentCore Browser uses AWS IPs; unlikely to be blocked |

### Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| the-internet.herokuapp.com | Free, stable, diverse UI patterns | Third-party dependency | ✅ Use for initial validation |
| Self-hosted test app | Full control, custom scenarios | Requires maintenance | Phase 2 |
| Production staging | Real business logic | Risk of side effects | Phase 3 (with guardrails) |

---

## Agent Testing Strategy

### Testing Pyramid

```
                    ┌─────────┐
                    │  E2E    │  Agent vs real site (the-internet)
                   ┌┴─────────┴┐
                   │ Golden Tests│  Known inputs → known outputs
                  ┌┴───────────┴┐
                  │  Eval (LLM)  │  LLM-as-Judge quality scoring
                 ┌┴─────────────┴┐
                 │  Config Valid.  │  harness.json schema check
                 └───────────────┘
```

### Level 1: Configuration Validation

Verify `harness.json` is valid before deployment:

```bash
agentcore validate
```

Checks:
- JSON schema valid
- Model ID exists in Bedrock
- Tool types are recognized
- allowedTools references valid tool names
- Limits are within service quotas

### Level 2: LLM-as-Judge Evaluation

```bash
agentcore add evaluator --name ui-test-quality \
  --criteria "Did the agent correctly identify all intentional bugs?" \
  --criteria "Are screenshots captured for every failure?" \
  --criteria "Is the severity classification accurate?" \
  --criteria "Is the report JSON well-structured and complete?" \
  --criteria "Did the agent follow the testing methodology in SKILL.md?"

agentcore run eval --harness ui-test-agent --evaluator ui-test-quality
```

### Level 3: Golden Test Cases

Pre-defined test scenarios with known expected outcomes:

| Golden Test | Target Page | Agent Should Find | Expected Result |
|-------------|-------------|-------------------|-----------------|
| GT-01 | `/login` (valid creds) | Successful login | PASS |
| GT-02 | `/login` (invalid creds) | Error message displayed | PASS (agent reports the error correctly) |
| GT-03 | `/dropdown` | Dropdown selection works | PASS |
| GT-04 | `/broken_images` | Broken image detected | FAIL (agent should detect broken images) |
| GT-05 | `/status_codes/500` | 500 error page | FAIL (agent should report server error) |
| GT-06 | `/javascript_alerts` | Alert handling | PASS |
| GT-07 | `/dynamic_loading/1` | Element appears after wait | PASS (agent waits correctly) |
| GT-08 | `/disappearing_elements` | Inconsistent navigation | Agent should note flakiness |

### Level 4: End-to-End Validation

Full agent run against the-internet with automated result checking:

```python
"""
Golden test runner — validates the UI Test Agent produces correct results.
"""

GOLDEN_EXPECTATIONS = {
    "Login with valid credentials (tomsmith/SuperSecretPassword!)": {
        "expected_status": "PASS",
        "must_contain": "Secure Area"
    },
    "Login with invalid credentials": {
        "expected_status": "PASS",  # Agent should PASS (correctly identifies error msg)
        "must_contain": "invalid"
    },
    "Detect broken images on /broken_images": {
        "expected_status": "FAIL",  # Agent should find broken images
        "must_contain": "broken"
    },
    "Navigate to /status_codes/500": {
        "expected_status": "FAIL",  # Agent should report 500 error
        "must_contain": "500"
    },
}

def validate_agent_report(report: dict) -> dict:
    """Compare agent report against golden expectations."""
    results = {"passed": 0, "failed": 0, "details": []}

    for test_name, expectation in GOLDEN_EXPECTATIONS.items():
        # Find matching test case in report
        matching = [tc for tc in report["testCases"] if test_name.lower() in tc["name"].lower()]

        if not matching:
            results["failed"] += 1
            results["details"].append(f"❌ {test_name}: NOT FOUND in report")
            continue

        tc = matching[0]
        if tc["status"] == expectation["expected_status"]:
            results["passed"] += 1
            results["details"].append(f"✅ {test_name}: correct status ({tc['status']})")
        else:
            results["failed"] += 1
            results["details"].append(
                f"❌ {test_name}: expected {expectation['expected_status']}, got {tc['status']}"
            )

    return results
```

---

## Test Execution Plan

### Phase 1: Smoke Test (First Deployment)

Run agent against 3 simple pages to verify basic functionality:

```bash
agentcore invoke --harness ui-test-agent \
  --session-id "$(uuidgen)" \
  "Test the following on https://the-internet.herokuapp.com:
   1. Login page (/login) — login with tomsmith/SuperSecretPassword! and verify success
   2. Dropdown page (/dropdown) — select Option 2 and verify selection
   3. Add/Remove Elements (/add_remove_elements/) — click Add Element and verify it appears"
```

**Success criteria:** Agent produces a valid JSON report with 3 test cases, all PASS.

### Phase 2: Failure Detection

Run agent against pages with known issues:

```bash
agentcore invoke --harness ui-test-agent \
  --session-id "$(uuidgen)" \
  "Test the following on https://the-internet.herokuapp.com:
   1. Broken Images page (/broken_images) — verify all images load correctly
   2. Status Codes 500 (/status_codes/500) — verify page handles errors gracefully"
```

**Success criteria:** Agent correctly identifies failures and classifies severity.

### Phase 3: Complex Interactions

```bash
agentcore invoke --harness ui-test-agent \
  --session-id "$(uuidgen)" \
  "Test the following on https://the-internet.herokuapp.com:
   1. Dynamic Loading (/dynamic_loading/1) — click Start, wait for element to appear
   2. JavaScript Alerts (/javascript_alerts) — trigger alert, confirm, and prompt
   3. Drag and Drop (/drag_and_drop) — drag column A to column B position"
```

**Success criteria:** Agent handles waits, dialogs, and drag-and-drop correctly.

### Phase 4: Regression (Ongoing)

After any change to:
- System prompt
- Model version
- Skills
- Tool configuration

Re-run all golden tests and compare to baseline.

---

## Metrics to Track

| Metric | Target | How to Measure |
|--------|--------|----------------|
| **Accuracy** | >90% correct PASS/FAIL classification | Golden tests |
| **False positive rate** | <5% | Tests marked FAIL that are actually PASS |
| **False negative rate** | <10% | Bugs missed (PASS when should be FAIL) |
| **Completion rate** | >95% | Agent finishes without timeout/error |
| **Report quality** | >4/5 LLM-judge score | Eval framework |
| **Avg duration** | <5 min for 5 test cases | CloudWatch metrics |

---

## CI/CD Integration for Agent Testing

```yaml
# Run golden tests on every change to agent config
on:
  push:
    paths:
      - 'app/ui-test-agent/**'
      - 'docs/ARCHITECTURE.md'

jobs:
  agent-regression:
    runs-on: ubuntu-latest
    steps:
      - name: Run golden tests
        run: python tests/golden_test_runner.py
      - name: Run eval
        run: agentcore run eval --harness ui-test-agent --evaluator ui-test-quality
```

---

*Last updated: 2026-05-16*
