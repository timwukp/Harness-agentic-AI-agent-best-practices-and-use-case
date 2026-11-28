#!/usr/bin/env python3
"""
Deploy the qa_tool_guard Lambda, the harness execution role's grant to invoke it, and an alarm (WS2).

Everything comes from qa_tool_guard_spec.json's `deploy` section. This script does NOT touch the harness:
tighten_harness_config.py owns the harness `hooks` list and points it at the alias this script prints.

Managed resources:
  - IAM role  <lambdaRoleName>          trust lambda.amazonaws.com; logs:CreateLogStream/PutLogEvents on its log group
  - log group /aws/lambda/<functionName> retention <logRetentionDays>
  - function  <functionName>            the package files, zipped deterministically; env QA_ALLOWED_ORIGINS
  - alias     <alias>                   the hook's target; its description records the previous version
  - inline policy <executionRoleGrantName> on each listed harness's execution role: lambda:InvokeFunction on the alias
  - alarm     <alarmName>               Errors + Throttles >= 1 in one period (optional --alarm-topic-arn)

Usage:
  python deploy_qa_tool_guard.py plan   --origins https://app,https://api,...   # change nothing (default)
  python deploy_qa_tool_guard.py apply  --origins ...  [--alarm-topic-arn ARN]
  python deploy_qa_tool_guard.py verify --origins ...  # config, code hash, grant, alarm, live decisions, log hygiene
  python deploy_qa_tool_guard.py rollback [--to-version N]                       # move the alias back
  python deploy_qa_tool_guard.py remove                                          # refused while any hook targets it

Exit codes:
  0  ok / no drift
  1  a resource verify or rollback needs is missing
  2  the SDK model lacks harness hooks (botocore < 1.43.120): GetHarness would hide them
  3  an AWS call failed
  4  plan: drift found
  5  verify: live state or a live decision differs from the spec
  6  remove refused: a harness hook still targets the guard
  7  refused input (empty --origins, unknown version)
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import pathlib
import re
import sys
import time
import uuid
import zipfile
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
SPEC = json.loads((HERE / "qa_tool_guard_spec.json").read_text())
D = SPEC["deploy"]
ALIAS_DESC = re.compile(r"^previous=(\d+|none)$")


class Fail(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code


def redact(s: str) -> str:
    return re.sub(r"\b\d{12}\b", "<ACCOUNT_ID>", str(s))


def say(msg: str) -> None:
    print(redact(msg))


def error_code(e: Exception) -> str:
    return getattr(e, "response", {}).get("Error", {}).get("Code", "") if hasattr(e, "response") else ""


# ── Package ──────────────────────────────────────────────────────────────────────────────────────
def build_zip(root: pathlib.Path = HERE) -> bytes:
    """Same bytes for the same files: fixed order, fixed timestamp and mode."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(D["packageFiles"]):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, (root / name).read_bytes())
    return buf.getvalue()


def code_sha256(zip_bytes: bytes) -> str:
    return base64.b64encode(hashlib.sha256(zip_bytes).digest()).decode()


# ── Desired documents ────────────────────────────────────────────────────────────────────────────
def log_group_name() -> str:
    return f"/aws/lambda/{D['functionName']}"


def lambda_trust() -> dict:
    return {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"},
                                                    "Action": "sts:AssumeRole"}]}


def lambda_logs_policy(region: str, account: str) -> dict:
    arn = f"arn:aws:logs:{region}:{account}:log-group:{log_group_name()}"
    return {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                                                    "Resource": f"{arn}:*"}]}


def alias_arn(region: str, account: str) -> str:
    return D["aliasArnTemplate"].format(region=region, account=account)


def function_arn(region: str, account: str) -> str:
    return alias_arn(region, account).rsplit(":", 1)[0]


def invoke_grant(region: str, account: str) -> dict:
    return {"Version": "2012-10-17", "Statement": [{"Sid": "InvokeQaToolGuard", "Effect": "Allow",
                                                    "Action": "lambda:InvokeFunction", "Resource": alias_arn(region, account)}]}


