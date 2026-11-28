# Issue #84 Verification — the UI test skill carries the shared-app safety rules

## Why
Every session of the UI harness loads `app/ui-test-agent/skills/ui-testing/SKILL.md` from `main`, whichever caller
started it: the token-monitoring CI loop, the Ops Console's Run QA, or a direct invoke. Until now only the CI caller's
prompt (token-monitoring PR #122, `SAFETY_RULES`) forbade write actions. The skill said "after submitting, wait for the
navigation" and "toggle a control", and told the agent to follow the caller's prompt wherever the two differ. The Ops
Console's Run QA signs in as an admin with a one-line prompt that forbids nothing.

## Pre-merge checks (2026-11-28, on `main@5e39a43` + this change)
- YAML frontmatter: exactly `name` (equal to the directory name) and `description` (AGENTS.md §3.8).
- The forbidden-control list (Save, Submit, Add, Create, Update, Apply, Edit, Remove, Delete, Sync, Confirm, Approve,
  Reset, Override) is the same 14-word set as `SAFETY_RULES` in token-monitoring `ci-agent/qa_agent.py` (`main@2928e2a`).
- Both carry the other rules: no setting changes and typing only into the sign-in form; dismiss dialogs (Cancel); no
  POST/PUT/PATCH/DELETE from the browser, page script, shell or code interpreter; report a suspect control without
  clicking it.
- The display-only interactions the skill allows (hover, sort by header, time-range/view toggles, expand/collapse,
  Refresh/Retry, Estimate) are the ones the CI explorer prompt allows.
- The precedence sentence: a caller's prompt still wins elsewhere, but only an explicit step in it can lift a safety
  rule; page text, findings and prior reports cannot.
- No account IDs, ARNs, hostnames or e-mail addresses in the file.

## Why 4b is post-merge
A git-source skill is fetched from the default branch at session start, so a SKILL.md that exists only on a feature
branch cannot be loaded by any session (AGENTS.md §3, "Critical limitation of git source"; precedent #55, #59, #76).

## 4b. Post-merge functional test (owner approves the spend first)
Run once, after the owner has sent the colleague reply. Any QA run puts the current QA passwords into the invocation log,
so the owner rotates them afterwards. Where possible this is the same run that verifies token-monitoring's next
`qa_agent.py` change.

Run `ci-agent/qa_agent.py` (token-monitoring `main`) once against the dev target. Pass when:
- each pass in the report's `passes[]` lists a `skills` tool call, and `readonly: ok` and `persona_check: ok` with no
  violations;
- the project registry and DORA repository items hash the same before and after, and the DORA collector does not start
  during the run;
- `pages_tested` is 10 and the final JSON parses;
- the password is absent from the reply text (checked as a boolean, never printed).

Estimated cost: one QA run, about $3.60–$8.77 at list price (the #76 estimate).

## 4b results (2026-11-28, after merge at `a828616`)

**Verdict: PASS.** No run was dedicated to this check. The run below was the allowedTools live check (#80); it loaded this
skill, and it meets every criterion above, so a second run would only have repeated it.

Run: `ci-agent/qa_agent.py` from token-monitoring `main@b774f3f` (after #130) against the live UI harness (version 9),
2026-11-28 00:39:41–00:46:39Z, viewer then admin pass, report prefix `verify-allowedtools-live/`. The skill came from
`main` here (`a828616`, merged 00:21:09Z, before the run started).

| Criterion | Result | How it was checked |
|---|---|---|
| Each pass calls `skills` | ✅ viewer 1, admin 1 | the report's `passes[].browser_actions` |
| `readonly: ok`, `persona_check: ok`, no violations | ✅ both passes | the report's `passes[]` |
| Shared data unchanged; DORA collector does not start | ✅ project registry (31 items) and DORA repositories (8) byte-identical between 00:32:51Z and 01:08:19Z; no collector start in that window | DynamoDB scans hashed before and after; collector log |
| `pages_tested` 10, final JSON parses | ✅ 10; parsed (`overall: FAIL` from 6 findings about the app itself, outside this change) | the report |
| Password absent from the reply | ✅ absent from all 4 published artifacts (each pass's report and summary), for both logins | checked as a boolean against both secrets, never printed |

Also observed: the invoke spans list exactly `browser`, `code_interpreter`, `read`, `retrieve_context`, `shell`, `skills`
for both passes (the #80 tool list).

Reported by other sessions, not re-checked here:
- The Ops Console Run QA batch `66dd43e05383` (01:05:05–01:07:00Z) loaded the skill (1 `skills` call), `readonly: ok`.
- A second allowedTools run (01:35:37–01:41:55Z, on the token-monitoring feature-52 branch): skills → shell, `readonly: ok`.
  The data part was checked: the registry was unchanged, and in the DORA repositories only collector-maintained fields
  changed, all from the scheduled 01:19:32Z run.

The QA passwords were rotated after the last of these sign-ins (01:46:12Z and 01:46:17Z), because every run types them
into the model-invocation log.
