#!/usr/bin/env python3
"""
Set up observability for AgentCore harnesses (issue #28).

Idempotent — running multiple times is safe.

What it does:

  A. Custom CWL log groups (compliance-bounded with retention):
       /aws/bedrock-agentcore/uitestagent
       /aws/bedrock-agentcore/bugfixagent
     Plus CloudWatch Logs Delivery for APPLICATION_LOGS → these groups.

  B. AgentCore runtime DEFAULT log groups (where rich OTel data actually flows):
       /aws/bedrock-agentcore/runtimes/<harness-name>-<ID>-DEFAULT
     Sets 30-day retention (default is None = never expire).
     This is where AgentCore writes structured OTel logs with trace_id/span_id/etc.

  C. X-Ray TRACES delivery (fills the "Tracing: Enabled" console field):
       APPLICATION_LOGS source → CWL destination
       TRACES source → XRAY destination

  D. ObservabilityAccess inline IAM policy on the harnesses' execution role:
       logs:Create/Put/Describe (scoped to /aws/bedrock-agentcore/*)
       xray:Put/Get for trace export

  E. Resource policy AWSLogDeliveryWrite20150319 extended to include
     /aws/bedrock-agentcore/* log groups (see "Why" below).

Why two destinations:
  - DEFAULT log group is auto-created by AgentCore and is where rich OTel
    structured logs land (per the runtime's hardcoded
    otel.resource.aws.log.group.names attribute). This is where alarms
    and queries should target for now.
  - Custom log group has compliance-bounded retention and shows up in the
    AgentCore console "Log delivery" section. APPLICATION_LOGS channel
    populates here when the runtime emits to it.

Usage:
  python setup_observability.py [--region us-east-1] [--dry-run]

Issue #28.
"""

import argparse
import json
import sys

import boto3
from botocore.exceptions import ClientError


HARNESSES = [
    {"name": "harness_UITestAgentHarness", "short": "ui-test", "log_group": "/aws/bedrock-agentcore/uitestagent"},
    {"name": "harness_BugFixAgentHarness", "short": "bug-fix", "log_group": "/aws/bedrock-agentcore/bugfixagent"},
]

LOG_RETENTION_DAYS = 30
POLICY_NAME = "ObservabilityAccess"


def upsert_log_group(logs, name: str, retention: int, dry_run: bool) -> None:
    existing = [
        lg for lg in logs.describe_log_groups(logGroupNamePrefix=name, limit=50).get("logGroups", [])
        if lg["logGroupName"] == name
    ]
    if not existing:
        if dry_run:
            print(f"    [DRY-RUN] would create log group: {name}")
            return
        logs.create_log_group(logGroupName=name)
        print(f"    ✓ created log group: {name}")
    else:
        print(f"    log group exists: {name}")
    if not dry_run:
        logs.put_retention_policy(logGroupName=name, retentionInDays=retention)


def set_default_log_group_retention(logs, harness_name: str, retention: int, dry_run: bool) -> None:
    """AgentCore auto-creates a default log group like
    /aws/bedrock-agentcore/runtimes/<harness>-<runtimeId>-DEFAULT.
    Set retention on it so logs don't accumulate indefinitely."""
    prefix = f"/aws/bedrock-agentcore/runtimes/{harness_name}-"
    found = [
        lg for lg in logs.describe_log_groups(logGroupNamePrefix=prefix, limit=10).get("logGroups", [])
        if lg["logGroupName"].endswith("-DEFAULT")
    ]
    if not found:
        print(f"    ⚠ no default log group found for {harness_name}")
        return
    for lg in found:
        if lg.get("retentionInDays") == retention:
            print(f"    default log group retention already {retention}d: <DEFAULT_LG>")
            continue
        if dry_run:
            print(f"    [DRY-RUN] would set retention {retention}d on default log group")
            continue
        logs.put_retention_policy(logGroupName=lg["logGroupName"], retentionInDays=retention)
        print(f"    ✓ set retention {retention}d on default log group: <DEFAULT_LG>")


def upsert_role_policy(iam, role_name: str, policy_doc: dict, dry_run: bool) -> None:
    if dry_run:
        print(f"    [DRY-RUN] would put inline policy {POLICY_NAME}")
        return
    iam.put_role_policy(RoleName=role_name, PolicyName=POLICY_NAME, PolicyDocument=json.dumps(policy_doc))
    print(f"    ✓ inline policy {POLICY_NAME} attached/updated")


