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

## 4b results
Pending.
