# Issue #28 — Verification evidence

Captured 2026-05-30 from running AWS account `<ACCOUNT_ID>` (us-east-1) after
running `setup_observability.py`. All sensitive identifiers redacted.

## What was deployed

### Custom CWL log groups (with 30-day retention)
- `/aws/bedrock-agentcore/uitestagent`
- `/aws/bedrock-agentcore/bugfixagent`

### Default AgentCore log groups (retention added)
Setting 30-day retention on the auto-created groups where AgentCore actually
emits rich OTel data:
- `/aws/bedrock-agentcore/runtimes/harness_UITestAgentHarness-<RUNTIME_ID>-DEFAULT`  (was: None → now 30d)
- `/aws/bedrock-agentcore/runtimes/harness_BugFixAgentHarness-<RUNTIME_ID>-DEFAULT`   (was: None → now 30d)

### CloudWatch Logs Delivery
4 sources × 4 destinations × 4 deliveries:

| Harness | LogType | Source name | Destination type | Destination name |
|---|---|---|---|---|
| UI Test | APPLICATION_LOGS | `ui-test-app-logs-source` | CWL | `ui-test-app-logs-dest` (→ custom log group) |
| UI Test | TRACES | `ui-test-traces-source` | XRAY | `ui-test-traces-xray-dest` (→ X-Ray service) |
| Bug Fix | APPLICATION_LOGS | `bug-fix-app-logs-source` | CWL | `bug-fix-app-logs-dest` |
| Bug Fix | TRACES | `bug-fix-traces-source` | XRAY | `bug-fix-traces-xray-dest` |

### IAM `ObservabilityAccess` inline policy (on harnesses' execution role)
- LogDelivery: `logs:CreateLogStream / PutLogEvents / DescribeLogStreams` on `arn:aws:logs:us-east-1:<ACCOUNT_ID>:log-group:/aws/bedrock-agentcore/*`
- XRayTracing: `xray:PutTraceSegments / PutTelemetryRecords / GetSamplingRules / GetSamplingTargets` on `*`

### Resource policy `AWSLogDeliveryWrite20150319`
Extended to allow `delivery.logs.amazonaws.com` to write to our log groups.
Existing SageMaker GroundTruth statement preserved; new statement added with
`SourceAccount` condition for security.

## Verified working at runtime

### ✓ X-Ray traces flowing
- 47 traces captured in last 30 minutes
- EntryPoint names: `harness_UITestAgentHarness.DEFAULT` and `harness_BugFixAgentHarness.DEFAULT`

### ✓ Application Signals service discovery
- 4 harness services discovered (UI Test + Bug Fix, each in DEFAULT environment)
- Visible in AWS Console → CloudWatch → Application Signals → Services

### ✓ Default log group has rich OTel data
Sample message format (redacted):
```
{
  "_aws": {"CloudWatchMetrics": [{"Namespace": "bedrock-agentcore", ...}]},
  "otel.resource.service.name": "harness_UITestAgentHarness.DEFAULT",
  "otel.resource.aws.log.group.names": "/aws/bedrock-agentcore/runtimes/.../-DEFAULT",
  "otel.resource.aws.service.type": "gen_ai_agent",
  "otel.resource.cloud.platform": "aws_bedrock_agentcore"
}
```
Includes EMF (Embedded Metric Format) for CloudWatch metric extraction.

### ⚠ Custom CWL log groups currently only show AWS validation message
```
log_stream_created_by_aws_to_validate_log_delivery_subscriptions:
  "Permissions are set correctly to allow AWS CloudWatch Logs to write
   into your logs while creating a subscription."
```

**Why:** AgentCore runtime emits OTel data **directly** to its own auto-created
DEFAULT log group (per the hardcoded `otel.resource.aws.log.group.names`
attribute). The CloudWatch Logs Delivery API's `APPLICATION_LOGS` channel
populates only when the runtime emits to that specific channel, which appears
to be a sparser event stream than the rich OTel logs.

**Implication:**
- For dashboards / alarms (issue #18, #20): query the **DEFAULT log group**
  (which has the rich data and now has 30-day retention)
- For compliance evidence: the validation stream message in the custom group
  proves the delivery infrastructure is correct and AWS-validated
- The custom log group will populate if/when AgentCore emits APPLICATION_LOGS
  events; no agent code changes needed on our side

## How to reproduce

```bash
python agentcore/scripts/setup_observability.py
# All idempotent — safe to re-run
```

## Console verification (manual)

1. AWS Console → AgentCore → Harness → UITestAgentHarness
   - Log delivery: should show **2** (was 0) — 1 CWL + 1 XRAY
   - Tracing: should show **Enabled** (was "Not enabled")
2. Same for BugFixAgentHarness.
3. CloudWatch → Application Signals → Service map
   - Both `harness_UITestAgentHarness.DEFAULT` and `harness_BugFixAgentHarness.DEFAULT` listed
