# AWS Bedrock AgentCore Harness — Best Practices

> **Status:** Public Preview (May 2026)
> **CLI Version:** `@aws/agentcore` v0.14.0
> **SDK:** `boto3` (`bedrock-agentcore` service client)
> **Regions:** us-east-1, us-west-2, eu-central-1, ap-southeast-2

---

## Table of Contents

1. [When to Choose AgentCore Harness](#when-to-choose-agentcore-harness)
2. [When NOT to Use Harness](#when-not-to-use-harness)
3. [Architecture Decision Framework](#architecture-decision-framework)
4. [Project Setup Best Practices](#project-setup-best-practices)
5. [Model Configuration](#model-configuration)
6. [Tool Integration](#tool-integration)
7. [Browser Tool — Production Features](#browser-tool--production-features)
8. [Memory Strategy](#memory-strategy)
9. [Environment & Skills](#environment--skills)
10. [Security](#security)
11. [Cost Control & Observability](#cost-control--observability)
12. [Development Workflow](#development-workflow)
13. [Production Readiness Checklist](#production-readiness-checklist)

---

## When to Choose AgentCore Harness

### The Core Value Proposition

AgentCore Harness replaces the undifferentiated heavy lifting of building an agent runtime. Instead of writing orchestration code, you **declare** what your agent does and AWS handles the infrastructure.

### Choose Harness When:

| Scenario | Why Harness Wins |
|----------|-----------------|
| **Rapid prototyping** | Go from idea to running agent in minutes, not days |
| **Multi-model experimentation** | Switch between Bedrock, OpenAI, Gemini with a config change — even mid-session |
| **Stateful agents** | Built-in memory (STM + LTM) and persistent filesystem per session |
| **Human-in-the-loop workflows** | Inline functions pause the agent and return control to your code |
| **Agents that need a shell** | Each session has its own microVM with filesystem + bash — run scripts, install packages, execute code |
| **Teams without infra expertise** | No Docker, no ECS, no Lambda wiring — just `agentcore deploy` |
| **Config-driven iteration** | Test N model/prompt/tool combinations without redeploying |
| **Secure multi-tenant agents** | Per-session isolation (Firecracker microVM), per-actor memory scoping |
| **Agents that browse the web** | Built-in Browser tool, no Playwright setup needed |
| **Agents that execute code** | Built-in Code Interpreter (Python/JS/TS sandbox) |

### Real-World Use Cases Best Suited for Harness:

1. **Coding assistants** — agent needs filesystem, shell, git, custom container
2. **Research agents** — browse web, synthesize findings, remember across sessions
3. **Data analysis agents** — execute Python, produce charts, persist results
4. **Customer support agents** — multi-tenant memory, human escalation via inline functions
5. **DevOps automation** — run shell commands, inspect infrastructure, take action
6. **Document processing** — upload files, process with code interpreter, return results

---

## When NOT to Use Harness

### Choose AgentCore Runtime (DIY) Instead When:

| Scenario | Why DIY is Better |
|----------|-------------------|
| **Custom orchestration logic** | You need non-standard agent loops (e.g., multi-agent coordination, custom retry/fallback) |
| **Embedding in existing apps** | Your agent is a component inside a larger application with its own HTTP server |
| **Sub-second latency requirements** | Harness has session startup overhead (~seconds for cold start) |
| **Streaming with custom protocols** | You need WebSocket or SSE with custom framing beyond what `InvokeHarness` provides |
| **Framework lock-in avoidance** | You want full control over the Strands/LangChain/etc. integration |
| **Cost-sensitive high-volume** | Thousands of short-lived, stateless invocations where microVM overhead matters |

### Choose Neither (Use Bedrock Agents Instead) When:

- You want a fully no-code solution with console-based configuration
- Your agent only needs simple tool calling without filesystem/shell access
- You don't need multi-model or mid-session model switching

---

## Architecture Decision Framework

```
┌─────────────────────────────────────────────────────────────┐
│                    Do you need...                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Filesystem + Shell access?  ──── YES ──→  HARNESS           │
│         │                                                    │
│         NO                                                   │
│         │                                                    │
│  Multi-model switching?  ──── YES ──→  HARNESS               │
│         │                                                    │
│         NO                                                   │
│         │                                                    │
│  Stateful sessions with memory?  ──── YES ──→  HARNESS       │
│         │                                                    │
│         NO                                                   │
│         │                                                    │
│  Custom orchestration logic?  ──── YES ──→  AGENTCORE (DIY)  │
│         │                                                    │
│         NO                                                   │
│         │                                                    │
│  Simple tool-calling agent?  ──── YES ──→  BEDROCK AGENTS    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Project Setup Best Practices

### 1. Use the CLI for Project Scaffolding

```bash
# Install (stable channel)
npm install -g @aws/agentcore

# Create project (interactive wizard recommended for first time)
agentcore create

# Or non-interactive for CI/CD
agentcore create --name my-agent --model-provider bedrock
```

### 2. Project Structure Convention

```
my-project/
├── agentcore/
│   ├── .env.local              # API keys (gitignored)
│   ├── agentcore.json          # Resource specifications
│   ├── aws-targets.json        # Deployment targets (account, region)
│   └── cdk/                    # CDK infrastructure (auto-generated)
├── app/
│   └── <AgentName>/
│       ├── main.py             # Agent entry point
│       ├── pyproject.toml      # Python dependencies
│       ├── harness.json        # Harness configuration (if using harness)
│       └── model/              # Model configuration
├── .gitignore
└── README.md
```

### 3. Git Hygiene

```gitignore
# Always gitignore
agentcore/.env.local
agentcore/.cli/
*.pyc
__pycache__/
```

---

## Model Configuration

### Best Practice: Set Sensible Defaults, Override at Invoke Time

```bash
# Set default model at creation
agentcore add harness --name my-agent \
  --model-id us.anthropic.claude-sonnet-4-5-20250514-v1:0 \
  --system-prompt "You are a helpful research assistant."

# Override for a specific call (no redeploy needed)
agentcore invoke --harness my-agent \
  --model-id us.anthropic.claude-opus-4-5-20251101-v1:0 \
  "Complex reasoning task that needs a stronger model"
```

### Multi-Model Strategy

> **Note:** The harness defaults to Claude Sonnet 4.6 (`global.anthropic.claude-sonnet-4-6`) if no model is specified. The CLI scaffolds projects with Claude Sonnet 4.5 (`us.anthropic.claude-sonnet-4-5-20250514-v1:0`).

| Use Case | Recommended Model | Why |
|----------|-------------------|-----|
| General tasks | Claude Sonnet 4.5/4.6 | Best cost/quality balance |
| Complex reasoning | Claude Opus 4.5 | Higher accuracy for hard problems |
| Fast lookups | Claude Haiku | Low latency, low cost |
| Code generation | Claude Sonnet 4.5+ or GPT-4.1 | Strong coding capabilities |
| Comparison testing | Switch mid-session | Same context, different model |

### Third-Party API Keys

```bash
# Store in Token Vault (never hardcode)
agentcore add credential --type api-key --name my-openai-key --api-key $OPENAI_API_KEY
agentcore deploy

# Use at invoke time
agentcore invoke --harness my-agent \
  --model-provider open_ai \
  --model-id gpt-4.1 \
  --api-key-arn arn:aws:bedrock-agentcore:us-west-2:123456789012:token-vault/default/apikeycredentialprovider/my-openai-key \
  "Your prompt"
```

**Rule:** Never put API keys in `harness.json` or source code. Always use AgentCore Identity Token Vault.

---

## Tool Integration

### Tool Selection Hierarchy

1. **Built-in tools first** — `shell` and `file_operations` are free and always available
2. **AgentCore services second** — Browser, Code Interpreter (managed, no setup)
3. **Remote MCP servers** — for simple external integrations
4. **AgentCore Gateway** — when you need auth, policy enforcement, or credential rotation
5. **Inline functions** — for human-in-the-loop or client-side logic

### Restrict Tools with `allowedTools`

```json
{
  "allowedTools": [
    "@builtin/shell",
    "@builtin/file_operations",
    "@exa/search",
    "@my-gateway/*"
  ]
}
```

**Rule:** In production, always set `allowedTools` explicitly. Never leave it as `*` (all tools allowed).

### Secure MCP Server Connections

```bash
# Bad: hardcoded API key
agentcore add tool --type remote_mcp --name exa \
  --url https://mcp.exa.ai/mcp \
  --header 'x-api-key=sk-live-xxx'

# Good: reference Token Vault
agentcore add tool --type remote_mcp --name exa \
  --url https://mcp.exa.ai/mcp \
  --header 'x-api-key=${arn:aws:bedrock-agentcore:us-west-2:123456789012:token-vault/default/apikeycredentialprovider/my-exa-key}'
```

### Inline Functions for Human-in-the-Loop

```python
# Client-side handling of inline function calls
response = client.invoke_harness(
    harnessArn=HARNESS_ARN,
    runtimeSessionId=SESSION_ID,
    tools=[{
        "type": "inline_function",
        "name": "approve_action",
        "config": {"inlineFunction": {
            "description": "Request human approval before executing.",
            "inputSchema": {
                "type": "object",
                "properties": {"action": {"type": "string"}, "risk": {"type": "string"}},
                "required": ["action", "risk"]
            }
        }}
    }],
    messages=[{"role": "user", "content": [{"text": "Delete the staging database"}]}],
)

# When stopReason == "tool_use", handle client-side and send result back
```

> **Browser tool note:** For Browser-tool-specific production features (profiles, session recording, Web Bot Auth), see the next section.

---

## Browser Tool — Production Features

The AgentCore Browser tool is fine for local development out of the box, but moving to production usually requires three additional features that are **not enabled by default**:

| Feature | Production reason |
|---|---|
| **Profiles** | Persist authenticated state so each test run doesn't pay the login round-trip |
| **Session Recording** | Compliance, audit, and debugging — replay every action a browser session took |
| **Web Bot Auth** | Cryptographically identify the browser to opt-in sites that reduce CAPTCHA for trusted bots |

Enable each only when you need it; defaults are conservative for cost and security reasons.

### 7.1 Browser Profiles — persist authenticated state across sessions

**What it is.** A named, AWS-managed storage container that holds cookies, local storage, and session state for the browser. When a browser session starts with a profile reference, the browser loads that state — equivalent to "the user is already logged in."

**When to use:**
- Repeated tests that all need the same authenticated user (login flow runs once, all subsequent runs skip it)
- SSO-heavy applications where the login flow is slow or interactive (MFA, OIDC redirect chains)
- Demo / customer-facing scenarios where you want a stable "demo user" session

**When NOT to use:**
- Login flow itself is what you're testing — you must start unauthenticated
- Multi-tenant agents where different actors must NEVER share state — risk of session leakage between tenants
- Short-lived auth (tokens that expire faster than your test cadence) — re-login anyway
- Anything testing logout / session-expiry behaviour

**Creating a profile (control plane):**

```python
import boto3

control = boto3.client("bedrock-agentcore-control", region_name="us-west-2")
profile = control.create_browser_profile(
    name="qa-test-user-staging",
    description="Pre-authenticated QA user for staging.example.com tests",
    # Encryption uses AWS-managed key by default; specify CMK for stricter control
    # kmsKeyArn="arn:aws:kms:us-west-2:<ACCOUNT_ID>:key/<KEY_ID>",
)
profile_id = profile["profileIdentifier"]
```

Then populate it once by running a session that performs the login. Subsequent sessions reference the profile and inherit the stored state.

**Using a profile (data plane):**

```python
data = boto3.client("bedrock-agentcore", region_name="us-west-2")
session = data.start_browser_session(
    browserIdentifier="aws.browser.v1",
    profileConfiguration={"profileIdentifier": profile_id},
    # ... viewport, timeout, etc.
)
```

**IAM:**
- Caller needs `bedrock-agentcore:CreateBrowserProfile` (control) and `bedrock-agentcore:StartBrowserSession` (data) — scope `Resource` to specific profile ARNs in production

**Security considerations:**
- **Per-tenant scoping:** Always use a profile-per-actor naming scheme (e.g. `qa-{tenantId}-staging`); never share a profile across tenants
- **Rotation:** Profiles persist indefinitely until deleted; treat them like any other long-lived credential and rotate periodically
- **Auditing:** CloudTrail logs every `StartBrowserSession` call, including the `profileIdentifier` used — enable trails on the AgentCore control plane

**Cost impact:** Profiles save Bedrock token cost on every test run that would otherwise drive a multi-step login. Storage is included in the Browser tool pricing — no separate per-profile fee at the time of writing.

**Anti-pattern:** Putting **production** credentials in a profile used by an agent that ever runs against staging or dev. If the profile leaks, all environments are compromised. Keep one profile per environment.

### 7.2 Session Recording — capture every action for compliance and debugging

**What it is.** Bedrock AgentCore Browser can record an entire browser session as a structured log of DOM mutations, network calls, console output, and screenshots. Recordings are written to an S3 bucket you provide and can be replayed in the AgentCore console.

**When to enable:**
- **Compliance / audit:** SOC2, HIPAA, or internal policy requires evidence that automation accessed only what it was authorized to
- **Production tests:** when an agent fails in CI, the recording is the fastest way to root-cause without re-running
- **Flaky test diagnosis:** intermittent failures often only reveal themselves on the 50th replay
- **Customer demos:** capture once, replay forever — no live infra required

**When NOT to enable:**
- Local dev iteration — slows everything down for no benefit
- Tests on PII-containing pages without strong S3 + KMS hygiene — recordings can capture screen content including sensitive data

**Configuration (data plane):**

```python
session = data.start_browser_session(
    browserIdentifier="aws.browser.v1",
    recordingConfiguration={
        "s3Bucket": "agentcore-browser-recordings-prod",
        "s3KeyPrefix": f"qa-runs/{date.today().isoformat()}/",
        # Optional: customer-managed KMS key for the recording
        "kmsKeyArn": "arn:aws:kms:us-west-2:<ACCOUNT_ID>:key/<KEY_ID>",
    },
    # ... profileConfiguration, viewport, timeout, etc.
)
```

**IAM — execution role needs to write to the bucket:**

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "s3:PutObject",
      "s3:PutObjectAcl"
    ],
    "Resource": "arn:aws:s3:::agentcore-browser-recordings-prod/qa-runs/*"
  }]
}
```

**S3 bucket policy — only AgentCore writes, only your account reads:**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowAgentCoreWrite",
      "Effect": "Allow",
      "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::agentcore-browser-recordings-prod/*",
      "Condition": {"StringEquals": {"aws:SourceAccount": "<ACCOUNT_ID>"}}
    },
    {
      "Sid": "DenyUnencryptedUploads",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::agentcore-browser-recordings-prod/*",
      "Condition": {"Null": {"s3:x-amz-server-side-encryption": "true"}}
    }
  ]
}
```

**Retention strategy.** Use S3 Lifecycle rules:

```json
{
  "Rules": [{
    "Id": "ExpireBrowserRecordings",
    "Status": "Enabled",
    "Prefix": "qa-runs/",
    "Expiration": {"Days": 90},
    "Transitions": [{"Days": 30, "StorageClass": "GLACIER"}]
  }]
}
```

90-day retention covers most audit windows; tier to Glacier after 30 days to keep storage cost trivial.

**Cost impact:**
- S3 storage: ~$0.023/GB/month standard, ~$0.004/GB/month Glacier
- A typical 5-minute test session produces 5–20 MB recorded — ~$0.002 per recording in standard tier
- Browser-side overhead is included in per-minute Browser pricing — no separate recording fee

**Security:**
- **Always encrypt at rest** — bucket policy `DenyUnencryptedUploads` above
- **Use a KMS CMK if recordings touch PII** — the default AWS-managed key is fine for internal QA, but customer-managed gives you key-rotation and access-audit control
- **Object Lock** on the bucket if recordings are evidentiary (legal / compliance) — prevents tampering even by privileged IAM users

### 7.3 Web Bot Auth — cryptographic identity to reduce CAPTCHA friction

**What it is.** Web Bot Auth is a draft IETF standard ([draft-meunier-web-bot-auth](https://datatracker.ietf.org/doc/draft-meunier-web-bot-auth/)) where a bot signs each HTTP request with a private key, and the target site verifies the signature against a registered public key. Sites that opt in can use this signal to **skip CAPTCHA challenges** for trusted bots while still blocking unknown automation.

The AgentCore Browser supports configuring a key pair so all browser-tool requests carry the signature.

**When useful:**
- The target site has explicitly opted into Web Bot Auth (e.g. participates in an industry pilot, has an `/.well-known/http-message-signatures-directory` endpoint)
- You're running synthetic monitoring against your own production sites and want monitoring traffic to bypass your bot mitigation
- You're testing partner sites where you have a relationship to register your bot identity

**When NOT useful:**
- Sites that haven't opted in — Web Bot Auth headers are ignored; CAPTCHA still fires
- Test environments you control — disable bot mitigation for the test source IP / VPC instead
- Any site where bypassing CAPTCHA would violate ToS — Web Bot Auth is a cooperative protocol, not a circumvention tool

**Configuration:**

```python
# 1. Generate Ed25519 key pair, register the public key with the target site's
#    Web Bot Auth directory (out-of-band; site-specific process)
# 2. Store the private key in AWS Secrets Manager
# 3. Configure the Browser session to sign with that key

session = data.start_browser_session(
    browserIdentifier="aws.browser.v1",
    webBotAuthConfiguration={
        "signingKeySecretArn": "arn:aws:secretsmanager:us-west-2:<ACCOUNT_ID>:secret:browser-webbotauth-key-XXXX",
        "keyId": "ui-test-agent-2026-q2",
    },
    # ... profileConfiguration, recordingConfiguration, etc.
)
```

**IAM — execution role needs read access to the secret:**

```json
{
  "Effect": "Allow",
  "Action": "secretsmanager:GetSecretValue",
  "Resource": "arn:aws:secretsmanager:us-west-2:<ACCOUNT_ID>:secret:browser-webbotauth-key-*"
}
```

**Limitations:**

- Not a CAPTCHA bypass — sites still choose whether to honor signed bots
- Adoption is early (2026); most public sites do not yet recognize it
- Each origin tracks its own list of trusted public keys — you cannot register once for the whole web

**Key rotation:** Treat the signing key like any other long-lived credential. Generate a new key annually, register the new public key with the target site's directory before deactivating the old one, then update `signingKeySecretArn` and `keyId` in the session config.

---

## Memory Strategy

### Default: Let the CLI Handle It

```bash
# Memory is enabled by default
agentcore create --name my-agent

# Disable only if you explicitly don't need it
agentcore create --name stateless-agent --no-harness-memory
```

### Multi-Tenant Memory with Actor IDs

```bash
# Each user gets isolated memory
agentcore invoke --harness my-agent --actor-id user-alice --session-id "$(uuidgen)" "Hello"
agentcore invoke --harness my-agent --actor-id user-bob --session-id "$(uuidgen)" "Hello"
```

**Rule:** Always pass `actorId` in multi-tenant applications. Without it, all users share the same memory namespace.

### Long-Term Memory Strategies

| Strategy | Use Case | Example |
|----------|----------|---------|
| **Semantic** | Domain facts, knowledge | "The client prefers PostgreSQL over MySQL" |
| **Summarization** | Session summaries | "In our last session, we decided to use React" |
| **User Preference** | User behavior/settings | "User prefers concise answers" |
| **Episodic** | Event sequences | "Steps taken to resolve the deployment issue" |

### Session Continuity Patterns

```bash
# Pattern 1: Continue same conversation (reuse session ID)
SESSION_ID="$(uuidgen)"
agentcore invoke --harness my-agent --session-id "$SESSION_ID" "Start research"
agentcore invoke --harness my-agent --session-id "$SESSION_ID" "Continue from where we left off"

# Pattern 2: New session, same actor (long-term memory carries over)
agentcore invoke --harness my-agent --actor-id alice --session-id "$(uuidgen)" "What do you remember?"
```

### Filesystem Persistence

The harness supports three filesystem types for persisting files beyond a single session:

| Type | Use Case | VPC Required |
|------|----------|--------------|
| **Session Storage** | Per-session files that survive stop/resume cycles | No |
| **Amazon EFS** | Shared storage across sessions and agents | Yes |
| **Amazon S3 Files** | Bidirectional sync with S3 bucket | Yes |

```bash
# Session storage (simplest — no VPC needed)
agentcore create --name my-agent --session-storage /mnt/data/

# EFS (shared across agents — requires VPC)
# Configure via boto3/AWS CLI with EFS access point ARN
```

**Best Practices:**
- Use **Session Storage** for scratch files and intermediate results within a session
- Use **EFS** when multiple agents or harnesses need to share the same files
- Use **S3 Files** when you need files accessible outside AgentCore (e.g., for downstream pipelines)
- Mount paths must be under `/mnt/`

---

## Environment & Skills

### Use `InvokeAgentRuntimeCommand` for Deterministic Work

```bash
# No model reasoning, no token cost
agentcore invoke --exec --harness my-agent --session-id "$SID" \
  "pip install pandas && git clone https://github.com/org/repo.git"
```

```python
# boto3 equivalent
response = client.invoke_agent_runtime_command(
    agentRuntimeArn=HARNESS_ARN,
    runtimeSessionId=SESSION_ID,
    body={"command": "ls -la /workspace"},
)

for event in response["stream"]:
    chunk = event.get("chunk", {})
    if "contentDelta" in chunk:
        delta = chunk["contentDelta"]
        if "stdout" in delta:
            print(delta["stdout"], end="", flush=True)
        if "stderr" in delta:
            print(delta["stderr"], end="", flush=True)
    elif "contentStop" in chunk:
        print(f"\n[exit code: {chunk['contentStop']['exitCode']}]")
```

**Rule:** Use `--exec` for setup, teardown, and deterministic scripts. Save model invocations for reasoning tasks.

### Environment Variables

Set environment variables in `harness.json`:

```json
{
  "environmentVariables": {
    "MY_API_URL": "https://api.example.com",
    "LOG_LEVEL": "debug"
  }
}
```

```bash
agentcore deploy  # Apply changes
```

**Rule:** Use environment variables for non-secret configuration. Use Token Vault for secrets.

### Custom Container Best Practices

```dockerfile
# Must be linux/arm64
FROM --platform=linux/arm64 python:3.12-slim

# Install your dependencies
RUN pip install pandas numpy scikit-learn
RUN apt-get update && apt-get install -y git curl

# Add your source code
COPY ./src /workspace/src

# Do NOT set ENTRYPOINT/CMD — harness overrides them
```

```bash
agentcore create --name ml-agent --container ./Dockerfile
agentcore deploy
```

### Skills for Domain Knowledge

```bash
# Bake into container (recommended for production)
# Or install at session start:
agentcore invoke --exec --harness my-agent --session-id "$SID" \
  "npx @anthropic-ai/agent-skills add xlsx github"

# Point harness at skills
agentcore add harness --name my-agent --skill-path .agents/skills/xlsx
```

---

## Security

### Execution Role — Least Privilege

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
```

**Rule:** Only grant the permissions your agent actually needs. Start minimal, add as needed.

### IAM Dual-Permission Model

Every Harness API requires permissions on **both** the harness resource and the underlying Runtime resource:

| API | Required IAM Actions |
|-----|---------------------|
| `InvokeHarness` | `bedrock-agentcore:InvokeHarness` + `bedrock-agentcore:InvokeAgentRuntime` |
| `InvokeAgentRuntimeCommand` | `bedrock-agentcore:InvokeAgentRuntimeCommand` + `bedrock-agentcore:InvokeAgentRuntime` |
| `CreateHarness` | `bedrock-agentcore:CreateHarness` + `bedrock-agentcore:CreateAgentRuntime` |
| `UpdateHarness` | `bedrock-agentcore:UpdateHarness` + `bedrock-agentcore:UpdateAgentRuntime` |
| `DeleteHarness` | `bedrock-agentcore:DeleteHarness` + `bedrock-agentcore:DeleteAgentRuntime` |

**Rule:** When writing IAM policies for harness callers, always include both actions. Missing the Runtime action will result in AccessDenied.

### Inbound OAuth for Multi-Tenant

```bash
agentcore add harness --name my-agent \
  --authorizer-type CUSTOM_JWT \
  --discovery-url https://cognito-idp.us-west-2.amazonaws.com/<POOL_ID>/.well-known/openid-configuration \
  --allowed-clients <CLIENT_ID>
```

**Rule:** Use OAuth (not just SigV4) when you need per-user credential scoping for downstream tools.

### VPC for Private Resources

```bash
agentcore add harness --name internal-agent \
  --network-mode VPC \
  --subnets subnet-0abc1234 \
  --security-groups sg-0abc1234
```

**Important:** VPC mode requires NAT gateway for ECR Public access (`public.ecr.aws`).

### Gateway Policies (Cedar)

Use AgentCore Gateway + Cedar policies to control:
- Who can call which tool
- Under which conditions
- With which arguments

### Browser Tool Security Notes

When using Browser-tool production features (Section 7):

- **Profiles** must be scoped per-tenant — sharing across tenants creates a session leak risk
- **Recording** S3 buckets must enforce encryption (KMS) and deny unencrypted uploads via bucket policy
- **Web Bot Auth** signing keys belong in Secrets Manager with rotation; never embed in code or `harness.json`

See Section 7 for full configuration and IAM policies.

---

## Cost Control & Observability

### Set Hard Limits

```bash
# maxIterations: Default 75 — reasoning/action cycles per invocation
# timeout: Default 3600 (1 hour) — wall-clock timeout
# max-tokens: Default none — token budget per invocation
# idle-timeout: Default 900 (15 min) — idle microVM keep-alive
# max-lifetime: Default 28800 (8 hours) — max microVM session lifetime

agentcore add harness --name my-agent \
  --max-iterations 50 \
  --timeout 1800 \
  --max-tokens 8192 \
  --idle-timeout 600 \
  --max-lifetime 14400 \
  --truncation-strategy sliding_window
```

**Rule:** Always set `maxIterations` and `timeoutSeconds` in production. A runaway agent loop can be expensive.

### Cost Optimization Tips

| Tip | Impact |
|-----|--------|
| Use `--exec` for deterministic work | Zero token cost for shell commands |
| Set `maxIterations` conservatively | Prevents infinite loops |
| Use Haiku for simple tasks | 10x cheaper than Opus |
| Set `idleRuntimeSessionTimeout` low | Reduces warm microVM costs |
| Use `truncation-strategy: summarization` | Reduces context window size over long sessions |
| Use Browser **profiles** (Section 7.1) | Skip login token cost on every test |

### Observability (Zero Config)

```bash
# Stream logs
agentcore logs --harness my-agent

# Filter errors
agentcore logs --harness my-agent --since 1h --level error

# List traces
agentcore traces list --harness my-agent

# Get specific trace
agentcore traces get <trace-id> --harness my-agent
```

All traces automatically flow to CloudWatch. Enable Transaction Search (one-time per account) to query them.

### Tags for Cost Allocation

```json
{
  "tags": {
    "team": "platform",
    "environment": "production",
    "cost-center": "engineering"
  }
}
```

---

## Development Workflow

### Recommended Flow

```
1. agentcore create          → Scaffold project
2. Edit harness.json         → Configure model, tools, memory
3. agentcore dev             → Local dev server + inspector UI
4. Iterate on config         → No redeploy needed for overrides
5. agentcore deploy          → Push to AWS
6. agentcore invoke          → Test deployed agent
7. agentcore logs            → Monitor
8. agentcore run eval        → Evaluate quality
```

### Local Development

```bash
agentcore dev
# Opens browser inspector at localhost:8080
# Chat with agent, inspect traces, override settings live
```

### Testing Multiple Configurations

```bash
# Test different models without redeploying
agentcore invoke --harness my-agent --model-id us.anthropic.claude-sonnet-4-5-20250514-v1:0 "Test prompt"
agentcore invoke --harness my-agent --model-id gpt-4.1 --model-provider open_ai "Same test prompt"

# Test different system prompts
agentcore invoke --harness my-agent --system-prompt "Be concise." "Explain quantum computing"
agentcore invoke --harness my-agent --system-prompt "Be thorough." "Explain quantum computing"
```

---

## Production Readiness Checklist

- [ ] **Limits set:** `maxIterations`, `timeoutSeconds`, `maxTokens` configured
- [ ] **Tools restricted:** `allowedTools` explicitly defined (not `*`)
- [ ] **Secrets in Token Vault:** No hardcoded API keys anywhere
- [ ] **OAuth configured:** If multi-tenant, inbound JWT authorizer enabled
- [ ] **VPC configured:** If accessing private resources
- [ ] **Memory scoped:** `actorId` passed for multi-tenant isolation
- [ ] **Tags applied:** For cost allocation and access control
- [ ] **Truncation strategy set:** `sliding_window` or `summarization`
- [ ] **Observability verified:** CloudWatch Transaction Search enabled
- [ ] **Evaluators configured:** Online eval for continuous quality monitoring
- [ ] **Custom container tested:** If using custom environment, verified on `linux/arm64`
- [ ] **Error handling:** Client handles `runtimeClientError` events in stream
- [ ] **Session ID strategy:** Documented how session IDs are generated and reused
- [ ] **Browser profiles:** Per-tenant scoping if Browser tool is used (Section 7.1)
- [ ] **Browser recording:** S3 bucket + KMS configured if compliance-bound (Section 7.2)
- [ ] **Web Bot Auth:** Signing key in Secrets Manager with rotation policy if applicable (Section 7.3)

---

## SDK Reference

### Harness APIs (boto3)

```python
import boto3

# Control plane
control = boto3.client("bedrock-agentcore-control", region_name="us-west-2")
control.create_harness(harnessName="...", executionRoleArn="...")
control.get_harness(harnessId="...")
control.update_harness(harnessId="...", maxIterations=50)
control.delete_harness(harnessId="...")
control.list_harnesses()

# Data plane
data = boto3.client("bedrock-agentcore", region_name="us-west-2")
data.invoke_harness(harnessArn="...", runtimeSessionId="...", messages=[...])
data.invoke_agent_runtime_command(agentRuntimeArn="...", runtimeSessionId="...", body={"command": "..."})
```

### Supported SDKs

| SDK | Service Client | Status |
|-----|---------------|--------|
| **Python (boto3)** | `bedrock-agentcore` / `bedrock-agentcore-control` | GA |
| **Kotlin** | `BedrockAgentCoreClient` | GA |
| **JavaScript** | `@aws-sdk/client-bedrock-agentcore` | GA |
| **CLI** | `aws bedrock-agentcore-control` / `aws bedrock-agentcore` | GA |
| **AgentCore CLI** | `@aws/agentcore` (npm) | v0.14.0 |

---

## Pricing

- **No separate Harness charge** — you pay only for underlying AgentCore capabilities used
- Model invocations billed per token (Bedrock pricing)
- Code Interpreter, Browser, Memory billed per usage
- MicroVM compute included in AgentCore Runtime pricing
- Browser session recording: S3 storage cost only (Browser-side overhead included in Browser pricing)
- Browser profiles: storage included in Browser pricing at the time of writing

---

*Last updated: 2026-05-30*
