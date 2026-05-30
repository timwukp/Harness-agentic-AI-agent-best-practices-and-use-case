# Issue #28 — Verification evidence

All output below collected from running AWS account `<ACCOUNT_ID>` (us-east-1) on 2026-05-30, after running `setup_observability.py`. All sensitive identifiers redacted.

## 1. Log groups (`aws logs describe-log-groups`)

```
/aws/bedrock-agentcore/uitestagent  retention: 30 days
/aws/bedrock-agentcore/bugfixagent  retention: 30 days
```

## 2. Delivery sources (`aws logs describe-delivery-sources`)

```
bug-fix-app-logs-source   APPLICATION_LOGS
bug-fix-traces-source     TRACES
ui-test-app-logs-source   APPLICATION_LOGS
ui-test-traces-source     TRACES
```

## 3. Delivery destinations (`aws logs describe-delivery-destinations`)

```
bug-fix-app-logs-dest      CWL    (→ CloudWatch log group)
bug-fix-traces-xray-dest   XRAY   (→ X-Ray service)
ui-test-app-logs-dest      CWL    (→ CloudWatch log group)
ui-test-traces-xray-dest   XRAY   (→ X-Ray service)
```

## 4. Deliveries (links source → destination)

```
bug-fix-app-logs-source   →  CWL  (bug-fix-app-logs-dest)
bug-fix-traces-source     →  XRAY (bug-fix-traces-xray-dest)
ui-test-app-logs-source   →  CWL  (ui-test-app-logs-dest)
ui-test-traces-source     →  XRAY (ui-test-traces-xray-dest)
```

## 5. IAM `ObservabilityAccess` inline policy

```
Sid: LogDelivery    logs:CreateLogStream / PutLogEvents / DescribeLogStreams
                    Resource: arn:aws:logs:us-east-1:<ACCOUNT_ID>:log-group:/aws/bedrock-agentcore/*
Sid: XRayTracing    xray:PutTraceSegments / PutTelemetryRecords / GetSamplingRules / GetSamplingTargets
                    Resource: *
```

## 6. Pre-existing default log groups confirmed live

```
/aws/bedrock-agentcore/runtimes/harness_UITestAgentHarness-<RUNTIME_ID>-DEFAULT
  Last event: 2026-05-30 23:44 (~7 min before this PR)
  Sample message: "Waiting for application startup. ... Uvicorn running on http://0.0.0.0:8080"
```

This pre-existing default log group already shows the runtime is logging actively. Our new delivery configuration tees future events to our custom log groups + X-Ray.

## 7. Console verification (manual — user to confirm post-merge)

In AWS Console → AgentCore → Harness → each harness:

- **Log delivery section:** should show **2** destinations (was 0):
  - 1× CWL → `/aws/bedrock-agentcore/{name}`
  - 1× XRAY → AWS X-Ray service
- **Tracing section:** should show **Enabled** (was "Not enabled")

## 8. End-to-end verification (manual — user to perform)

After merging, in the AWS console click "Test harness" on UITestAgentHarness with a simple prompt like "What is 2+2?". Then within 5 minutes:

- `aws logs tail /aws/bedrock-agentcore/uitestagent --since 5m` should stream events
- AWS Console → CloudWatch → Application Signals → Service map should show `harness_UITestAgentHarness`

(I cannot perform this step programmatically because the public boto3 SDK does not yet expose the `InvokeHarness` API; harness invocation is currently console-only or via AWS internal SDK. This was confirmed during implementation.)

## Notes

- **Idempotent:** running the script a second time prints "exists" for everything that's already there, no errors.
- **No code committed depends on the actual deployed resource IDs** — the script discovers harnesses by name (`harness_UITestAgentHarness`, `harness_BugFixAgentHarness`) at runtime.
