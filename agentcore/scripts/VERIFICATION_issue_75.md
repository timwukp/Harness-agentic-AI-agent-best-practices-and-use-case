# Issue #75 Verification — `tighten_harness_config.py` must not regress the live harnesses

Live state read 2026-11-27 with `get_harness` / `list_tags_for_resource` (read-only),
boto3 1.43.68, region us-east-1.

| Field | UITestAgentHarness v8 | BugFixAgentHarness v7 |
|---|---|---|
| model | `global.anthropic.claude-sonnet-5-5` | `global.anthropic.claude-opus-5-5` |
| allowedTools | `["*"]` | `["code_interpreter"]` |
| maxTokens / maxIterations / timeoutSeconds | 65536 / 100 / 3600 | 131072 / 30 / 1800 |
| tag `environment` | `production` | `production` |

## The regression, reproduced

`--dry-run` of the script on `main` against the live harnesses (exit code 0):

```
=== UITestAgentHarness ===
  → drift detected:
      allowedTools: ['*'] → ['browser', 'code_interpreter']
=== BugFixAgentHarness ===
  → drift detected:
      maxTokens: 131072 → 32768
⚠ Dry run complete — drifts detected. Re-run without --dry-run to apply.
```

Applying it would have:
- removed `shell` from the UI agent. The agent reads the login secret through `shell`:
  the AWS-managed Code Interpreter has no AWS credentials (`NoCredentialsError`).
- cut the Bug-Fix agent's output budget to a quarter (AGENTS.md §3.15 raised it
  32k → 131072 for a reason).

## Why `["*"]` for the UI harness, not a glob list

From `aws/spans`, the six retained UI sessions (2026-10-29 → 10-30):
- `gen_ai.agent.tools` on every `invoke_agent` span:
  `["shell", "file_operations", "browser", "code_interpreter", "skills"]`.
- `execute_tool` spans: `browser` 377, `shell` 36, `code_interpreter` 16.
- 5 `Secrets Manager.GetSecretValue` spans, emitted by the harness runtime.

`["browser_*", "code_interpreter*", "skills"]` (AGENTS.md §3.11.3) drops `shell`. Under
glob semantics, `browser_*` doesn't match the runtime tool name `browser` either.
Narrowing below `"*"` needs its own live test.

## The new script against the live harnesses (`--dry-run`, default `--environment dev`)

Exit code 4 (drift found; nothing narrows or lowers):

```
=== UITestAgentHarness ===
  version: 8   status: READY
  model:   global.anthropic.claude-sonnet-5-5
  field                live                     desired                  verdict
  allowedTools         ['*']                    ['*']                    same
  maxTokens            65536                    65536                    same
  maxIterations        100                      100                      same
  timeoutSeconds       3600                     3600                     same
  tag team             'qa-platform'            'qa-platform'            same
  tag cost-center      'engineering'            'engineering'            same
  tag agent-type       'ui-test'                'ui-test'                same
  tag environment      'production'             'dev'                    change

=== BugFixAgentHarness ===
  version: 7   status: READY
  model:   global.anthropic.claude-opus-5-5
  field                live                     desired                  verdict
  allowedTools         ['code_interpreter']     ['code_interpreter']     same
  maxTokens            131072                   131072                   same
  maxIterations        30                       30                       same
  timeoutSeconds       1800                     1800                     same
  tag team             'qa-platform'            'qa-platform'            same
  tag cost-center      'engineering'            'engineering'            same
  tag agent-type       'bug-fix'                'bug-fix'                same
  tag environment      'production'             'dev'                    change

regressions: 0
```

With `--environment production`, every row is `same` and the exit code is 0.

## Offline checks (fake control plane, no AWS calls)

20 checks, all passing:
- the classifier marks `["*"] → list` and `["*"] → globs` as NARROW, and `131072 → 32768` as LOWER;
- `find_harness` finds a harness on the last page of a paginated `list_harnesses`;
- the old DESIRED gives exit 5 on `--dry-run`, and plain apply refuses it with no `update_harness` call;
- with `--allow-narrowing`, `update_harness` carries only the drifting fields;
- plain apply sets `environment=dev` through `tag_resource`, makes no `update_harness` call,
  and the re-run makes no calls;
- a missing harness gives exit 1;
- a different live model prints the re-size warning.

Mutation check: breaking LOWER detection, pagination, or the missing-harness exit each
turns at least one check red.

## 4a. API-level live test

- [x] Dry run against both live harnesses (above): 0 tool or limit changes.
- [ ] Apply: changing the live `environment` tag is an owner account operation. Run
      `python agentcore/scripts/tighten_harness_config.py` (two `tag_resource` calls, no
      `update_harness`), then re-run it: expect exit 0 and "No changes needed", and a
      `--dry-run` with exit 0.

## 4b. Functional / E2E test

No tool list or limit changes, so the harnesses keep running what they ran on 2026-10-29/30
(the six sessions above; the pr-113 round passed with 10 pages tested). The `environment` tag
has no runtime effect. The post-merge QA and Bug-Fix invokes planned for issue #76 (skills)
run under exactly this config.
