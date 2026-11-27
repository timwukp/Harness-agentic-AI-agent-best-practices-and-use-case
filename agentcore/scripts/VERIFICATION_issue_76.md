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

## 4b results (2026-11-27, after merge at `d74037e`)

### QA

`ci-agent/qa_agent.py` (token-monitoring `7c06d3e`), unchanged, against the dev target.
Session `qa-verify-issue76-324e13ab…`, S3 prefix `verify-issue-76/`, 5 min 36 s.

| Check | Result |
|---|---|
| Skill loads | ✅ One `execute_tool skills` span (success). None of the six sessions on 2026-10-29/30 had one. |
| Secret read without a repeated sandbox retry | ✅ One `code_interpreter` call, then `shell`, then browsing; sign-in worked. Spans don't record tool payloads, so they can't show which call returned the secret. |
| Final JSON parses, `pages_tested` = 10 | ✅ |
| Verdict vs pr-113 (PASS, 0 findings, 2026-10-30) | ⚠ FAIL, 5 findings (3 MEDIUM, 2 LOW). Each quotes on-screen values: a freshness line that tracks the rollup rather than a call (F-001); billed vs logged gap (F-002); DORA median 42 min vs 39 min recomputed from the listed PRs (F-003); Athena data through 11-18 (F-004); no client-side format check on "Add repository" (F-005: typed, not submitted). They describe app and data state after 10-30, not a tool failure. Not verified independently. |
| Password absent | ✅ Absent from the reply, the report and stderr (boolean check; the value was never printed). |

Concurrency: another QA verification ran on the same harness from 14:05:30 to 14:12:38Z (a viewer pass, then an admin pass, each with its own session ID). All three sessions returned full reports. This differs from #64, where overlapping runs ended terminated or empty. In the invocation log, this run's browser session is `qa-tokenmonitor-i76`.

Tokens: 1,744,380 input (1,685,009 cache read, 59,289 cache write), 22,764 output. That is about $0.55 at Sonnet 5.5 list price. The pre-merge estimate of $3.60–$8.77 assumed October's sessions, which had 0 cache reads.

### Bug-Fix

`ci-agent/bugfix_agent.py` `main()` ran unchanged except `_dirty_paths`. The target was a throwaway repo: one TypeScript file with a ×100 formatting bug, a plan naming it, and one HIGH finding. The repo has no commit (a local hook blocks `git commit`), so `_dirty_paths` was replaced by a content-hash comparison against the seeded files. Session `bugfix-ci-af48abcf…`, 46 s.

| Check | Result |
|---|---|
| `gen_ai.agent.tools` | `["skills"]`. The plain name `code_interpreter` filters out the declared tool (`code_interpreter_1`), as AGENTS.md §3.11.3 says. |
| Skill loads | ✅ One `execute_tool skills` span (success). |
| Reply shape | ✅ Starts with a `diff` fence. One fenced block, no JSON proposal, no PR / MCP / Cedar / approval text. The analysis follows the skill: root cause, why this file, risk. It also notes it has only the one file. |
| Orchestrator path | ✅ `extract_diff` → `diff_is_confined` → `git apply`: 1/1 patched. The fix is correct: it drops the `/ 100`. |

Tokens: 9,706 input (3,753 cache read, 5,947 cache write), 1,010 output. That is about $0.05 at Opus 5.5 list price. `input_tokens` includes the cache tokens: 3,753 + 5,947 = 9,700 of 9,706.

### What changed since October

With `["*"]`, UITestAgentHarness v8 now offers `shell, read, write, edit, web_fetch, browser, code_interpreter, subagent, retrieve_context, skills, todo_write`. In October it offered `shell, file_operations, browser, code_interpreter, skills`. The harness version did not change; the platform's built-in set did. ui-testing/SKILL.md no longer names `file_operations`.