def function_config(role_arn: str, origins: str) -> dict:
    return {"Runtime": D["runtime"], "Handler": D["handler"], "Role": role_arn, "Timeout": D["timeoutSeconds"],
            "MemorySize": D["memoryMB"], "Environment": {"Variables": {SPEC["origins"]["env"]: origins}}}


def alarm_args(topic: str | None) -> dict:
    fn = D["functionName"]
    metric = lambda mid, name: {"Id": mid, "ReturnData": False, "MetricStat": {
        "Metric": {"Namespace": "AWS/Lambda", "MetricName": name,
                   "Dimensions": [{"Name": "FunctionName", "Value": fn}]},
        "Period": D["alarmPeriodSeconds"], "Stat": "Sum"}}
    args = {"AlarmName": D["alarmName"],
            "AlarmDescription": "qa_tool_guard errors or throttles: every tool call it judges is denied (failureMode deny)",
            "Metrics": [metric("errors", "Errors"), metric("throttles", "Throttles"),
                        {"Id": "total", "Expression": "errors + throttles", "ReturnData": True}],
            "EvaluationPeriods": 1, "Threshold": 1.0, "ComparisonOperator": "GreaterThanOrEqualToThreshold",
            "TreatMissingData": "notBreaching", "ActionsEnabled": bool(topic)}
    if topic:
        args["AlarmActions"] = [topic]
    return args


def same_policy(a: Any, b: Any) -> bool:
    canon = lambda d: json.dumps(json.loads(d) if isinstance(d, str) else d, sort_keys=True)
    return canon(a) == canon(b)


# ── Live reads ───────────────────────────────────────────────────────────────────────────────────
class Aws:
    def __init__(self, session: Any, region: str, sleep=time.sleep):
        self.region, self.sleep = region, sleep
        self.iam = session.client("iam")
        self.logs = session.client("logs", region_name=region)
        self.lam = session.client("lambda", region_name=region)
        self.cw = session.client("cloudwatch", region_name=region)
        self.control = session.client("bedrock-agentcore-control", region_name=region)
        self.account = session.client("sts").get_caller_identity()["Account"]

    def model_knows_hooks(self) -> bool:
        sm = self.control.meta.service_model
        try:
            harness = sm.operation_model("GetHarness").output_shape.members["harness"]
            return "hooks" in harness.members and "hooks" in sm.operation_model("UpdateHarness").input_shape.members
        except Exception:  # noqa: BLE001
            return False

    def harnesses(self) -> list[dict]:
        out, token = [], None
        while True:
            page = self.control.list_harnesses(**({"nextToken": token} if token else {}))
            out += page.get("harnesses", [])
            token = page.get("nextToken")
            if not token:
                return out

    def harness_detail(self, name: str) -> dict:
        match = [h for h in self.harnesses() if h.get("harnessName") == name]
        if not match:
            raise Fail(1, f"harness {name} not found")
        return self.control.get_harness(harnessId=match[0]["harnessId"])["harness"]

    def role(self, name: str) -> dict | None:
        try:
            return self.iam.get_role(RoleName=name)["Role"]
        except Exception as e:  # noqa: BLE001
            if error_code(e) == "NoSuchEntity":
                return None
            raise

    def role_policy(self, role: str, name: str) -> dict | None:
        try:
            return self.iam.get_role_policy(RoleName=role, PolicyName=name)["PolicyDocument"]
        except Exception as e:  # noqa: BLE001
            if error_code(e) == "NoSuchEntity":
                return None
            raise

    def function(self) -> dict | None:
        try:
            return self.lam.get_function_configuration(FunctionName=D["functionName"])
        except Exception as e:  # noqa: BLE001
            if error_code(e) == "ResourceNotFoundException":
                return None
            raise

    def alias(self) -> dict | None:
        try:
            return self.lam.get_alias(FunctionName=D["functionName"], Name=D["alias"])
        except Exception as e:  # noqa: BLE001
            if error_code(e) == "ResourceNotFoundException":
                return None
            raise

    def versions(self) -> list[dict]:
        out, marker = [], None
        while True:
            page = self.lam.list_versions_by_function(FunctionName=D["functionName"], **({"Marker": marker} if marker else {}))
            out += [v for v in page.get("Versions", []) if v.get("Version") != "$LATEST"]
            marker = page.get("NextMarker")
            if not marker:
                return out

    def log_group(self) -> dict | None:
        groups = self.logs.describe_log_groups(logGroupNamePrefix=log_group_name()).get("logGroups", [])
        return next((g for g in groups if g.get("logGroupName") == log_group_name()), None)

    def alarm(self) -> dict | None:
        alarms = self.cw.describe_alarms(AlarmNames=[D["alarmName"]]).get("MetricAlarms", [])
        return alarms[0] if alarms else None

    def wait_updated(self) -> None:
        for _ in range(60):
            cfg = self.lam.get_function_configuration(FunctionName=D["functionName"])
            if cfg.get("State", "Active") == "Active" and cfg.get("LastUpdateStatus", "Successful") == "Successful":
                return
            if cfg.get("LastUpdateStatus") == "Failed" or cfg.get("State") == "Failed":
                raise Fail(3, "function update failed")
            self.sleep(2)
        raise Fail(3, "function did not become Active/Successful in 120 s")


