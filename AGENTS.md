# AGENTS.md — Quick orientation for AI agents (and the humans working with them)

> If you're an AI agent (Claude, GPT, etc.) about to make changes to this
> repo, read this file first. It contains hard-learned facts that will save
> you time, plus pointers to the authoritative AWS docs you'll need.

This file follows the convention of AWS's own [bedrock-agentcore-sdk-python](https://github.com/aws/bedrock-agentcore-sdk-python) repo, which also has an AGENTS.md.

The *why* behind this file (the methodology) is documented in two sibling docs:
- [`docs/methodology/agent-onboarding.md`](docs/methodology/agent-onboarding.md) — Agent-Ready Repository Pattern (context durability)
- [`docs/methodology/change-discipline.md`](docs/methodology/change-discipline.md) — how to land changes (issue granularity, PR sizing, anti-patterns, stacked PRs)

Read either if you want to understand the pattern, or apply it to another repo.

---

## 0. What this project is

A **production-ready UI Test Agent** built on Amazon Bedrock AgentCore — an AI agent that navigates web UIs like a human QA tester and reports PASS/FAIL with evidence. Plus a downstream **Bug-Fix Agent** that auto-generates patches.

- Main entry point for the running agent: `app/ui-test-agent/main.py`
- Architecture: `docs/ARCHITECTURE.md`
- AgentCore best practices: `docs/BEST_PRACTICES.md` (English) / `docs/BEST_PRACTICES_zh-TW.md`
- How to contribute changes: `docs/DEVELOPMENT_WORKFLOW.md` ⭐ **read this before opening any PR**
- Production hardening plan: `docs/PRODUCTION_HARDENING.md`

---

## 1. Authoritative AWS references

When you need facts, look here in this priority order:

| Source | What to look up there | URL |
|---|---|---|
| **AWS Bedrock AgentCore Developer Guide** | Concepts, tutorials, "how to" docs | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/ |
| **AWS Bedrock AgentCore Control Plane API Reference** | Exact API shapes, request/response JSON, field constraints | https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/Welcome.html |
| **`aws/bedrock-agentcore-sdk-python` GitHub repo** | Agent-side SDK source code (`BedrockAgentCoreApp`, `MemorySessionManager`, `BrowserClient`, `CodeInterpreterClient`) | https://github.com/aws/bedrock-agentcore-sdk-python |
| **AgentCore samples** | Working code examples | https://github.com/awslabs/amazon-bedrock-agentcore-samples |
| **CloudFormation `AWS::BedrockAgentCore::*`** | Schema-as-truth for all resource fields | https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/AWS_BedrockAgentCore.html |
| **AWS CLI Reference** | CLI command shapes | https://docs.aws.amazon.com/cli/latest/reference/bedrock-agentcore-control/ |

Two specific pages worth pinning to memory:

- **Memory get-started:** https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-get-started.html
- **Harness overview:** https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness.html
- **HarnessAgentCoreMemoryConfiguration API:** https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_HarnessAgentCoreMemoryConfiguration.html

---

## 2. Tooling versions that matter

AWS Bedrock AgentCore is a **preview** service that adds operations frequently. **Use latest SDK / CLI** unless you have a specific reason not to.

| Tool | Minimum version | Why |
|---|---|---|
| **boto3 / botocore** | **≥ 1.43.18** | Older versions (e.g. 1.42.x) **do NOT have the 5 Harness operations** (`create_harness`, `update_harness`, `get_harness`, `list_harnesses`, `delete_harness`). 1.42.79 returns 0 harness-related ops; 1.43.18 returns 5. |
| **AWS CLI v2** | **≥ 2.34.57** | Earlier CLI versions don't ship `delete-harness` / `update-harness` etc. AWS CLI 2.31.x in this project's environment is too old. |
| **AgentCore CLI (`@aws/agentcore`)** | npm latest | For interactive scaffolding (`agentcore create`, `agentcore add memory`, `agentcore deploy`). Optional but useful for some workflows. |
| **`bedrock-agentcore` Python SDK** | latest pip | The agent-side SDK (used by `app/ui-test-agent/main.py`). Provides `BedrockAgentCoreApp`, `MemorySessionManager`, `BrowserClient`, `CodeInterpreterClient`. |
| **AWS Account region** | `us-east-1` (preview) | Project deploys to `us-east-1`. AgentCore preview is also in `us-west-2`, `eu-central-1`, `ap-southeast-2`. |

