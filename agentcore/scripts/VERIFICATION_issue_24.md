# Issue #24 — Memory on UITestAgentHarness

## Summary

`UITestAgentHarness` console showed "Memory is not configured", but on
inspection an AgentCore Memory resource **already exists** with all four
strategies fully configured. The original Runtime (`uitestagent_uitestagent`)
has it attached via an env var; the Harness was deployed separately
(`deploy_harness.py`) without it.

This issue is therefore about **attaching the existing memory to the harness**,
not about creating a new memory resource.

## Existing Memory resource (verified live)

```
Name:                uitestagent_uitestagentMemory
Status:              ACTIVE
Created:             2026-05-16
Event expiry:        30 days
Strategies (4):
  EPISODIC          → /episodes/{actorId}/{sessionId}
  SEMANTIC          → /users/{actorId}/facts
  SUMMARIZATION     → /summaries/{actorId}/{sessionId}
  USER_PREFERENCE   → /users/{actorId}/preferences
```

Matches the design in `docs/ARCHITECTURE.md §7 Self-Learning & Memory
Architecture`.

## How the original Runtime has Memory attached

```
Runtime:  uitestagent_uitestagent
Env var:  MEMORY_UITESTAGENTMEMORY_ID = uitestagent_uitestagentMemory-<MEM_ID>
```

The Strands SDK reads `MEMORY_*_ID` env vars at startup to bootstrap
`get_memory_session_manager()` (see `app/ui-test-agent/main.py` line ~152).

## Why we can't programmatically attach

Public boto3 (1.42.79) does NOT expose `CreateHarness` / `UpdateHarness`.
Probing the control plane confirms:

```
$ aws bedrock-agentcore-control update-agent-runtime --agent-runtime-id ...

ValidationException: This agent runtime is managed by harness '...' and
cannot be updated directly. Use UpdateHarness to update this resource.
```

Until `UpdateHarness` ships in public SDK (preview API), Memory attachment
to a Harness is a **console-only** operation.

## Manual attachment steps

1. AWS Console → **Bedrock AgentCore → Harness → UITestAgentHarness**
2. Click **[Edit]**
3. In the **Memory** section, select the existing memory:
   `uitestagent_uitestagentMemory`
4. **Save** and wait for harness status to return to READY (~30-60 sec)

After save, the harness's environment variables should include:
```
MEMORY_UITESTAGENTUITESTAGENTMEMORY_ID = uitestagent_uitestagentMemory-<MEM_ID>
```

## actorId convention for UITestAgentHarness

When invoking the harness, pass `actorId` per call to scope memory namespaces:

| Caller | actorId | Why |
|---|---|---|
| **CI pipeline (GitHub Actions)** | `ci-pipeline` | All CI runs share memory — agent learns app-wide patterns |
| **Ad-hoc dev** | `dev-{username}` | Per-developer scratch memory |
| **Admin Portal manual run** (future) | `portal-{cognito-user}` | Per-user memory once #N12 lands |
| **Multi-tenant** (future) | `tenant-{tenantId}` | Tenant isolation per #N12 |

`{actorId}` substitutes into the memory namespace templates above.
Example: CI run with `actorId=ci-pipeline` writes to
`/users/ci-pipeline/facts` (semantic), `/episodes/ci-pipeline/{sessionId}`
(episodic), etc.

## Verification (after console attach)

Run the helper script:
```
python agentcore/scripts/attach_memory.py
```
Expected output: `✓ Memory already attached via env var: MEMORY_UITESTAGENTUITESTAGENTMEMORY_ID`

Run a test invocation via console with prompt asking for past memories,
e.g. *"What patterns did we discover in past test runs?"* — agent should
draw on stored episodic/semantic memory.

CloudWatch metrics: `aws bedrock-agentcore list-memory-records` should show
records being created during invocations.

## Out of Scope

- BugFixAgent Memory — separate issue **#25**
- Multi-tenant scoping with Cognito JWT — issue **#N12** (#35)
- Reusable script update for self-applying once UpdateHarness ships in
  public SDK — placeholder code in attach_memory.py
