"""Offline tests for deploy_qa_tool_guard.py against an in-memory AWS double.

Run from this directory:  python3 -m unittest -v test_deploy_qa_tool_guard
The double refuses what real AWS refuses (a just-created role Lambda cannot assume yet, publish_version
with a stale CodeSha256, deleting a role that still has inline policies), and its Lambda invoke runs the
handler FROM THE UPLOADED ZIP, so verify exercises the artifact, not this directory.
"""
import contextlib
import importlib
import io
import json
import os
import pathlib
import sys
import tempfile
import types
import unittest
import zipfile
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
ACCOUNT = "111122223333"
CASES = json.loads((HERE / "qa_tool_guard_cases.json").read_text())
FIXTURE_ORIGINS = CASES["env"]["QA_ALLOWED_ORIGINS"]
REAL_LIKE_ORIGINS = "https://d111.cloudfront.example,https://abc.execute-api.us-east-1.example"


def load_deploy():
    sys.path.insert(0, str(HERE))
    try:
        import deploy_qa_tool_guard
        return importlib.reload(deploy_qa_tool_guard)
    finally:
        sys.path.remove(str(HERE))


class AwsError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class Shape:
    def __init__(self, members):
        self.members = members


class World:
    def __init__(self, hooks_in_model=True):
        self.writes, self.reads = [], []
        self.roles = {"AgentCore-exec-role": {"Arn": f"arn:aws:iam::{ACCOUNT}:role/AgentCore-exec-role",
                                              "AssumeRolePolicyDocument": {}, "policies": {}}}
        self.groups, self.log_lines, self.alarms = {}, [], {}
        self.fn, self.versions, self.alias = None, {}, None
        self.harness_hooks = []
        self.hooks_in_model = hooks_in_model
        self.role_unassumable_tries = 2
        self.lying = None       # "allow-all" | "print-event"
        self.drop_logs = False

    def client(self, name, region_name=None):
        return {"sts": Sts, "iam": Iam, "logs": Logs, "lambda": Lambda, "cloudwatch": Cw,
                "bedrock-agentcore-control": Control}[name](self)


class Svc:
    WRITES = ()

    def __init__(self, w):
        self.w = w

    def __getattribute__(self, item):
        attr = object.__getattribute__(self, item)
        if callable(attr) and not item.startswith("_") and item != "meta":
            w = object.__getattribute__(self, "w")
            (w.writes if item in type(self).WRITES else w.reads).append((type(self).__name__, item))
        return attr


class Sts(Svc):
    def get_caller_identity(self):
        return {"Account": ACCOUNT}


class Iam(Svc):
    WRITES = ("create_role", "update_assume_role_policy", "put_role_policy", "delete_role_policy", "delete_role")

    def _role(self, n):
        if n not in self.w.roles:
            raise AwsError("NoSuchEntity")
        return self.w.roles[n]

    def get_role(self, RoleName):
        r = self._role(RoleName)
        return {"Role": {"Arn": r["Arn"], "AssumeRolePolicyDocument": r["AssumeRolePolicyDocument"]}}

    def create_role(self, RoleName, AssumeRolePolicyDocument, **_):
        if RoleName in self.w.roles:
            raise AwsError("EntityAlreadyExists")
        self.w.roles[RoleName] = {"Arn": f"arn:aws:iam::{ACCOUNT}:role/{RoleName}",
                                  "AssumeRolePolicyDocument": json.loads(AssumeRolePolicyDocument), "policies": {}}

    def update_assume_role_policy(self, RoleName, PolicyDocument):
        self._role(RoleName)["AssumeRolePolicyDocument"] = json.loads(PolicyDocument)

    def put_role_policy(self, RoleName, PolicyName, PolicyDocument):
        self._role(RoleName)["policies"][PolicyName] = json.loads(PolicyDocument)

    def get_role_policy(self, RoleName, PolicyName):
        p = self._role(RoleName)["policies"]
        if PolicyName not in p:
            raise AwsError("NoSuchEntity")
        return {"PolicyDocument": p[PolicyName]}

    def delete_role_policy(self, RoleName, PolicyName):
        self._role(RoleName)["policies"].pop(PolicyName)

    def delete_role(self, RoleName):
        if self._role(RoleName)["policies"]:
            raise AwsError("DeleteConflict")
        del self.w.roles[RoleName]


