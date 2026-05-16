# Downstream Bug-Fix Agent — Design Document

> **Version:** 0.2.0  
> **Status:** Design

---

## Purpose

When the UI Test Agent finds failures, the Bug-Fix Agent automatically:
1. Receives structured failure data (expected vs actual, console errors, screenshots)
2. Clones the repository and analyzes the relevant source code
3. Identifies the root cause
4. Writes a minimal fix
5. Runs unit tests to verify
6. Creates a PR with the fix
7. Triggers the UI Test Agent to re-verify

---

## Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    BUG-FIX AGENT WORKFLOW                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. RECEIVE          UI Test Agent calls trigger_fix_agent        │
│     │                with failure details                         │
│     ▼                                                            │
│  2. ANALYZE          Clone repo, read failing code,              │
│     │                correlate error with source                  │
│     ▼                                                            │
│  3. DIAGNOSE         Identify root cause from:                   │
│     │                - Console error + stack trace                │
│     │                - Expected vs actual behavior                │
│     │                - Screenshot context                         │
│     ▼                                                            │
│  4. FIX              Write minimal code change                   │
│     │                (smallest diff that resolves the issue)      │
│     ▼                                                            │
│  5. VERIFY           Run unit tests, lint, type check             │
│     │                                                            │
│     ▼                                                            │
│  6. SUBMIT           Create PR with:                             │
│     │                - Fix description                            │
│     │                - Root cause analysis                        │
│     │                - Test case that triggered the fix           │
│     ▼                                                            │
│  7. RE-TEST          Trigger UI Test Agent on PR preview          │
│                      to confirm the fix works                     │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Architecture

```
┌──────────────────┐         ┌──────────────────────────────────────┐
│  UI Test Agent   │         │  Bug-Fix Agent (AgentCore Harness)    │
│                  │         │                                       │
│  trigger_fix     │────────▶│  Tools:                               │
│  _agent()        │         │  ├── Shell (git clone, npm test)      │
│                  │         │  ├── Code Interpreter (analyze code)  │
│                  │         │  ├── GitHub MCP (create PR)           │
│                  │◀────────│  └── Inline: request_ui_retest        │
│  (re-test PR)    │         │                                       │
└──────────────────┘         └──────────────────────────────────────┘
```

---

## Input Schema (from UI Test Agent)

```json
{
  "failures": [
    {
      "test_case_id": "TC-002",
      "name": "Login with invalid password shows error",
      "expected": "Error message: 'Invalid credentials'",
      "actual": "500 Internal Server Error",
      "severity": "HIGH",
      "console_error": "TypeError: Cannot read property 'message' of undefined",
      "screenshot_path": "s3://reports/screenshots/TC-002-error.png",
      "page_url": "https://staging.example.com/login"
    }
  ],
  "repository_url": "https://github.com/org/frontend-app",
  "branch": "feature/login-redesign",
  "test_suite": "login-flow-regression"
}
```

---

## Harness Configuration

```json
{
  "name": "bug-fix-agent",
  "model": {
    "bedrockModelConfig": {
      "modelId": "us.anthropic.claude-sonnet-4-5-20250514-v1:0"
    }
  },
  "systemPrompt": [{
    "text": "You are an expert frontend developer specializing in bug fixes. Given test failure reports from a UI testing agent, you:\n\n1. Analyze the failure (expected vs actual, console errors, screenshots)\n2. Clone the repository and find the relevant source code\n3. Identify the root cause with high confidence\n4. Write the MINIMAL fix (smallest diff that resolves the issue)\n5. Verify the fix passes lint and unit tests\n6. Create a PR with clear description\n\nRules:\n- NEVER make changes beyond what's needed to fix the reported issue\n- NEVER refactor unrelated code\n- ALWAYS run tests before submitting\n- ALWAYS explain your root cause analysis in the PR description\n- If you cannot identify the root cause with >80% confidence, call request_human_review instead of guessing\n- Prefer defensive fixes (null checks, error boundaries) over architectural changes"
  }],
  "tools": [
    {"type": "agentcore_code_interpreter", "name": "code_interpreter"},
    {
      "type": "remote_mcp",
      "name": "github",
      "config": {"remoteMcp": {
        "url": "https://api.githubcopilot.com/mcp/",
        "headers": {"Authorization": "Bearer ${arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:token-vault/default/apikeycredentialprovider/github-token}"}
      }}
    },
    {
      "type": "inline_function",
      "name": "request_ui_retest",
      "config": {"inlineFunction": {
        "description": "Trigger the UI Test Agent to re-run the failing tests against the PR preview URL.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "pr_number": {"type": "integer", "description": "PR number created"},
            "pr_url": {"type": "string", "description": "URL of the created PR"},
            "preview_url": {"type": "string", "description": "Preview deployment URL for the PR"},
            "test_cases": {"type": "array", "items": {"type": "string"}, "description": "Test case IDs to re-run"}
          },
          "required": ["pr_number", "pr_url", "test_cases"]
        }
      }}
    },
    {
      "type": "inline_function",
      "name": "request_human_review",
      "config": {"inlineFunction": {
        "description": "Escalate to human developer when root cause cannot be determined with high confidence.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "test_case_id": {"type": "string"},
            "analysis": {"type": "string", "description": "What you've determined so far"},
            "uncertainty": {"type": "string", "description": "Why you're not confident"},
            "suggested_files": {"type": "array", "items": {"type": "string"}, "description": "Files that likely contain the bug"}
          },
          "required": ["test_case_id", "analysis", "uncertainty"]
        }
      }}
    }
  ],
  "allowedTools": [
    "@builtin/shell",
    "@builtin/file_operations",
    "code_interpreter",
    "@github/*",
    "request_ui_retest",
    "request_human_review"
  ],
  "maxIterations": 50,
  "timeoutSeconds": 900,
  "maxTokens": 32768,
  "truncationStrategy": "sliding_window",
  "memory": {
    "agentCoreMemoryConfiguration": {
      "strategies": ["semantic", "episodic"]
    }
  },
  "tags": {
    "team": "qa-automation",
    "use-case": "bug-fix",
    "environment": "staging"
  }
}
```

