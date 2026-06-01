# Issue #60 Verification — BugFix Memory IAM gap hotfix

## 4a. API-level live test

### Step 1 — Dry run

```
=== Discovered 4 harness(es) ===

  BugFixAgentHarness:
    role:       AgentCore-uitestagent-def-ApplicationAgentUitestage-<ID>
    memory:     arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:memory/bugfixagent_bugfixagentMemory-<ID>
    namespaces: ['/fix-history/*/*', '/fix-patterns/*']
    policy:     BugFixAgentHarnessMemoryAccess
    drift:      YES — will apply
    DRY-RUN: would PutRolePolicy

  UITestAgentHarness:
    role:       AgentCore-uitestagent-def-ApplicationAgentUitestage-<ID>
    memory:     arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:memory/uitestagent_uitestagentMemory-<ID>
    namespaces: ['/episodes/*/*', '/summaries/*/*', '/users/*/facts', '/users/*/preferences']
    policy:     UITestAgentHarnessMemoryAccess
    drift:      YES — will apply
    DRY-RUN: would PutRolePolicy

=== Summary ===
  applied:  2
  no-op:    0
```

The `harness_agent_Cobol` and `harness_legal_doc_review` harnesses have no Memory wired and were correctly skipped (no output).

The drift on `UITestAgentHarness` is because the CDK-managed default policy `ApplicationAgentUitestagentRuntimeExecutionRoleDefaultPolicy555FED3B` historically grants UI Test Memory perms via its embedded statements — which is the wrong layer for forward-going operability. The script creates a canonical per-harness policy `<HarnessName>MemoryAccess` so future harnesses follow one consistent pattern.

The CDK default policy is left untouched (would fight CDK if removed).

### Step 2 — Apply

```
=== Discovered 4 harness(es) ===

  BugFixAgentHarness:
    drift:      YES — will apply
    ✓ applied + verified

  UITestAgentHarness:
    drift:      YES — will apply
    ✓ applied + verified

=== Summary ===
  applied:  2
  no-op:    0
```

Each apply was followed by `iam:GetRolePolicy` round-trip to confirm the policy document matches what was written.

### Step 3 — Idempotent re-run

Re-running with no manual IAM drift between runs:

```
=== Summary ===
  applied:  0
  no-op:    2
```

Zero IAM mutations on second run. Idempotency confirmed.

### Step 4 — Final IAM state on shared role

```
$ aws iam list-role-policies --role-name AgentCore-uitestagent-def-ApplicationAgentUitestage-<ID>
ApplicationAgentUitestagentRuntimeExecutionRoleDefaultPolicy555FED3B  ← CDK-managed (unchanged)
BrowserAccess                                                          ← pre-existing
BugFixAgentHarnessMemoryAccess                                         ← NEW (this PR)
ObservabilityAccess                                                    ← pre-existing
UITestAgentHarnessMemoryAccess                                         ← NEW (this PR)
```

5 inline policies, all canonical-named.

## 4b. Functional / E2E test

Three live invocations against `BugFixAgentHarness` after IAM apply:

### Test A — skill load (was failing pre-fix with AccessDenied on ListEvents)

```
Session: backfill-pr55-cf01422c<ID>2048dab7df00e431852f
Latency: 22.2s | Tool calls: ['skills'] | Final stop: end_turn
Skill content fetched: 6837 chars
Skill content markers found: ['When to ask for human approval', 'auth', 'payment', 'deletion', 'anti-pattern']
```

Response excerpt (verbatim citation of skill rule):

> "Yes — Human Approval Is Required First. Do NOT Fix Autonomously."
>
> The specific rule from my loaded guidelines is unambiguous:
> **"If fix touches auth/payment/deletion → ALWAYS escalate via `request_pr_approval`"**

### Test B — Memory write side

After session A completed:

```python
data.list_events(memoryId="bugfixagent_bugfixagentMemory-<ID>",
                 actorId="repo-timwukp-...",
                 sessionId=session_a)
→ 10 events written (USER, ASSISTANT, toolUse, toolResult)

data.list_memory_records(memoryId="bugfixagent_bugfixagentMemory-<ID>",
                         namespace="/fix-patterns/repo-timwukp-...")
→ 1 long-term record extracted within minutes:
   id=mem-3f5f79fe-9cfc-46d0-...
   content: "The user encountered a bug where clicking a button causes
             a page crash with a TypeError because a function expects
             a list but receives None, located in a payment processing
             code path."
```

✅ CreateEvent (write) works
✅ ListEvents (read) works
✅ FixPatternStrategy extracted 1 record from raw events
✅ ListMemoryRecords + RetrieveMemoryRecords against `/fix-patterns/*` namespace work (within IAM condition)

### Test C — Trivial post-canonical-policy invoke (smoke test)

```
Session: backfill-issue60-8be89e727430656d3edc88c6297f5a
Final stop: end_turn
Response: "OK"
✅ Post-canonical-policy invocation succeeds
```

## Pre-fix evidence (the failure that surfaced this issue)

```
EventStreamError: An error occurred (runtimeClientError) when calling the
  InvokeHarness operation:
  An error occurred (AccessDeniedException) when calling the ListEvents operation:
  User: arn:aws:sts::<ACCOUNT_ID>:assumed-role/AgentCore-uitestagent-def-Application
        AgentUitestage-<ID>/BedrockAgentCore-<session-id>
  is not authorized to perform: bedrock-agentcore:ListEvents
  on resource: arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:memory/bugfixagent_bug
               fixagentMemory-<ID>
  because no identity-based policy allows the bedrock-agentcore:ListEvents action
```

## Risk assessment

**Low.** Pure IAM additions; no resource removals; idempotent script; CDK-managed default policy untouched. Rollback = `iam:DeleteRolePolicy --policy-name <Harness>MemoryAccess`.

The script's discover-by-name pattern means it correctly handles future Memory wires for new harnesses without code change — assuming naming convention `<HarnessName>MemoryAccess` is honored.

## Process learnings

This is the **second consecutive 4b backfill discovery** (after PR #59 / issue #58):

| PR | Bug | Time-to-detection | Time-to-fix |
|---|---|---|---|
| #51 (UI Test skill) | Missing YAML frontmatter | 14 days | <1h via #58/#59 |
| #54 (BugFix Memory) | IAM gap (this issue) | 7 days | <1h via this PR |

Both lay dormant; both would have stayed dormant if PR #57's mandate hadn't forced 4b functional testing. The methodology is paying for itself by an order of magnitude per discovery.
