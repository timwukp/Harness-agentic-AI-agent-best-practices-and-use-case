---
name: ui-testing
description: UI testing methodology for the UI Test Agent — the harness browser tool, sign-in from Secrets Manager, what to check on each page, severity classification, and the final JSON report the CI orchestrator parses
---

# UI Testing Skill

You test a deployed web application through the harness tools. The CI caller
(`ci-agent/qa_agent.py` in the reference deployment) gives you the target URL,
the Secrets Manager secret ID for the login, the S3 location for artifacts, and
the exact report schema. Where the caller's prompt and this skill differ, follow
the prompt.

## Tools

With the reference configuration (`allowedTools: ["*"]`) the harness offers
`browser`, `shell` and `code_interpreter`, described below, plus built-in tools
for files, web fetch, sub-agents, memory, to-dos and `skills`. The built-in set
changes with the platform.

- **`browser`** is one tool; you choose `action.type`. Start with `init_session`
  (give a `session_name` and a `description`), then pass the same `session_name`
  to every later call. Main actions:
  - `navigate` (`url`), `back`, `refresh`
  - `click` and `type` (a CSS `selector`; `type` also takes `text`), `press_key`
  - `get_text` (`selector`), `get_html`, `evaluate` (a JavaScript `script`)
  - `screenshot` (optional `path`)
  - `list_tabs`, `new_tab`, `switch_tab`, `close_tab`
  - `network_intercept` (a URL `pattern`), `execute_cdp`

  There is no accessibility-tree action and no action that returns console
  messages or the network log. Find elements with `get_html` or `evaluate`, and
  address them by CSS selector (`button[type=submit]`, `[aria-label="…"]`,
  `a[href="/usage"]`).
- **`shell`** runs bash in the harness runtime, with the harness execution role.
- **`code_interpreter`** is a separate sandbox. The AWS-managed default Code
  Interpreter has no AWS credentials: boto3 calls there raise `NoCredentialsError`.

## Signing in

- The login is in **AWS Secrets Manager**, not in environment variables. The
  caller names the secret ID; the secret's JSON holds the app URL and the sign-in
  email and password.
- Read it with boto3 `secretsmanager.get_secret_value`, run from `shell` (for
  example `python3 - <<'EOF' … EOF`). If you try `code_interpreter` first and get
  `NoCredentialsError`, switch to `shell`; don't retry the sandbox.
- The password has to reach the `type` action, so it passes through your context
  once. Don't repeat it anywhere else: not in your text, reports, findings,
  evidence, file names or the final JSON.
- Sign in, wait for the app shell (for example the sidebar navigation), and take a
  screenshot. If sign-in fails, quote the exact error and stop (see "When you
  can't test").

## Testing each page

### Before checking a page
1. Navigate, then wait until it has rendered: no spinner, and the content you
   expect is present (check with `get_text` or `evaluate`).
2. Install error capture with `evaluate`: handlers for `error` and
   `unhandledrejection`, and a wrapper around `fetch` and `XMLHttpRequest` that
   records non-2xx responses. A full page load clears them, so install them again
   after each `navigate`. Client-side route changes keep them.
3. Take a screenshot as the baseline. Note the URL and `document.title`.

### Interacting
- **Click:** prefer buttons, links and menu items. Use a selector that names the
  element, not a position.
- **Type:** clear the field first, then type. Read the value back with `evaluate`.
- **Forms:** after submitting, wait for the navigation or the response before
  judging the result.
- **Dialogs:** check for `[role=dialog]` with `evaluate`.
- Interact where it tests something: hover a chart, sort a table, toggle a control.

### After each action
1. Did the expected UI change happen?
2. Read back the captured errors and failed requests with `evaluate`.
3. Is the page still responsive?
4. Take an "after" screenshot.

### Across pages
Cross-check values that should agree between pages (totals, counts, dates). A
mismatch is at least HIGH. If the page itself discloses and quantifies a
difference, that is expected behaviour, unless the stated cause can't account for
the size or direction of the gap.

## Severity classification

- **CRITICAL:** application crash, data loss, security vulnerability
- **HIGH:** core functionality broken; the user cannot complete a primary task
- **MEDIUM:** the feature works but behaves incorrectly, or the UX is poor
- **LOW:** cosmetic issues, minor text errors, alignment problems

Only CRITICAL, HIGH and MEDIUM findings go to the Bug-Fix Agent. LOW findings
are reported only.

## Common failure patterns

- Element not found → check that the page finished rendering; SPAs render late.
- Timeout → the page may be slow; wait longer before filing it.
- Unexpected redirect → check for an expired session or a server error.
- Captured error → record the full message and stack.
- Visual mismatch → take a screenshot and describe the difference.

## Report

1. Write `/mnt/reports/test-report-latest.json`, `/mnt/reports/summary.md` and
   `/mnt/reports/screenshots/`, and upload them to the S3 prefix the caller gives
   (with boto3 from `shell`, which has the role). The caller also uploads the
   report it parsed, so the final JSON is the copy that counts.
2. End your reply with **one fenced `json` block** holding the object the caller
   asks for:
   `{"overall": "PASS"|"FAIL", "pages_tested": <int>, "findings": [{"id", "page", "severity", "summary", "evidence", "suspected_source"}]}`.
   When the caller passes prior findings, add `"reconciliation"` with one entry
   per prior finding, `FIXED` or `STILL_FAILING`. A prior finding that still
   reproduces goes in `findings` too.
3. Every problem you noticed must be in `findings`. The caller derives the verdict
   from `findings`, not from your `overall`, so a problem described only in prose
   is lost. An explicitly empty `findings` list means PASS.
4. Set `suspected_source` to a repo-relative file path when you can tell which
   file is at fault. The Bug-Fix orchestrator gives that exact file to the
   Bug-Fix Agent when the path exists; otherwise it guesses from keywords in file
   names.
5. If you run low on steps or time, stop exploring and emit the JSON with what you
   have.

## When you can't test

The report has no BLOCKED verdict. If sign-in fails, a CAPTCHA appears, or the
site returns 5xx, stop and file one finding that quotes the exact error, and set
`pages_tested` to the pages you actually covered. Never report PASS for a run that
couldn't test. If you hit a redirect loop, stop after 3 attempts.
