# Issue #76 Verification — skills describe the real CI flow

Both live harnesses load these skills from `main` through the `git` skill source, which has
no branch field (AGENTS.md §3.2.5). The functional check can only run after merge, which is
the "When to deviate" path that PR #55 / #59 set as precedent.

## What the old skills claimed, against the live system

| Old claim | Live reality (2026-11-27) |
|---|---|
| bug-fixing: read the repo and open the PR through a GitHub MCP | Neither harness has an MCP tool. BugFix tools: one `agentcore_code_interpreter`. `ci-agent/bugfix_agent.py` puts one file's text in the prompt and takes the first unified diff from the reply. |
| bug-fixing: Cedar denies pushes to `main` | Neither harness has a gateway tool or a policy field in `get_harness`. The workflow pushes to the PR head branch; `main` is ruleset-protected, and a human merges. |
| bug-fixing: call `request_pr_approval` (#33) | No inline function on either harness (#33 is open). |
| bug-fixing: emit a JSON fix proposal; the orchestrator parses it | The orchestrator parses only the diff (`extract_diff`) and asks for the diff first. |
| bug-fixing: run unit tests; prefer a rollback for CRITICAL | The agent gets one file, not the repo. Diffs are confined to that file, content edits only (`diff_is_confined`, `PROTECTED_PREFIXES`). |
| ui-testing: credentials from environment variables | The only env var on the UI harness is `OTEL_TRACES_SAMPLER`. The login is in Secrets Manager (`qa_agent.py` STEP 0). The Code Interpreter attempt raises `NoCredentialsError`; `shell` reads it (eval logs mention the error in 52 sessions from 2026-09-29 to 10-30). |
| ui-testing: `browser_console_messages`, `browser_network_requests`, accessibility tree | The runtime `browser` tool has 22 `action.type` values (from its `gen_ai.tool.json_schema`): none returns console or network logs, and none reads the accessibility tree. |
| ui-testing: mark untestable runs BLOCKED | The report schema is `overall` PASS/FAIL plus `findings`. The orchestrator derives the verdict from `findings` and records UNKNOWN when there is no report. |

## Pre-merge checks

- Both files start with YAML frontmatter, and `yaml.safe_load` returns exactly `name`
  (equal to the directory name) and `description` (AGENTS.md §3.8).
- The example diff in bug-fixing/SKILL.md, run through the orchestrator's own code:
  `extract_diff` finds it; `diff_is_confined(diff, rel)` returns `(True, '')`; the same diff
  aimed at `.github/x.yml` is refused as a protected path; `git apply --check` gives exit code 0.

## 4b. Post-merge functional test (owner approves the spend first)

**QA:** run `ci-agent/qa_agent.py` (token-monitoring `main`) once against the dev target. Pass when:
- the session has an `execute_tool skills` span, or the reply quotes ui-testing content;
- the secret is read on the first `shell` attempt, without a repeated sandbox retry;
- the final JSON parses and `pages_tested` is 10;
- the verdict matches the last round (pr-113: PASS, 0 findings), or each difference is a real
  finding;
- the password is absent from the reply text (checked as a boolean, never printed).

Estimated cost: one run took 1.7–4.2 M input tokens on 2026-10-29/30, about $3.60–$8.77 at
Sonnet 5.5's $2/$10 per-MTok list price. Bedrock bills its own rate.

**Bug-Fix:** one `invoke_harness` with the exact prompt `bugfix_agent.py` builds: a synthetic
finding and a small file with one bug, and no answer-key comments. Pass when:
- `gen_ai.agent.tools` on the `invoke_agent` span is recorded. This also answers whether
  `["code_interpreter"]` exposes `code_interpreter` and `skills`.
- the skill loads;
- the reply starts with the diff, carries no JSON or PR text, and passes `extract_diff`,
  `diff_is_confined` and `git apply --check`.

Estimated cost: under $1 at Opus 5.5's $4/$20 per-MTok list price for a file of a few hundred
lines. No retained spans measure this, so the figure is a guess.

Results go in this file through a follow-up doc-only PR.