# ── Plan ─────────────────────────────────────────────────────────────────────────────────────────
def plan(aws: Aws, origins: str, topic: str | None, zip_bytes: bytes) -> list[tuple[str, str]]:
    """[(resource, 'create'|'update'|'same')] in apply order."""
    rows = []
    role = aws.role(D["lambdaRoleName"])
    if role is None:
        rows += [("lambda role", "create"), ("lambda role logs policy", "create")]
    else:
        trust_ok = same_policy(role["AssumeRolePolicyDocument"], lambda_trust())
        rows.append(("lambda role", "same" if trust_ok else "update"))
        logs = aws.role_policy(D["lambdaRoleName"], "logs")
        rows.append(("lambda role logs policy", "create" if logs is None else
                     "same" if same_policy(logs, lambda_logs_policy(aws.region, aws.account)) else "update"))
    group = aws.log_group()
    rows.append(("log group", "create" if group is None else
                 "same" if group.get("retentionInDays") == D["logRetentionDays"] else "update"))
    fn = aws.function()
    role_arn = role["Arn"] if role else f"arn:aws:iam::{aws.account}:role/{D['lambdaRoleName']}"
    if fn is None:
        rows.append(("function", "create"))
    else:
        want = function_config(role_arn, origins)
        drift = fn.get("CodeSha256") != code_sha256(zip_bytes) or any(fn.get(k) != v for k, v in want.items()) \
            or fn.get("Architectures", ["x86_64"]) != [D["architecture"]]
        rows.append(("function", "update" if drift else "same"))
    alias = aws.alias() if fn else None
    if alias is None:
        rows.append(("alias", "create"))
    else:
        published = {v["Version"]: v for v in aws.versions()}
        cur = published.get(alias.get("FunctionVersion"), {})
        fresh = rows[-1][1] == "same" and cur.get("CodeSha256") == fn.get("CodeSha256") \
            and cur.get("Environment") == fn.get("Environment")
        rows.append(("alias", "same" if fresh else "update"))
    for name in D["harnesses"]:
        exec_role = aws.harness_detail(name)["executionRoleArn"].split("/")[-1]
        grant = aws.role_policy(exec_role, D["executionRoleGrantName"])
        rows.append((f"invoke grant on {name} execution role", "create" if grant is None else
                     "same" if same_policy(grant, invoke_grant(aws.region, aws.account)) else "update"))
    alarm = aws.alarm()
    want_alarm = alarm_args(topic)
    if alarm is None:
        rows.append(("alarm", "create"))
    else:
        keys = ("Threshold", "ComparisonOperator", "EvaluationPeriods", "TreatMissingData")
        same = all(alarm.get(k) == want_alarm[k] for k in keys) and \
            (alarm.get("AlarmActions") or []) == want_alarm.get("AlarmActions", [])
        rows.append(("alarm", "same" if same else "update"))
    return rows


