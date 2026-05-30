# Production Hardening Plan

> **Status:** Design only — deployment is a separate work stream
> **Version:** 0.2.0
> **Last Updated:** 2026-05-30
> **Owner:** Project maintainer
> **Audience:** Anyone deploying this UI Test Agent to a production-bound environment

---

## What this doc is

A **project-specific playbook** for the six Priority 4 hardening items from `PROJECT_STATE.md`. For each item:

- Why *this project* needs it
- The exact design we'll deploy (IAM, Dockerfile, naming conventions, code patches)
- Validation criterion ("done" definition)
- Cost impact
- Cross-link to the underlying mechanism if covered elsewhere

## What this doc isn't

- **Not a generic AWS guide.** For mechanics like "how do Browser profiles work in AWS", see [`BEST_PRACTICES.md` §7](BEST_PRACTICES.md#browser-tool--production-features). This doc only covers the *project-specific* slice.
- **Not a deployment script.** Each item below ends with "*Status: not deployed*". Real deployment is a separate work stream (one or more follow-up issues + PRs).
- **Not a complete production checklist.** It only covers the six items already flagged in `PROJECT_STATE.md`. Things like multi-region failover or cross-account isolation are explicitly out of scope.

## Sequencing recommendation

| Order | Item | Why this order |
|---|---|---|
| **1** | Container deployment | Unblocks everything else. Until this lands, the Browser tool can only run from a developer laptop. |
| **2** | CloudWatch alarms | Lowest-risk, highest-value. No infra changes needed beyond the alarm definitions. Provides safety net before we add more moving parts. |
| **3** | Browser session recording | Once Container mode is live, recording becomes useful for diagnosing the issues we couldn't see before. |
| **4** | Browser profiles | Most useful when running CI/CD frequently — depends on Container mode being stable first. |
| **5** | Online eval | Builds on `eval_runner.py` (already exists) plus EventBridge — no infra dependencies on the others. |
| **6** | Web Bot Auth | Lowest priority. Defer until target sites we test against actually adopt the standard. |

Items 1–2 are **prerequisites for confident production use**. Items 3–6 are **incremental quality-of-life upgrades** that can be added in any order once 1–2 are in place.

---

## 1. Container Deployment Mode

### Problem

`PROJECT_STATE.md` "Key Finding" documents:

> Browser tool **fails in Runtime CodeZip mode** (Playwright binary permission error)

The Browser tool's strands integration tries to invoke a local Playwright binary as a fallback, which doesn't have execute permissions in the CodeZip runtime layer. This means the agent works locally (where the laptop has Playwright installed) but fails when deployed.

The two viable fixes are:
- **(a)** Resolve the strands_tools "remote-only" path so it never tries to invoke a local binary
- **(b)** Switch to **Container deployment mode**, where we control the image and can install Playwright correctly

We choose **(b)** because it gives more control going forward (custom dependencies, security baseline, base-image hardening) and unblocks future agent-side instrumentation.

### Solution design

Replace the CodeZip deployment with a custom container based on `linux/arm64` (required by AgentCore Runtime per [BEST_PRACTICES.md § Custom Container](BEST_PRACTICES.md#custom-container-best-practices)).

#### Dockerfile

```dockerfile
# app/ui-test-agent/Dockerfile
# Required by AgentCore Runtime
FROM --platform=linux/arm64 python:3.12-slim

# System dependencies needed by Playwright + AgentCore SDK
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifest first (layer cache)
WORKDIR /workspace
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    bedrock-agentcore \
    strands-agents \
    strands-agents-tools \
    boto3

# Note: We do NOT install Playwright binaries — the strands AgentCoreBrowser
# tool routes all browser actions to the remote AgentCore Browser service.
# Installing Playwright locally was the bug; not installing it is the fix.

# Copy agent source
COPY main.py memory/ model/ mcp_client/ skills/ ./

# Do NOT set ENTRYPOINT/CMD — AgentCore Runtime overrides them.
# The runtime invokes the entry point declared in agentcore.json.
```

The key insight: **don't install Playwright locally.** The strands `AgentCoreBrowser` tool calls the remote Browser service via boto3; the local binary is only used as a fallback path that we want to avoid entirely.

#### Build and deploy

```bash
# Build for arm64 even on x86 dev machines
docker buildx build --platform linux/arm64 \
  -t ui-test-agent:0.2.1 \
  -f app/ui-test-agent/Dockerfile \
  app/ui-test-agent/

# Tag for ECR
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="$ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/ui-test-agent"
docker tag ui-test-agent:0.2.1 "$ECR_REPO:0.2.1"

# Push
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com"
aws ecr create-repository --repository-name ui-test-agent --region us-east-1 || true
docker push "$ECR_REPO:0.2.1"

# Update agentcore.json to point at the image, then redeploy
agentcore deploy
```

#### IAM impact

The execution role needs `ecr:GetDownloadUrlForLayer`, `ecr:BatchGetImage`, `ecr:BatchCheckLayerAvailability` for the ECR repo. Add to `AgentCore-uitestagent-def-...` role:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:BatchCheckLayerAvailability"
    ],
    "Resource": "arn:aws:ecr:us-east-1:<ACCOUNT_ID>:repository/ui-test-agent"
  }, {
    "Effect": "Allow",
    "Action": "ecr:GetAuthorizationToken",
    "Resource": "*"
  }]
}
```

If the Runtime is configured for VPC mode, NAT gateway is required for ECR Public access — same caveat noted in [BEST_PRACTICES.md § Security](BEST_PRACTICES.md#security).

### Validation

- [ ] Container image successfully pushed to `<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/ui-test-agent:0.2.1`
- [ ] `agentcore deploy` succeeds with the container reference
- [ ] **Smoke test:** `agentcore invoke --session-id "$(uuidgen)" "Open https://the-internet.herokuapp.com/login and report the page title"` returns the expected title without a Playwright permission error
- [ ] Re-run of golden tests via `python eval_runner.py --harness-arn $RUNTIME_ARN` shows ≥ 5/6 pass (matching local results)
- [ ] CloudWatch logs show no `chrome` / `playwright` permission errors

### Cost impact

| Component | One-time | Recurring |
|---|---|---|
| ECR storage (~200 MB image) | $0 | ~$0.02/month |
| Build pipeline (manual `docker buildx`) | $0 | $0 |
| **No additional Bedrock / AgentCore charges** — the Runtime pricing is unchanged regardless of CodeZip vs Container | | |

Container mode adds a few seconds of cold-start latency (image pull) on the first session of an idle period, but warm sessions are unaffected.

**Status:** not deployed.

---

## 2. CloudWatch Alarms

### Problem

The agent has no operational backstop. If a session goes into an infinite loop, hits a CAPTCHA wall and retries forever, or accidentally navigates to production, we have no automated detection. The `Anomaly Detection` table in `ARCHITECTURE.md` §7 (Guardrails) lists what we *should* detect but doesn't define the alarms.

### Solution design

Four CloudWatch metric alarms, each with a clear action.

#### Alarm 1: Token usage spike (runaway loop detector)

| Field | Value |
|---|---|
| Metric namespace | `AWS/Bedrock` |
| Metric name | `InputTokens` (or `InvocationCount` if more reliable) |
| Dimensions | `ModelId = us.anthropic.claude-sonnet-4-5-20250514-v1:0` |
| Statistic | `Sum` |
| Period | 60 seconds |
| Threshold | `> 50000 tokens / minute` (rough proxy for "agent stuck consuming context") |
| Action | SNS topic → on-call email + auto-disable the Runtime endpoint |

#### Alarm 2: Session duration approaching timeout

| Field | Value |
|---|---|
| Metric namespace | `AWS/BedrockAgentCore` |
| Metric name | `RuntimeSessionDurationSeconds` |
| Dimensions | `RuntimeArn = <UI_TEST_AGENT_ARN>` |
| Statistic | `Maximum` |
| Period | 60 seconds |
| Threshold | `> 1440` (80% of 1800s timeout configured in `harness.json`) |
| Action | SNS notification (informational; no auto-action) |

This is a **leading indicator** — it gives the orchestrator a chance to gracefully terminate the session before the hard timeout.

#### Alarm 3: Repeated identical browser actions (stuck-state detector)

| Field | Value |
|---|---|
| Metric source | Custom — emit from `main.py` when same browser action runs N times in a row |
| Metric name | `StuckStateDetected` |
| Statistic | `Sum` |
| Period | 300 seconds |
| Threshold | `≥ 1` (any single occurrence) |
| Action | SNS notification + capture session state to S3 for analysis |

This requires a small `main.py` instrumentation patch: track the last action signature in session memory, increment a counter on repeat, emit a CloudWatch metric via `boto3.client("cloudwatch").put_metric_data` when count > 5.

#### Alarm 4: Navigation to unexpected domain (security tripwire)

| Field | Value |
|---|---|
| Metric source | Custom — emit from `main.py` whenever `browser.navigate` URL host doesn't match the allowlist |
| Metric name | `UnexpectedDomainNavigation` |
| Statistic | `Sum` |
| Period | 60 seconds |
| Threshold | `≥ 1` |
| Action | SNS critical alert + immediately stop the runtime session |

The agent's system prompt already says "Never navigate outside the target domain" — this alarm catches the case where the prompt is bypassed (prompt injection, model error). The orchestrator-side allowlist (`ARCHITECTURE.md` §7 → `validate_target_url`) is the first line of defence; this alarm is the second.

#### Terraform / CDK / boto3 — pick one

The repo's `agentcore/cdk/` directory already contains CDK infra. Adding the alarms is a CDK addition:

```typescript
// agentcore/cdk/lib/alarms-stack.ts (new file)
import * as cdk from 'aws-cdk-lib';
import * as cw from 'aws-cdk-lib/aws-cloudwatch';
import * as sns from 'aws-cdk-lib/aws-sns';

