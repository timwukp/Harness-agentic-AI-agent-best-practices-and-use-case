# qa_tool_guard: a `before_tool_call` hook for the QA harnesses

A Lambda that the UI test harness calls before every tool call. It returns `allow` or `deny`. A deny skips the call and
the agent loop continues (harness lifecycle hooks:
<https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-lifecycle-hooks.html>). It enforces, at the tool
boundary, the shared-app safety rules that the prompt (`SAFETY_RULES`) and the ui-testing skill state as guidance:
- no write-type clicks;
- no non-GET requests from a script, shell or code;
- navigation and script requests only to the allowed origins;
- typing only into the sign-in form in the admin pass;
- deny when the context is truncated or the payload is malformed.

The prompt rules stay. Without them the model keeps trying calls the guard denies and burns iterations. The real
control remains the app's server refusing a non-admin's writes. The guard is defense in depth.

## Files

| File | Role |
|---|---|
| `qa_tool_guard_spec.json` | **The one copy of the rules**: control words, patterns, tool and action lists, rule ids and texts, the hook entry, the deploy settings, assumptions, and the consumer rule |
| `qa_tool_guard.py` | The handler. It applies the spec and holds no rule of its own (a test checks this). It returns only `{decision, reason}` with reason `<rule id>: <rule text>`, and logs one line of spec-listed fields. It never logs or echoes tool input |
| `qa_tool_guard_cases.json` | 102 full hook payloads with the expected decision and rule id |
| `qa_tool_guard_stream_cases.json` | 14 InvokeHarness event streams with the verdict a consumer must compute (`ok` / `violated` / `unobserved`) |
| `qa_tool_guard_consumer.py` | The reference consumer: it reads the guard's `hookEvent` decisions from a stream |
| `SHA256SUMS` | Pins for the spec and both fixtures. Vendored copies (token-monitoring, ops-console) compare against it |
| `deploy_qa_tool_guard.py` | `plan` / `apply` / `verify` / `rollback` / `remove` for the Lambda, its role, log group, alias `live`, the execution role's invoke grant, and an alarm. It never touches the harness |
| `test_*.py`, `mutate_*.py` | Stdlib tests and mutation checks, below |

## Run the checks (no AWS access needed)

```bash
cd agentcore/hooks/qa_tool_guard
python3 -m unittest test_qa_tool_guard test_qa_tool_guard_consumer test_deploy_qa_tool_guard
python3 mutate_qa_tool_guard.py         # every spec/handler mutant must turn the suite red
python3 mutate_deploy_qa_tool_guard.py  # every deploy-script mutant must turn its tests red
```

## Turn it on and off

**On:**
1. `deploy_qa_tool_guard.py apply --origins <app,api,cognito origins>`, then `verify`.
2. `agentcore/scripts/tighten_harness_config.py --hooks on`. It reads `hookConfig` here verbatim and fills the arn from
   `deploy.aliasArnTemplate`.

**Off:**
1. `tighten_harness_config.py --hooks off --allow-narrowing`, plus `--allow-empty-hooks` when the guard is the only hook.
2. `deploy_qa_tool_guard.py remove`, which is refused while any hook still targets the guard.

**Roll back the guard's code or origins:** `deploy_qa_tool_guard.py rollback`. It moves the alias and needs no
UpdateHarness.

Both scripts need botocore **1.43.120 or later**. Older models lack `UpdateHarness.hooks` and the `hookEvent` stream
event. A consumer on an older SDK sees no decisions, so it reports `unobserved` (red), never `ok`.

## Known limits

- **Pattern matching on model-written input** can't prove a script harmless. It denies the known write paths (clicks
  on write-type controls, non-GET methods, `sendBeacon`, `requestSubmit`, `curl -d`, off-list hosts) and fails closed
  on anything unrecognised.
- **Admin strict mode keys on `sessionId` ending in `-admin`.** That the hook's `sessionId` equals the caller's
  `runtimeSessionId` is unverified until the live check (`agentcore/scripts/VERIFICATION_issue_89.md`, 4b).
- **Deprecated `file_operations` events** (harnesses created before 2026-11-12) are allowed for `view` only, until
  2026-12-12. A dated test fails from that day to force removing the allowance.
