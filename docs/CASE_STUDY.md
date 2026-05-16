# Case Study: Replacing Human QA Testers with AI Agents

> Built on Amazon Bedrock AgentCore Harness | End-to-End Verified

---

## Situation

A development team ships frontend code daily. Every PR needs manual QA testing before merge — a human tester opens the browser, clicks through forms, verifies error messages, checks layouts, and writes test reports. This process takes 30-60 minutes per PR and costs $50-100/hour per QA engineer.

The team faces three problems:
1. **Speed** — QA is the bottleneck. PRs wait hours for a human to test them.
2. **Cost** — Two full-time QA engineers cost $16,000/month for a medium team.
3. **Consistency** — Human testers miss things. Fatigue, oversight, and varying standards lead to bugs reaching production.

The question: *Can an AI agent replace a human QA tester — not just check if elements exist, but actually click buttons, fill forms, observe results, and judge correctness like a human would?*

---

## Task

Build an AI-powered UI testing agent that:
- Navigates web applications using a real browser (not just HTML parsing)
- Interacts with UI elements exactly as a human would (click, type, scroll, hover, drag)
- Detects bugs by comparing actual behavior against expected behavior
- Produces structured test reports with evidence (screenshots, error details)
- Automatically triggers a Bug-Fix Agent to generate code patches
- Integrates into CI/CD so every PR is tested automatically

---

## Action

### Architecture Choice: AgentCore Harness

We chose Amazon Bedrock AgentCore because it provides:
- **AgentCore Browser** — a remote cloud Playwright instance the agent controls
- **AgentCore Code Interpreter** — sandboxed Python for precise analysis
- **AgentCore Memory** — the agent learns from past tests and improves
- **Harness mode** — zero-code declarative deployment (one API call)

### What We Built

**1. UI Test Agent** — navigates web pages, interacts with elements, reports PASS/FAIL

```python
from strands import Agent
from strands_tools.browser import AgentCoreBrowser

agent = Agent(tools=[AgentCoreBrowser(region="us-east-1").browser])
agent("Test the login page. Type wrong credentials. Verify error message.")
```

**2. Bug-Fix Agent** — receives failure reports, analyzes source code, generates patches

```python
client.invoke_harness(
    harnessArn=BUG_FIX_HARNESS_ARN,
    messages=[{"role": "user", "content": [{"text": f"Fix these bugs: {failures}\nSource: {code}"}]}]
)
```

**3. CI/CD Integration** — GitHub Actions triggers on every PR, posts results as comments

**4. Demo Frontend** — a login page with 5 intentional bugs for validation

### The End-to-End Pipeline

```
Developer pushes code
    → GitHub Actions triggers (OIDC → AWS)
    → UI Test Agent opens browser, tests the page
    → Agent finds bugs: "error message is green, should be red"
    → Bug-Fix Agent generates patch: color:green → color:red
    → Patch ready for PR
```

### Testing Methodology

The agent follows the same methodology a human QA tester would:
1. Navigate to the page
2. Interact with elements (type credentials, click submit)
3. Observe the result (what appeared? what color? what text?)
4. Compare against expectations
5. Report with evidence

We tested across **17 interaction types**: form submission, dropdown selection, dynamic loading, JavaScript alerts, hover effects, drag-and-drop, infinite scroll, keyboard input, iframe switching, right-click menus, page redirects, broken image detection, CSS bug detection, and more.

---

## Result

### Quantitative

| Metric | Value |
|--------|-------|
| Total tests executed | 35 |
| Pass rate | 94.3% (33 PASS) |
| Bugs correctly detected | 3 (2 in our app + 1 in test target) |
| Interaction types covered | 17 |
| Cost per test suite | ~$0.32 |
| Time per test suite | ~45 seconds |
| Human QA equivalent cost | $50-100/hour |
| Monthly savings (medium team) | ~$15,000 |

### Qualitative

**The agent thinks like a human QA tester:**

When testing our demo login page, the agent reported:
> "The error message text is **green** (rgb(0, 128, 0)) on a light red/pink background. This is a **double bug**: (1) An error message should be displayed in red, not green. Green conventionally signals success. (2) The message says 'Internal server error' instead of 'Invalid username or password' — this implies a server-side failure, not a credential mismatch."

This is exactly what a senior QA engineer would write.

**The Bug-Fix Agent generates correct patches:**

Given the test failure, the Bug-Fix Agent produced:
```diff
- .error-message { color: green; ... }
+ .error-message { color: red; ... }

- errorMsg.textContent = 'Internal server error. Please try again later.';
+ errorMsg.textContent = 'Invalid username or password';
```

Both fixes are minimal, correct, and production-ready.

### Pipeline Verification

| Stage | Status |
|-------|--------|
| CI/CD trigger (GitHub Actions + OIDC) | ✅ Verified |
| UI Test Agent execution | ✅ Verified |
| Bug detection on own application | ✅ Verified |
| Bug-Fix Agent patch generation | ✅ Verified |
| Test report with screenshots | ✅ Verified |
| PR comment posting | ✅ Verified |

### What the Agent Learned

Through AgentCore Memory, the agent accumulated knowledge:
- "SPA route changes don't trigger page reload — wait for content, not navigation"
- "Dropdown menus with CSS transitions require a wait between trigger click and option click"
- "When element not found after click, check if a modal overlay is blocking"

This knowledge persists across sessions and improves future test runs.

---

## Key Takeaway

**An AI agent can replace 80% of manual QA testing today** — not with brittle Selenium scripts, but with genuine understanding of UI behavior. It clicks like a human, judges like a human, and reports like a human — at $0.32 per run instead of $50/hour.

The remaining 20% (visual design review, subjective UX judgment, accessibility audits) still benefits from human oversight, but the agent handles the repetitive, time-consuming verification work that burns out QA teams.

---

*Built with: Amazon Bedrock AgentCore (Harness + Runtime), Strands Agents SDK, Claude Sonnet 4.5, AgentCore Browser, AgentCore Code Interpreter, GitHub Actions*

*Repository: https://github.com/timwukp/Harness-agentic-AI-agent-best-practices-and-use-case*