export class UITestAgentAlarmsStack extends cdk.Stack {
  constructor(scope: cdk.App, id: string) {
    super(scope, id);

    const onCallTopic = new sns.Topic(this, 'OnCall', {
      topicName: 'ui-test-agent-oncall',
    });

    new cw.Alarm(this, 'TokenSpike', {
      metric: new cw.Metric({
        namespace: 'AWS/Bedrock',
        metricName: 'InputTokens',
        dimensionsMap: {
          ModelId: 'us.anthropic.claude-sonnet-4-5-20250514-v1:0',
        },
        statistic: 'Sum',
        period: cdk.Duration.seconds(60),
      }),
      threshold: 50000,
      evaluationPeriods: 1,
      treatMissingData: cw.TreatMissingData.NOT_BREACHING,
      alarmDescription: 'UI Test Agent token consumption spiked — possible runaway loop',
    }).addAlarmAction(new cw.SnsAction(onCallTopic));

    // ... 3 more alarms
  }
}
```

### IAM impact

Add to the agent's execution role:

```json
{
  "Effect": "Allow",
  "Action": "cloudwatch:PutMetricData",
  "Resource": "*",
  "Condition": {
    "StringEquals": {"cloudwatch:namespace": "UITestAgent"}
  }
}
```

This lets `main.py` emit the custom `StuckStateDetected` and `UnexpectedDomainNavigation` metrics, scoped to the project's namespace.

### Validation

- [ ] All 4 alarms exist in CloudWatch console under stack `UITestAgentAlarmsStack`
- [ ] SNS topic `ui-test-agent-oncall` exists and has a subscriber
- [ ] **Synthetic test for Alarm 1:** invoke a deliberately verbose prompt; confirm alarm fires
- [ ] **Synthetic test for Alarm 4:** patch `main.py` system prompt to allow `example.com`, then submit a prompt asking it to navigate there; confirm alarm fires and session is stopped
- [ ] Alarm history shows OK → ALARM → OK transitions during the synthetic tests
- [ ] On-call subscriber received notifications

### Cost impact

| Component | Monthly cost |
|---|---|
| 4 CloudWatch alarms | $0.40 (~$0.10 each) |
| Custom metrics (2 namespaces) | ~$0.30 (low publish rate) |
| SNS notifications | < $0.01 (for typical low alarm volume) |
| **Total** | **~$0.71 / month** |

**Status:** not deployed.

---

## 3. Browser Session Recording (S3)

### Generic mechanics

See [BEST_PRACTICES.md §7.2](BEST_PRACTICES.md#72-session-recording--capture-every-action-for-compliance-and-debugging) for the AWS API, IAM template, S3 bucket policy, and KMS pattern. This section only covers project-specific decisions.

### Project-specific design

#### Bucket naming

```
agentcore-ui-test-agent-recordings-<ACCOUNT_ID>-us-east-1
```

Following AWS best practice (account ID in name to avoid global-namespace collisions, region suffix for cross-region clarity).

#### Prefix structure

```
<bucket>/
├── runs/
│   ├── 2026-05-30/
│   │   ├── session-{uuid}.recording
│   │   └── session-{uuid}.metadata.json
│   ├── 2026-05-31/
│   │   └── ...
└── archived/  # used only after Lifecycle transitions
```

`runs/{date}/` makes lifecycle rules straightforward and makes it trivial to query "show me all sessions from a given day" via `aws s3 ls`.

#### When to enable

Per `BEST_PRACTICES.md` guidance, recording is **opt-in per session** rather than always-on, because:

- Local dev iteration doesn't benefit and the overhead is wasted
- Most CI/CD runs against well-known test sites don't need replay
- Compliance-bound runs (SOC2 audit, customer-data scenarios) are the right use case

The orchestrator (`invoke.py` / `e2e_pipeline.py`) decides whether to pass `recordingConfiguration` based on a `RECORD_SESSION` env var or an explicit flag.

#### Lifecycle

```json
{
  "Rules": [{
    "Id": "ExpireUITestRecordings",
    "Status": "Enabled",
    "Prefix": "runs/",
    "Transitions": [{"Days": 30, "StorageClass": "GLACIER"}],
    "Expiration": {"Days": 90}
  }]
}
```

90-day retention covers SOC2 audit windows. Adjust to longer if regulated industries require it (HIPAA: 6 years; in that case override per-bucket via tags).

### Code wire-up in `main.py`

```python
# main.py — minimal patch for opt-in recording
import os
RECORDING_BUCKET = os.environ.get("RECORDING_BUCKET", "")
ENABLE_RECORDING = os.environ.get("ENABLE_RECORDING", "false") == "true"