# ── Apply ────────────────────────────────────────────────────────────────────────────────────────
def apply(aws: Aws, origins: str, topic: str | None, zip_bytes: bytes) -> str:
    rows = dict(plan(aws, origins, topic, zip_bytes))
    region, account, fn_name = aws.region, aws.account, D["functionName"]
    if rows["lambda role"] == "create":
        aws.iam.create_role(RoleName=D["lambdaRoleName"], AssumeRolePolicyDocument=json.dumps(lambda_trust()),
                            Description="qa_tool_guard Lambda: writes its own log group only",
                            Tags=[{"Key": "component", "Value": "qa-tool-guard"}])
    elif rows["lambda role"] == "update":
        aws.iam.update_assume_role_policy(RoleName=D["lambdaRoleName"], PolicyDocument=json.dumps(lambda_trust()))
    if rows["lambda role logs policy"] != "same":
        aws.iam.put_role_policy(RoleName=D["lambdaRoleName"], PolicyName="logs",
                                PolicyDocument=json.dumps(lambda_logs_policy(region, account)))
    if rows["log group"] == "create":
        aws.logs.create_log_group(logGroupName=log_group_name())
    if rows["log group"] != "same":
        aws.logs.put_retention_policy(logGroupName=log_group_name(), retentionInDays=D["logRetentionDays"])
    role_arn = f"arn:aws:iam::{account}:role/{D['lambdaRoleName']}"
    cfg = function_config(role_arn, origins)
    previous = "none"
    if rows["function"] == "create":
        for attempt in range(12):  # a new role takes seconds to become assumable by Lambda
            try:
                aws.lam.create_function(FunctionName=fn_name, Code={"ZipFile": zip_bytes}, Publish=False,
                                        Architectures=[D["architecture"]], **cfg)
                break
            except Exception as e:  # noqa: BLE001
                if error_code(e) != "InvalidParameterValueException" or attempt == 11:
                    raise
                aws.sleep(5)
        aws.wait_updated()
    elif rows["function"] == "update":
        alias = aws.alias()
        previous = alias["FunctionVersion"] if alias else "none"
        aws.lam.update_function_code(FunctionName=fn_name, ZipFile=zip_bytes, Architectures=[D["architecture"]])
        aws.wait_updated()
        aws.lam.update_function_configuration(FunctionName=fn_name, **cfg)
        aws.wait_updated()
    if rows["function"] != "same" or rows["alias"] != "same":
        if rows["alias"] == "update" and previous == "none":
            alias = aws.alias()
            previous = alias["FunctionVersion"] if alias else "none"
        version = aws.lam.publish_version(FunctionName=fn_name, CodeSha256=code_sha256(zip_bytes),
                                          Description="qa_tool_guard spec sha256 " +
                                          hashlib.sha256((HERE / "qa_tool_guard_spec.json").read_bytes()).hexdigest()[:16])["Version"]
        if aws.alias() is None:
            aws.lam.create_alias(FunctionName=fn_name, Name=D["alias"], FunctionVersion=version,
                                 Description="previous=none")
        else:
            aws.lam.update_alias(FunctionName=fn_name, Name=D["alias"], FunctionVersion=version,
                                 Description=f"previous={previous}")
        say(f"  ✓ alias {D['alias']} -> version {version} (previous={previous})")
    for name in D["harnesses"]:
        if rows[f"invoke grant on {name} execution role"] != "same":
            exec_role = aws.harness_detail(name)["executionRoleArn"].split("/")[-1]
            aws.iam.put_role_policy(RoleName=exec_role, PolicyName=D["executionRoleGrantName"],
                                    PolicyDocument=json.dumps(invoke_grant(region, account)))
    if rows["alarm"] != "same":
        aws.cw.put_metric_alarm(**alarm_args(topic))
    return alias_arn(region, account)


