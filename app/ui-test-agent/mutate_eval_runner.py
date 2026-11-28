"""Mutation check for eval_runner.py: every mutant must turn test_eval_runner red.

Run from anywhere:  python3 -B mutate_eval_runner.py
Each mutant gets a fresh temp copy of eval_runner.py, test_eval_runner.py and the demo page the golden cases are
derived from (app/demo-frontend/index.html, in the same relative place), and the suite runs with -B and
PYTHONDONTWRITEBYTECODE=1, so no cached bytecode can stand in for the mutant. A mutation text that is not found
exactly once, a mutant that does not compile, a red baseline, or a run of 0 tests is an error (exit 2).
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
# (source, destination) relative to the repo root; the test reads the page two directories up from itself.
ROOT = HERE.parent.parent
FILES = [("app/ui-test-agent/eval_runner.py",) * 2, ("app/ui-test-agent/test_eval_runner.py",) * 2,
         ("app/demo-frontend/index.html",) * 2]
M = {
    "default 60 s read timeout": ("config=Config(read_timeout=READ_TIMEOUT_SECONDS))", "config=Config())"),
    "session ID not printed": ('f"session {session_id}" + ', '"" + '),
    "red reply not shown": ('        if status != "ok":\n            print(f"    reply ends:', '        if False:\n            print(f"    reply ends:'),
    "invoke_agent_runtime again": ("client.invoke_harness(**request)", "client.invoke_agent_runtime(**request)"),
    "expected_status not compared": ('    if verdict != case["expected_status"]:\n', "    if False:\n"),
    "zero cases pass": ('results["total"] > 0 and', 'results["total"] >= 0 and'),
    "exit code ignores failures": ('results["passed"] == results["total"] else 1', "True else 1"),
    "main always exits 0": ("    return exit_code(results)\n", "    return 0\n"),
    "qualifier dropped": ('        request["qualifier"] = qualifier\n', "        pass\n"),
    "maxTokens override sent": ('        "actorId": actor_id,\n', '        "actorId": actor_id,\n        "maxTokens": 4096,\n'),
    "skills override sent": ('        "actorId": actor_id,\n', '        "actorId": actor_id,\n        "skills": [],\n'),
    "verdict instruction dropped": (".replace(URL_PLACEHOLDER, target_url) + VERDICT_INSTRUCTION",
                                    ".replace(URL_PLACEHOLDER, target_url)"),
    "target URL not substituted": ('return case["prompt"].replace(URL_PLACEHOLDER, target_url) + VERDICT_INSTRUCTION',
                                   'return case["prompt"] + VERDICT_INSTRUCTION'),
    "target URL unchecked": ("    if not is_target_url(args.target_url):\n", "    if False:\n"),
    "any URL scheme accepted": ('parts.scheme in ("http", "https")', "bool(parts.scheme)"),
    "URL host not required": ("and bool(parts.hostname) and", "and"),
    "URL whitespace accepted": (" and not any(c.isspace() for c in url)", ""),
    "third-party default target": ('parser.add_argument("--target-url", required=True,',
                                   'parser.add_argument("--target-url", default="https://the-internet.herokuapp.com/login",'),
    "prompt hard-codes a host": ('"prompt": "Open {url}. Type admin in the Username field and password123',
                                 '"prompt": "Open https://the-internet.herokuapp.com/login. Type admin in the Username field and password123'),
    "BUG 2 case expects PASS": ('"expected_status": "FAIL",\n        "must_contain": ["green"],',
                                '"expected_status": "PASS",\n        "must_contain": ["green"],'),
    "BUG 4 case relabeled": ('"bugs": [4],', '"bugs": [5],'),
    "PASS case given a bug": ('"id": "GT-LOGIN",\n        "bugs": [],', '"id": "GT-LOGIN",\n        "bugs": [2],'),
    "BUG 1 dropped from the overlay case": ('"bugs": [1, 3],', '"bugs": [3],'),
    "overlay case asks about the button": ("Check that every part of the Password field takes a click: ",
                                           "Check that every part of the Login button takes a click: "),
    "citation off by one line": ('(18, ".error-message { color: green;")', '(19, ".error-message { color: green;")'),
    "runner names another page": ('TARGET_PAGE = "app/demo-frontend/index.html"', 'TARGET_PAGE = "docs/demo/index.html"'),
    "keyword not on the page": ('"must_contain": ["login successful"],', '"must_contain": ["logged in"],'),
    "one session for all cases": ("        session_id = str(uuid.uuid4())\n",
                                  '        session_id = "golden-" + actor_id + "-" + "0" * 20\n'),
    "actorId reused across runs": ("actor_id = ACTOR_PREFIX + uuid.uuid4().hex[:12]", 'actor_id = ACTOR_PREFIX + "shared"'),
    "stopReason ignored": ('    if reply["stop_reason"] != "end_turn":\n', "    if False:\n"),
    "missing messageStop read as end_turn": ("text, stop_reason, error = [], None, None",
                                             'text, stop_reason, error = [], "end_turn", None'),
    "stream error event ignored": ("            if name in event and error is None:\n", "            if False:\n"),
    "tool input read as reply": ('        if "text" in delta:\n', '        if "text" in delta or "toolUse" in delta:\n'
                                 '            delta = {"text": delta.get("text") or delta["toolUse"].get("input", "")}\n'),
    "text blocks joined without a break": ('                text.append("\\n")\n', "                pass\n"),
    "break only on an index change": ("        else:\n            run = None\n", ""),
    "verdict line start not anchored": ('r"^[ \\t>*_#`-]*VERDICT', 'r"VERDICT'),
    "verdict line end not anchored": ('(PASS|FAIL|BLOCKED|SKIPPED)[*_`.! \\t\\r]*$"', '(PASS|FAIL|BLOCKED|SKIPPED)"'),
    "first verdict wins": ("return found[-1].upper() if found else None", "return found[0].upper() if found else None"),
    "verdict case-sensitive": ("re.IGNORECASE | re.MULTILINE)", "re.MULTILINE)"),
    "evidence needs every keyword": ("    if not any(kw in lowered", "    if not all(kw in lowered"),
    "evidence check removed": ('    if not any(kw in lowered for kw in case["must_contain"]):\n', "    if False:\n"),
    "call error aborts the run": ("        except Exception as e:\n", "        except KeyError as e:\n"),
    "runtime ARN accepted": ("    if not HARNESS_ARN_RE.fullmatch(args.harness_arn):\n", "    if False:\n"),
    "qualifier format unchecked": ("    if args.qualifier is not None and not QUALIFIER_RE.fullmatch(args.qualifier):\n",
                                   "    if False:\n"),
}


def run(mut):
    """Return (returncode, tests ran) of the suite on a fresh copy, with `mut` applied to eval_runner.py."""
    d = pathlib.Path(tempfile.mkdtemp(prefix="eval-runner-mutant-"))
    try:
        for src, dst in FILES:
            (d / dst).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / src, d / dst)
        work = d / "app" / "ui-test-agent"
        if mut:
            old, new = mut
            p = work / "eval_runner.py"
            s = p.read_text()
            if s.count(old) != 1:
                print(f"error: mutation text found {s.count(old)} times: {old!r}", file=sys.stderr)
                raise SystemExit(2)
            s = s.replace(old, new)
            try:
                compile(s, str(p), "exec")  # a mutant that does not compile proves nothing
            except SyntaxError as e:
                print(f"error: mutant does not compile: {e}", file=sys.stderr)
                raise SystemExit(2)
            p.write_text(s)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, "-B", "-m", "unittest", "test_eval_runner"], cwd=work, env=env,
                           capture_output=True, text=True, timeout=300)
        m = re.search(r"^Ran (\d+) tests?", r.stderr, re.M)
        return r.returncode, int(m.group(1)) if m else 0
    finally:
        shutil.rmtree(d)


if __name__ == "__main__":
    if len(M) < 6:
        print(f"error: only {len(M)} mutants"); sys.exit(2)
    rc, baseline = run(None)
    if rc != 0 or baseline == 0:
        print(f"error: baseline is not green (rc {rc}, {baseline} tests ran)"); sys.exit(2)
    survivors = []
    for name, mut in M.items():
        rc, ran = run(mut)
        if rc == 0:
            survivors.append(name)
        print(f"{'killed  ' if rc else 'SURVIVED'} {name} (rc {rc}, {ran} tests ran)", flush=True)
    print(f"baseline green ({baseline} tests); {len(M)} mutants; {len(M) - len(survivors)} killed, "
          f"{len(survivors)} survived")
    sys.exit(1 if survivors else 0)