# When starting a browser session inside the agent's tool wiring, pass
# recordingConfiguration if enabled. The exact integration point depends
# on whether we wrap AgentCoreBrowser ourselves or rely on the strands
# default — the strands tool currently does NOT expose recordingConfiguration,
# so we'll need to either contribute upstream or maintain a small fork.
```

**Caveat:** as of this writing, the strands `AgentCoreBrowser` tool doesn't expose `recordingConfiguration` as a parameter. Two options:

1. **Wrap it ourselves.** Replace the strands tool with a thin wrapper that calls `boto3.start_browser_session(...recordingConfiguration=...)` and passes the resulting handle to a custom Browser-control tool. More flexible but more code to maintain.
2. **Contribute upstream.** PR `recordingConfiguration` support to `strands-tools`. Cleaner long-term but bottlenecked on upstream review.

Recommended: start with **(2)** as a parallel effort; ship Container mode first; revisit (1) only if (2) stalls.

### Validation

- [ ] Bucket `agentcore-ui-test-agent-recordings-<ACCOUNT_ID>-us-east-1` exists with KMS encryption + `DenyUnencryptedUploads` policy
- [ ] Lifecycle rule visible in S3 console
- [ ] Smoke test session with `ENABLE_RECORDING=true` produces files under `runs/<today>/`
- [ ] Recording is replayable in AgentCore console
- [ ] Without `ENABLE_RECORDING=true`, no files written (verify opt-in works)
- [ ] CloudTrail confirms `kms:Encrypt` is being called for each upload

### Cost impact

| Component | Monthly cost |
|---|---|
| S3 storage (assume 100 sessions × 10 MB × 30 days) | ~$0.07 standard, ~$0.01 Glacier |
| KMS key (CMK) | $1.00 (flat, regardless of usage) |
| KMS encrypt requests | < $0.01 |
| **Total** | **~$1.10 / month** for typical CI volume |

**Status:** not deployed.

---

## 4. Browser Profiles

### Generic mechanics

See [BEST_PRACTICES.md §7.1](BEST_PRACTICES.md#71-browser-profiles--persist-authenticated-state-across-sessions) for control-plane / data-plane API and security pattern.

### Project-specific design

#### Naming convention

```
ui-test-agent-{environment}-{persona}
```

Examples:
- `ui-test-agent-staging-qa-user`
- `ui-test-agent-staging-admin-user`
- `ui-test-agent-prod-readonly-monitor`

Note: **never** create profiles for production-write personas. The agent has a system-prompt rule against modifying state in production; profiles for write-permitted personas would create a one-bug-from-disaster situation.

#### Tenant scoping

The current project doesn't have multi-tenancy yet. **Decision:** start with single-tenant profiles ("one profile per environment-persona combination"). When multi-tenancy lands, evolve to `ui-test-agent-{tenantId}-{environment}-{persona}` and migrate.

Recording the decision now prevents the anti-pattern called out in BEST_PRACTICES (sharing a profile across tenants).

#### Population workflow

```bash
# One-time, manual: populate a profile by running a session that logs in
SESSION_ID="$(uuidgen)"
agentcore invoke --runtime-arn $UI_TEST_AGENT_ARN --session-id "$SESSION_ID" \
  --extra-payload '{"profileIdentifier": "ui-test-agent-staging-qa-user"}' \
  "Navigate to https://staging.example.com/login. Type 'qa@example.com' and password '$QA_PASSWORD'. Click Login. Verify you're redirected to /dashboard. Stop."