# ── Verify ───────────────────────────────────────────────────────────────────────────────────────
def verify(aws: Aws, origins: str, topic: str | None, zip_bytes: bytes, cases: dict) -> list[str]:
    """Problems found; [] means verified."""
    problems = [f"{r}: {s}" for r, s in plan(aws, origins, topic, zip_bytes) if s != "same"]
    if problems:
        return problems
    # One case per rule (plus the secret-marker case), invoked through the alias the hook targets. When the
    # live origins differ from the fixture's, allow cases that name fixture hosts would be judged against
    # other origins, so those are skipped; each rule keeps a representative.
    listed = {o.strip() for o in origins.split(",") if o.strip()}
    same_origins = listed == {o.strip() for o in cases["env"][SPEC["origins"]["env"]].split(",")}
    by_rule: dict[str, dict] = {}
    for c in cases["cases"]:
        # Only an allow depends on a fixture host being listed; every deny here is decided by a rule that
        # runs before, or does not depend on, the allow-list (an unlisted host can only add denies).
        if c.get("env") is not None or (not same_origins and c["expect"]["decision"] == "allow"
                                        and ".example.test" in json.dumps(c["event"])):
            continue
        by_rule.setdefault(c["expect"]["rule"], c)
    marker = cases["secretMarkers"][0]
    marked = json.loads(json.dumps(next(c for c in cases["cases"] if marker in json.dumps(c["event"]))))
    marked["id"] += " (marker)"
    marked["event"]["hookEventId"] = str(uuid.uuid4())
    start_ms = int(time.time() * 1000) - 60_000
    for c in list(by_rule.values()) + [marked]:
        resp = aws.lam.invoke(FunctionName=D["functionName"], Qualifier=D["alias"], Payload=json.dumps(c["event"]).encode())
        if resp.get("FunctionError"):
            problems.append(f"{c['id']}: function error")
            continue
        got = json.loads(resp["Payload"].read())
        if got.get("decision") != c["expect"]["decision"] or not str(got.get("reason", "")).startswith(c["expect"]["rule"] + ":"):
            problems.append(f"{c['id']}: got {got.get('decision')} {str(got.get('reason', ''))[:4]}, "
                            f"want {c['expect']['decision']} {c['expect']['rule']}")
    missing_rules = set(SPEC["rules"]) - set(by_rule) - {"G09"}
    if missing_rules:
        problems.append(f"no replayable case for rule(s) {', '.join(sorted(missing_rules))}")
    # Log hygiene, measured at the meter: the marked invocation's own line must have arrived, and the
    # password marker must appear nowhere in the log group.
    hook_id = marked["event"]["hookEventId"]
    arrived = False
    for _ in range(30):
        ev = aws.logs.filter_log_events(logGroupName=log_group_name(), startTime=start_ms, filterPattern=f'"{hook_id}"')
        if ev.get("events"):
            arrived = True
            break
        aws.sleep(2)
    if not arrived:
        problems.append("log line of the marked invocation never arrived; log hygiene unproven")
    elif aws.logs.filter_log_events(logGroupName=log_group_name(), startTime=start_ms, filterPattern=f'"{marker}"').get("events"):
        problems.append("the password marker appears in the guard's logs")
    return problems


# ── Rollback / remove ────────────────────────────────────────────────────────────────────────────
def rollback(aws: Aws, to_version: str | None) -> str:
    alias = aws.alias()
    if alias is None:
        raise Fail(1, "no alias to roll back")
    m = ALIAS_DESC.match(alias.get("Description") or "")
    target = to_version or (m.group(1) if m else "none")
    if target == "none":
        raise Fail(7, "no previous version recorded; pass --to-version N")
    if target not in {v["Version"] for v in aws.versions()}:
        raise Fail(7, f"version {target} does not exist")
    aws.lam.update_alias(FunctionName=D["functionName"], Name=D["alias"], FunctionVersion=target,
                         Description=f"previous={alias['FunctionVersion']}")
    return target


