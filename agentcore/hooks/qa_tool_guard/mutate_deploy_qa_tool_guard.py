"""Mutation check for deploy_qa_tool_guard.py: every mutant must turn test_deploy_qa_tool_guard red.
Fresh temp copy per mutant, bytecode off; a mutation text not found exactly once is an error."""
import os, pathlib, shutil, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
FILES = ["deploy_qa_tool_guard.py", "test_deploy_qa_tool_guard.py", "qa_tool_guard.py", "qa_tool_guard_spec.json",
         "qa_tool_guard_cases.json"]
M = {
    "grant on any function": ('"Action": "lambda:InvokeFunction", "Resource": alias_arn(region, account)}', '"Action": "lambda:InvokeFunction", "Resource": "*"}'),
    "trust widened": ('{"Service": "lambda.amazonaws.com"}', '{"Service": ["lambda.amazonaws.com", "ec2.amazonaws.com"]}'),
    "remove ignores live hooks": ("    if live:\n        raise Fail(6", "    if False:\n        raise Fail(6"),
    "hook match exact only": ('if arn == fn or arn.startswith(fn + ":"):', "if arn == fn:"),
    "old SDK accepted": ('return "hooks" in harness.members and "hooks" in sm.operation_model("UpdateHarness").input_shape.members', "return True"),
    "log arrival assumed": ("    arrived = False\n", "    arrived = True\n"),
    "marker check removed": ("filterPattern=f'\"{marker}\"').get(\"events\"):", "filterPattern=f'\"{marker}\"').get(\"events\") and False:"),
    "decision not compared": ('if got.get("decision") != c["expect"]["decision"] or', 'if False and'),
    "plan ignores code hash": ('drift = fn.get("CodeSha256") != code_sha256(zip_bytes) or', "drift ="),
    "plan ignores config": ("or any(fn.get(k) != v for k, v in want.items())", "or False"),
    "previous not recorded": ('Description=f"previous={previous}")', 'Description="previous=none")'),
    "rollback skips existence check": ('if target not in {v["Version"] for v in aws.versions()}:', "if False:"),
    "empty origins accepted": ('if a.command in ("plan", "apply", "verify") and not [o for o in a.origins.split(",") if o.strip()]:', "if False:"),
    "no redaction": ('    print(redact(msg))', '    print(msg)'),
    "no role propagation retry": ("for attempt in range(12):", "for attempt in range(1):"),
    "role deleted before its policy": ('        if aws.role_policy(D["lambdaRoleName"], "logs") is not None:\n            aws.iam.delete_role_policy(RoleName=D["lambdaRoleName"], PolicyName="logs")\n', ""),
    "retention not set": ('    if rows["log group"] != "same":\n        aws.logs.put_retention_policy', '    if False:\n        aws.logs.put_retention_policy'),
    "exec grant skipped on create": ('if rows[f"invoke grant on {name} execution role"] != "same":', 'if rows[f"invoke grant on {name} execution role"] == "update":'),
    "verify skips drift check": ("    if problems:\n        return problems\n", ""),
    "missing rule not reported": ("    if missing_rules:\n", "    if False:\n"),
}


def run(mut):
    d = pathlib.Path(tempfile.mkdtemp(prefix="dqg-mutant-"))
    try:
        for f in FILES:
            shutil.copyfile(HERE / f, d / f)
        if mut:
            old, new = mut
            p = d / "deploy_qa_tool_guard.py"; s = p.read_text()
            if s.count(old) != 1:
                raise SystemExit(f"mutation text found {s.count(old)} times: {old!r}")
            p.write_text(s.replace(old, new))
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, "-m", "unittest", "test_deploy_qa_tool_guard"], cwd=d, env=env,
                              capture_output=True, timeout=300).returncode
    finally:
        shutil.rmtree(d)


if __name__ == "__main__":
    if run(None) != 0:
        print("baseline is red"); sys.exit(2)
    survivors = [n for n, m in M.items() if run(m) == 0]
    print(f"baseline green; {len(M)} mutants; {len(M) - len(survivors)} killed, {len(survivors)} survived")
    for n in survivors:
        print("SURVIVED:", n)
    sys.exit(1 if survivors else 0)
