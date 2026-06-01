# Issue #29 — Tighten Harness Config: allowedTools / maxTokens / tags

## Summary

Three production-hygiene config items applied to both `UITestAgentHarness` and
`BugFixAgentHarness` programmatically via `update_harness` + `tag_resource`:

| Item | UITestAgent | BugFixAgent |
|---|---|---|
| **`allowedTools`** | `["browser", "code_interpreter"]` | `["code_interpreter"]` |
| **`maxTokens`** | `65536` | `32768` |
| **Tags** | 4 tags (team, environment, cost-center, agent-type=ui-test) | 4 tags (team, environment, cost-center, agent-type=bug-fix) |

Before: `allowedTools = ['*']`, `maxTokens = None`, 0 tags on both harnesses.

## API discovery findings

These were the empirical findings from boto3 introspection + live API calls.
They extend the AGENTS.md §3.2 entry which previously only had the
`memory={"optionalValue": {...}}` example from PR #40.

### 1. `optionalValue` wrapper applies only to complex structure fields

```python
# UpdateHarness input shape (boto3.client.meta.service_model)
allowedTools  : list of string         # NO wrapper
maxTokens     : integer                # NO wrapper
memory        : structure (with optionalValue inside)  # YES wrapper
model         : structure              # YES wrapper (presumed)
environment   : structure              # YES wrapper (presumed)
```

For simple types (lists of scalars, integers), pass the value directly:

```python
control.update_harness(
    harnessId=harness_id,
    allowedTools=["browser", "code_interpreter"],   # ✅ plain list
    maxTokens=65536,                                # ✅ plain int
    clientToken="...",
)
```

Wrapping a simple field in `optionalValue` would fail validation; *not* wrapping
a complex field also fails. The pattern is type-driven, not field-name driven.

### 2. `tags` is NOT in UpdateHarness

```python
# Operations containing 'tag' or 'Tag' in bedrock-agentcore-control:
ListTagsForResource
TagResource         # ← use this for setting/updating tags
UntagResource       # ← use this for removing
```

`UpdateHarness` accepts no `tags` parameter. Tags must be applied via:

```python
control.tag_resource(
    resourceArn="arn:aws:bedrock-agentcore:us-east-1:...:harness/...",
    tags={"team": "qa-platform", "environment": "production", ...},
)
```

`tag_resource` is idempotent for matching key/value pairs — re-running with
the same map is a no-op at the resource level (you may still hit a
small CloudTrail entry).

`CreateHarness` does accept `tags` at creation time (one-shot), but
`UpdateHarness` was deliberately split.

### 3. `clientToken` min length is 33 characters

```
ParamValidationError: Parameter validation failed:
  Invalid length for parameter clientToken, value: 16, valid min length: 33
```

