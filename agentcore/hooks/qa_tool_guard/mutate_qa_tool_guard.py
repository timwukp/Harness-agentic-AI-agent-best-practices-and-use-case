"""Mutation check for qa_tool_guard: every mutant of the spec or the handler must turn the suite red.

Run from anywhere:  python3 mutate_qa_tool_guard.py
Each mutant runs in a fresh temporary copy of this directory with bytecode writing off, so no
cached .pyc or earlier mutant can serve the test. A source mutation whose text is not found
exactly once is an error, not a pass. Exit 0 only if the baseline is green and every mutant is killed.
"""
import copy
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
FILES = ["qa_tool_guard.py", "qa_tool_guard_spec.json", "qa_tool_guard_cases.json", "test_qa_tool_guard.py"]


def spec_mutant(fn):
    def apply(d):
        p = d / "qa_tool_guard_spec.json"
        s = json.loads(p.read_text())
        fn(s)
        p.write_text(json.dumps(s, indent=2))
    return apply


def source_mutant(old, new):
    def apply(d):
        p = d / "qa_tool_guard.py"
        src = p.read_text()
        if src.count(old) != 1:
            raise SystemExit(f"mutation text found {src.count(old)} times, expected 1: {old!r}")
        p.write_text(src.replace(old, new))
    return apply


def drop(key, word):
    return lambda s: s[key].remove(word)


SPEC_MUTANTS = {f"drop forbidden control {w}": spec_mutant(drop("forbiddenControls", w)) for w in
                json.loads((HERE / "qa_tool_guard_spec.json").read_text())["forbiddenControls"]}
SPEC_MUTANTS.update({
    "drop danger style": spec_mutant(drop("dangerousStyles", "danger")),
    "denyOnTruncation false": spec_mutant(lambda s: s.update(denyOnTruncation=False)),
    "hookConfig failureMode allow": spec_mutant(lambda s: s["hookConfig"][0]["beforeToolCall"]["target"]["lambda"].update(failureMode="allow")),
    "failureMode allow": spec_mutant(lambda s: s.update(failureMode="allow")),
    "decisionOnError allow": spec_mutant(lambda s: s.update(decisionOnError="allow")),
    "hookConfig adds afterToolCall": spec_mutant(lambda s: s["hookConfig"].append({"afterToolCall": copy.deepcopy(s["hookConfig"][0]["beforeToolCall"])})),
    "origin env renamed": spec_mutant(lambda s: s["origins"].update(env="QA_ORIGINS_UNSET")),
    "about:blank dropped": spec_mutant(lambda s: s["origins"].update(alwaysAllowedNavigations=[])),
    "strict pattern never matches": spec_mutant(lambda s: s.update(strictSessionIdPattern="$^")),
    "strict pattern unanchored": spec_mutant(lambda s: s.update(strictSessionIdPattern="-admin")),
    "write becomes read-only": spec_mutant(lambda s: s["tools"]["readOnlyTools"].append("write")),
    "Delete key allowed": spec_mutant(lambda s: s["tools"]["browser"]["allowedKeys"].append("Delete")),
    "Runtime.evaluate read-only": spec_mutant(lambda s: s["tools"]["browser"]["cdpReadOnlyMethods"].append("Runtime.evaluate")),
    "set_cookies allowed": spec_mutant(lambda s: s["tools"]["browser"]["allowedActions"].append("set_cookies")),
    "admin may evaluate": spec_mutant(lambda s: s["tools"]["browser"]["strictAllowedActions"].append("evaluate")),
    "amazonaws suffix without dot": spec_mutant(lambda s: s.update(shellAllowedHostSuffixes=["amazonaws.com"])),
    "file_operations str_replace allowed": spec_mutant(lambda s: s["tools"]["file_operations"]["allowedCommands"].append("str_replace")),
    "nonGet loses sendBeacon": spec_mutant(lambda s: s["patterns"].update(nonGet=s["patterns"]["nonGet"].replace("|sendBeacon", ""))),
    "nonGet loses requestSubmit": spec_mutant(lambda s: s["patterns"].update(nonGet=s["patterns"]["nonGet"].replace("submit|requestSubmit", "submit"))),
    "shell body upload pattern empty": spec_mutant(lambda s: s["patterns"].update(shellBodyUpload="(?!)")),
    "credentialField loses word boundary": spec_mutant(lambda s: s["patterns"].update(credentialField="e-?mail|password|user")),
    "file_operations sunset moved": spec_mutant(lambda s: s["tools"]["file_operations"].update(removeAfter="2027-06-01T00:00:00Z")),
    "w3.org ignore dropped": spec_mutant(lambda s: s["origins"].update(scriptUrlIgnorePrefixes=[])),
})