class Logs(Svc):
    WRITES = ("create_log_group", "put_retention_policy")

    def describe_log_groups(self, logGroupNamePrefix):
        return {"logGroups": [g for n, g in self.w.groups.items() if n.startswith(logGroupNamePrefix)]}

    def create_log_group(self, logGroupName):
        if logGroupName in self.w.groups:
            raise AwsError("ResourceAlreadyExistsException")
        self.w.groups[logGroupName] = {"logGroupName": logGroupName}

    def put_retention_policy(self, logGroupName, retentionInDays):
        self.w.groups[logGroupName]["retentionInDays"] = retentionInDays

    def filter_log_events(self, logGroupName, startTime, filterPattern):
        needle = filterPattern.strip('"')
        return {"events": [{"message": m} for m in self.w.log_lines if needle in m]}


def sha(zip_bytes):
    import base64, hashlib
    return base64.b64encode(hashlib.sha256(zip_bytes).digest()).decode()


class Lambda(Svc):
    WRITES = ("create_function", "update_function_code", "update_function_configuration", "publish_version",
              "create_alias", "update_alias", "delete_alias", "delete_function")

    def _need(self):
        if self.w.fn is None:
            raise AwsError("ResourceNotFoundException")
        return self.w.fn

    def _cfg(self, f):
        return {k: f[k] for k in ("Runtime", "Handler", "Role", "Timeout", "MemorySize", "Environment", "Architectures",
                                  "CodeSha256")} | {"State": "Active", "LastUpdateStatus": "Successful"}

    def create_function(self, FunctionName, Code, Publish, Architectures, Role, **cfg):
        role = Role.split("/")[-1]
        if role not in self.w.roles or self.w.role_unassumable_tries > 0:
            self.w.role_unassumable_tries -= 1
            raise AwsError("InvalidParameterValueException")
        self.w.fn = dict(cfg, Role=Role, Architectures=Architectures, zip=Code["ZipFile"], CodeSha256=sha(Code["ZipFile"]))

    def get_function_configuration(self, FunctionName):
        return self._cfg(self._need())

    def update_function_code(self, FunctionName, ZipFile, Architectures):
        f = self._need()
        f.update(zip=ZipFile, CodeSha256=sha(ZipFile), Architectures=Architectures)

    def update_function_configuration(self, FunctionName, **cfg):
        self._need().update(cfg)

    def publish_version(self, FunctionName, CodeSha256, Description):
        f = self._need()
        if CodeSha256 != f["CodeSha256"]:
            raise AwsError("PreconditionFailedException")
        v = str(len(self.w.versions) + 1)
        self.w.versions[v] = json.loads(json.dumps({k: f[k] for k in f if k != "zip"})) | {"zip": f["zip"], "Version": v}
        return {"Version": v}

    def list_versions_by_function(self, FunctionName, **_):
        self._need()
        return {"Versions": [{"Version": "$LATEST"}] + [{k: v[k] for k in v if k != "zip"} for v in self.w.versions.values()]}

    def get_alias(self, FunctionName, Name):
        self._need()
        if self.w.alias is None:
            raise AwsError("ResourceNotFoundException")
        return dict(self.w.alias)

    def create_alias(self, FunctionName, Name, FunctionVersion, Description):
        self.w.alias = {"Name": Name, "FunctionVersion": FunctionVersion, "Description": Description}

    def update_alias(self, FunctionName, Name, FunctionVersion, Description):
        self.w.alias = {"Name": Name, "FunctionVersion": FunctionVersion, "Description": Description}

    def delete_alias(self, FunctionName, Name):
        self.w.alias = None

    def delete_function(self, FunctionName):
        self.w.fn, self.w.versions = None, {}

    def invoke(self, FunctionName, Qualifier, Payload):
        version = self.w.versions[self.w.alias["FunctionVersion"]]
        event = json.loads(Payload)
        with tempfile.TemporaryDirectory() as d:
            zipfile.ZipFile(io.BytesIO(version["zip"])).extractall(d)
            out = io.StringIO()
            env = dict(version["Environment"]["Variables"], QA_TOOL_GUARD_SPEC=os.path.join(d, "qa_tool_guard_spec.json"))
            sys.path.insert(0, d)
            try:
                with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out):
                    sys.modules.pop("qa_tool_guard", None)
                    mod = importlib.import_module("qa_tool_guard")
                    result = mod.lambda_handler(event, None)
                    if self.w.lying == "allow-all":
                        result = {"decision": "allow", "reason": "A00: allowed"}
                    if self.w.lying == "print-event":
                        print(json.dumps(event))
            finally:
                sys.path.remove(d)
                sys.modules.pop("qa_tool_guard", None)
        if not self.w.drop_logs:
            self.w.log_lines += out.getvalue().splitlines()
        return {"Payload": io.BytesIO(json.dumps(result).encode())}