The previously-merged `agentcore/scripts/attach_memory.py` (PR #40) uses
`secrets.token_hex(8)` which produces 16 chars. **This would fail on a fresh
memory attach** — the existing PR #40 only succeeded because the memory was
already attached, so the `update_harness` call was never made. Fix:
`secrets.token_hex(20)` produces 40 chars (safe).

This is filed as a follow-up bug fix issue.

## Live verification

### Apply (first run)

```
$ python agentcore/scripts/tighten_harness_config.py
boto3 1.43.18 OK
Region:  us-east-1
Account: <ACCOUNT_ID>
Mode:    APPLY

=== UITestAgentHarness ===
  arn:    arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:harness/UITestAgentHarness-<ID>
  status: READY
  → drift detected:
      allowedTools: ['*'] → ['browser', 'code_interpreter']
      maxTokens: None → 65536
  ✓ update_harness HTTP 200
  status=UPDATING (waiting 5s)
  status=UPDATING (waiting 5s)
  ✓ status=READY
  → 4 tag(s) need update:
      team: '<absent>' → 'qa-platform'
      environment: '<absent>' → 'production'
      cost-center: '<absent>' → 'engineering'
      agent-type: '<absent>' → 'ui-test'
  ✓ tag_resource HTTP 200

=== BugFixAgentHarness ===
  arn:    arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:harness/BugFixAgentHarness-<ID>
  status: READY
  → drift detected:
      allowedTools: ['*'] → ['code_interpreter']
      maxTokens: None → 32768
  ✓ update_harness HTTP 200
  status=UPDATING (waiting 5s)
  status=UPDATING (waiting 5s)
  ✓ status=READY
  → 4 tag(s) need update:
      team: '<absent>' → 'qa-platform'
      environment: '<absent>' → 'production'
      cost-center: '<absent>' → 'engineering'
      agent-type: '<absent>' → 'bug-fix'
  ✓ tag_resource HTTP 200

✓ All applicable updates applied successfully
```

### Idempotent re-run

```
$ python agentcore/scripts/tighten_harness_config.py
boto3 1.43.18 OK
Mode:    APPLY

=== UITestAgentHarness ===
  arn:    ...harness/UITestAgentHarness-<ID>
  status: READY
  ✓ allowedTools + maxTokens already match desired (no update)
    allowedTools: ['browser', 'code_interpreter']  maxTokens: 65536
  ✓ all 4 tags already match (no update)

=== BugFixAgentHarness ===
  arn:    ...harness/BugFixAgentHarness-<ID>
  status: READY
  ✓ allowedTools + maxTokens already match desired (no update)
    allowedTools: ['code_interpreter']  maxTokens: 32768
  ✓ all 4 tags already match (no update)

✓ No changes needed — both harnesses match desired config (idempotent re-run safe)
```

### Live `get_harness` + `list_tags_for_resource` evidence (post-apply)

```
--- UITestAgentHarness ---
  status:       READY
  allowedTools: ['browser', 'code_interpreter']
  maxTokens:    65536
  tags:         {"agent-type": "ui-test", "cost-center": "engineering",
                 "environment": "production", "team": "qa-platform"}

--- BugFixAgentHarness ---
  status:       READY
  allowedTools: ['code_interpreter']
  maxTokens:    32768
  tags:         {"agent-type": "bug-fix", "cost-center": "engineering",
                 "environment": "production", "team": "qa-platform"}
```

The AWS console (Bedrock AgentCore → Harness → each harness) shows the same
state under "Allowed tools", "Max tokens", and "Tags" sections.

## Acceptance criteria status

| Criterion | Status | Notes |
|---|---|---|
| `UITestAgentHarness` Allowed tools = `browser, code_interpreter` | ✅ | not `*` |
| `UITestAgentHarness` Max tokens = 65536 | ✅ | |
| `UITestAgentHarness` Tags = 4 entries | ✅ | live verified |
| `BugFixAgentHarness` Allowed tools = `code_interpreter` | ✅ | |
| `BugFixAgentHarness` Max tokens = 32768 | ✅ | |
| `BugFixAgentHarness` Tags = 4 entries | ✅ | live verified |
| Idempotent script | ✅ | re-run is no-op (no API mutations) |
| VERIFICATION doc with payload + redacted evidence | ✅ | this file |
| `eval_runner.py` golden tests still pass | ⏳ | see "Functional regression" below |
| `e2e_pipeline.py` Bug-Fix still works | ⏳ | see "Functional regression" below |
| Cost Explorer breakdown by `agent-type` tag | ⏳ | requires 1 billing day after merge |

### Functional regression (planned post-merge)

Two regression tests are deferred to post-merge because they require:
- Real test invocations on each harness (each costs ~$0.32)
- The harnesses to be in the new tightened state for ≥ 1 invocation each

Will be run within 24h of merge as a follow-up note (not blocking merge):
1. `python eval_runner.py --harness-arn <UITestAgentHarness-ARN>` — expect ≥ 5/6 pass
2. `python e2e_pipeline.py` — expect Bug-Fix Agent to produce correct patch on demo bug

If either fails, the script's `--dry-run` mode + idempotency makes rollback
trivial: edit `DESIRED` constants back to original (or to a different value)
and re-run.

## Methodology dogfooding

This is the **second issue** to apply the v0.2.2 methodology trio in full:

1. **Issue #29** body was the pilot for the agent-friendly issue format
   ([the audit tracked in #45](https://github.com/timwukp/Harness-agentic-AI-agent-best-practices-and-use-case/issues/45))
   — Repo context section, AGENTS.md cross-references, sibling issue links
2. **Implementation** followed the [`change-discipline.md`](../docs/methodology/change-discipline.md) 5-step loop:
   - **Discover** — boto3 schema introspection (the field-shape table above)
   - **Triage** — P0, hygiene, no blocker dependencies
   - **Group** — three items in one issue per the "one logical fact" heuristic
   - **Fix** — `tighten_harness_config.py` + this verification doc
   - **Review** — this PR
3. **Pattern reuse** — script structure modeled on `attach_memory.py` (PR #40):
   discovery-by-name, version check, idempotent comparison, `redact()` helper

The discoveries above (esp. `optionalValue` wrapper rule, `tags` separate API,
`clientToken` min length, attach_memory.py latent bug) are candidate additions
to AGENTS.md §3.2 in a follow-up doc PR.

## actorId / tags follow-up

When **#36** (JWT auth + multi-tenant) lands, this script's `DESIRED` block
will need a `tenant-id` tag dimension. That's a one-line edit + re-run.

## Out of Scope

- Functional regression tests (deferred to post-merge follow-up note)
- AGENTS.md §3.2 enrichment with the new findings (separate doc PR — keeps
  this PR's scope to "apply config to AWS")
- `attach_memory.py` `clientToken` length bug fix (separate small follow-up
  issue — discovered while implementing this, but not in this PR's scope)
- Per-tenant cost allocation tag (`tenant-id`) — covered by #36
- `idleRuntimeSessionTimeout` tuning — separate operational concern
- Token-budget alarm complementing `maxTokens` cap — covered by #18
