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
- Live harness state (2026-07-25): `UITestAgentHarness` v5 and `BugFixAgentHarness` v3 both run `global.anthropic.claude-opus-4-8` (upgraded from `global.anthropic.claude-sonnet-4-6` via a one-line `UpdateHarness` — see §3.2.1's working example). The model is a per-deployment choice; anyone deploying their own copy can pick any Bedrock model.
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
| **`aws/bedrock-agentcore-sdk-python` GitHub repo** | Agent-side SDK source code | https://github.com/aws/bedrock-agentcore-sdk-python |
| **AgentCore samples** | Working code examples | https://github.com/awslabs/amazon-bedrock-agentcore-samples |
| **CloudFormation `AWS::BedrockAgentCore::*`** | Schema-as-truth for all resource fields | https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/AWS_BedrockAgentCore.html |
| **AWS CLI Reference** | CLI command shapes | https://docs.aws.amazon.com/cli/latest/reference/bedrock-agentcore-control/ |

Two specific pages worth pinning to memory:

- **Memory get-started:** https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-get-started.html
- **Harness overview:** https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness.html
- **HarnessAgentCoreMemoryConfiguration API:** https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_HarnessAgentCoreMemoryConfiguration.html
- **Connect to tools (harness-tools):** https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-tools.html

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

These cost real debugging time during issues #28 (observability), #24 (memory attachment), #29 (harness config tightening), #58 (SKILL.md format), #60 (Memory IAM gap), #21/#65 (tools wiring + invocation). Know them up front:

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

### 3.2 `UpdateHarness` payload rules

Discovered via schema introspection (see §7.1) in PR #47 / VERIFICATION_issue_29.md.

#### 3.2.1 `optionalValue` wrapper is **per-field**, not all-structures

> ⚠️ **Corrected against live boto3 1.43.29** — the earlier rule in this file said "all structure fields wrap with optionalValue" with `model`/`environment`/`truncation` marked *(presumed)*. Schema introspection of the actual SDK shows that's wrong: only **three** fields wrap. `model` / `environment` / `truncation` are passed **directly** and are rejected if you wrap them. Source: [`agentcore-harness-builder` skill](https://github.com/timwukp/agent-skills-best-practice/tree/main/skills/skills/agentcore-harness-builder), verified end-to-end against AWS in the Quick POC run (PR #14 in `agent-skills-best-practice`).

The wrapper is **per-field**: only fields whose live shape literally contains an `optionalValue` member wrap. Verify on your installed boto3:

```python
shape = client.meta.service_model.operation_model("UpdateHarness").input_shape
for n, m in shape.members.items():
    if m.type_name == "structure":
        wraps = "optionalValue" in getattr(m, "members", {})
        print(n, "->", "WRAPS optionalValue" if wraps else "DIRECT (no wrapper)")
```

Verified result on boto3 1.43.29:

| Field | Type | optionalValue wrapper? |
|---|---|---|
| `memory` | structure | ✅ **WRAPS** |
| `environmentArtifact` | structure | ✅ **WRAPS** |
| `authorizerConfiguration` | structure | ✅ **WRAPS** |
| `model` | structure | ❌ direct (rejects wrapper) |
| `environment` | structure | ❌ direct (rejects wrapper) |
| `truncation` | structure | ❌ direct (rejects wrapper) |
| `allowedTools`, `tools`, `skills`, `systemPrompt` | list | ❌ direct |
| `maxTokens`, `maxIterations`, `timeoutSeconds` | integer | ❌ direct |

Working examples:

```python
# ✅ correct — list/integer pass directly
control.update_harness(
    harnessId=harness_id,
    allowedTools=["*"],                # see also §3.11.3 — no browser_* glob
    maxTokens=65536,
    clientToken=secrets.token_hex(20),
)

# ✅ correct — only the three structure fields below take optionalValue
control.update_harness(
    harnessId=harness_id,
    memory={"optionalValue": {"agentCoreMemoryConfiguration": {...}}},
    environmentArtifact={"optionalValue": {"containerConfiguration": {"containerUri": "..."}}},
    authorizerConfiguration={"optionalValue": {"customJWTAuthorizer": {...}}},
    clientToken=secrets.token_hex(20),
)

# ✅ correct — model / environment / truncation are passed direct (NO wrapper)
control.update_harness(
    harnessId=harness_id,
    model={"bedrockModelConfig": {"modelId": "global.anthropic.claude-opus-4-8", "apiFormat": "converse_stream"}},
    truncation={"strategy": "sliding_window", "config": {"slidingWindow": {"messagesCount": 150}}},
    environment={"agentCoreRuntimeEnvironment": {"networkConfiguration": {"networkMode": "PUBLIC"}}},
    clientToken=secrets.token_hex(20),
)

# ❌ wrong — wrapping a non-optionalValue field is rejected with
#   "Unknown parameter in model: 'optionalValue', must be one of: bedrockModelConfig, ..."
control.update_harness(harnessId=harness_id,
    model={"optionalValue": {"bedrockModelConfig": {...}}})  # rejected
```

**Field shape table** (from `boto3.client(...).meta.service_model.operation_model("UpdateHarness").input_shape.members`):

| Field | Shape | Wrapper? |
|---|---|---|
| `allowedTools` | list of string | None |
| `maxTokens` | integer | None |
| `maxIterations` | integer | None |
| `timeoutSeconds` | integer | None |
| `executionRoleArn` | string | None |
| `systemPrompt` | list of structure | None (list of structures, not optionalValue) |
| `tools` | list of structure | None |
| `skills` | list of structure | None |
| `memory` | structure | `optionalValue` |
| `environmentArtifact` | structure | `optionalValue` |
| `model` | structure | `optionalValue` (presumed; verify) |
| `environment` | structure | `optionalValue` (presumed; verify) |
| `authorizerConfiguration` | structure | `optionalValue` (presumed; verify) |
| `truncation` | structure | `optionalValue` (presumed; verify) |

#### 3.2.2 `tags` is NOT on `UpdateHarness` — use `TagResource`

```python
# ❌ This will fail — tags is not a UpdateHarness parameter
control.update_harness(harnessId=h, tags={...})  # rejected

# ✅ Tags require a separate API call
control.tag_resource(
    resourceArn="arn:aws:bedrock-agentcore:us-east-1:...:harness/...",
    tags={"team": "qa-platform", "environment": "production", ...},
)
```

`tag_resource` is idempotent for matching key/value pairs.

`CreateHarness` accepts `tags` at creation time, but `UpdateHarness` was deliberately split. Same pattern likely applies to other resource types (memories, runtimes).

#### 3.2.3 `clientToken` min length is 33 characters

```
ParamValidationError: Parameter validation failed:
  Invalid length for parameter clientToken, value: 16, valid min length: 33
```

`secrets.token_hex(8)` gives 16 chars — **too short, will fail validation**.
`secrets.token_hex(20)` gives 40 chars — safe.

This caused a latent bug in PR #40's `attach_memory.py` (filed as #46, fixed in PR #50) — it never tripped in production because the memory was already attached on first run, so the `update_harness` call was never made. The bug also motivated the §4 live-test mandate (PR #53).

#### 3.2.4 Memory: `strategyId`, NOT `memoryStrategyId`

When building `retrievalConfig` inside the memory payload:

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

#### 3.2.5 `skills` member is a UNION of three source types — `git` source has NO branch field

`UpdateHarness.skills` accepts a list of skill objects. Each skill object has exactly ONE source type from a 3-way UNION:

```python
# Option A: path source (local file in container; useful for custom-image deployments)
{"path": {"path": "/skills/ui-testing"}}

# Option B: s3 source (object in S3 bucket)
{"s3": {"bucket": "my-bucket", "prefix": "skills/ui-testing", "versionId": "..."}}

# Option C: git source (path inside a GitHub repo at default branch)
{"git": {
    "url": "https://github.com/owner/repo",
    "path": "app/ui-test-agent/skills/ui-testing"
    # NO "branch" field — fetches from the repo's default branch
    # NO "auth" needed for public repos; private repos use Token Vault
}}
```

**Critical limitation of git source:** there is **no `branch` field** on `git` source. AgentCore fetches from the repo's **default branch** (`main`) at session start. This has two implications:

- 4b functional verification of a git-source skill is **impossible pre-merge** for a SKILL.md that lives only on a feature branch — it's the legitimate "alternative verification path" per change-discipline.md "When to deviate" (PR #55 / #59 set the precedent).
- Forking a private branch for testing won't work; the SKILL.md must be on the default branch first.

Verified via schema introspection (§7.1) in PR #51 / #55.

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
- Each Memory has multiple **strategies** (semantic, episodic, summarization, user_preference, custom). See §3.10 for the UNION shape.
- A Memory is attached to a Harness via `update_harness(memory={...})` (or set on creation). **See §3.9 — there is a required IAM step that's separate from this attachment.**
- Memory namespace templates use `{actorId}` and `{sessionId}` placeholders. The agent invocation determines the actual values.
- This project's convention for `actorId`:
  - `ci-pipeline` for CI runs (shared memory across tests)
  - `dev-{username}` for ad-hoc dev runs
  - `repo-{owner}-{name}` for Bug-Fix Agent (per-repo scoping; see PR #54)
  - `tenant-{tenantId}` for future multi-tenant (tracked in #36)

### 3.8 SKILL.md must have YAML frontmatter (`name` + `description`)

A `SKILL.md` file referenced by `skills[].git.path`, `skills[].path.path`, or `skills[].s3.prefix` MUST start with a YAML frontmatter block:

````markdown
---
name: ui-testing
description: Methodology and rubrics for UI testing
---

# UI Testing Skill
... rest of skill content ...
````

Without the frontmatter, `InvokeHarness` fails at session start with:

```
runtimeClientError: SKILL.md in .agents/skills/git/<hash>/<repo-path>/skills/<skill-name>
has no YAML frontmatter (must start with ---)
```

Required keys:
- `name` — identifier the agent uses to invoke the skill (lowercase, no spaces). The agent calls `skills` tool with `{"skill_name": "<name>"}`.
- `description` — one-line description of what the skill does

This requirement is undocumented in the official AgentCore guide. Both PR #51 (UI Test) and PR #55 (Bug-Fix) initially shipped without it; both surfaced as production bugs caught by PR #57's mandatory 4b functional test (issues #58, #60). Fixed in PR #59 / PR #55 commit `27ed0be0`.

Always validate this requirement before opening a PR that ships a new SKILL.md.

### 3.9 Memory wiring requires THREE coordinated steps (not two)

A working Memory wiring is NOT just "create the Memory + tell the harness about it". The harness's IAM execution role also needs explicit Memory data plane permissions on the new Memory ARN. Without step 3, every harness invocation fails with `AccessDeniedException: ListEvents` at session start.

| # | Step | Tool / API |
|---|---|---|
| 1 | Create the Memory resource | `bedrock-agentcore-control:CreateMemory` (e.g. `create_bugfix_memory.py`) |
| 2 | Reference it from the harness | `bedrock-agentcore-control:UpdateHarness(memory={...})` (e.g. `attach_memory.py`) |
| 3 | **Grant the harness's executionRoleArn perms on the Memory ARN** | **`iam:PutRolePolicy` (e.g. `grant_memory_access.py`)** |

Required permissions in step 3:

| Action set | When needed | Example actions |
|---|---|---|
| Memory events (read + write) | Every session start (auto by runtime) | `ListEvents`, `CreateEvent`, `GetEvent`, `ListSessions`, `ListActors` |
| Memory record retrieval | Every session start with `retrievalConfig` | `ListMemoryRecords`, `RetrieveMemoryRecords` (scoped by `bedrock-agentcore:namespace` Condition) |

The retrieval Condition's `bedrock-agentcore:namespace` IAM key must match the namespace **patterns** in `retrievalConfig`. Note the conversion:

| Where | Format | Example |
|---|---|---|
| `Memory.retrievalConfig` keys | `{placeholder}` syntax | `/fix-history/{actorId}/{sessionId}` |
| IAM Condition `StringLike` value | glob `*` pattern | `/fix-history/*/*` |

Convert via regex `\{[^}]+\}` → `*`.

**Convention used in this repo:** inline policy named `<HarnessName>MemoryAccess` per Memory wire. The `grant_memory_access.py` script (PR #61) is idempotent and discovers harnesses with Memory wired automatically. As of PR #64, both `attach_memory.py` and `create_bugfix_memory.py` call this function automatically as their final step.

This was discovered the hard way: PR #54 wired BugFix Memory but skipped step 3; PR #57's 4b mandate caught it on the first invocation; fixed in PR #61.

### 3.10 `Memory.memoryStrategies` member is a UNION; episodic needs `reflectionConfiguration`

Each item in `CreateMemory.memoryStrategies` (and the same for the strategies-modifications shape on `UpdateMemory`) is a UNION over 5 strategy types — exactly ONE key per item:

| Key | Purpose | Required sub-fields |
|---|---|---|
| `semanticMemoryStrategy` | Vector-similar past content | `name`, `namespaces`, `description` |
| `summaryMemoryStrategy` | Compressed conversation summaries | `name`, `namespaces`, `description` |
| `userPreferenceMemoryStrategy` | Per-actor preferences (auto-extracted) | `name`, `namespaces`, `description` |
| `episodicMemoryStrategy` | Past sessions as discrete episodes | `name`, `namespaces`, `description`, **`reflectionConfiguration`** |
| `customMemoryStrategy` | Bring-your-own (advanced) | `name`, `namespaces`, `description`, `customConfiguration` |

Caveats discovered in PR #54:

1. **`namespaces`** is a list of **strings** with `{actorId}` / `{sessionId}` placeholders — e.g. `["/fix-patterns/{actorId}"]`. These translate to glob patterns in IAM Condition (see §3.9).

2. **`episodicMemoryStrategy` requires `reflectionConfiguration`**. Validation rejects an episodic strategy without it. Minimum form:

   ```python
   {"reflectionConfiguration": {"reflectionPrefix": "Episode summary:"}}
   ```

   This prefix is the marker the strategy uses to identify the start of each episode in the event stream.

3. Strategy modifications on `UpdateMemory` use `addMemoryStrategies` / `modifyMemoryStrategies` / `deleteMemoryStrategies` — separate fields, not direct list assignment.

Adding new strategies has cost implications: each strategy processes events in background to extract long-term records, consuming compute resources.

### 3.11 Harness tools wiring — 4 gotchas that cost a lot of debug time

Discovered while investigating issue #21 (originally framed as "Container mode for Playwright"; turned out to be 4 separate config bugs).

#### 3.11.1 Harness mode is already a Container deployment by default

Don't be misled by older docs about "switching to Container mode". When you create a Harness, AgentCore provisions a runtime with the public harness loader image as `containerConfiguration.containerUri`:

```json
"agentRuntimeArtifact": {
  "containerConfiguration": {
    "containerUri": "public.ecr.aws/i0n3d3i5/harness-us-east-1:latest"
  }
}
```

The Harness IS the container. The image already has all the wiring for `agentcore_browser`, `agentcore_code_interpreter`, `skills`, etc. **You do not need to build a custom image** to use these tools (issue #21's original framing was wrong).

If you want to switch to a custom image (advanced), `update_harness(environmentArtifact={"optionalValue": {"containerConfiguration": {"containerUri": "<your-ecr-uri>"}}})` is the API. Don't do this without a strong reason (custom image must implement the harness protocol — HTTP server contract, OTel emission, the agentcore_* tool primitives).

#### 3.11.2 `tools[].config` is documented optional but practically required

The schema shows `tools.member.config` as optional (only `type` is in `required_members`). But omitting `config` means the tool is stored on the harness but **not actually wired at runtime** — agent only sees `skills`.

```python
# ❌ Stored but not wired — agent doesn't see browser/code_interpreter
tools = [
    {"type": "agentcore_browser", "name": "browser"},
    {"type": "agentcore_code_interpreter", "name": "code_interpreter"},
]

# ✅ Wired — config is the activation
tools = [
    {
        "type": "agentcore_browser",
        "name": "browser",
        "config": {
            "agentCoreBrowser": {
                "browserArn": "arn:aws:bedrock-agentcore:us-east-1:aws:browser/aws.browser.v1"
            }
        },
    },
    {
        "type": "agentcore_code_interpreter",
        "name": "code_interpreter",
        "config": {
            "agentCoreCodeInterpreter": {
                "codeInterpreterArn": "arn:aws:bedrock-agentcore:us-east-1:aws:code-interpreter/aws.codeinterpreter.v1"
            }
        },
    },
]
```

The `config` UNION has 5 keys (one per tool type): `remoteMcp` / `agentCoreBrowser` / `agentCoreGateway` / `inlineFunction` / `agentCoreCodeInterpreter`. Empty `{}` for the inner config also works (uses default browser/code-interpreter ARNs), but explicit ARNs are more robust.

#### 3.11.3 `allowedTools` plain-name doesn't match declared tools — use globs

The doc table at https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-tools.html#allowedtools-patterns shows plain names matching builtins (`shell`, `file_operations`). For DECLARED tools (browser, code_interpreter, inline functions), plain names like `"browser"` **do not match** — the entry is filtered out.

```python
# ❌ Filters out browser AND code_interpreter; agent sees only skills
allowedTools = ["browser", "code_interpreter"]

# ✅ Glob matches the primitives the tools expose
allowedTools = ["browser_*", "code_interpreter*", "skills"]

# Also works:
allowedTools = ["*"]  # everything (broad)
```

(`skills` is plain because it's a builtin; matches by name fine.)

#### 3.11.4 `agentcore_browser` exposes 6 primitives, not a single name

When wired via `agentCoreBrowser` config, the tool exposes these primitives to the agent (verified live):

```
browser_navigate
browser_click
browser_type
browser_screenshot
browser_console_messages
browser_network_requests
```

So `allowedTools` must reference primitives or use `browser_*` glob. The harness's `tools[].name = "browser"` is the configuration name; the runtime expansion to primitives is hidden behind the public harness loader.

The agentcore_code_interpreter likely has a similar primitive expansion (not yet enumerated; investigated as part of issue #65).

**Note:** As of issue #65 (filed when this gotcha was discovered), invoking these primitives from the agent still returns errors at the data plane layer — the primitives are visible but `browser_navigate` calls fail. Issue #65 tracks the remaining fix (likely IAM or session resource provisioning).

---
### 3.12 Live View take/release tears down the harness automation context

When an agent runs on a managed Harness with the built-in Browser tool and a human needs to complete an interactive SSO login (IAM Identity Center, MFA, OTP-by-email), there is a real, undocumented gotcha:

- **Broken path:** human clicks **"Take control"** in Browser Live View, completes SSO+OTP, clicks **"Release control"**, then the agent resumes. → The agent's automation context is destroyed; subsequent calls return `Target page, context or browser has been closed` and the backend reports "not initialized / sessions gone". Reproduced across three orchestration strategies (concurrent, hands-off, signal-gated). Filed upstream: <https://github.com/aws/bedrock-agentcore-sdk-python/issues/518>.
- **Working path (workaround):** human interacts in Live View **without** clicking Take control (types directly), AND the agent on resume **must reconnect** — re-read the current page (fresh navigate / get_text / snapshot), do **not** reuse its pre-login page handle. The authenticated session then carries over.

Pair this with an **S3-signal handoff** so the agent stays hands-off the browser while the human logs in (poll an S3 flag via the shell tool only) and a long `read_timeout` (≥ 1800s) on the boto3 client so the streamed turn doesn't get killed by the default 60s read timeout.

Full pattern + scripts: see `references/browser-auth.md` in the [`agentcore-harness-builder`](https://github.com/timwukp/agent-skills-best-practice/tree/main/skills/skills/agentcore-harness-builder/references/browser-auth.md) skill. This is the same pattern that drove the validated Quick POC run cited in §0 of this file's project README.


### 3.13 The agent loop MUST include the deploy path (or it can never converge)

The QA↔Bug-Fix feedback loop (auto-fix commit → PR re-trigger → re-test until green, capped by
`MAX_FIX_ROUNDS`) has a failure mode that is invisible in design reviews and fatal in production:

- the Bug-Fix Agent patches **the repository**;
- the QA agent tests **the running environment** (a deployed site);
- if nothing deploys the fix between those two steps, every re-test round sees the OLD deployment,
  reports the same findings, burns another fix round on already-fixed code, and the loop exits as a
  false failure after `MAX_FIX_ROUNDS`.

This exact gap shipped in the first version of our own `ui-qa-agent.yml`: the repo's `deploy.yml`
was `workflow_dispatch`-only (manual), so auto-fix commits never reached the CloudFront site the QA
agent was testing. The loop *looked* complete — trigger, test, fix, re-trigger — and could never
converge.

**Rule: the pipe between "agent fixes the repo" and "agent tests the environment" (build → upload →
cache invalidation → wait-until-live) is part of the loop, not an external assumption.** Put the
deploy step inside the QA workflow itself, before the test run, and wait for propagation
(`aws cloudfront wait invalidation-completed`) — a fast re-test against a stale CDN is the same bug
with extra steps.

Corollary — make convergence observable: pass the previous round's report to the QA agent
(`--prior-report`) and require a per-finding verdict (`FIXED` / `STILL_FAILING`) in the output. A
"green" run that never re-checked the specific prior findings is weak evidence; a reconciliation
table on the PR is strong evidence.

### 3.14 Agents hand off unfixable bugs as failing tests — treat the red CI as a work contract

Observed live (PR #30 of the token-monitoring demo, 2026-07-25), unprompted: the Bug-Fix Agent hit
findings it could not fix from inside the repo — a missing pricing entry (it doesn't know real
rates and refused to invent them) and a data-layer dedup rule. Instead of skipping them or
hallucinating values, it **wrote failing guard tests that pin the correct behavior**:

- `matchRate('fable-5') must return a non-zero rate (pricing entry must exist)` — red until a
  human added the real \$10/\$50 per-MTok rates;
- `summarizeCosts merges ARN-vs-bare-id duplicate rows and drops zero-usage rows` — red until the
  dedup logic was implemented to that exact spec.

That is test-driven development used as an **agent→human handoff protocol**: the failing test is a
machine-checkable requirements doc. The human contribution (real pricing data, a product decision)
plugs into a contract the agent already wrote, and `jest` answers "did I satisfy it?" — no
re-review by the agent needed.

Two rules that fall out of this:

1. **Don't "fix" a red CI by deleting an agent-authored test.** First check whether it encodes a
   real requirement the agent couldn't satisfy alone (ours did, both times). Delete only when the
   test asserts something that genuinely doesn't exist (we also saw that once: a test for a
   nonexistent `ContainmentDecision.timestamp` field — invented, not pinned).
2. **Prompt for it.** If you want this behavior reliably, add to the bug-fix agent's instructions:
   "If a finding needs data or a decision you don't have, write a failing test that specifies the
   correct behavior instead of guessing." Stronger models (Opus-tier and above) do this
   spontaneously; weaker ones need the nudge.

## 4. Repo methodology — read this before opening a PR

This repo's methodology has three layers:

| Layer | Document | What it covers |
|---|---|---|
| **Artifact** | [`AGENTS.md`](AGENTS.md) (this file) | Institutional memory: invariants, AWS gotchas, tooling versions |
| **Abstract pattern: context** | [`docs/methodology/agent-onboarding.md`](docs/methodology/agent-onboarding.md) | How to make any repo legible to AI agents |
| **Abstract pattern: change** | [`docs/methodology/change-discipline.md`](docs/methodology/change-discipline.md) | How to land changes: issue granularity, PR sizing, anti-patterns, stacked PRs, templates, **comprehensive testing mandate** |
| **Practical contract** | [`docs/DEVELOPMENT_WORKFLOW.md`](docs/DEVELOPMENT_WORKFLOW.md) | The lightweight day-to-day contract for THIS repo |

Order of consultation when planning a change:
1. **AGENTS.md** — does my change violate an invariant?
2. **change-discipline.md** — is this stack-eligible? Does my 4b plan need a 2-PR split?
3. **DEVELOPMENT_WORKFLOW.md** — what does the issue/PR template look like?

In practice every change follows the **issue → fix → PR** loop. Brief summary:

1. Open an **issue** with: Problem / Evidence / Proposed Solution / Acceptance Criteria / Priority / Effort / Out of Scope.
2. Branch named `<type>/issue-<N>-<short-desc>` (e.g. `feat/issue-24-memory-uitestagent`).
3. Commits follow [Conventional Commits](https://www.conventionalcommits.org/) format with `(#N)` issue reference.
4. **One issue = one logical change.** Don't bundle unrelated work.
5. **⚠️ Comprehensive test on AWS BEFORE opening the PR** for any code touching AWS APIs:
   - **(4a)** API-level: apply + idempotent re-run + `get_*`/`list_*` verify path
   - **(4b)** Functional / E2E: invoke the feature, observe runtime behavior matches expectations
   - BOTH required. Doc-only PRs exempt. Deferring "to post-merge" or "to save money" is NOT acceptable.
   - If 4b genuinely cannot be done pre-merge (e.g. depends on same-PR content reaching `main`), split into prereq PR + main PR — not a follow-up.
   - See [`change-discipline.md` §"5-step loop" Step 4](docs/methodology/change-discipline.md#step-4-fix-one-issue-at-a-time) for full criteria.
6. PR description follows the template in `docs/DEVELOPMENT_WORKFLOW.md` (both 4a and 4b checkboxes).
7. PRs reference `Closes #N` so GitHub auto-closes the issue on merge.
8. Each PR is reviewed and merged before starting the next one.

### Issue label convention

| Label | Use for |
|---|---|
| `enhancement` / `feature` | You already know what to do. Issue defines acceptance criteria. |
| `bug` | Something is broken; fix in scope is clear. |
| `documentation` | Docs-only changes. |
| `discussion` | You don't yet know the right answer. Use the discussion-issue template. |

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
| Programmatic harness update (memory attach) | `agentcore/scripts/attach_memory.py` (PR #40, fixed in PR #50, trinity-aware in PR #64) |
| Programmatic harness update (allowedTools / maxTokens / tags) | `agentcore/scripts/tighten_harness_config.py` (PR #47) |
| Programmatic harness update (skills via git source) | `agentcore/scripts/wire_skills.py` (PR #51, extended in PR #55) |
| Two-phase create + attach (memory) | `agentcore/scripts/create_bugfix_memory.py` (PR #54, trinity-aware in PR #64) |
| **IAM grant for Memory data plane (post-Memory-wire)** | **`agentcore/scripts/grant_memory_access.py` (PR #61, importable function in PR #64)** |
| AWS-resource-aware test verification with redaction | `agentcore/scripts/VERIFICATION_issue_28.md` |
| Methodology dogfooding | `docs/DEVELOPMENT_WORKFLOW.md` (PR #3) |
| Agent-Ready Repo Pattern | `docs/methodology/agent-onboarding.md` (PR #42) |
| Change-discipline methodology | `docs/methodology/change-discipline.md` (PR #44, tightened PR #53, PR #57) |

---

## 7. When you're stuck

**Always do this first** for any AWS API work:

### 7.1 SDK schema introspection

```python
import boto3
c = boto3.client("bedrock-agentcore-control", region_name="us-east-1")
op = c.meta.service_model.operation_model("UpdateHarness")  # or any op name
print("Input fields:")
for name, member in op.input_shape.members.items():
    print(f"  {name}: {member.type_name}")
    # for nested structures, recurse via member.members
```

This reveals:
- Exact field names (case-sensitive)
- Field shapes (string / integer / list / structure / map)
- Whether a field is a structure (likely `optionalValue` wrapper) or a plain type (no wrapper) — see §3.2.1
- Required vs optional fields (via `op.input_shape.required_members`)
- Sub-structure UNIONs (e.g. `tools[].config`, `skills[].member`, `Memory.memoryStrategies[].member`)

Doing this BEFORE writing payload code saves hours.

### 7.2 List operations containing a keyword

```python
for op_name in c.meta.service_model.operation_names:
    if "tag" in op_name.lower():
        print(op_name)
```

Useful for discovering side-channel APIs like `TagResource` / `ListTagsForResource` / `UntagResource` that aren't fields on the main `Update*` operations.

### 7.3 Other escalation steps

If the public boto3 SDK seems to lack an operation you need:

1. **Check your boto3 version first.** `pip show boto3 | grep -i version`. AgentCore adds operations in nearly every release; older versions just don't have them.
2. **Search AWS docs:** `https://docs.aws.amazon.com/search?searchPath=documentation&searchQuery=YOUR_OPERATION` — if the operation is documented, it exists in the API even if your local SDK is out of date.
3. **Look at the CloudFormation type spec** for the resource — that's the schema-of-truth.
4. **Check the [bedrock-agentcore-sdk-python](https://github.com/aws/bedrock-agentcore-sdk-python) source** — even if the operation isn't there, allowlisted method names hint at API shapes.
5. **Don't conclude "console-only" without verifying SDK version.**

### 7.4 "Memory wired but invocation fails 401 / AccessDenied"

Symptom:

```
EventStreamError: ...AccessDeniedException...is not authorized to perform:
  bedrock-agentcore:ListEvents on resource: ...:memory/...
```

Cause: harness execution role missing Memory data plane perms on the Memory ARN — see §3.9 (Memory wiring trinity, step 3 was skipped).

Fix:

```bash
/path/to/newer-boto3/python3 agentcore/scripts/grant_memory_access.py
```

The script discovers harnesses with Memory wired and ensures each role has the canonical `<HarnessName>MemoryAccess` inline policy. Idempotent — safe to re-run. As of PR #64, the Memory wire scripts call this automatically as a final step.

If the policy already exists but invocation still fails, check the `bedrock-agentcore:namespace` Condition allows the namespaces in your harness's `retrievalConfig` (see §3.9 namespace conversion rule).

### 7.5 SKILL.md not loading at session start

Symptom:

```
runtimeClientError: SKILL.md in .agents/skills/git/<hash>/.../<skill-name>
has no YAML frontmatter (must start with ---)
```

Cause: missing or malformed YAML frontmatter — see §3.8.

Fix: prepend the file with the frontmatter block. For git-source skills, the fix must merge to default branch before it takes effect (see §3.2.5 — there's no branch field on git source).

### 7.6 Harness has tools declared but agent says "I only have skills"

Symptom: agent enumerates tools and reports only `skills` is available, even though `harness.json` declares browser/code_interpreter/inline_functions.

Cause: one of three configuration bugs (see §3.11):

1. `tools[].config` field is missing — tool isn't actually wired (§3.11.2)
2. `allowedTools` uses plain names — they don't match declared tools (§3.11.3)
3. `agentcore_browser` exposes primitives, not a single name — you allowed `["browser"]` but the runtime knows `["browser_navigate", ...]` (§3.11.4)

Fix:

```python
# 1. Add config to each tool
tools = [{"type": "agentcore_browser", "name": "browser",
          "config": {"agentCoreBrowser": {"browserArn": "..."}}}]

# 2. Use globs in allowedTools
allowedTools = ["browser_*", "code_interpreter*", "skills"]

# 3. Apply
control.update_harness(harnessId=..., tools=tools, allowedTools=allowedTools, clientToken=...)
```

If the agent now sees the primitives but invocations of `browser_navigate` etc. fail with errors, that's a different bug — see issue #65.

---

## 8. Project state (auto-stale; check git for current)

- `PROJECT_STATE.md` — persistent project state, updated periodically
- `CHANGELOG.md` — Keep-a-Changelog versioned history
- Last major audit: **v0.2.1** (2026-05-30) — sync of all docs with code reality
- v0.2.2 in progress: Harness configuration (Memory + skills + tighten + IAM + tools-wiring) + comprehensive testing methodology

---

*If you find a new gotcha while working on this repo, add it to Section 3 of this file in your PR. Future agents will thank you.*
