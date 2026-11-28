# Issue #93 Verification — `eval_runner.py` invokes the harness, tests the in-repo demo page, and fails on a wrong verdict

> 4b **passed live on 2026-11-28** (owner-approved): 5/5 on the default endpoint and 5/5 through `--qualifier DEFAULT`. Results are at the end.

## Why
`app/ui-test-agent/eval_runner.py` v0.2.0 could not do its job, against either target:
- It called `invoke_agent_runtime(agentRuntimeArn=<harness ARN>, body=...)`. The harness's data-plane call is
  `InvokeHarness` (AGENTS.md §3.1). `InvokeAgentRuntime` also has no `body` member: its required members are
  `agentRuntimeArn` and `payload` (botocore 1.43.120). So botocore's parameter validation rejects every case before
  any request is sent, and every run ends 0/6 with exit 1. This is read from the model and reproduced with the
  validating double below, not run against botocore itself.
- It never read `expected_status`. A case passed when the reply contained any `must_contain` keyword, and a reply
  with the opposite verdict still names the keyword.
- With no cases it exited 0 (`failed == 0`).

**Readers** (line numbers on `main@c839d7c`). Nothing in the repo runs the script:
- `.github/workflows/ui-test.yml:66` runs `invoke.py`.
- No Makefile, no script and no test imports it.

Only documents tell a person to run it:
- `app/ui-test-agent/README.md:37`
- `docs/ARCHITECTURE.md:722`, `:781`, `:796`
- `docs/DESIGN_UI_TEST_AGENT.md:382`
- `docs/PRODUCTION_HARDENING.md:35`, `:152`, `:475–498`, `:636`
- `agentcore/scripts/VERIFICATION_issue_29.md:192`, `:203` (left ⏳; it could not have passed)