# Profile state is persisted; subsequent sessions referencing the same
# profile will skip the login step.
```

### Code wire-up

Same caveat as Recording: the strands `AgentCoreBrowser` tool doesn't currently expose `profileConfiguration` either. Same two paths (wrap or upstream PR), and they should be tackled together since they're sibling features in the AWS API.

### Validation

- [ ] At least one profile (e.g. `ui-test-agent-staging-qa-user`) exists in the AgentCore control plane
- [ ] Profile is populated via the manual workflow above
- [ ] Subsequent test session referencing the profile lands on `/dashboard` directly (no login flow in agent trace)
- [ ] Token cost for that test is measurably lower than a no-profile equivalent (target: 30%+ reduction on auth-heavy tests)

### Cost impact

Storage included in Browser pricing — no separate fee at the time of writing.

**Token savings:** for an auth-heavy test (5 minutes total, 2 minutes spent in login flow), profile use saves ~40% of the per-test token cost. On a CI run of 10 such tests/day, savings ~$1.30/day = **~$40/month saved**.

**Status:** not deployed.

---

## 5. Online Eval (Continuous Quality Monitoring)

### Problem

The existing `eval_runner.py` (covered in [ARCHITECTURE.md §10.2](ARCHITECTURE.md#agent-testing-strategy)) only runs when someone manually invokes it. After a model upgrade, system-prompt change, or skill update, regressions can go unnoticed for days.

### Solution design

Schedule `eval_runner.py` via EventBridge on a **daily** cadence, post results to a CloudWatch dashboard, and alarm on regression.

#### EventBridge schedule

```yaml
# agentcore/cdk/lib/eval-schedule-stack.ts (new)
{
  "ScheduleExpression": "cron(0 6 * * ? *)",  # 06:00 UTC daily
  "Target": {
    "Arn": "<eval-runner-lambda-arn>",
    "Input": {
      "harness_arn": "<UI_TEST_AGENT_ARN>",
      "region": "us-east-1"
    }
  }
}
```

The target is a small Lambda that wraps `eval_runner.py`. The Lambda:
1. Invokes `run_golden_tests(...)` from the existing module
2. Writes the JSON result to `s3://<recordings-bucket>/eval-runs/<date>.json`
3. Emits a CloudWatch metric `UITestAgent/EvalPassRate` with the value
4. Returns the result for CloudWatch Logs Insights later

