# Issue #24 — Memory on UITestAgentHarness

## Summary

`UITestAgentHarness` had no Memory configured. An AgentCore Memory resource
(`uitestagent_uitestagentMemory`) **already existed** with all four strategies
fully configured — created when the original Runtime was deployed, but never
attached to the Harness which was deployed separately via `deploy_harness.py`.

This issue attaches the existing Memory to the Harness **programmatically**
via `update_harness` (boto3 ≥ 1.43.18). The original PR assumed this required
a manual console step; further investigation showed the operation is
available in the public SDK once boto3 is recent enough. See AGENTS.md §3.6
and §7.5.

## Existing Memory resource (verified live)

```
Name:                uitestagent_uitestagentMemory-<MEM_ID>
Status:              ACTIVE
Created:             2026-05-16
Event expiry:        30 days
Strategies (4):
  EPISODIC          → /episodes/{actorId}/{sessionId}    (uitestagentMemory_Episodic-<ID>)
  SEMANTIC          → /users/{actorId}/facts             (uitestagentMemory_Semantic-<ID>)
  SUMMARIZATION     → /summaries/{actorId}/{sessionId}   (uitestagentMemory_Summarization-<ID>)
  USER_PREFERENCE   → /users/{actorId}/preferences       (uitestagentMemory_Userpreference-<ID>)
```

Matches the design in `docs/ARCHITECTURE.md §7 Self-Learning & Memory
Architecture`.

## Programmatic attach via `update_harness`

The script `agentcore/scripts/attach_memory.py` calls:

```python
control = boto3.client("bedrock-agentcore-control", region_name="us-east-1")
control.update_harness(
    harnessId="UITestAgentHarness-<ID>",
    memory={
        "optionalValue": {
            "agentCoreMemoryConfiguration": {
                "arn": "arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:memory/uitestagent_uitestagentMemory-<MEM_ID>",
                "actorId": "ci-pipeline",
                "messagesCount": 20,
                "retrievalConfig": {
                    "/episodes/{actorId}/{sessionId}":  {"strategyId": "uitestagentMemory_Episodic-<ID>",     "topK": 10, "relevanceScore": 0.2},
                    "/users/{actorId}/facts":           {"strategyId": "uitestagentMemory_Semantic-<ID>",     "topK": 10, "relevanceScore": 0.2},
                    "/summaries/{actorId}/{sessionId}": {"strategyId": "uitestagentMemory_Summarization-<ID>","topK": 10, "relevanceScore": 0.2},
                    "/users/{actorId}/preferences":     {"strategyId": "uitestagentMemory_Userpreference-<ID>","topK": 10, "relevanceScore": 0.2},
                }
            }
        }
    },
    clientToken="...",
)
```