def upsert_service_resource_policy(logs, account_id: str, region: str, dry_run: bool) -> None:
    """Extend the AWSLogDeliveryWrite20150319 policy (or create it) to allow
    delivery.logs.amazonaws.com to write to our /aws/bedrock-agentcore/* log groups.
    Existing statements (e.g. for SageMaker GroundTruth) are preserved."""
    policy_name = "AWSLogDeliveryWrite20150319"
    existing_statements = []
    try:
        for p in logs.describe_resource_policies().get("resourcePolicies", []):
            if p["policyName"] == policy_name:
                existing_statements = json.loads(p["policyDocument"]).get("Statement", [])
                break
    except ClientError:
        pass
    # Drop any prior AgentCore statement we might have added so it can be reset cleanly
    existing_statements = [s for s in existing_statements if s.get("Sid") != "AWSLogDeliveryWriteAgentCore"]
    agentcore_statement = {
        "Sid": "AWSLogDeliveryWriteAgentCore",
        "Effect": "Allow",
        "Principal": {"Service": "delivery.logs.amazonaws.com"},
        "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
        "Resource": [
            f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/uitestagent:log-stream:*",
            f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/bugfixagent:log-stream:*",
        ],
        "Condition": {"StringEquals": {"aws:SourceAccount": account_id}},
    }
    new_doc = {"Version": "2012-10-17", "Statement": existing_statements + [agentcore_statement]}
    if dry_run:
        print(f"    [DRY-RUN] would put resource policy {policy_name} with {len(new_doc['Statement'])} statements")
        return
    logs.put_resource_policy(policyName=policy_name, policyDocument=json.dumps(new_doc))
    print(f"    ✓ resource policy {policy_name} extended (preserves existing, adds AgentCore log groups)")


def get_or_create_source(logs, name: str, resource_arn: str, log_type: str, dry_run: bool) -> None:
    try:
        logs.get_delivery_source(name=name)
        print(f"    source exists: {name} ({log_type})")
        return
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    if dry_run:
        print(f"    [DRY-RUN] would create source: {name} ({log_type})")
        return
    logs.put_delivery_source(name=name, resourceArn=resource_arn, logType=log_type)
    print(f"    ✓ created source: {name} ({log_type})")


def get_or_create_destination_cwl(logs, name: str, log_group_arn: str, dry_run: bool) -> str:
    try:
        return logs.get_delivery_destination(name=name)["deliveryDestination"]["arn"]
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    if dry_run:
        return ""
    return logs.put_delivery_destination(
        name=name,
        deliveryDestinationConfiguration={"destinationResourceArn": log_group_arn},
        outputFormat="json",
        deliveryDestinationType="CWL",
    )["deliveryDestination"]["arn"]


def get_or_create_destination_xray(logs, name: str, dry_run: bool) -> str:
    try:
        return logs.get_delivery_destination(name=name)["deliveryDestination"]["arn"]
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    if dry_run:
        return ""
    return logs.put_delivery_destination(name=name, deliveryDestinationType="XRAY")["deliveryDestination"]["arn"]