class Cw(Svc):
    WRITES = ("put_metric_alarm", "delete_alarms")

    def describe_alarms(self, AlarmNames):
        return {"MetricAlarms": [self.w.alarms[n] for n in AlarmNames if n in self.w.alarms]}

    def put_metric_alarm(self, **a):
        self.w.alarms[a["AlarmName"]] = dict(a)

    def delete_alarms(self, AlarmNames):
        for n in AlarmNames:
            self.w.alarms.pop(n, None)


class Control(Svc):
    def __init__(self, w):
        super().__init__(w)
        harness = Shape({"executionRoleArn": None} | ({"hooks": None} if w.hooks_in_model else {}))
        ops = {"GetHarness": types.SimpleNamespace(output_shape=Shape({"harness": harness})),
               "UpdateHarness": types.SimpleNamespace(input_shape=Shape({"hooks": None} if w.hooks_in_model else {}))}
        self.meta = types.SimpleNamespace(service_model=types.SimpleNamespace(operation_model=lambda n: ops[n]))

    def list_harnesses(self, **_):
        return {"harnesses": [{"harnessName": "UITestAgentHarness", "harnessId": "UITestAgentHarness-abc"}]}

    def get_harness(self, harnessId):
        return {"harness": {"executionRoleArn": self.w.roles["AgentCore-exec-role"]["Arn"], "hooks": self.w.harness_hooks}}


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.d = load_deploy()
        self.w = World()
        self.out = io.StringIO()

    def run_cmd(self, *args, world=None):
        w = world or self.w
        with contextlib.redirect_stdout(self.out):
            return self.d.main(list(args), session=w, sleep=lambda s: None)

    def writes_since(self, n):
        return self.w.writes[n:]

    # package
    def test_zip_is_deterministic_and_holds_only_the_package(self):
        a, b = self.d.build_zip(), self.d.build_zip()
        self.assertEqual(a, b)
        names = zipfile.ZipFile(io.BytesIO(a)).namelist()
        self.assertEqual(names, sorted(self.d.D["packageFiles"]))
        self.assertEqual(zipfile.ZipFile(io.BytesIO(a)).read("qa_tool_guard.py"), (HERE / "qa_tool_guard.py").read_bytes())

    def test_lambda_timeout_is_below_the_hook_timeout(self):
        hook = self.d.SPEC["hookConfig"][0]["beforeToolCall"]["target"]["lambda"]
        self.assertLess(self.d.D["timeoutSeconds"], hook["timeoutSeconds"])

    # documents
    def test_documents_are_least_privilege(self):
        self.assertEqual(self.d.lambda_trust()["Statement"], [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"},
                                                               "Action": "sts:AssumeRole"}])
        logs = self.d.lambda_logs_policy("us-east-1", ACCOUNT)["Statement"]
        self.assertEqual(logs, [{"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                                 "Resource": f"arn:aws:logs:us-east-1:{ACCOUNT}:log-group:/aws/lambda/qa-tool-guard:*"}])
        grant = self.d.invoke_grant("us-east-1", ACCOUNT)["Statement"]
        self.assertEqual(grant, [{"Sid": "InvokeQaToolGuard", "Effect": "Allow", "Action": "lambda:InvokeFunction",
                                  "Resource": f"arn:aws:lambda:us-east-1:{ACCOUNT}:function:qa-tool-guard:live"}])

    # plan / apply
    def test_plan_on_empty_account_writes_nothing(self):
        self.assertEqual(self.run_cmd("plan", "--origins", FIXTURE_ORIGINS), 4)
        self.assertEqual(self.w.writes, [])
        self.assertIn("create  function", self.out.getvalue())

    def test_apply_then_plan_is_clean_and_reapply_writes_nothing(self):
        self.assertEqual(self.run_cmd("apply", "--origins", FIXTURE_ORIGINS), 0)
        self.assertEqual(self.w.alias["FunctionVersion"], "1")
        self.assertEqual(self.w.roles["AgentCore-exec-role"]["policies"]["QaToolGuardInvoke"],
                         self.d.invoke_grant("us-east-1", ACCOUNT))
        self.assertEqual(self.w.groups["/aws/lambda/qa-tool-guard"]["retentionInDays"], 30)
        self.assertEqual(self.w.fn["Environment"], {"Variables": {"QA_ALLOWED_ORIGINS": FIXTURE_ORIGINS}})
        n = len(self.w.writes)
        self.assertEqual(self.run_cmd("plan", "--origins", FIXTURE_ORIGINS), 0)
        self.assertEqual(self.run_cmd("apply", "--origins", FIXTURE_ORIGINS), 0)
        self.assertEqual(self.writes_since(n), [])

    def test_apply_waits_out_role_propagation(self):
        self.w.role_unassumable_tries = 3
        self.assertEqual(self.run_cmd("apply", "--origins", FIXTURE_ORIGINS), 0)
        self.assertIsNotNone(self.w.fn)

    def test_origin_change_publishes_a_new_version_and_records_the_previous(self):
        self.run_cmd("apply", "--origins", FIXTURE_ORIGINS)
        self.assertEqual(self.run_cmd("plan", "--origins", REAL_LIKE_ORIGINS), 4)
        self.assertEqual(self.run_cmd("apply", "--origins", REAL_LIKE_ORIGINS), 0)
        self.assertEqual(self.w.alias, {"Name": "live", "FunctionVersion": "2", "Description": "previous=1"})
        self.assertEqual(self.w.versions["2"]["Environment"]["Variables"]["QA_ALLOWED_ORIGINS"], REAL_LIKE_ORIGINS)

    def test_code_change_publishes_a_new_version(self):
        self.run_cmd("apply", "--origins", FIXTURE_ORIGINS)
        original = self.d.build_zip
        self.d.build_zip = lambda root=HERE: original(root) + b""  # same bytes: no change expected
        self.assertEqual(self.run_cmd("plan", "--origins", FIXTURE_ORIGINS), 0)
        with tempfile.TemporaryDirectory() as tmp:
            for f in self.d.D["packageFiles"]:
                (pathlib.Path(tmp) / f).write_bytes((HERE / f).read_bytes())
            with open(pathlib.Path(tmp) / "qa_tool_guard.py", "a") as fh:
                fh.write("\n# changed\n")
            self.d.build_zip = lambda root=HERE: original(pathlib.Path(tmp))
            self.assertEqual(self.run_cmd("apply", "--origins", FIXTURE_ORIGINS), 0)
        self.assertEqual(self.w.alias["FunctionVersion"], "2")

    def test_empty_origins_refused_before_any_call(self):
        self.assertEqual(self.run_cmd("apply", "--origins", " , "), 7)
        self.assertEqual(self.w.writes + self.w.reads, [])

    def test_old_sdk_refused(self):
        w = World(hooks_in_model=False)
        self.assertEqual(self.run_cmd("apply", "--origins", FIXTURE_ORIGINS, world=w), 2)
        self.assertEqual(w.writes, [])

    # verify
    def test_verify_passes_against_the_uploaded_artifact(self):
        self.run_cmd("apply", "--origins", FIXTURE_ORIGINS)
        self.assertEqual(self.run_cmd("verify", "--origins", FIXTURE_ORIGINS), 0, self.out.getvalue())

    def test_verify_passes_with_real_origins(self):
        self.run_cmd("apply", "--origins", REAL_LIKE_ORIGINS)
        self.assertEqual(self.run_cmd("verify", "--origins", REAL_LIKE_ORIGINS), 0, self.out.getvalue())

    def test_verify_catches_a_guard_that_allows_everything(self):
        self.run_cmd("apply", "--origins", FIXTURE_ORIGINS)
        self.w.lying = "allow-all"
        self.assertEqual(self.run_cmd("verify", "--origins", FIXTURE_ORIGINS), 5)

    def test_verify_catches_the_password_in_logs(self):
        self.run_cmd("apply", "--origins", FIXTURE_ORIGINS)
        self.w.lying = "print-event"
        self.assertEqual(self.run_cmd("verify", "--origins", FIXTURE_ORIGINS), 5)
        self.assertIn("password marker appears", self.out.getvalue())
        self.assertNotIn(CASES["secretMarkers"][0], self.out.getvalue())

    def test_verify_does_not_call_missing_logs_clean(self):
        self.run_cmd("apply", "--origins", FIXTURE_ORIGINS)
        self.w.drop_logs = True
        self.assertEqual(self.run_cmd("verify", "--origins", FIXTURE_ORIGINS), 5)
        self.assertIn("never arrived", self.out.getvalue())

    def test_verify_reports_drift_without_invoking(self):
        self.run_cmd("apply", "--origins", FIXTURE_ORIGINS)
        del self.w.roles["AgentCore-exec-role"]["policies"]["QaToolGuardInvoke"]
        self.assertEqual(self.run_cmd("verify", "--origins", FIXTURE_ORIGINS), 5)
        self.assertNotIn(("Lambda", "invoke"), self.w.reads)

    def test_verify_reports_a_rule_it_cannot_replay(self):
        self.run_cmd("apply", "--origins", FIXTURE_ORIGINS)
        trimmed = dict(CASES, cases=[c for c in CASES["cases"] if c["expect"]["rule"] != "S01"])
        aws = self.d.Aws(self.w, "us-east-1", sleep=lambda s: None)
        with contextlib.redirect_stdout(io.StringIO()):
            problems = self.d.verify(aws, FIXTURE_ORIGINS, None, self.d.build_zip(), trimmed)
        self.assertEqual(problems, ["no replayable case for rule(s) S01"])

    # rollback / remove
    def test_rollback_moves_the_alias_back_and_forward(self):
        self.run_cmd("apply", "--origins", FIXTURE_ORIGINS)
        self.run_cmd("apply", "--origins", REAL_LIKE_ORIGINS)
        self.assertEqual(self.run_cmd("rollback"), 0)
        self.assertEqual(self.w.alias, {"Name": "live", "FunctionVersion": "1", "Description": "previous=2"})
        self.assertEqual(self.run_cmd("rollback"), 0)
        self.assertEqual(self.w.alias["FunctionVersion"], "2")
        self.assertEqual(self.run_cmd("rollback", "--to-version", "99"), 7)

    def test_rollback_without_history_is_refused(self):
        self.run_cmd("apply", "--origins", FIXTURE_ORIGINS)
        self.assertEqual(self.run_cmd("rollback"), 7)

    def test_remove_refused_while_a_hook_targets_the_guard(self):
        self.run_cmd("apply", "--origins", FIXTURE_ORIGINS)
        self.w.harness_hooks = [{"beforeToolCall": {"name": "qa_tool_guard", "target": {"lambda": {
            "arn": f"arn:aws:lambda:us-east-1:{ACCOUNT}:function:qa-tool-guard:live", "failureMode": "deny"}}}}]
        n = len(self.w.writes)
        self.assertEqual(self.run_cmd("remove"), 6)
        self.assertEqual(self.writes_since(n), [])

    def test_remove_tears_down_and_keeps_logs(self):
        self.run_cmd("apply", "--origins", FIXTURE_ORIGINS)
        self.w.harness_hooks = [{"beforeToolCall": {"name": "other", "target": {"lambda": {
            "arn": f"arn:aws:lambda:us-east-1:{ACCOUNT}:function:qa-tool-guard-other:live"}}}}]
        self.assertEqual(self.run_cmd("remove"), 0, self.out.getvalue())
        self.assertIsNone(self.w.fn)
        self.assertNotIn("QaToolGuardLambdaRole", self.w.roles)
        self.assertNotIn("QaToolGuardInvoke", self.w.roles["AgentCore-exec-role"]["policies"])
        self.assertEqual(self.w.alarms, {})
        self.assertIn("/aws/lambda/qa-tool-guard", self.w.groups)

    # output hygiene
    def test_output_never_prints_the_account_id(self):
        self.run_cmd("apply", "--origins", FIXTURE_ORIGINS)
        self.run_cmd("verify", "--origins", FIXTURE_ORIGINS)
        self.assertNotIn(ACCOUNT, self.out.getvalue())
        self.assertIn("<ACCOUNT_ID>", self.out.getvalue())


if __name__ == "__main__":
    unittest.main()
