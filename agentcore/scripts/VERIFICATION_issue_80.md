# Issue #80 Verification — a fixed `allowedTools` for UITestAgentHarness

Tested 2026-11-27 with boto3 1.43.67, region us-east-1. Account IDs, harness IDs and role
suffixes are redacted. The live harnesses were only read (`get_harness`); nothing here
changed them.

## Live state

| | UITestAgentHarness v8 |
|---|---|
| `allowedTools` | `["*"]` |
| configured tools | `agentcore_browser` named `aws_browser_v1`, `agentcore_code_interpreter` named `aws_codeinterpreter_v1` |
| model | `global.anthropic.claude-sonnet-5-5` |

The repo's own install path names the same tools differently: `browser` and
`code_interpreter` in `app/ui-test-agent/deploy_harness.py` and `harness.json`.

## What a QA run uses (`aws/spans`, all 11 retained UITestAgentHarness sessions)

`gen_ai.agent.tools` on each session's `invoke_agent` span:

| Sessions | Offered under `["*"]` |
|---|---|
| 6, 2026-10-29..30 | shell, file_operations, browser, code_interpreter, skills |
| 5, 2026-11-27 (two CI runs of 2 passes each, plus the #76 4b run) | shell, read, write, edit, web_fetch, browser, code_interpreter, subagent, retrieve_context, skills, todo_write |

The harness version (v8) did not change between the two rows; the platform's
recommended built-in set did.

`execute_tool` spans, all 11 sessions: browser 572, shell 60, code_interpreter 23,
retrieve_context 6, skills 3, read 3. Nothing else was called.

| Tool | Calls | Decision | Why |
|---|---|---|---|
| browser | 572 | keep | the test itself |
| shell | 60 | keep | reads the login secret: the AWS-managed Code Interpreter has no AWS credentials, the harness runtime has the execution role |
| code_interpreter | 23 | keep | STEP 0 and STEP 3 of the prompt name it |
| retrieve_context | 6 (2 of 5 sessions) | keep | reads back a tool result over ~1,500 tokens that the harness moved out of context ([harness-tools](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-tools.html)). It is not Memory. |
| skills | 3 | keep | loads ui-testing/SKILL.md |
| read | 3 (3 of 5 sessions) | keep | its description says it returns png/jpg as media the model can view: the agent can look at its own saved screenshots, which `shell` cannot show it |
| web_fetch | 0 | drop | fetches any URL |
| subagent | 0 | drop | a child agent that gets shell and web_fetch |
| write, edit | 0 | drop | `shell` already writes the report files |
| todo_write | 0 | drop | not used |

## Throwaway harness

`UITestAgentToolsProbe` copies the live harness: model, system prompt, tools (same names),
skills, limits, truncation, network mode PUBLIC, lifecycle, environment variables and the
shared execution role. It has **no memory**:
- `CreateHarness` without a `memory` field creates a managed memory. The shared role has
  no grant on it, and the first invoke failed with `AccessDeniedException ... ListEvents`.
  The probe was deleted and recreated with `memory={"disabled": {}}`.
- `DeleteHarness` defaults to `deleteManagedMemory=true`, so the throwaway never
  references the live UI agent's memory.

Memory is not a tool and does not appear in `gen_ai.agent.tools`.

## Which selector forms work (one short invoke each, `gen_ai.agent.tools` from the span)

| `allowedTools` | Offered |
|---|---|
| `["*"]` (control) | the same 11 tools as the live harness |
| `["shell", "read", "retrieve_context", "skills", "@aws_browser_v1", "@aws_codeinterpreter_v1"]` | **shell, read, browser, code_interpreter, retrieve_context, skills** |
| `["shell", "read", "retrieve_context", "@browser", "@code_interpreter"]` | shell, read, retrieve_context, skills |
| `["shell", "browser", "code_interpreter"]` | shell, skills |
| `["browser_*", "code_interpreter*", "skills"]` (AGENTS.md §3.11.3 before this PR) | skills |

- A configured tool is selected only by `@` plus its configured `tools[].name`. The model
  sees the tools as `browser` and `code_interpreter`, but `@browser` selects nothing here.
- `skills` is offered whether or not it is listed.
- The 5 dropped tools are 1,496 input tokens per model request (15,664 vs 14,168 on the
  first request). That saves little money, and it is not the reason for the change.

Hence `DESIRED` writes `@{agentcore_browser}` / `@{agentcore_code_interpreter}`, and the
script resolves them from each harness's own `tools` list.

## Offline checks (fake control plane, no AWS calls)

16 checks, all passing:
- the resolver maps the live names to `@aws_browser_v1` / `@aws_codeinterpreter_v1`, the
  `deploy_harness.py` names to `@browser` / `@code_interpreter`, and two browsers to both;
- a missing tool type raises, and `main` then exits 6 without updating that harness;
- `["*"]` → the list is NARROW: `--dry-run` exits 5, a plain apply is refused with no
  `update_harness`, `--allow-narrowing` sends one `update_harness` carrying only
  `allowedTools`, and the re-run and the dry run after it exit 0 with no calls;
- a missing harness still exits 1;
- `poll_until_ready` with an injected clock: a 238 s update ends READY.

Mutation check: 8 mutants, each turns at least one check red (resolver never matches, no
raise on a missing type, runtime name instead of `tools[].name`, `main` skips resolution,
exit 6 dropped, `web_fetch` left in DESIRED, NARROW disabled, poll limit back at 120 s).

## 4a. API-level live test (the changed script, unmodified, against the throwaway)

`DESIRED` was re-keyed in memory to `UITestAgentToolsProbe` (the UI entry, unchanged). The
live harnesses were not in `DESIRED` during the run. The throwaway was first set to `["*"]`,
the live value.

**First run (poll limit 120 s): the apply reported failure while the update was still running.**

| Step | Exit | Note |
|---|---|---|
| `--dry-run` | 5 | `allowedTools ['*'] → [... '@aws_browser_v1', '@aws_codeinterpreter_v1'] NARROW` |
| apply | 5 | refused, no `update_harness` |
| `--allow-narrowing` | **3** | `ERROR: timeout waiting for READY` after 126 s; READY 101 s later; the tag step never ran |

Each of the 6 updates measured on the throwaway took 223–238 s to reach READY. The script
now polls up to 600 s.

**Second run (poll limit 600 s):**

| Step | Exit | Note |
|---|---|---|
| `--dry-run` | 5 | NARROW reported |
| apply | 5 | refused, no `update_harness` |
| `--allow-narrowing` | 0 | `update_harness HTTP 200 (['allowedTools'])`, READY after 227 s, version 8 → 9 |
| re-run `--allow-narrowing` | 0 | `✓ No changes needed (idempotent re-run safe)` |
| `--dry-run` | 0 | every row `same` |

`get_harness` afterwards: `allowedTools = ["shell", "read", "retrieve_context", "skills",
"@aws_browser_v1", "@aws_codeinterpreter_v1"]`.

## 4b. Functional / E2E test

One `ci-agent/qa_agent.py` run (token-monitoring `main` `2928e2a`, unchanged: a viewer pass
that explores every page and a read-only admin pass) against the throwaway's full ARN, on the
shared dev app.

Pass criteria, written before the run:
1. `gen_ai.agent.tools` on both sessions' `invoke_agent` spans is exactly shell, read,
   browser, code_interpreter, retrieve_context, skills.
2. No `execute_tool` span names any other tool.
3. Viewer pass: sign-in works, `pages_tested` = 10, `persona_check` = ok.
4. Admin pass: `persona_check` = ok.
5. `readonly` = ok on both passes. `unobserved` would mean the stream no longer carries
   parseable browser actions, which counts as a regression.
6. The report parses (`overall` is not UNKNOWN).

Findings are compared with today's live runs (token-monitoring #123–#128); they describe
the app, so they are not a pass criterion.

Pre-flight: no other QA session on the dev app (no UITestAgentHarness span in the last
15 min, no `ui-qa-agent` workflow run in progress).

### Results

Run 2026-11-27 16:00:47–16:06:39Z (5 min 52 s): sessions `qa-verify-allowedtools-238eeb37…`
(viewer) and `…-admin`, S3 prefix `verify-allowedtools/`. `qa_agent.py` was the `main` blob
(`f198ba4`), run with boto3 1.43.67 (CI pins 1.43.120).

| # | Criterion | Result |
|---|---|---|
| 1 | `gen_ai.agent.tools`, both sessions | ✅ shell, read, browser, code_interpreter, retrieve_context, skills on both |
| 2 | No other tool called | ✅ Viewer: browser 80 (2 returned an error), read 10, shell 5, code_interpreter 1, retrieve_context 1, skills 1. Admin: browser 10, shell 3, read 1, code_interpreter 1. |
| 3 | Viewer: sign-in, 10 pages, persona | ✅ `pages_tested` 10, `persona_check` ok (saw non-admin) |
| 4 | Admin persona | ✅ `persona_check` ok (saw admin) |
| 5 | `readonly` | ✅ ok on both, 0 violations. The stream audit saw the viewer's click 13, type 2, evaluate 45, screenshot 19, and the admin's single click (Sign in), navigate 2, get_text 1, get_html 1. |
| 6 | Report parses | ✅ `overall` FAIL (8 findings, 3 MEDIUM), not UNKNOWN |

The 8 findings describe the app, not the tools:
- 4 match issues filed in the token-monitoring repo on 2026-11-27: #123, #124, #126 and #128 (now 15 of 23 projects).
- 1 matches F-003 of the #76 run (DORA median 42 vs 39 min).
- 3 are not among #123–#128: the rollup start date differs between Overview and Cost; Latency shows 8,615 streaming invocations against 8,622 summed over the TTFB series; values are misleading while loading.

They were not verified independently and are left to that repo.

Tokens:

| Pass | Input | Cache read | Cache write | Output |
|---|---|---|---|---|
| Viewer | 3,426,296 | 3,339,789 | 86,369 | 26,098 |
| Admin | 271,931 | 259,860 | 12,043 | 4,899 |

## Not covered

- The skill loads from `main` through the `git` source, which has no branch field (AGENTS.md §3.2.5). So 4b ran with
  `main`'s ui-testing/SKILL.md, whose Tools paragraph still names the `["*"]` set. This PR's edit to that
  paragraph is descriptive: the tools the agent gets come from `allowedTools`, not from the skill.

- The live UITestAgentHarness keeps `["*"]` until the owner runs
  `python agentcore/scripts/tighten_harness_config.py --allow-narrowing --environment production`
  after merge. That is about 4 minutes of `UPDATING` per harness.
- `shell` still reaches the network (network mode PUBLIC). This list removes the
  dedicated fetch and delegation tools and stops the set from growing when the platform
  adds tools. It does not stop exfiltration through `shell`.
- BugFixAgentHarness is unchanged. Its `["code_interpreter"]` matches no built-in, so it is
  offered only `skills` (VERIFICATION_issue_76.md).

Cleanup: UITestAgentToolsProbe was deleted after the run. `list_harnesses` is back to 18 entries,
with no probe-named memory or runtime, and both live harnesses still read v8 `["*"]` / v7.

Cost: probes $0.083; QA run $0.92 ($0.81 viewer + $0.11 admin) (Sonnet 5.5 list price: $2 input, $10 output,
$0.10 cache read, $2.50 cache write per MTok). Bedrock bills its own rate.