**Fix, not retire.** #20 asked for a daily scheduled run of this script, to catch regressions on the live agent.
Online evaluation already does that: it is enabled on the live harness with 100% sampling (2026-11-27 triage), and
the proposed triage moves the alarm onto its score (#18). What online evaluation cannot do is check a change
*before* it is live, against a page whose answers are known: a live session carries no expected verdict.

Harness changes land often (#24, #26, #29, #75, #80). #80's functional check ran a full QA pass on a throwaway copy,
and that pass checks structure (the tools offered, pages tested, persona). It does not check that a known bug is
called FAIL. A fixed runner does that, against a copy or a candidate endpoint (`--qualifier`), in 5 short sessions.
It is a pre-promotion check, not a scheduled job.

**Why the target changed.** v0.2.0's six cases all targeted the third-party `the-internet.herokuapp.com`, and three
things rule that site out:
- **Blocked by planned work.** The WS2 guard (`qa_tool_guard`, #89) and the WS4 custom browser (#90) allow only the
  app's own origins, so those cases would go permanently red.
- **Unreachable in VPC mode.** A customer running the harness in VPC mode may not reach the site at all.
- **Outside our control.** The site's content can change without notice.

The golden set now targets the in-repo demo page, `app/demo-frontend/index.html`. It marks five deliberate bugs,
`BUG 1` … `BUG 5`, and PROJECT_STATE.md:89, 215 describe it. Its URL is a parameter (`--target-url`), with no default.
An install hosts the page on an allow-listed origin of the customer's own.

## The golden set, derived from `app/demo-frontend/index.html`

A golden case must have an answer every competent tester agrees on. So there is one case per **observable** defect,
not one per comment marker.

| Case | Page markers | Lines | Derivation | Expected | Keyword |
|---|---|---|---|---|---|
| GT-LOGIN | none | 64–65 | `admin` / `password123` shows "Login successful! Welcome, admin" | PASS | `login successful` |
| GT-OVERLAY | BUG 1, BUG 3 | 11, 14, 20–21, 33, 36–37 | A transparent `.overlay-bug`, 20 px tall with `margin-top: -25px` and z-index 10, sits after the password group (15 px bottom margin). It covers the lower-left of the Password field, so clicks there don't reach the input | FAIL | `overlay`, `transparent` |
| GT-BUG2 | BUG 2 | 17–18, 69–70 | Wrong credentials show `.error-message`, and its `color` is green | FAIL | `green` |
| GT-BUG4 | BUG 4 | 56–57, 69 | Only the username is checked, so `admin` with an empty password reaches the server-error message | FAIL | `server error` |
| GT-BUG5 | BUG 5 | 68–69 | Wrong credentials show "Internal server error. Please try again later." | FAIL | `server error` |

- **Citations.** Each case carries `source`, a list of (line, text) pairs, and the tests check every pair against the
  file: 18 citations.
- **Markers.** `bugs` lists the page markers a case covers, and each FAIL case cites each of its markers. Each marker
  maps to exactly one case. `BUG 1` and `BUG 3` must share one, and no other markers may. So a future recall figure
  never counts the overlay twice.
- **Keywords and hosts.** Every keyword occurs in the page. No prompt names a host: `{url}` is replaced with
  `--target-url`.

**BUG 1 and BUG 3: the page's comments are wrong about the rendered page.**
- **What the comments say.** The comments (index.html:14, 20, 36) say the overlay covers the submit button.
- **What a browser shows.** Measured by the commander session on 2026-11-28 in the built-in browser at 1280×800 (a
  first read at 0×0 was invalid and discarded):

  | Element | Top (px) | Bottom (px) |
  |---|---|---|
  | `.overlay-bug` | 306.9 | 326.9 |
  | Password field | 279.4 | 316.9 |
  | Login button | 331.9 | 374.4 |

- **The effect.** The gap above the button is 5.0 px, with no overlap.
  - `elementFromPoint` hit the button at 81 of 81 points on the button.
  - It hit the overlay at 8 of 81 points on the Password field, in the lower-left.

  This agrees with the CSS worked by hand before the measurement: index.html:21 (20 px tall, `margin-top: -25px`)
  after index.html:11 (a 15 px margin).
- **What the case asks.** "The button is stacked under a z-index-10 element" is a fact of the code, not a defect a
  tester can observe: the button works everywhere. A competent agent would answer PASS, and the case would score that
  as wrong. So the old BUG 1 case is gone. The one overlay case, GT-OVERLAY, asks about the Password field, and a test
  checks that its prompt does not mention the button.
- **The page itself is not edited.** Run #9's history and the GitHub Pages mirror refer to those bytes. Fixing the
  BUG 1 and BUG 3 comments is a follow-up for the owner.

## Pre-merge checks (2026-11-28, offline, on `main@c839d7c` + this change)

**Tests:** `app/ui-test-agent/test_eval_runner.py`, 44 tests, stdlib only. The demo page itself is unchanged
(sha256 `4d0d02e989af498e…`, the same as its `docs/demo/index.html` mirror and the hosted copy).

- **The double.** The fake `boto3` validates each request against the request members and required members of
  botocore 1.43.120, as botocore's parameter validation does. It also checks the session-ID length (33–100) and the
  message union. It replays scripted `InvokeHarness` streams with tool-use, hook and reasoning events mixed in.
- **What the tests cover:**
  - **The golden set and the page agree.**
    - The runner names the same page as the test.
    - There are 5 cases, 1 PASS and 4 FAIL, and the expected verdict follows from the markers.
    - The marker map follows its rule. The rule's own test gives six bad sets, each breaking exactly one part of it.
    - Every citation matches its line, each FAIL case cites its markers, and every keyword occurs in the page.
    - No prompt names a host, and the overlay case asks about the Password field, not the button.
  - **The request.**
    - `invoke_harness` is called once per case, and `invoke_agent_runtime` never is.
    - The request carries exactly `harnessArn`, `runtimeSessionId`, `actorId`, `messages`, plus `qualifier` when
      given. No per-call override field is sent (`model`, `systemPrompt`, `tools`, `skills`, `allowedTools`,
      `maxTokens`, `maxIterations`, `timeoutSeconds`).
    - `--target-url` reaches every prompt exactly once, for two different URLs.
    - Each case gets its own session ID, and the `actorId` is new for each run and shared by its cases.
    - The read timeout is at least 900 s.
  - **The verdict.**
    - A wrong verdict is a `MISMATCH`, even when the reply names the evidence keyword.
    - The last verdict line wins, read case-insensitively through Markdown.
    - A verdict is a whole line: the restated options, the echoed instruction and a verdict at the end of a sentence
      are not verdicts. A verdict in its own text block, or after a tool call, starts its own line.
  - **ERRORs.** Each of these is an `ERROR`: no verdict line; a verdict only in tool input or reasoning; a stop reason
    other than `end_turn`; no `messageStop`; an error event; a failed call; a stream broken mid-way. A failed case does
    not stop the run.
  - **Evidence.** The evidence check needs any one keyword, not all of them.
  - **Zero cases** is a failure, in-process, and on the CLI with an emptied case list: exactly exit 1, with
    "No golden case ran".
  - **The CLI.**
    - Exit 0 when all pass, 1 on a mismatch.
    - Exit 2, with no call made, for each of these: a runtime ARN; a bad endpoint name; a missing `--target-url`; a
      `--target-url` that is not an http(s) URL with a host; a `--target-url` with whitespace.
    - It prints every session ID, and the end of the reply for each red case.
- **The CLI tests** run `python -B eval_runner.py` as a subprocess with the fake on `PYTHONPATH`, so the asserted exit
  codes are what a shell sees.

| Run | Python 3.14.7 | Python 3.12.12 |
|---|---|---|
| **Red:** the new tests against the **base** `eval_runner.py` (sha256 `0a2644958c093fbc…`) | 43 of 44 red (15 fail, 28 error) | the same 43, by name |
| **Green:** this change | 44 / 44 ok, 0 skipped | 44 / 44 ok, 0 skipped |
| `mutate_eval_runner.py` (fresh temp copy of the runner, the tests and the page per mutant, `-B`, `PYTHONDONTWRITEBYTECODE=1`) | 44 mutants, 44 killed | 44 mutants, 44 killed |

- **The one green test on the base** checks the test's own marker-map rule with synthetic cases. It reads nothing
  from the runner.
- **Edits to the test's marker-map rule.** Dropping any one of its five checks turns that rule's test red (probed on
  a temp copy).

**The base's behavior, probed directly.** Most of the base's reds above are interface errors, because the base has no
`--target-url` and no `source` fields. So three probes run the base's own code (the same on both Pythons):
- **Its CLI with its own arguments**, against the validating double: 6/6
  `ERROR: InvokeAgentRuntime: unknown parameters ['body'], missing required ['payload']`, exit 1.
- **Its check, with a double that accepts its call:** six replies, each carrying the *opposite* verdict and the evidence
  keyword, scored 6 passed / 0 failed.
- **Its CLI with the case list emptied:** `Results: 0/0 passed`, exit 0.

**Mutants.** Each one is killed by the test written for it. A no-op mutant (a trailing comment) survives, so the
harness tells a change in behavior from no change. Its own refusals exit 2: a mutation text not found exactly once,
and a mutant that does not compile (probed). The mutants:
- **The call and its arguments:**
  - `invoke_agent_runtime` again;
  - qualifier dropped;
  - `maxTokens` or `skills` override sent;
  - verdict instruction dropped;
  - one session for all cases;
  - actorId reused across runs;
  - the default 60 s read timeout.
- **The target URL:**
  - not substituted into the prompt;
  - unchecked;
  - any scheme accepted;
  - host not required;
  - whitespace accepted;
  - a third-party default instead of a required argument;
  - a prompt that hard-codes a host.
- **The golden set:**
  - the BUG 2 case expects PASS;
  - the BUG 4 case relabeled as BUG 5;
  - the PASS case given a bug;
  - BUG 1 dropped from the overlay case;
  - the overlay case asks about the button;
  - a citation off by one line;
  - a keyword not on the page;
  - the runner names another page.
- **Reading the stream:**
  - `stopReason` ignored;
  - missing `messageStop` read as `end_turn`;
  - stream error event ignored;
  - tool input read as the reply;
  - text blocks joined without a break;
  - a break only on an index change.
- **Judging the verdict:**
  - `expected_status` not compared;
  - first verdict wins;
  - verdict case-sensitive;
  - verdict line start or end not anchored (two mutants);
  - evidence needs every keyword;
  - evidence check removed.
- **The run and the exit code:**
  - call error aborts the run;
  - zero cases pass;
  - exit code ignores failures;
  - `main` always exits 0;
  - session ID not printed;
  - red reply not shown.
- **The other arguments:**
  - runtime ARN accepted;
  - qualifier format unchecked.

**Edits to the page turn the suite red.** On a temp copy, each of these edits to `index.html` fails the citation
test:
- fixing BUG 2 (`color: red`);
- fixing BUG 4 (checking the password);
- fixing BUG 5 (an invalid-credentials message);
- adding a `BUG 6` marker, which the marker-map test also catches.

A no-op edit to the page stays green. Changing the page therefore means updating the golden set in the same change.

**API shape** (read from `botocore/data/bedrock-agentcore/2024-02-28/service-2.json.gz`, 1.43.120, without importing
botocore):
- The test's member lists equal the model's, for `InvokeHarness` (18 members) and `InvokeAgentRuntime` (16).
- The `HarnessArn` and `HarnessEndpointName` patterns are copied verbatim into the script.
- The stream's three exception members are the three in `STREAM_ERRORS`.
- The override fields are all `InvokeHarness` members. The script sends only `harnessArn`, `runtimeSessionId`
  (a header), `actorId`, `messages` and `qualifier`.

**Public-repo hygiene:** the tests use the documentation account `111122223333`, a made-up harness ID and `.test`
hosts. No real account, ARN or host is added. The hosted mirror's URL appears only in 4b below.

## 4b. Pending live: one golden run against the live UI harness
Run it from the repo root with credentials for the dev account. Use boto3/botocore 1.43.120: the model this change was
checked against, and CI's pin (VERIFICATION_issue_89.md). AGENTS.md §2's floor of 1.43.18 is for the control-plane
harness operations, and no older model was checked for `qualifier`. The run only invokes: it changes no harness
configuration.

**Target.** The hosted copy today is the GitHub Pages mirror of `docs/demo/index.html` (PROJECT_STATE.md:120, URL from
`app/ui-test-agent/e2e_pipeline.py:21`). On 2026-11-28 the commander session saw it return 200, with the repo file's
sha256. An install would host `app/demo-frontend/` on an allow-listed origin of the customer's own, and pass that URL
instead.

**Pre-flight:**
- The hosted page must still be that file.
- The #89 guard and the #90 custom browser must not be attached yet: neither allows the Pages origin.
- `DEFAULT` exists: on 2026-11-28 a live `get-harness-endpoint` showed `DEFAULT`, READY, `liveVersion` 11. Re-read it,
  because the run is against the version live at that time.

```bash
REGION=us-east-1
DEMO_PAGE_URL="https://timwukp.github.io/Harness-agentic-AI-agent-best-practices-and-use-case/demo/index.html"
curl -fsS "$DEMO_PAGE_URL" | shasum -a 256; shasum -a 256 app/demo-frontend/index.html   # must be equal
HARNESS_ID=$(aws bedrock-agentcore-control list-harnesses --region $REGION \
  --query "harnesses[?harnessName=='UITestAgentHarness'].harnessId | [0]" --output text)
HARNESS_ARN=$(aws bedrock-agentcore-control list-harnesses --region $REGION \
  --query "harnesses[?harnessName=='UITestAgentHarness'].arn | [0]" --output text)
aws bedrock-agentcore-control get-harness --region $REGION --harness-id "$HARNESS_ID" \
  --query 'harness.{version: harnessVersion, hooks: hooks}'          # record the version; hooks must be empty or null
aws bedrock-agentcore-control list-harness-endpoints --region $REGION --harness-id "$HARNESS_ID" \
  --query 'endpoints[].{name: endpointName, live: liveVersion, status: status}'   # record them

python3 app/ui-test-agent/eval_runner.py --harness-arn "$HARNESS_ARN" --target-url "$DEMO_PAGE_URL" --region $REGION
echo "exit=$?"
python3 app/ui-test-agent/eval_runner.py --harness-arn "$HARNESS_ARN" --target-url "$DEMO_PAGE_URL" \
  --qualifier DEFAULT --region $REGION
echo "exit=$?"
```

Pass criteria, written before the run:

| Criterion | Pass when |
|---|---|
| Verdicts | Both runs (default endpoint, then `--qualifier DEFAULT`) exit 0 with `Results: 5/5 passed` |
| Pinned config | For each printed session ID, the `invoke_agent` span shows the harness's own model and `gen_ai.agent.tools` = the six tools in `tighten_harness_config.py` `DESIRED`. That shows no per-call override reached the service |
| Stream contract | No case is an `ERROR` for `no VERDICT line`. If one is, its `reply ends:` line shows which of two causes it is: the reply text is not in `contentBlockDelta.delta.text` (the line is empty), or the agent did not put the verdict on a line of its own |
| GT-OVERLAY | The reply places the overlay on the Password field (its lower part or lower-left), not on the button |
| Stopping rule | A red run is re-run once, and both are reported. A case red in both is a finding, and 4b fails. A case red in only one is recorded as run-to-run variation. 4b still needs a 5/5 run, and it gets no further re-runs |

**Cost:** not measured. The design estimate in PRODUCTION_HARDENING.md §5 is about $0.32 per case. That is about $1.60
per run of 5, and $3.20 for the two runs. The first run's token usage (from its spans) replaces the estimate here.

**Side effect:** each run writes Memory events under its own actor, `golden-eval-<12 hex>`, and they expire with the
memory's event expiry.

## Not covered
- **The live stream.** Only 4b shows whether the live reply keeps its text in `contentBlockDelta.delta.text`, and
  whether the agent, under the ui-testing skill, puts the verdict on a line of its own. A verdict written inside a
  sentence is an `ERROR`, a loud red rather than a silent pass.
- **Follow-up for the owner: fix the demo page's BUG 1 and BUG 3 comments** (index.html:14, 20, 36). Rendered, the
  overlay covers the Password field, not the submit button. This change leaves the page's bytes alone.
- **Hosting and allow-lists** (out of scope):
  - hosting `app/demo-frontend/` inside the customer's account is a WS6 installer item;
  - adding its origin to the `qa_tool_guard` origin list (#89) and the custom browser's URL allow-list (#90) belongs
    to those changes.
- **The Strands Runtime.** The runner does not invoke `main.py` through `InvokeAgentRuntime`. The v0.2.0 runner could
  not either, because botocore rejected its `body` argument.
- **Files this change did not edit**, because other sessions own them:
  - `README.md:255`: the tree does not list `test_eval_runner.py` and `mutate_eval_runner.py`;
  - `AGENTS.md` §3.7: the actorId convention does not list `golden-eval-<run>`;
  - `VERIFICATION_issue_29.md:203`: it still shows the v0.2.0 command, with no `--target-url`, and expects "≥ 5/6".
    The runner now needs `--target-url`, and exits 0 only when all 5 cases pass.
- **`app/ui-test-agent/test_config.json` has no reader.** Only `README.md:258` lists it. It is left as it is.

## Results
_4b run on 2026-11-28 by the commander session, on the owner's "Approve 4b"._

**Pre-flight** (10:27:20Z):
- The hosted page's sha256 equals `app/demo-frontend/index.html` (`4d0d02e989af498e…`).
- UITestAgentHarness is v11, READY. `hooks` is null, and the browser is the managed `aws.browser.v1`, so neither the
  #89 guard nor the #90 custom browser is attached.
- `DEFAULT` is READY, with `liveVersion` 11.
- The client is boto3/botocore 1.43.120.

| Criterion | Result |
|---|---|
| Verdicts | **PASS.** Run 1 (default endpoint, 10:28:08–10:31:12Z, actorId `golden-eval-1fd74f6ba0da`): `Results: 5/5 passed`, exit 0. Run 2 (`--qualifier DEFAULT`, 10:31:34–10:33:43Z, actorId `golden-eval-4b165bf1b504`): `Results: 5/5 passed`, exit 0 |
| Pinned config | **PASS, 10/10 sessions.** Each `invoke_agent` span (aws/spans) shows `gen_ai.request.model` = `global.anthropic.claude-sonnet-5-5`, which is the harness's own `modelId`. `gen_ai.agent.tools` is exactly {shell, read, browser, code_interpreter, retrieve_context, skills}, which is the six-tool `allowedTools`. `harness.endpoint.qualifier` is `DEFAULT` for both runs. So no per-call override reached the service |
| Stream contract | **PASS.** No case was an ERROR. Every reply carried its verdict on its own line |
| GT-OVERLAY | **PASS in both runs.** The replies were read back from Memory events. Run 1 (`8135ed26…`): "div.overlay-bug … covers the bottom-left part of input#password … Clicks there hit the overlay instead of the input" (225 of 816 sampled points). Run 2 (`017eb0e1…`): the overlay covers "the bottom ~7 px of the input, across about the left 190 px" (160 of 656 points). Neither places it on the button |
| Stopping rule | Not invoked. No red run |

**Sessions** (all are `golden-eval-*` actors; exclude them from online-evaluation and quality figures):
- Run 1: f96e2619…, 8135ed26…, 02b0723e…, a8bf0dab…, a7d2441a…
- Run 2: 496cdd62…, 017eb0e1…, d10d7953…, 8d3c8d4a…, 68f5028d…

**Token use** (`invoke_agent` spans, 10 sessions):
- **Input:** 1,570,613 tokens. Of these, 1,507,003 (96%) were cache reads, 63,418 were cache writes, and about 190 were
  uncached.
- **Output:** 17,530 tokens.
- **Per session:** about 157k input and 1.75k output, with the prompt cache doing most of the work.
- **Dollar cost:** not computed here. Multiply these tokens by the Bedrock list price for the model, or read Cost
  Explorer a day later.

**Measured timings:** about 3 min per run of 5 cases, against the 900 s read timeout.

**One spans note for the next run:** `aws/spans` lags. Two of run 2's spans appeared about 3–4 minutes after the run
ended. A Logs Insights query found them where a `filter-log-events` term pattern had returned nothing.