#### CloudWatch alarm on regression

```typescript
new cw.Alarm(this, 'EvalPassRateRegression', {
  metric: new cw.Metric({
    namespace: 'UITestAgent',
    metricName: 'EvalPassRate',
    statistic: 'Average',
    period: cdk.Duration.hours(24),
  }),
  threshold: 0.83,  // 5/6 pass — drop from 6/6 baseline triggers alarm
  comparisonOperator: cw.ComparisonOperator.LESS_THAN_THRESHOLD,
  evaluationPeriods: 2,  // Two consecutive days of regression
  alarmDescription: 'Daily golden-test pass rate dropped below 5/6 — investigate agent change',
});
```

Two consecutive failed days avoids alerting on transient AWS issues.

#### CloudWatch dashboard

Single dashboard `UITestAgent-Eval` showing:
- Pass rate over time (line graph)
- Per-test status (heatmap of GT-01 … GT-06 over last 30 days)
- Token cost per eval run (line graph; helps catch model bloat)

### Validation

- [ ] EventBridge schedule visible at 06:00 UTC daily
- [ ] Lambda function `eval-runner-fn` deployed and idempotent
- [ ] First scheduled run produces a file in `s3://<bucket>/eval-runs/<date>.json`
- [ ] CloudWatch metric `UITestAgent/EvalPassRate` has data points
- [ ] Dashboard renders all three graphs
- [ ] Synthetic regression: temporarily make GT-01 fail (e.g. break the system prompt), wait 2 days, confirm alarm fires

