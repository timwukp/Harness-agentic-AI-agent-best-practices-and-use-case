# Issue #25 — BugFixAgent Memory (semantic + episodic)

## Summary

`BugFixAgentHarness` previously had **Memory not configured** (per console).
This PR creates a new AgentCore Memory resource with 2 strategies (semantic + episodic)
and attaches it to `BugFixAgentHarness` programmatically — a two-phase script:

| Phase | API | What |
|---|---|---|
| **A** | `create_memory` | Create `bugfixagent_bugfixagentMemory` with 2 strategies; poll CREATING → ACTIVE |
| **B** | `update_harness(memory={"optionalValue": {...}})` | Attach the new memory ARN to BugFixAgentHarness with retrievalConfig + actorId |

Live-tested per change-discipline.md Step 4 mandate (PR #53). First forward-implementation PR under the new rule.

## API discovery findings

These extend AGENTS.md §3 (candidate addition for §3.8 in a follow-up doc PR):

### CreateMemory schema

```
CreateMemory required: name, eventExpiryDuration

memoryStrategies: list of structure (UNION variants)
  ├─ semanticMemoryStrategy:        {name*, description, namespaces, namespaceTemplates, memoryRecordSchema}
  ├─ episodicMemoryStrategy:        {name*, description, namespaces, namespaceTemplates, reflectionConfiguration, memoryRecordSchema}
  ├─ summaryMemoryStrategy:         {name*, description, namespaces, namespaceTemplates, memoryRecordSchema}
  ├─ userPreferenceMemoryStrategy:  {name*, description, namespaces, namespaceTemplates, memoryRecordSchema}
  └─ customMemoryStrategy:          {name*, description, namespaces, namespaceTemplates, configuration, memoryRecordSchema}
```

Same UNION-variant pattern as `skills.member` (PR #51) — discovered via `§7.1` schema introspection.

### Episodic strategy: reflection namespace must be a prefix

When using `episodicMemoryStrategy`, the `reflectionConfiguration.namespaces` must be a **prefix** of the strategy's main `namespaces`. The default reflection namespace `/strategies/{memoryStrategyId}/actors/{actorId}/` will NOT match a custom episodic namespace like `/fix-history/{actorId}/{sessionId}`.

If omitted, `CreateMemory` returns:

```
ValidationException: Reflection namespace '/strategies/{memoryStrategyId}/actors/{actorId}/' must be the same as or a prefix of the episodic namespace for strategy FixHistoryStrategy
```

Working pattern (this PR):

```python
{
    "episodicMemoryStrategy": {
        "name": "FixHistoryStrategy",
        "namespaces": ["/fix-history/{actorId}/{sessionId}"],
        "reflectionConfiguration": {
            "namespaces": ["/fix-history/{actorId}"],   # prefix of the above
        },
    }
}
```

The existing `uitestagent_uitestagentMemory` follows the same pattern: `/episodes/{actorId}/{sessionId}` with reflection at `/episodes/{actorId}`.

### Memory creation is async

`create_memory` returns immediately with `status=CREATING`. Polling `get_memory` shows ACTIVE after ~150 seconds in our test (slower than harness updates, which take ~10s). Script polls with `MAX_POLL_SECONDS=300, POLL_INTERVAL=10` to handle this.

## Configuration

### 2 strategies (narrower than UI Test's 4-strategy)

Per the audited issue body — Bug-Fix needs are narrower than UI Test:

| Strategy | Namespace | Purpose |
|---|---|---|
| `FixPatternStrategy` (semantic) | `/fix-patterns/{actorId}` | Long-lived fix patterns + root-cause taxonomy ("when error message color is wrong, check `.error-message {color}` first") |
| `FixHistoryStrategy` (episodic) | `/fix-history/{actorId}/{sessionId}` | Per-session fix outcomes ("On 2026-05-16 fixed error-message: green → red, PR succeeded") |

Skipped:
- `summaryMemoryStrategy` — Bug-Fix sessions are short, no compression needed
- `userPreferenceMemoryStrategy` — no team-specific quirks expected at current scale

### actorId convention: per-repo

Per issue body — different from UITestAgent's `ci-pipeline`:

```
repo-{owner}-{name}
```

For this repo: `repo-timwukp-Harness-agentic-AI-agent-best-practices-and-use-case`

Each codebase gets its own memory namespace because fix patterns for `frontend-app` don't apply to `backend-api`. When **#36** (multi-tenant JWT) lands, this evolves to `tenant-{id}-repo-{owner}-{name}`.

### retrievalConfig parameters

- `topK = 5` (smaller than UI Test's 10 — Bug-Fix sessions need less context)
- `relevanceScore = 0.3` (slightly higher threshold than UI Test's 0.2 — fix patterns should be specifically relevant)

## Live verification (mandatory per change-discipline.md Step 4)

### Apply (first run)

```
$ python agentcore/scripts/create_bugfix_memory.py
boto3 1.43.18 OK
Mode:    APPLY

=== Phase A: Memory 'bugfixagent_bugfixagentMemory' ===
  → memory 'bugfixagent_bugfixagentMemory' not found — creating with 2 strategies
  ✓ create_memory HTTP 200
  Polling get_memory until status=ACTIVE (max 300s)...
    status=CREATING (waiting 10s)
    [...15 polls, ~150s total...]
  ✓ memory ACTIVE
  ARN: arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:memory/bugfixagent_bugfixagentMemory-<MEM_ID>
  strategies: 2
    - EPISODIC         → /fix-history/{actorId}/{sessionId}  (id=FixHistoryStrategy-<ID>)
    - SEMANTIC         → /fix-patterns/{actorId}  (id=FixPatternStrategy-<ID>)

=== Phase B: Attach to BugFixAgentHarness ===
  arn:    arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:harness/BugFixAgentHarness-<ID>
  status: READY
  → attaching memory to BugFixAgentHarness
    actorId: repo-timwukp-Harness-agentic-AI-agent-best-practices-and-use-case
    retrievalConfig namespaces: 2
      - /fix-history/{actorId}/{sessionId}  topK=5  relevance=0.3
      - /fix-patterns/{actorId}  topK=5  relevance=0.3
  ✓ update_harness HTTP 200
    status=UPDATING (waiting 5s)
    status=UPDATING (waiting 5s)
  ✓ harness READY

✓ Done — re-run for idempotency confirmation
```

### Idempotent re-run

```
$ python agentcore/scripts/create_bugfix_memory.py
boto3 1.43.18 OK
Mode:    APPLY

=== Phase A: Memory 'bugfixagent_bugfixagentMemory' ===
  ✓ memory 'bugfixagent_bugfixagentMemory' already exists (status=ACTIVE)
  ARN: arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:memory/bugfixagent_bugfixagentMemory-<MEM_ID>
  strategies: 2
    - EPISODIC         → /fix-history/{actorId}/{sessionId}  (id=FixHistoryStrategy-<ID>)
    - SEMANTIC         → /fix-patterns/{actorId}  (id=FixPatternStrategy-<ID>)

=== Phase B: Attach to BugFixAgentHarness ===
  arn:    arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:harness/BugFixAgentHarness-<ID>
  status: READY
  ✓ memory already attached to BugFixAgentHarness (no update)

✓ Done
```

Zero API mutations on re-run.

### Live `get_harness` + `get_memory` evidence

```
--- Memory bugfixagent_bugfixagentMemory ---
  status:      ACTIVE
  arn:         arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:memory/bugfixagent_bugfixagentMemory-<MEM_ID>
  eventExpiry: 30 days
  strategy: EPISODIC   ns=['/fix-history/{actorId}/{sessionId}']  id=FixHistoryStrategy-<ID>
  strategy: SEMANTIC   ns=['/fix-patterns/{actorId}']             id=FixPatternStrategy-<ID>

--- BugFixAgentHarness ---
  status:               READY
  memory.arn:           arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:memory/bugfixagent_bugfixagentMemory-<MEM_ID>
  memory.actorId:       repo-timwukp-Harness-agentic-AI-agent-best-practices-and-use-case
  memory.messagesCount: 20
  memory.retrievalConfig:
    - /fix-patterns/{actorId}                topK=5  relevance=0.3  strategyId=FixPatternStrategy-<ID>
    - /fix-history/{actorId}/{sessionId}     topK=5  relevance=0.3  strategyId=FixHistoryStrategy-<ID>
```

The AWS console (Bedrock AgentCore → Harness → BugFixAgentHarness → Memory section) shows the same configuration.

## Acceptance criteria status

| Criterion | Status | Notes |
|---|---|---|
| Memory resource exists with semantic + episodic strategies | ✅ | live verified |
| BugFixAgentHarness console shows the Memory ARN | ✅ | live verified |
| Idempotent script | ✅ | re-run is no-op |
| VERIFICATION doc with redacted evidence | ✅ | this file |
| `actorId` set per-repo on every invocation | ✅ | wired in update_harness payload |
| **Live-test on AWS BEFORE this PR** (per Step 4) | ✅ | apply + idempotent re-run + get_harness done in this branch BEFORE PR open |
| Functional test: agent recalls prior fix on second run | ⏳ | requires test invocation post-merge with actual demo bug |
| CloudWatch shows Memory read/write metrics > 0 | ⏳ | after invocations |
| Update `e2e_pipeline.py` and `a2a_handoff.py` to set actorId | ⏳ | follow-up — orchestrator changes are separate concern |

## Methodology dogfooding

**This is the first forward-implementation PR under PR #53's mandatory live-test rule.** The methodology worked exactly as designed:

1. **Schema introspection at Step 0** (per AGENTS.md §7.1) revealed:
   - `memoryStrategies.member` is a UNION (5 variants)
   - `episodicMemoryStrategy` has `reflectionConfiguration` (would have been missed if I'd only known about the 4-strategy pattern)
2. **Live-test surfaced a real ValidationException** that local validation would not have caught — `reflection namespace must be a prefix of the episodic namespace`. Without Step 4's mandate to APPLY (not just `--dry-run`), this would have surfaced post-merge.
3. **Cross-reference to existing `uitestagent_uitestagentMemory`** (via `get_memory`) showed the canonical reflection-prefix pattern. Cheap recovery once the bug surfaced.
4. **AGENTS.md §3.2.3 (clientToken length, from PR #50)** consumed cleanly — used `secrets.token_hex(20)` from day 1, no rediscovery cost.
5. **AGENTS.md §3.2.4 (`strategyId`)** consumed cleanly — used the right field name throughout.
6. **AGENTS.md §3.7 (actorId conventions)** consumed cleanly — used `repo-{owner}-{name}` pattern.

The two-phase script architecture (create + attach with idempotent short-circuits at each phase) is reusable for any future "create-then-attach" scenarios. Candidate canonical pattern.

## Out of Scope (filed as candidate follow-ups)

- **AGENTS.md §3.8 enrichment** — `CreateMemory.memoryStrategies` UNION variants + episodic reflection-prefix constraint should be lifted into AGENTS.md institutional memory (rhythm: PR #47 → PR #49; PR #51 → PR #53; this PR → next doc PR)
- **Functional test** — agent recalls prior fix in second invocation; requires actual demo bug + 2 sessions; post-merge
- **Orchestrator changes** — `e2e_pipeline.py` / `a2a_handoff.py` need to pass `actorId` per invocation; separate small PR
- **Switch to `tenant-{id}-repo-{owner}-{name}`** when **#36** (JWT auth) lands

## Risk

**Low.** Two-phase idempotent script. Memory is a new resource (no migration risk). Attach is reversible (set memory back to None via `update_harness`). The existing `uitestagent_uitestagentMemory` was the reference pattern — same repo, same patterns.

If anything goes wrong post-merge (e.g. memory queries fail), rollback is:
1. `update_harness(harnessId=BugFixAgent, memory={"optionalValue": null})` to detach (verify exact null-payload form)
2. `delete_memory(memoryId=...)` to remove the resource