def get_or_create_delivery(logs, source_name: str, dest_arn: str, dry_run: bool) -> None:
    deliveries = logs.describe_deliveries().get("deliveries", [])
    if any(d.get("deliverySourceName") == source_name and d.get("deliveryDestinationArn") == dest_arn for d in deliveries):
        return
    if dry_run:
        return
    logs.create_delivery(deliverySourceName=source_name, deliveryDestinationArn=dest_arn)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sts = boto3.client("sts")
    account_id = sts.get_caller_identity()["Account"]
    region = args.region
    dry_run = args.dry_run
    print(f"AWS account: <ACCOUNT_ID>  region: {region}\nMode: {'DRY-RUN' if dry_run else 'APPLY'}\n")

    logs_client = boto3.client("logs", region_name=region)
    iam = boto3.client("iam")
    agentcore = boto3.client("bedrock-agentcore-control", region_name=region)

    runtimes = {r["agentRuntimeName"]: r for r in agentcore.list_agent_runtimes()["agentRuntimes"]}
    role_arn = None
    print("=== Step 0: Verify harnesses ===")
    for h in HARNESSES:
        if h["name"] not in runtimes:
            print(f"  ✗ Not found: {h['name']}")
            return 1
        details = agentcore.get_agent_runtime(agentRuntimeId=runtimes[h["name"]]["agentRuntimeId"])
        if role_arn is None:
            role_arn = details["roleArn"]
        print(f"  ✓ {h['name']}")
    role_name = role_arn.split("/")[-1]
    print()

    # Step 1: Custom log groups (with retention)
    print("=== Step 1: Custom CWL log groups (compliance-bounded) ===")
    for h in HARNESSES:
        upsert_log_group(logs_client, h["log_group"], LOG_RETENTION_DAYS, dry_run)
    print()

    # Step 1b: Default log group retention (30d on the auto-created group where rich OTel data flows)
    print("=== Step 1b: Set 30d retention on AgentCore default log groups ===")
    for h in HARNESSES:
        set_default_log_group_retention(logs_client, h["name"], LOG_RETENTION_DAYS, dry_run)
    print()

    # Step 2: IAM
    print("=== Step 2: IAM ObservabilityAccess on execution role ===")
    upsert_role_policy(iam, role_name, {
        "Version": "2012-10-17",
        "Statement": [
            {"Sid": "LogDelivery", "Effect": "Allow",
             "Action": ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"],
             "Resource": f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/*"},
            {"Sid": "XRayTracing", "Effect": "Allow",
             "Action": ["xray:PutTraceSegments", "xray:PutTelemetryRecords",
                        "xray:GetSamplingRules", "xray:GetSamplingTargets"],
             "Resource": "*"},
        ],
    }, dry_run)
    print()

    # Step 3: Service resource policy (allows delivery.logs.amazonaws.com to write)
    print("=== Step 3: Logs delivery service resource policy ===")
    upsert_service_resource_policy(logs_client, account_id, region, dry_run)
    print()

    # Step 4: Deliveries
    print("=== Step 4: APPLICATION_LOGS + TRACES deliveries ===")
    for h in HARNESSES:
        runtime_arn = runtimes[h["name"]]["agentRuntimeArn"]
        # APPLICATION_LOGS → CWL log group
        src_logs = f"{h['short']}-app-logs-source"
        dst_logs = f"{h['short']}-app-logs-dest"
        log_group_arn = f"arn:aws:logs:{region}:{account_id}:log-group:{h['log_group']}:*"
        print(f"  {h['name']} / APPLICATION_LOGS:")
        get_or_create_source(logs_client, src_logs, runtime_arn, "APPLICATION_LOGS", dry_run)
        dst_logs_arn = get_or_create_destination_cwl(logs_client, dst_logs, log_group_arn, dry_run)
        if dst_logs_arn:
            get_or_create_delivery(logs_client, src_logs, dst_logs_arn, dry_run)
            print(f"    ✓ delivery linked: {src_logs} → {dst_logs}")
        # TRACES → X-Ray service
        src_tr = f"{h['short']}-traces-source"
        dst_tr = f"{h['short']}-traces-xray-dest"
        print(f"  {h['name']} / TRACES:")
        get_or_create_source(logs_client, src_tr, runtime_arn, "TRACES", dry_run)
        dst_tr_arn = get_or_create_destination_xray(logs_client, dst_tr, dry_run)
        if dst_tr_arn:
            get_or_create_delivery(logs_client, src_tr, dst_tr_arn, dry_run)
            print(f"    ✓ delivery linked: {src_tr} → {dst_tr}")
    print()

    print("=== ✅ Setup complete ===")
    print()
    print("In AWS console (AgentCore → Harness → each harness):")
    print("  - Log delivery: 2 destinations (was 0)")
    print("  - Tracing: Enabled (was Not enabled)")
    print()
    print("Where to look for data:")
    print("  - Rich OTel runtime logs (with trace_id/span_id/EMF metrics):")
    print("      /aws/bedrock-agentcore/runtimes/harness_UITestAgentHarness-*-DEFAULT")
    print("      /aws/bedrock-agentcore/runtimes/harness_BugFixAgentHarness-*-DEFAULT")
    print("      ↑ now with 30-day retention")
    print("  - X-Ray traces:")
    print("      AWS Console → CloudWatch → Application Signals → Service map")
    print("      AWS Console → X-Ray → Traces")
    print("  - Custom CWL log groups (sparser per-invocation events):")
    print("      /aws/bedrock-agentcore/uitestagent")
    print("      /aws/bedrock-agentcore/bugfixagent")
    print("      ↑ populates when AgentCore emits to APPLICATION_LOGS channel")
    return 0


if __name__ == "__main__":
    sys.exit(main())