### Quick install / upgrade

```bash
# Latest boto3 (most important — must be 1.43.18+ for harness ops)
pip3 install --upgrade boto3 botocore

# If pip refuses on system Python, use a venv:
python3 -m venv ~/.venvs/agentcore
~/.venvs/agentcore/bin/pip install --upgrade boto3 botocore
~/.venvs/agentcore/bin/python3 your_script.py

# AWS CLI v2 (latest)
curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o /tmp/aws.pkg
sudo installer -pkg /tmp/aws.pkg -target /

# AgentCore CLI (optional)
npm install -g @aws/agentcore

# Verify
python3 -c "import boto3; print(boto3.__version__)"   # expect ≥ 1.43.18
aws --version                                          # expect ≥ 2.34.57
```

---

## 3. Hard-learned facts (gotchas to skip)

These cost real debugging time during issues #28 (observability) and #24 (memory attachment). Know them up front:

### 3.1 Harness vs Runtime — the same thing under the hood, but two APIs

- A **Harness** in AgentCore terms = a managed wrapper around an `agent_runtime` resource.
- `aws bedrock-agentcore-control list-agent-runtimes` returns BOTH normal runtimes AND harness-managed runtimes. The harness-managed ones have **`harness_*` prefix** in `agentRuntimeName`.
- Each harness has TWO ARNs:
  - `arn:aws:bedrock-agentcore:<region>:<account>:harness/<NAME>-<id>` — the harness resource (manage via `*Harness` APIs)
  - `arn:aws:bedrock-agentcore:<region>:<account>:runtime/harness_<NAME>-<id>` — the underlying runtime (auto-created by the harness)
- **`UpdateAgentRuntime` is REJECTED for harness-managed runtimes** with:
  > `"This agent runtime is managed by harness '...' and cannot be updated directly. Use UpdateHarness to update this resource."`
- For modification, use the **`*Harness` family** (boto3 ≥ 1.43.18 required).
- For invocation, use **`InvokeHarness`** (NOT `InvokeAgentRuntime`).

### 3.2 API field-name gotchas

When calling `update_harness(memory={...})`, the structure is:

```python
memory = {
    "optionalValue": {
        "agentCoreMemoryConfiguration": {
            "arn": "arn:aws:bedrock-agentcore:...:memory/...",
            "actorId": "...",
            "messagesCount": 20,
            "retrievalConfig": {
                "<namespace>": {
                    "strategyId": "...",      # ← NOT "memoryStrategyId"
                    "topK": 10,
                    "relevanceScore": 0.2,
                }
            }
        }
    }
}
```

- ✅ `strategyId`
- ❌ `memoryStrategyId` (you'd guess this from the API ref but it's wrong; the hint comes from validation errors)

### 3.3 CloudWatch Logs Delivery for AgentCore

Three valid `logType` values:
- `APPLICATION_LOGS` — sparse per-invocation events; goes to CWL log group
- `TRACES` — OTel traces; goes to **X-Ray service** (`deliveryDestinationType=XRAY`), **NOT a log group**
- `USAGE_LOGS` — usage events (probed but not used yet)

XRAY destinations have **no `outputFormat` parameter** — pass only `name` and `deliveryDestinationType="XRAY"`.

```python
# ✅ correct
logs.put_delivery_destination(
    name="my-xray-dest",
    deliveryDestinationType="XRAY",
)

# ❌ rejected with "XRay delivery destination does not support any output format"
logs.put_delivery_destination(
    name="my-xray-dest",
    outputFormat="json",          # ← XRAY doesn't take this
    deliveryDestinationType="XRAY",
)
```

### 3.4 `AWSLogDeliveryWrite20150319` resource policy

