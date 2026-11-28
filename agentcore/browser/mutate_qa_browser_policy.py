"""Mutation check for the QA browser policy builder: every mutant must turn test_qa_browser_policy red.
Fresh temp copy per mutant, bytecode off; a mutation text not found exactly once is an error."""
import json, os, pathlib, shutil, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
FILES = ["build_qa_browser_policy.py", "qa_browser_policy_spec.json", "test_qa_browser_policy.py",
         "fixtures/synthetic-viewer-run.json"]


def src(old, new):
    def apply(d):
        p = d / "build_qa_browser_policy.py"; s = p.read_text()
        if s.count(old) != 1:
            raise SystemExit(f"mutation text found {s.count(old)} times: {old!r}")
        p.write_text(s.replace(old, new))
    return apply


def spec(fn):
    def apply(d):
        p = d / "qa_browser_policy_spec.json"; s = json.loads(p.read_text()); fn(s); p.write_text(json.dumps(s))
    return apply


MUTANTS = {
    "blocklist emptied": spec(lambda s: s["managedPolicy"].update(URLBlocklist=[])),
    "password manager on": spec(lambda s: s["managedPolicy"].update(PasswordManagerEnabled=True)),
    "recording on": spec(lambda s: s["recording"].update(enabled=True)),
    "cognito role dropped": spec(lambda s: s["originRoles"].pop("cognito")),
    "data scheme not ignored": spec(lambda s: s["ignoredRequestSchemes"].remove("data")),
    "http accepted": src('if parts.scheme != "https"', 'if parts.scheme not in ("https", "http")'),
    "userinfo accepted": src(" or parts.username is not None or parts.password is not None", ""),
    "default port kept": src('(f":{port}" if port and port != 443 else "")', '(f":{port}" if port else "")'),
    "region unchecked": src('if not REGION.match(str(region)):', 'if False:'),
    "deploy gate ignores synthetic flag": src('if a.for_deploy and not recorded:', 'if a.for_deploy and not a.fixture:'),
    "unlisted origins not enforced": src("    if missing:\n", "    if False:\n"),
    "empty fixture accepted": src('    if not urls:\n        raise ValueError', '    if False:\n        raise ValueError'),
    "hash not canonical": src('sort_keys=True, separators=(",", ":")', 'separators=(",", ":")'),
}


def run(apply):
    d = pathlib.Path(tempfile.mkdtemp(prefix="qbp-mutant-"))
    try:
        for f in FILES:
            (d / f).parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(HERE / f, d / f)
        if apply:
            apply(d)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, "-m", "unittest", "test_qa_browser_policy"], cwd=d, env=env,
                              capture_output=True, timeout=120).returncode
    finally:
        shutil.rmtree(d)


if __name__ == "__main__":
    if run(None) != 0:
        print("baseline is red"); sys.exit(2)
    survivors = [n for n, a in MUTANTS.items() if run(a) == 0]
    print(f"baseline green; {len(MUTANTS)} mutants; {len(MUTANTS) - len(survivors)} killed, {len(survivors)} survived")
    for n in survivors:
        print("SURVIVED:", n)
    sys.exit(1 if survivors else 0)