def hooks_targeting_guard(aws: Aws) -> list[str]:
    fn = function_arn(aws.region, aws.account)
    found = []
    for h in aws.harnesses():
        detail = aws.control.get_harness(harnessId=h["harnessId"])["harness"]
        for hook in detail.get("hooks") or []:
            for event, cfg in hook.items():
                arn = ((cfg.get("target") or {}).get("lambda") or {}).get("arn", "")
                if arn == fn or arn.startswith(fn + ":"):
                    found.append(f"{h.get('harnessName')}.{event}.{cfg.get('name')}")
    return found


def remove(aws: Aws) -> None:
    live = hooks_targeting_guard(aws)
    if live:
        raise Fail(6, f"hooks still target the guard: {', '.join(live)}. Remove them first "
                      f"(tighten_harness_config.py --hooks off --allow-narrowing, plus --allow-empty-hooks when the guard is the only hook); with failureMode deny, deleting the guard under a live hook denies every tool call")
    if aws.alarm():
        aws.cw.delete_alarms(AlarmNames=[D["alarmName"]])
    for name in D["harnesses"]:
        exec_role = aws.harness_detail(name)["executionRoleArn"].split("/")[-1]
        if aws.role_policy(exec_role, D["executionRoleGrantName"]) is not None:
            aws.iam.delete_role_policy(RoleName=exec_role, PolicyName=D["executionRoleGrantName"])
    if aws.function():
        if aws.alias():
            aws.lam.delete_alias(FunctionName=D["functionName"], Name=D["alias"])
        aws.lam.delete_function(FunctionName=D["functionName"])
    if aws.role(D["lambdaRoleName"]):
        if aws.role_policy(D["lambdaRoleName"], "logs") is not None:
            aws.iam.delete_role_policy(RoleName=D["lambdaRoleName"], PolicyName="logs")
        aws.iam.delete_role(RoleName=D["lambdaRoleName"])
    say(f"  ✓ removed; log group {log_group_name()} kept as evidence")


# ── Main ─────────────────────────────────────────────────────────────────────────────────────────
def main(argv=None, session=None, sleep=time.sleep) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="plan", choices=["plan", "apply", "verify", "rollback", "remove"])
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--origins", default="", help="QA_ALLOWED_ORIGINS for the guard (comma-separated)")
    ap.add_argument("--alarm-topic-arn")
    ap.add_argument("--to-version")
    a = ap.parse_args(argv)
    if a.command in ("plan", "apply", "verify") and not [o for o in a.origins.split(",") if o.strip()]:
        say("ERROR: --origins is empty; the guard would deny every navigation. Pass the app's origins.")
        return 7
    if session is None:
        import boto3
        session = boto3.Session(region_name=a.region)
    try:
        aws = Aws(session, a.region, sleep)
        if not aws.model_knows_hooks():
            say("ERROR: this SDK's model has no harness hooks (need botocore >= 1.43.120); GetHarness would hide them")
            return 2
        zip_bytes = build_zip()
        say(f"package sha256 {code_sha256(zip_bytes)}  command {a.command}")
        if a.command == "plan":
            rows = plan(aws, a.origins, a.alarm_topic_arn, zip_bytes)
            for r, s in rows:
                say(f"  {s:7} {r}")
            return 4 if any(s != "same" for _, s in rows) else 0
        if a.command == "apply":
            arn = apply(aws, a.origins, a.alarm_topic_arn, zip_bytes)
            say(f"  ✓ applied. Hook target (fill hookConfig arn): {arn}")
            return 0
        if a.command == "verify":
            cases = json.loads((HERE / "qa_tool_guard_cases.json").read_text())
            problems = verify(aws, a.origins, a.alarm_topic_arn, zip_bytes, cases)
            for p in problems:
                say(f"  ✗ {p}")
            if not problems:
                say("  ✓ verified: config, code hash, grant, alarm, live decisions, no password in logs")
            return 5 if problems else 0
        if a.command == "rollback":
            say(f"  ✓ alias {D['alias']} -> version {rollback(aws, a.to_version)}")
            return 0
        remove(aws)
        return 0
    except Fail as f:
        say(f"ERROR: {f}")
        return f.code
    except Exception as e:  # noqa: BLE001
        say(f"ERROR: AWS call failed: {error_code(e) or type(e).__name__}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