When `aws logs create-delivery` succeeds but no events flow, the cause is often the **resource policy on the destination log group**. AWS auto-creates a policy named `AWSLogDeliveryWrite20150319` for some services (e.g. SageMaker GroundTruth) but **does NOT auto-add new services** to the same policy. You must extend it manually:

```python
# Append a statement allowing delivery.logs.amazonaws.com to write to your specific log groups
# Preserve existing statements (don't replace the whole policy)
```

See `agentcore/scripts/setup_observability.py` for a working idempotent implementation.

### 3.5 AgentCore default log groups

When a Runtime is created, AgentCore **auto-creates** a default log group:

```
/aws/bedrock-agentcore/runtimes/<runtime-name>-<id>-DEFAULT
```

This is where the runtime emits **rich OTel structured logs** (with `trace_id`, `span_id`, `resource.service.name`, EMF metric blocks). The `otel.resource.aws.log.group.names` attribute is hardcoded to point here.

When you set up `APPLICATION_LOGS` delivery to a custom log group, you get **a different (sparser) channel** — not a duplicate of DEFAULT. For dashboards / alarms, query the DEFAULT log group (which has data) plus X-Ray (which has traces).

The default group has retention `None` (never expire) by default. Set retention explicitly to bound storage.

### 3.6 AgentCore SDK structure