---

## Fix Strategy

### Decision Tree

```
Failure received
    │
    ├── Console error with stack trace?
    │   └── YES → Trace to source file + line → Apply targeted fix
    │
    ├── Expected vs actual mismatch (no error)?
    │   └── YES → Analyze UI logic (state, rendering, CSS) → Fix logic
    │
    ├── Timeout / element not found?
    │   └── YES → Check async loading, race conditions → Add wait/guard
    │
    └── Cannot determine root cause?
        └── Call request_human_review with analysis so far
```

### Fix Categories

| Category | Example | Typical Fix |
|----------|---------|-------------|
| **Null reference** | `Cannot read 'x' of undefined` | Add null check / optional chaining |
| **Missing error handling** | 500 instead of 401 | Add try-catch, return proper status |
| **CSS/Layout** | Element hidden, z-index | Fix CSS specificity, positioning |
| **Async race condition** | Element not found | Add loading state, await |
| **State management** | Wrong data displayed | Fix state update logic |
| **API contract** | Wrong response format | Fix serialization/parsing |

---

## PR Template

```markdown
## 🔧 Auto-Fix: {test_case_name}

### Root Cause
{root_cause_analysis}

### Fix
{description_of_change}

### Evidence
- **Test Case:** {test_case_id}
- **Expected:** {expected}
- **Actual:** {actual}
- **Console Error:** `{console_error}`

### Changes
- `{file_path}`: {what_changed}

### Verification
- [x] Unit tests pass
- [x] Lint passes
- [ ] UI Test Agent re-verification (pending)

---
*This PR was automatically generated by the Bug-Fix Agent based on UI Test Agent findings.*
*Review carefully before merging.*
```

---

## Guardrails

| Guardrail | Implementation |
|-----------|---------------|
| **Scope limit** | Only modify files related to the reported failure |
| **No refactoring** | System prompt prohibits unrelated changes |
| **Test verification** | Must run `npm test` / `pytest` before PR |
| **Confidence threshold** | Escalate to human if <80% confident |
| **PR size limit** | Max 50 lines changed; escalate if larger fix needed |
| **Branch protection** | PR requires human approval before merge |
| **No production access** | Agent only has access to staging/dev branches |

---

## Self-Learning (Shared Memory with UI Test Agent)

The Bug-Fix Agent shares memory namespace with the UI Test Agent:

```
/knowledge/{actorId}/fix-patterns/
```

### What It Learns

| Trigger | Learning Stored |
|---------|----------------|
| Fix successfully resolves issue | "Pattern: {error_type} in {framework} → fix with {approach}" |
| Same bug type appears 3+ times | "Recurring issue: {pattern}. Suggest adding lint rule or test." |
| Fix rejected by human reviewer | "Approach X doesn't work for {scenario}. Use Y instead." |
| UI re-test confirms fix | Increase confidence score for that fix pattern |

### Example Learned Pattern

```json
{
  "namespace": "/knowledge/ci-pipeline/fix-patterns/",
  "content": "When React components throw 'Cannot read property of undefined' on error responses, the root cause is usually missing null check in the API response handler. Fix: add optional chaining (?.) on the response object before accessing nested properties. Success rate: 92% across 12 instances.",
  "metadata": {
    "error_type": "TypeError",
    "framework": "React",
    "fix_approach": "optional_chaining",
    "confidence": 0.92,
    "instances": 12
  }
}
```

---

## Integration Flow (Complete Pipeline)

```
Developer pushes code
    │
    ▼
GitHub Actions triggers UI Test Agent
    │
    ▼
UI Test Agent finds 2 failures
    │
    ├── TC-002: 500 error (HIGH)
    └── TC-007: Button unresponsive (MEDIUM)
    │
    ▼
trigger_fix_agent called with failure data
    │
    ▼
Bug-Fix Agent:
    ├── Clones repo, checks out branch
    ├── TC-002: Finds null ref in auth.controller.ts → adds null check
    ├── TC-007: Finds z-index conflict in button.css → fixes stacking
    ├── Runs npm test → all pass
    └── Creates PR #42 with both fixes
    │
    ▼
request_ui_retest called
    │
    ▼
UI Test Agent re-runs TC-002 and TC-007 on PR preview
    │
    ├── TC-002: PASS ✅
    └── TC-007: PASS ✅
    │
    ▼
PR #42 marked as "verified" → ready for human review
```

---

## Cost Estimate

| Component | Per Fix | Notes |
|-----------|---------|-------|
| Clone + analyze | ~$0.10 | Token cost for reading code |
| Write fix | ~$0.05 | Small diff generation |
| Run tests | ~$0.02 | Shell execution (zero tokens) |
| Create PR | ~$0.03 | GitHub API calls |
| **Total per fix** | **~$0.20** | |
| UI re-test | ~$0.15 | Separate UI Test Agent run |
| **Total end-to-end** | **~$0.35** | vs. 30-60 min developer time |

---

*Last updated: 2026-05-16*
