#!/usr/bin/env python3
"""
Set up observability for AgentCore harnesses (issue #28).

Idempotent — running multiple times is safe.

Configures:
  1. Per-harness CloudWatch log group for APPLICATION_LOGS (30-day retention)
  2. CloudWatch Logs Delivery for APPLICATION_LOGS  → log group (CWL destination)
  3. CloudWatch Logs Delivery for TRACES            → X-Ray service (XRAY destination)
  4. IAM inline policy "ObservabilityAccess" on the harnesses' execution role
     (logs:Put/Describe + xray:Put/Get)

Result in AWS console (AgentCore → Harness → each harness):
  - Log delivery: 2 destinations (was 0)         ← 1 CWL for app logs, 1 XRAY for traces
  - Tracing: Enabled (was Not enabled)

Usage:
  python setup_observability.py [--region us-east-1] [--dry-run]
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
    if existing:
        print(f"    log group exists: {name}")
    elif not dry_run:
        logs.create_log_group(logGroupName=name)
        print(f"    ✓ created log group: {name}")
    if not dry_run:
        logs.put_retention_policy(logGroupName=name, retentionInDays=retention)


def upsert_role_policy(iam, role_name: str, policy_doc: dict, dry_run: bool) -> None:
    if dry_run:
        print(f"    [DRY-RUN] would put inline policy {POLICY_NAME}")
        return
    iam.put_role_policy(RoleName=role_name, PolicyName=POLICY_NAME, PolicyDocument=json.dumps(policy_doc))
    print(f"    ✓ inline policy {POLICY_NAME} attached/updated")


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
        d = logs.get_delivery_destination(name=name)["deliveryDestination"]
        print(f"    destination exists: {name} (CWL)")
        return d["arn"]
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    if dry_run:
        print(f"    [DRY-RUN] would create destination: {name} (CWL)")
        return ""
    d = logs.put_delivery_destination(
        name=name,
        deliveryDestinationConfiguration={"destinationResourceArn": log_group_arn},
        outputFormat="json",
        deliveryDestinationType="CWL",
    )["deliveryDestination"]
    print(f"    ✓ created destination: {name} (CWL → log group)")
    return d["arn"]


def get_or_create_destination_xray(logs, name: str, dry_run: bool) -> str:
    try:
        d = logs.get_delivery_destination(name=name)["deliveryDestination"]
        print(f"    destination exists: {name} (XRAY)")
        return d["arn"]
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    if dry_run:
        print(f"    [DRY-RUN] would create destination: {name} (XRAY)")
        return ""
    d = logs.put_delivery_destination(
        name=name, deliveryDestinationType="XRAY",
    )["deliveryDestination"]
    print(f"    ✓ created destination: {name} (XRAY → service)")
    return d["arn"]


def get_or_create_delivery(logs, source_name: str, dest_arn: str, dry_run: bool) -> None:
    deliveries = logs.describe_deliveries().get("deliveries", [])
    if any(
        d.get("deliverySourceName") == source_name and d.get("deliveryDestinationArn") == dest_arn
        for d in deliveries
    ):
        print(f"    delivery exists: {source_name} → ...")
        return
    if dry_run:
        print(f"    [DRY-RUN] would create delivery: {source_name} → ...")
        return
    logs.create_delivery(deliverySourceName=source_name, deliveryDestinationArn=dest_arn)
    print(f"    ✓ created delivery: {source_name} → ...")


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

    print("=== Step 1: Log groups ===")
    for h in HARNESSES:
        upsert_log_group(logs_client, h["log_group"], LOG_RETENTION_DAYS, dry_run)
    print()

    print("=== Step 2: IAM policy on execution role ===")
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

    print("=== Step 3: Deliveries ===")
    for h in HARNESSES:
        runtime_arn = runtimes[h["name"]]["agentRuntimeArn"]
        print(f"  {h['name']}:")
        # APPLICATION_LOGS → CWL log group
        src_logs = f"{h['short']}-app-logs-source"
        dst_logs = f"{h['short']}-app-logs-dest"
        log_group_arn = f"arn:aws:logs:{region}:{account_id}:log-group:{h['log_group']}:*"
        get_or_create_source(logs_client, src_logs, runtime_arn, "APPLICATION_LOGS", dry_run)
        dst_logs_arn = get_or_create_destination_cwl(logs_client, dst_logs, log_group_arn, dry_run)
        if dst_logs_arn:
            get_or_create_delivery(logs_client, src_logs, dst_logs_arn, dry_run)
        # TRACES → X-Ray service
        src_tr = f"{h['short']}-traces-source"
        dst_tr = f"{h['short']}-traces-xray-dest"
        get_or_create_source(logs_client, src_tr, runtime_arn, "TRACES", dry_run)
        dst_tr_arn = get_or_create_destination_xray(logs_client, dst_tr, dry_run)
        if dst_tr_arn:
            get_or_create_delivery(logs_client, src_tr, dst_tr_arn, dry_run)
    print()

    print("=== ✅ Observability setup complete ===")
    print("\nIn the AWS console (AgentCore → Harness):")
    print("  - Log delivery: 2 (CWL for app logs, XRAY for traces)")
    print("  - Tracing: Enabled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