The Python SDK [`bedrock-agentcore-sdk-python`](https://github.com/aws/bedrock-agentcore-sdk-python) is the **agent-side** SDK — it provides helpers for code RUNNING INSIDE the Runtime (memory client, browser client, code interpreter client, runtime app server).

Management-plane CRUD (CreateHarness, UpdateMemory, etc.) lives in **boto3** under the `bedrock-agentcore-control` service client. The SDK has an `AgentCoreRuntimeClient` class that wraps a subset of management APIs but currently **does not expose harness operations** (it allowlists only `*_agent_runtime*` methods). For harness operations, call `boto3.client("bedrock-agentcore-control")` directly.

### 3.7 Memory event flow

- AgentCore **Memory** is a separate resource from a Harness.
- Each Memory has multiple **strategies** (semantic, episodic, summarization, user_preference, custom).
- A Memory is attached to a Harness via `update_harness(memory={...})` (or set on creation).
- Memory namespace templates use `{actorId}` and `{sessionId}` placeholders. The agent invocation determines the actual values.
- This project's convention for `actorId`:
  - `ci-pipeline` for CI runs (shared memory across tests)
  - `dev-{username}` for ad-hoc dev runs
  - `tenant-{tenantId}` for future multi-tenant (tracked in #35)

---

## 4. Repo methodology — read this before opening a PR

This repo's methodology has three layers:

| Layer | Document | What it covers |
|---|---|---|
| **Artifact** | [`AGENTS.md`](AGENTS.md) (this file) | Institutional memory: invariants, AWS gotchas, tooling versions |
| **Abstract pattern: context** | [`docs/methodology/agent-onboarding.md`](docs/methodology/agent-onboarding.md) | How to make any repo legible to AI agents (Agent-Ready Repository Pattern) |
| **Abstract pattern: change** | [`docs/methodology/change-discipline.md`](docs/methodology/change-discipline.md) | How to land changes: issue granularity, PR sizing, anti-patterns, stacked PRs, templates |
| **Practical contract** | [`docs/DEVELOPMENT_WORKFLOW.md`](docs/DEVELOPMENT_WORKFLOW.md) | The lightweight day-to-day contract for THIS repo |

Order of consultation when planning a change:
1. **AGENTS.md** — does my change violate an invariant?
2. **change-discipline.md** — is this stack-eligible or one parallel issue?
3. **DEVELOPMENT_WORKFLOW.md** — what does the issue/PR template look like?

In practice every change follows the **issue → fix → PR** loop. Brief summary:

1. Open an **issue** with: Problem / Evidence / Proposed Solution / Acceptance Criteria / Priority / Effort / Out of Scope.
2. Branch named `<type>/issue-<N>-<short-desc>` (e.g. `feat/issue-24-memory-uitestagent`).
3. Commits follow [Conventional Commits](https://www.conventionalcommits.org/) format with `(#N)` issue reference.
4. **One issue = one logical change.** Don't bundle unrelated work.
5. PR description follows the template in `docs/DEVELOPMENT_WORKFLOW.md`.
6. PRs reference `Closes #N` so GitHub auto-closes the issue on merge.
7. Each PR is reviewed and merged before starting the next one.

### Issue label convention

| Label | Use for |
|---|---|
| `enhancement` / `feature` | You already know what to do. Issue defines acceptance criteria. |
| `bug` | Something is broken; fix in scope is clear. |
| `documentation` | Docs-only changes. |
| `discussion` | You don't yet know the right answer. Use the template in `docs/methodology/agent-onboarding.md` (Context / Working assumptions / Open questions / Repo context). Often spawns one or more feature issues afterwards. |

---

## 5. Account / credential hygiene

This is a public repo. **Never** commit:

- AWS account number (use `<ACCOUNT_ID>` placeholder)
- IAM role suffix / random IDs (use `<IAM_ROLE_ID>`, `<RUNTIME_ID>`, `<HARNESS_ID>`, `<MEM_ID>`)
- API keys / secrets (use Secrets Manager / Token Vault, reference by ARN)
- Real PII (use synthetic test data only)

When generating evidence (CLI output for PRs), redact via:

```bash
# Redact account number
aws ... | sed 's/[0-9]\{12\}/<ACCOUNT_ID>/g'

# Redact resource random suffixes
| sed 's/-[a-zA-Z0-9]\{10\}\b/-<RESOURCE_ID>/g'
```

For CDK, use `cdk.Aws.ACCOUNT_ID` (synth-time substitution) — never hardcode.
For boto3, use `sts.get_caller_identity()["Account"]` — never hardcode.

---

## 6. Useful patterns from past PRs

| Pattern | Example PR / file |
|---|---|
| Idempotent setup script (CloudWatch logs delivery) | `agentcore/scripts/setup_observability.py` (PR #39) |
| Programmatic harness update | `agentcore/scripts/attach_memory.py` (PR #40) |
| AWS-resource-aware test verification with redaction | `agentcore/scripts/VERIFICATION_issue_28.md` |
| Methodology dogfooding (each PR follows the workflow it documents) | `docs/DEVELOPMENT_WORKFLOW.md` (PR #3) |
| Agent-Ready Repo Pattern (AGENTS.md + agent-onboarding.md) | `docs/methodology/agent-onboarding.md` (PR #42) |
| Change-discipline methodology (round-trip lineage with dora-metrics) | `docs/methodology/change-discipline.md` (PR #43) |

---

## 7. When you're stuck

If the public boto3 SDK seems to lack an operation you need:

1. **Check your boto3 version first.** `pip show boto3 | grep -i version`. AgentCore adds operations in nearly every release; older versions just don't have them.
2. **Search AWS docs:** `https://docs.aws.amazon.com/search?searchPath=documentation&searchQuery=YOUR_OPERATION` — if the operation is documented, it exists in the API even if your local SDK is out of date.
3. **Look at the CloudFormation type spec** for the resource — that's the schema-of-truth.
4. **Check the [bedrock-agentcore-sdk-python](https://github.com/aws/bedrock-agentcore-sdk-python) source** — even if the operation isn't there, allowlisted method names hint at API shapes.
5. **Don't conclude "console-only" without verifying SDK version.** The project's PR #40 was originally written assuming Memory attachment was console-only because boto3 1.42.x lacks `update_harness`. boto3 1.43.18 has it.

---

## 8. Project state (auto-stale; check git for current)

- `PROJECT_STATE.md` — persistent project state, updated periodically
- `CHANGELOG.md` — Keep-a-Changelog versioned history
- Last major audit: **v0.2.1** (2026-05-30) — sync of all docs with code reality
- v0.2.2 in progress: Harness configuration improvements (Memory, Skills, Tools, Observability) tracked in issues #18 onwards

---

*If you find a new gotcha while working on this repo, add it to Section 3 of this file in your PR. Future agents will thank you.*