SOURCE_MUTANTS = {
    "origin rule removed": source_mutant('if origin_of(url) not in origins:\n        raise Deny("B05")', "pass"),
    "userinfo check removed": source_mutant(" or parts.username is not None or parts.password is not None", ""),
    "sign-in exemption on click removed": source_mutant("if WRITE_CONTROL.search(target) and not SIGN_IN.search(target):", "if WRITE_CONTROL.search(target):"),
    "sign-in stripped from script removed": source_mutant("WRITE_CONTROL.search(SIGN_IN.sub(\" \", script))", "WRITE_CONTROL.search(script)"),
    "script click check removed": source_mutant("(SCRIPT_CLICK.search(script) and WRITE_CONTROL.search(SIGN_IN.sub(\" \", script)))", "False"),
    "script origin check removed": source_mutant('if any(origin_of(u) not in origins for u in script_urls(script)):\n            raise Deny("B08")', "pass"),
    "truncation check removed": source_mutant("if SPEC[\"denyOnTruncation\"] and is_truncated(ctx):", "if False:"),
    "nested truncation not searched": source_mutant(' or any(is_truncated(v) for v in value.values())', ""),
    "strict never on": source_mutant('strict = bool(STRICT_SESSION.search(str(event.get("sessionId") or "")))', "strict = False"),
    "admin click rule removed": source_mutant('if strict and not SIGN_IN.search(target):\n            raise Deny("B03")', "pass"),
    "admin type rule removed": source_mutant('raise Deny("B04")', "pass"),
    "shell off-list host allowed": source_mutant('        raise Deny("S02")', "        continue"),
    "shell host suffix check removed": source_mutant(' and host.endswith(tuple(SPEC["shellAllowedHostSuffixes"]))', ""),
    "unknown tool allowed": source_mutant('    else:\n        raise Deny("G03")', '    else:\n        return "A00", None'),
    "wrong event allowed": source_mutant('if event.get("event") != SPEC["event"]:', "if False:"),
    "error allows": source_mutant('rule = "G09"', 'rule = "A00"'),
    "log carries the event": source_mutant('print(json.dumps({k: record[k] for k in SPEC["logging"]["fields"]}))', "print(json.dumps(event, default=str))"),
    "reason echoes input": source_mutant('"reason": f"{rule}: {RULES[rule]}"', '"reason": f"{rule}: {RULES[rule]} {json.dumps(event, default=str)}"'),
    "url field not checked": source_mutant('if "url" in action:', "if False:"),
}


def run_suite(d):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("QA_TOOL_GUARD_SPEC", None)
    r = subprocess.run([sys.executable, "-m", "unittest", "test_qa_tool_guard"], cwd=d, env=env,
                       capture_output=True, text=True, timeout=120)
    return r.returncode


def in_copy(apply):
    d = pathlib.Path(tempfile.mkdtemp(prefix="qtg-mutant-"))
    try:
        for f in FILES:
            shutil.copyfile(HERE / f, d / f)
        if apply:
            apply(d)
        return run_suite(d)
    finally:
        shutil.rmtree(d)


def main():
    if in_copy(None) != 0:
        print("baseline is red; fix it before mutating")
        return 2
    mutants = {**SPEC_MUTANTS, **SOURCE_MUTANTS}
    survivors = [name for name, apply in mutants.items() if in_copy(apply) == 0]
    print(f"baseline green; {len(mutants)} mutants ({len(SPEC_MUTANTS)} spec, {len(SOURCE_MUTANTS)} source); "
          f"{len(mutants) - len(survivors)} killed, {len(survivors)} survived")
    for name in survivors:
        print("SURVIVED:", name)
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