Two field-name gotchas (recorded in [AGENTS.md §3.2](../../AGENTS.md#32-api-field-name-gotchas)):

1. The memory wrapper uses **`optionalValue`** at the outer layer — pass
   `{"optionalValue": {"agentCoreMemoryConfiguration": {...}}}`, not
   `{"agentCoreMemoryConfiguration": {...}}` directly.
2. Each entry in `retrievalConfig` uses **`strategyId`** — NOT
   `memoryStrategyId` (the latter is what you'd guess from the
   memory resource shape, but it's wrong here).

## Live verification

After running the script, `get_harness` confirms the attach succeeded:

```
$ python agentcore/scripts/attach_memory.py
boto3 1.43.18 OK

Region:  us-east-1
Account: <ACCOUNT_ID>

Searching for harness: UITestAgentHarness
  Found: arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:harness/UITestAgentHarness-<ID>  status=READY
Searching for memory with name prefix: uitestagent_uitestagentMemory
  Found: arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:memory/uitestagent_uitestagentMemory-<MEM_ID>  status=ACTIVE
  Strategies (4):
    - EPISODIC         → /episodes/{actorId}/{sessionId}    (uitestagentMemory_Episodic-<ID>)
    - SEMANTIC         → /users/{actorId}/facts             (uitestagentMemory_Semantic-<ID>)
    - SUMMARIZATION    → /summaries/{actorId}/{sessionId}   (uitestagentMemory_Summarization-<ID>)
    - USER_PREFERENCE  → /users/{actorId}/preferences       (uitestagentMemory_Userpreference-<ID>)

✓ Memory is ALREADY ATTACHED (idempotent — no action taken)
  actorId:       ci-pipeline
  messagesCount: 20
  retrievalConfig namespaces: 4
    - /episodes/{actorId}/{sessionId}          topK=10  relevance=0.2
    - /users/{actorId}/preferences             topK=10  relevance=0.2
    - /summaries/{actorId}/{sessionId}         topK=10  relevance=0.2
    - /users/{actorId}/facts                   topK=10  relevance=0.2
```

Exit code: 0 (idempotent — safe to re-run any time).

The same evidence is also visible in the AWS console:
*Bedrock AgentCore → Harness → UITestAgentHarness → Memory section*
shows the memory resource configured with actorId `ci-pipeline` and
4 retrieval configs.

## actorId convention for UITestAgentHarness

| Caller | actorId | Why |
|---|---|---|
| **CI pipeline (GitHub Actions)** | `ci-pipeline` | All CI runs share memory — agent learns app-wide patterns |
| **Ad-hoc dev** | `dev-{username}` | Per-developer scratch memory |
| **Admin Portal manual run** (future) | `portal-{cognito-user}` | Per-user memory once #36 lands |
| **Multi-tenant** (future) | `tenant-{tenantId}` | Tenant isolation per #35 |

`{actorId}` substitutes into the memory namespace templates above.
Example: CI run with `actorId=ci-pipeline` writes to
`/users/ci-pipeline/facts` (semantic), `/episodes/ci-pipeline/{sessionId}`
(episodic), etc.

## Tooling note (recorded in [AGENTS.md §2](../../AGENTS.md#2-tooling-versions-that-matter))

This script requires **boto3 ≥ 1.43.18**. Older versions (e.g. 1.42.79
shipped with system pip on this project's environment) silently lack
the 5 Harness operations — the client object simply has no
`create_harness` / `update_harness` etc. attributes. The script
verifies the version on startup and exits with a clear error message
+ upgrade instructions if too old.

## Acceptance criteria status

| Criterion | Status |
|---|---|
| Memory resource exists with 4 strategies | ✅ already done (May 16) |
| Console shows Memory ARN under Memory section | ✅ live verified |
| `actorId` strategy documented | ✅ this PR (table above) |
| Memory retention configured (30d episodic) | ✅ already done (eventExpiryDuration=30) |
| Programmatic attach script (idempotent) | ✅ this PR |
| Live `get_harness` shows memory configured | ✅ this PR (output above) |
| Functional test: agent recalls prior memory | ⏳ requires test invocation post-merge |
| CloudWatch shows Memory metrics > 0 | ⏳ after invocations |

## Out of Scope

- BugFixAgentHarness Memory — separate issue **#25** (similar pattern,
  but needs to first CREATE a memory resource since none exists yet)
- Multi-tenant `actorId` scoping with Cognito JWT — issue **#35**
- Functional test (agent recalls prior memory across sessions) — needs
  separate test plan; will be covered in a follow-up issue

## Related discoveries (now in AGENTS.md)

This PR's investigation produced 3 institutional-memory entries that
landed in [AGENTS.md](../../AGENTS.md) (PR #42):

- §3.1 **Harness vs Runtime** distinction (`UpdateAgentRuntime` is
  rejected for harness-managed runtimes; use `UpdateHarness`)
- §3.2 **Field-name gotcha** (`strategyId`, not `memoryStrategyId`)
- §3.6 **AgentCore SDK structure** (boto3 control plane vs.
  bedrock-agentcore-sdk-python agent-side SDK)

Future contributors won't need to re-discover these.