### Cost impact

| Component | Monthly cost |
|---|---|
| Lambda (~30 invocations × ~5 min) | ~$0.30 |
| Daily eval runs (6 tests × ~$0.32 avg) × 30 days | ~$57 |
| CloudWatch dashboard + metrics | ~$3 |
| **Total** | **~$60 / month** |

This is the most expensive item on the list. Consider reducing cadence to weekly (~$15/month) if 5–7 day regression detection is acceptable for the business.

**Status:** not deployed.

---

## 6. Web Bot Auth

### Generic mechanics

See [BEST_PRACTICES.md §7.3](BEST_PRACTICES.md#73-web-bot-auth--cryptographic-identity-to-reduce-captcha-friction).

### Project-specific assessment

The current test target inventory is:

- `the-internet.herokuapp.com` (golden tests) — does **not** participate in Web Bot Auth (it's a public test sandbox; bot signals don't change behaviour)
- `app/demo-frontend/` on GitHub Pages — does **not** participate; we control it but adding Web Bot Auth verification logic is out of scope
- Hypothetical future production / staging targets — depends on the customer

### Decision

**Defer until a target adopts the standard.** Web Bot Auth requires:

- A public key registered with each target site's directory (out-of-band per site)
- A maintained signing key in Secrets Manager
- Key rotation tracking per target

For zero current benefit, the carrying cost (key management, rotation policy, IAM scoping) is not justified.

### When to revisit

Re-evaluate when **any** of:

- A target site we run real CI against publishes a Web Bot Auth directory
- An internal monitoring use case emerges where bot mitigation is biting our own synthetic checks
- The standard moves to RFC and adoption hits ~5% of the public web

Until then, the design is captured in `BEST_PRACTICES.md §7.3` as ready-to-deploy guidance — when the trigger condition fires, we follow that pattern with these project-specific additions:

- Secret name: `ui-test-agent/webbotauth/<target-domain>`
- Key ID format: `ui-test-agent-<year>-q<quarter>` (rotation hint baked into name)
- One key per target domain (don't share across sites; each domain manages its own trust list)

### Validation (when deployed)

- [ ] Key generated and stored at `arn:aws:secretsmanager:us-east-1:<ACCOUNT_ID>:secret:ui-test-agent/webbotauth/<target-domain>`
- [ ] Public key registered at `https://<target>/.well-known/http-message-signatures-directory` (or via target's process)
- [ ] Test session against target shows reduced CAPTCHA frequency vs. control runs
- [ ] Key rotation runbook in this section of the doc

### Cost impact

| Component | Monthly cost |
|---|---|
| Secrets Manager (1 secret, signing key) | $0.40 |
| KMS for the secret (uses default AWS-managed) | $0 |
| **Total** | **~$0.40 / month** per target |

**Status:** not deployed (deferred).

---

## Cost summary

If all six items are deployed for a typical CI usage profile (10 test runs / day, 1 target):

| Item | Monthly cost | Monthly *savings* |
|---|---|---|
| 1. Container deployment | ~$0.02 | $0 |
| 2. CloudWatch alarms | ~$0.71 | (prevention only — no direct $) |
| 3. Session recording | ~$1.10 | (debug time savings — not quantified) |
| 4. Browser profiles | $0 | ~$40 (auth token reduction on CI) |
| 5. Online eval | ~$60 | (catches regressions early — large but unquantified) |
| 6. Web Bot Auth | ~$0.40 | (deferred — $0 today) |
| **Net** | **~$22 / month** (savings exceed costs) | |

The *net* monthly impact is **savings**, primarily because Browser profiles dominate. If skipping eval (item 5) the net is **~$38 / month savings**.

---

## Master validation checklist

After all six items are deployed, all of the following should be true:

### Item 1 — Container deployment
- [ ] ECR image present at `<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/ui-test-agent:0.2.1`
- [ ] `agentcore deploy` succeeds with container reference
- [ ] Smoke test passes without Playwright permission error
- [ ] eval_runner.py shows ≥ 5/6 pass on the deployed Runtime

### Item 2 — CloudWatch alarms
- [ ] 4 alarms exist (Token Spike, Session Duration, Stuck State, Unexpected Domain)
- [ ] SNS topic has at least one subscriber
- [ ] Synthetic tests confirmed alarm firing for Token Spike and Unexpected Domain

### Item 3 — Session recording
- [ ] Bucket exists with KMS + lifecycle rules
- [ ] Opt-in via `ENABLE_RECORDING=true` works
- [ ] Recording is replayable in AgentCore console

### Item 4 — Browser profiles
- [ ] At least one profile exists and is populated
- [ ] Subsequent session reuses login state
- [ ] Measurable token reduction confirmed

### Item 5 — Online eval
- [ ] EventBridge schedule active
- [ ] Lambda + Dashboard deployed
- [ ] Regression alarm verified via synthetic test

### Item 6 — Web Bot Auth
- [ ] *Deferred — no target site requires it. Re-evaluate quarterly.*

---

## How this fits the wider docs

| Concern | Where covered |
|---|---|
| Why these features exist (AWS-side mechanics) | [BEST_PRACTICES.md §7](BEST_PRACTICES.md#browser-tool--production-features) |
| How they fit the system architecture | [ARCHITECTURE.md §6 Code Interpreter](ARCHITECTURE.md#code-interpreter-integration), [§13 A2A](ARCHITECTURE.md#a2a-protocol--agent-to-agent-communication) |
| What's currently deployed for this project | [PROJECT_STATE.md](../PROJECT_STATE.md) "Deployed Resources" |
| **What we'll deploy next and how** | This document |
| Workflow for getting it deployed | [DEVELOPMENT_WORKFLOW.md](DEVELOPMENT_WORKFLOW.md) |

---

## Follow-up work (not in this PR)

Each item below should be a separate issue + PR when actually deployed:

1. `feat(deploy): switch UI Test Agent to Container mode` — implements §1
2. `feat(ops): add CloudWatch alarms for UI Test Agent` — implements §2
3. `feat(observability): enable Browser session recording with S3 bucket` — implements §3
4. `feat(perf): add Browser profiles for staging QA personas` — implements §4
5. `feat(quality): schedule daily golden-test eval runs` — implements §5
6. `feat(security): adopt Web Bot Auth for <target>` — implements §6 (when triggered)

Each of those issues should reference back to its corresponding section of this doc.
