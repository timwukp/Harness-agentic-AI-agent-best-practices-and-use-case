"""Offline tests for eval_runner.py, the golden-test runner for the UI Test Agent harness.

Run from this directory:  python3 -B -m unittest -v test_eval_runner
Stdlib only; boto3 is not needed. The golden cases are checked against the page they describe,
app/demo-frontend/index.html (two directories up from here), line by line. The AWS double is a fake `boto3` module (FAKE_BOTO3 below). It checks each
request against the request members of the botocore 1.43.120 model, the way botocore's parameter validation does,
so a wrong operation or a wrong member name fails here as it would against the real client. It replays scripted
InvokeHarness event streams in the botocore dict form.

The CLI tests run the script as a subprocess (`python -B eval_runner.py ...`) with the fake on PYTHONPATH, so
the exit codes asserted are the ones a shell or CI job would see.
"""
import contextlib
import importlib
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "eval_runner.py"
ARN = "arn:aws:bedrock-agentcore:us-east-1:111122223333:harness/UITestAgentHarness-abcde12345"
RUNTIME_ARN = "arn:aws:bedrock-agentcore:us-east-1:111122223333:runtime/harness_UITestAgentHarness-abcde12345"
# Placeholder hosts (.test is reserved): the runner takes the demo page's URL as a parameter.
URL = "https://demo.example.test/demo/index.html"
OTHER_URL = "http://qa-demo.internal.example.test:8080/index.html"

# Request members in botocore 1.43.120, data/bedrock-agentcore/2024-02-28/service-2.json.gz.
MODELS = {
    "InvokeHarness": {
        "members": ["harnessArn", "qualifier", "runtimeSessionId", "runtimeUserId", "traceParent", "traceState",
                    "traceId", "baggage", "messages", "model", "systemPrompt", "tools", "skills", "allowedTools",
                    "maxIterations", "maxTokens", "timeoutSeconds", "actorId"],
        "required": ["harnessArn", "runtimeSessionId", "messages"],
    },
    "InvokeAgentRuntime": {
        "members": ["contentType", "accept", "mcpSessionId", "runtimeSessionId", "mcpProtocolVersion", "mcpMethod",
                    "mcpName", "runtimeUserId", "traceId", "traceParent", "traceState", "baggage", "agentRuntimeArn",
                    "qualifier", "accountId", "payload"],
        "required": ["agentRuntimeArn", "payload"],
    },
}
# InvokeHarness members that replace the harness version's own configuration for one call.
OVERRIDE_FIELDS = {"model", "systemPrompt", "tools", "skills", "allowedTools", "maxTokens", "maxIterations",
                   "timeoutSeconds"}

FAKE_BOTO3 = r'''
"""Fake boto3 for test_eval_runner. State lives in $FAKE_BOTO3_STATE: scenario.json in, calls.jsonl out."""
import json
import os
import pathlib


class ParamValidationError(Exception):
    pass


class ClientError(Exception):
    pass


def _state():
    d = pathlib.Path(os.environ["FAKE_BOTO3_STATE"])
    return d, json.loads((d / "scenario.json").read_text())


def _record(entry):
    d, _ = _state()
    with open(d / "calls.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


def _validate(op, kw):
    _, sc = _state()
    model = sc["models"][op]
    unknown = sorted(set(kw) - set(model["members"]))
    missing = sorted(set(model["required"]) - set(kw))
    if unknown or missing:
        raise ParamValidationError(f"{op}: unknown parameters {unknown}, missing required {missing}")


def _validate_messages(messages):
    if not isinstance(messages, list) or not messages:
        raise ParamValidationError("messages must be a non-empty list")
    for m in messages:
        if set(m) != {"role", "content"} or m["role"] not in ("user", "assistant"):
            raise ParamValidationError(f"bad HarnessMessage {sorted(m)}")
        for block in m["content"]:
            keys = set(block)
            if len(keys) != 1 or not keys <= {"text", "toolUse", "toolResult", "reasoningContent"}:
                raise ParamValidationError(f"HarnessContentBlock is a union, got {sorted(keys)}")
            if "text" in block and (not isinstance(block["text"], str) or not block["text"]):
                raise ParamValidationError("text must be a non-empty string")


def _events(reply):
    for ev in reply.get("events", []):
        if ev == "RAISE":
            raise ClientError("EventStreamError: connection reset mid-stream")
        yield ev


class _Client:
    def __init__(self, region):
        self.region = region

    def invoke_agent_runtime(self, **kw):
        _record({"op": "invoke_agent_runtime", "keys": sorted(kw)})
        _validate("InvokeAgentRuntime", kw)
        raise ClientError("ValidationException: agentRuntimeArn is not an agent runtime")

    def invoke_harness(self, **kw):
        _record({"op": "invoke_harness", "kwargs": kw})
        _validate("InvokeHarness", kw)
        sid = kw["runtimeSessionId"]
        if not isinstance(sid, str) or not 33 <= len(sid) <= 100:
            raise ParamValidationError("runtimeSessionId length must be 33..100")
        _validate_messages(kw["messages"])
        _, sc = _state()
        text = kw["messages"][0]["content"][0]["text"]
        hits = [r for key, r in sc["replies"].items() if key in text]
        if len(hits) != 1:
            raise AssertionError(f"{len(hits)} scripted replies match this prompt")
        if "raise" in hits[0]:
            raise ClientError(hits[0]["raise"])
        return {"stream": _events(hits[0])}


def client(service_name, region_name=None, config=None, **kw):
    _record({"op": "client", "service": service_name, "region": region_name,
             "read_timeout": getattr(config, "read_timeout", None)})
    return _Client(region_name)
'''

FAKE_BOTOCORE_CONFIG = r'''
class Config:
    def __init__(self, **kw):
        self.__dict__.update(kw)
'''


def load():
    sys.path.insert(0, str(HERE))
    try:
        import eval_runner
        return importlib.reload(eval_runner)
    finally:
        sys.path.remove(str(HERE))


ER = load()
# The page the golden cases describe. eval_runner.TARGET_PAGE must name the same file.
TARGET_PAGE = "app/demo-frontend/index.html"
PAGE = HERE.parent.parent / TARGET_PAGE
PAGE_LINES = PAGE.read_text().splitlines()
N = len(ER.GOLDEN_TESTS)


def events(text, stop="end_turn", noise=True):
    """One InvokeHarness stream: tool-call noise, then the reply, then messageStop and metadata.

    `text` is one text block, or a list of blocks. Each block arrives as two deltas.
    """
    evs = [{"messageStart": {"role": "assistant"}}]
    if noise:
        # Tool input and reasoning that carry a well-formed verdict line, which must not be read as the reply.
        evs += [
            {"contentBlockStart": {"contentBlockIndex": 0,
                                   "start": {"toolUse": {"toolUseId": "tooluse_s001", "name": "browser"}}}},
            {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"toolUse": {"input": "\nVERDICT: PASS\n"}}}},
            {"contentBlockStop": {"contentBlockIndex": 0}},
            {"hookEvent": {"hookEventId": "00000000-0000-4000-9000-e00000000001", "name": "qa_tool_guard",
                           "type": "before_tool_call", "decision": "allow", "reason": "A00: rule text"}},
            {"contentBlockDelta": {"contentBlockIndex": 1,
                                   "delta": {"reasoningContent": {"text": "\nVERDICT: PASS\n"}}}},
        ]
    for index, block in enumerate([text] if isinstance(text, str) else text, start=2):
        half = len(block) // 2
        for chunk in (block[:half], block[half:]):
            if chunk:
                evs.append({"contentBlockDelta": {"contentBlockIndex": index, "delta": {"text": chunk}}})
        evs.append({"contentBlockStop": {"contentBlockIndex": index}})
    if stop:
        evs.append({"messageStop": {"stopReason": stop}})
    evs.append({"metadata": {"usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                             "metrics": {"latencyMs": 1}}})
    return evs


def good_text(case):
    return f"Checked the page. Evidence: {case['must_contain'][0]}.\nVERDICT: {case['expected_status']}"


def scenario(overrides=None, url=URL):
    """Every golden case answers correctly unless `overrides` maps its id to another reply."""
    overrides = overrides or {}
    replies = {}
    for case in ER.GOLDEN_TESTS:
        replies[case["prompt"].replace("{url}", url)] = overrides.get(case["id"], {"events": events(good_text(case))})
    return {"models": MODELS, "replies": replies}


class Fake:
    """The fake boto3 module plus its state directory."""

    def __init__(self, sc):
        self.tmp = tempfile.TemporaryDirectory(prefix="eval-runner-test-")
        self.dir = pathlib.Path(self.tmp.name)
        (self.dir / "scenario.json").write_text(json.dumps(sc))
        (self.dir / "pkg").mkdir()
        (self.dir / "pkg" / "boto3.py").write_text(FAKE_BOTO3)
        (self.dir / "pkg" / "botocore").mkdir()
        (self.dir / "pkg" / "botocore" / "__init__.py").write_text("")
        (self.dir / "pkg" / "botocore" / "config.py").write_text(FAKE_BOTOCORE_CONFIG)

    def calls(self, op=None):
        p = self.dir / "calls.jsonl"
        rows = [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []
        return [r for r in rows if op is None or r["op"] == op]

    def modules(self):
        boto3 = types.ModuleType("boto3")
        exec(compile(FAKE_BOTO3, "fake_boto3", "exec"), boto3.__dict__)
        config = types.ModuleType("botocore.config")
        exec(compile(FAKE_BOTOCORE_CONFIG, "fake_botocore_config", "exec"), config.__dict__)
        botocore = types.ModuleType("botocore")
        botocore.config = config
        return {"boto3": boto3, "botocore": botocore, "botocore.config": config}

    def close(self):
        self.tmp.cleanup()


@contextlib.contextmanager
def faked(sc):
    fake = Fake(sc)
    try:
        with mock.patch.dict(os.environ, {"FAKE_BOTO3_STATE": str(fake.dir)}), \
                mock.patch.dict(sys.modules, fake.modules()), \
                contextlib.redirect_stdout(io.StringIO()):
            yield fake
    finally:
        fake.close()


def run(overrides=None, url=URL, **kw):
    """run_golden_tests against the fake; returns (results, fake calls)."""
    with faked(scenario(overrides, url)) as fake:
        results = ER.run_golden_tests(ARN, url, **kw)
        return results, fake.calls()


def detail(results, case_id):
    return next(d for d in results["details"] if d["id"] == case_id)


def case(case_id):
    return next(c for c in ER.GOLDEN_TESTS if c["id"] == case_id)


# Page BUG markers that are one rendered defect, so they must share one case, and only they may.
# BUG 1 and BUG 3, measured in a browser at 1280x800 on 2026-11-28: the overlay covers the lower-left of the
# Password field (8 of 81 sampled points) and misses the Login button by 5.0 px (81 of 81 points hit the button).
SHARED_MARKERS = {frozenset({1, 3})}


def page_markers():
    return sorted({int(n) for n in re.findall(r"BUG (\d+):", PAGE.read_text())})


def marker_map_problems(cases, markers):
    """How the cases fail to map the page's BUG markers one to one ([] when each marker maps to exactly one case)."""
    problems = []
    for m in markers:
        owners = [c["id"] for c in cases if m in c["bugs"]]
        if len(owners) != 1:
            problems.append(f"BUG {m} maps to {len(owners)} cases {owners}")
    for c in cases:
        if len(set(c["bugs"])) != len(c["bugs"]):
            problems.append(f"{c['id']} names a BUG twice")
        if set(c["bugs"]) - set(markers):
            problems.append(f"{c['id']} names BUG {sorted(set(c['bugs']) - set(markers))}, not on the page")
        if len(set(c["bugs"])) > 1 and frozenset(c["bugs"]) not in SHARED_MARKERS:
            problems.append(f"{c['id']} counts BUG {sorted(c['bugs'])} as one defect")
    for group in SHARED_MARKERS:
        owners = sorted({c["id"] for c in cases for m in group if m in c["bugs"]})
        if len(owners) > 1:
            problems.append(f"BUG {sorted(group)} are one defect but map to {owners}")
    return problems


class GoldenCases(unittest.TestCase):
    """The golden set is derived from app/demo-frontend/index.html, and must stay in step with it."""

    def test_runner_names_the_same_page(self):
        self.assertEqual(ER.TARGET_PAGE, TARGET_PAGE)

    def test_five_cases_one_pass_four_fail(self):
        self.assertEqual([c["id"] for c in ER.GOLDEN_TESTS],
                         ["GT-LOGIN", "GT-OVERLAY", "GT-BUG2", "GT-BUG4", "GT-BUG5"])
        self.assertEqual(sorted(c["expected_status"] for c in ER.GOLDEN_TESTS), ["FAIL"] * 4 + ["PASS"])

    def test_each_bug_marker_maps_to_exactly_one_case(self):
        self.assertEqual(page_markers(), [1, 2, 3, 4, 5])
        self.assertEqual(marker_map_problems(ER.GOLDEN_TESTS, page_markers()), [])

    def test_the_map_rule_catches_each_problem(self):
        def c(i, *bugs):
            return {"id": i, "bugs": list(bugs)}
        ok = [c("L"), c("O", 1, 3), c("B2", 2), c("B4", 4), c("B5", 5)]
        self.assertEqual(marker_map_problems(ok, [1, 2, 3, 4, 5]), [])
        # Each bad set breaks exactly one rule, so dropping any one check from marker_map_problems turns this red.
        bad = {
            "maps to 0 cases": [c("L"), c("O", 1, 3), c("B2", 2), c("B4", 4)],
            "maps to 2 cases": ok + [c("X", 5)],
            "as one defect": [c("L"), c("O", 1, 3), c("B24", 2, 4), c("B5", 5)],
            "are one defect but map to": [c("L"), c("B1", 1), c("B3", 3), c("B2", 2), c("B4", 4), c("B5", 5)],
            "not on the page": ok + [c("X", 6)],
            "names a BUG twice": [c("L"), c("O", 1, 3, 3), c("B2", 2), c("B4", 4), c("B5", 5)],
        }
        for why, cases in bad.items():
            problems = marker_map_problems(cases, [1, 2, 3, 4, 5])
            self.assertEqual(len(problems), 1, (why, problems))
            self.assertIn(why, problems[0])

    def test_expected_verdict_follows_from_the_bugs(self):
        for c in ER.GOLDEN_TESTS:
            self.assertEqual(c["expected_status"], "FAIL" if c["bugs"] else "PASS", c["id"])

    def test_every_citation_matches_its_line_in_the_page(self):
        for c in ER.GOLDEN_TESTS:
            self.assertTrue(c["source"], c["id"])
            for line, text in c["source"]:
                self.assertIn(text, PAGE_LINES[line - 1], f"{c['id']} cites {TARGET_PAGE}:{line}")

    def test_each_fail_case_cites_its_bug_markers(self):
        for c in ER.GOLDEN_TESTS:
            cited = [PAGE_LINES[line - 1] for line, _ in c["source"]]
            for n in c["bugs"]:
                self.assertTrue(any(f"BUG {n}:" in t for t in cited), f"{c['id']} BUG {n}")

    def test_keywords_come_from_the_page(self):
        page = PAGE.read_text().lower()
        for c in ER.GOLDEN_TESTS:
            self.assertTrue(c["must_contain"], c["id"])
            for k in c["must_contain"]:
                # The evidence check lower-cases the reply, so a keyword with a capital could never match.
                self.assertEqual(k, k.lower(), c["id"])
                self.assertIn(k, page, c["id"])

    def test_prompts_name_no_host_of_their_own(self):
        for c in ER.GOLDEN_TESTS:
            self.assertEqual(c["prompt"].count("{url}"), 1, c["id"])
            self.assertNotRegex(c["prompt"], r"https?://|www\.|herokuapp", c["id"])

    def test_overlay_case_asks_about_the_password_field_not_the_button(self):
        # Rendered, the overlay misses the button; a case about the button would score a correct PASS as wrong.
        prompt = case("GT-OVERLAY")["prompt"]
        self.assertIn("Password field", prompt)
        self.assertNotIn("button", prompt.lower())


class Request(unittest.TestCase):
    def test_calls_invoke_harness_never_invoke_agent_runtime(self):
        _, calls = run(region="us-west-2")
        self.assertEqual([c["op"] for c in calls], ["client"] + ["invoke_harness"] * N,
                         [c.get("op") for c in calls])
        self.assertEqual((calls[0]["service"], calls[0]["region"]), ("bedrock-agentcore", "us-west-2"))

    def test_client_read_timeout_outlasts_an_agent_turn(self):
        # botocore's default is 60 s; the repo raised it to 900 s for harness turns (AGENTS.md 3.15).
        _, calls = run()
        self.assertGreaterEqual(calls[0]["read_timeout"] or 0, 900)

    def test_request_carries_only_arn_session_actor_and_prompt(self):
        _, calls = run()
        sessions = set()
        for c, golden in zip(calls[1:], ER.GOLDEN_TESTS):
            kw = c["kwargs"]
            self.assertEqual(set(kw), {"harnessArn", "runtimeSessionId", "actorId", "messages"})
            self.assertEqual(kw["harnessArn"], ARN)
            self.assertEqual(len(kw["messages"]), 1)
            self.assertEqual(kw["messages"][0]["role"], "user")
            self.assertEqual(kw["messages"][0]["content"],
                             [{"text": golden["prompt"].replace("{url}", URL) + ER.VERDICT_INSTRUCTION}])
            self.assertRegex(kw["runtimeSessionId"], r"^[a-zA-Z0-9][a-zA-Z0-9-_]{32,99}$")
            sessions.add(kw["runtimeSessionId"])
        self.assertEqual(len(sessions), N, "each case needs its own session")

    def test_target_url_reaches_every_prompt(self):
        for url in (URL, OTHER_URL):
            _, calls = run(url=url)
            texts = [c["kwargs"]["messages"][0]["content"][0]["text"] for c in calls[1:]]
            self.assertEqual(len(texts), N)
            for text in texts:
                self.assertEqual(text.count(url), 1, text)
                self.assertNotIn("{url}", text)

    def test_never_sends_a_per_call_override(self):
        for qualifier in (None, "canary"):
            _, calls = run(qualifier=qualifier)
            for c in calls[1:]:
                self.assertEqual(set(c["kwargs"]) & OVERRIDE_FIELDS, set(), qualifier)
                self.assertTrue(set(c["kwargs"]) <= set(MODELS["InvokeHarness"]["members"]))

    def test_qualifier_is_forwarded_only_when_given(self):
        _, calls = run(qualifier="canary")
        self.assertEqual([c["kwargs"].get("qualifier") for c in calls[1:]], ["canary"] * N)
        _, calls = run()
        self.assertFalse(any("qualifier" in c["kwargs"] for c in calls[1:]))

    def test_actor_id_is_fresh_per_run_and_shared_within_it(self):
        _, first = run()
        _, second = run()
        a = {c["kwargs"]["actorId"] for c in first[1:]}
        b = {c["kwargs"]["actorId"] for c in second[1:]}
        self.assertEqual(len(a), 1)
        self.assertEqual(len(b), 1)
        self.assertNotEqual(a, b, "a reused actorId lets Memory recall an earlier run's verdicts")
        self.assertTrue(next(iter(a)).startswith("golden-eval-"))


class Verdicts(unittest.TestCase):
    def assertOnly(self, results, case_id, status):
        self.assertEqual(detail(results, case_id)["status"], status, detail(results, case_id))
        others = [d for d in results["details"] if d["id"] != case_id]
        self.assertEqual([d["status"] for d in others], ["ok"] * (N - 1), others)
        self.assertEqual((results["total"], results["passed"], results["failed"]), (N, N - 1, 1))
        self.assertEqual(ER.exit_code(results), 1)

    def test_all_verdicts_match(self):
        results, _ = run()
        self.assertEqual((results["total"], results["passed"], results["failed"]), (N, N, 0), results["details"])
        self.assertEqual(ER.exit_code(results), 0)

    def test_wrong_verdict_with_the_evidence_keyword_still_fails(self):
        # GT-BUG2 expects FAIL. The reply names the green text, so the old keyword check passed it.
        results, _ = run({"GT-BUG2": {"events": events("The error text is green.\nVERDICT: PASS")}})
        self.assertOnly(results, "GT-BUG2", "MISMATCH")
        self.assertEqual(detail(results, "GT-BUG2")["verdict"], "PASS")

    def test_last_verdict_line_wins(self):
        results, _ = run({"GT-LOGIN": {"events": events("Draft:\nVERDICT: FAIL\nThen it showed 'Login successful! "
                                                        "Welcome, admin'.\nVERDICT: PASS")}})
        self.assertEqual(ER.exit_code(results), 0, results["details"])
        results, _ = run({"GT-LOGIN": {"events": events("Draft:\nVERDICT: PASS\nNo login successful message.\n"
                                                        "VERDICT: FAIL")}})
        self.assertOnly(results, "GT-LOGIN", "MISMATCH")

    def test_restated_options_are_not_a_verdict(self):
        # GT-LOGIN expects PASS. Read as a verdict, this line would pass it.
        results, _ = run({"GT-LOGIN": {"events": events("Login successful! Welcome, admin\n"
                                                        "VERDICT: PASS or VERDICT: FAIL")}})
        self.assertOnly(results, "GT-LOGIN", "ERROR")

    def test_echoed_instruction_is_not_a_verdict(self):
        # GT-BUG5 expects FAIL. The instruction's last words are "VERDICT: FAIL, with nothing else on that line."
        results, _ = run({"GT-BUG5": {"events": events("It said Internal server error.\n"
                                                       + ER.VERDICT_INSTRUCTION.strip())}})
        self.assertOnly(results, "GT-BUG5", "ERROR")
        results, _ = run({"GT-BUG5": {"events": events("It said Internal server error. VERDICT: FAIL")}})
        self.assertOnly(results, "GT-BUG5", "ERROR")

    def test_verdict_in_its_own_block_is_a_line(self):
        results, _ = run({"GT-BUG2": {"events": events(["The error text is green, rgb(0, 128, 0).", "VERDICT: FAIL"])}})
        self.assertEqual(ER.exit_code(results), 0, results["details"])

    def test_text_after_a_tool_call_starts_a_new_line(self):
        # Block indexes can restart in a new message, so a tool call between two text deltas also breaks the line.
        evs = events("The error text is green.", noise=False)
        stop = next(i for i, e in enumerate(evs) if "messageStop" in e)
        evs[stop:stop] = [
            {"contentBlockStart": {"contentBlockIndex": 3,
                                   "start": {"toolUse": {"toolUseId": "tooluse_s002", "name": "browser"}}}},
            {"contentBlockStop": {"contentBlockIndex": 3}},
            {"contentBlockDelta": {"contentBlockIndex": 2, "delta": {"text": "VERDICT: FAIL"}}},
        ]
        results, _ = run({"GT-BUG2": {"events": evs}})
        self.assertEqual(ER.exit_code(results), 0, results["details"])

    def test_verdict_is_read_case_insensitively_through_markdown(self):
        results, _ = run({"GT-BUG4": {"events": events("It showed Internal server error.\n**Verdict: fail**")}})
        self.assertEqual(ER.exit_code(results), 0, results["details"])
        self.assertEqual(detail(results, "GT-BUG4")["verdict"], "FAIL")

    def test_no_verdict_line_is_an_error(self):
        results, _ = run({"GT-BUG5": {"events": events("It said Internal server error. Please try again later.")}})
        self.assertOnly(results, "GT-BUG5", "ERROR")

    def test_tool_input_and_reasoning_are_not_the_reply(self):
        # events() puts a "VERDICT: PASS" line in a toolUse input delta and a reasoningContent delta.
        results, _ = run({"GT-OVERLAY": {"events": events("The overlay-bug div covers the field's lower left.")}})
        self.assertOnly(results, "GT-OVERLAY", "ERROR")

    def test_run_that_did_not_end_its_turn_is_an_error(self):
        for stop in ("max_iterations_exceeded", "timeout_exceeded", "tool_use", "hook_stopped"):
            results, _ = run({"GT-BUG4": {"events": events(good_text(case("GT-BUG4")), stop=stop)}})
            self.assertOnly(results, "GT-BUG4", "ERROR")
            self.assertIn(stop, detail(results, "GT-BUG4")["reason"])

    def test_stream_without_message_stop_is_an_error(self):
        results, _ = run({"GT-BUG4": {"events": events(good_text(case("GT-BUG4")), stop=None)}})
        self.assertOnly(results, "GT-BUG4", "ERROR")

    def test_error_event_in_the_stream_is_an_error(self):
        evs = events(good_text(case("GT-OVERLAY")))
        evs.insert(-2, {"runtimeClientError": {"message": "browser session lost"}})
        results, _ = run({"GT-OVERLAY": {"events": evs}})
        self.assertOnly(results, "GT-OVERLAY", "ERROR")
        self.assertIn("browser session lost", detail(results, "GT-OVERLAY")["reason"])

    def test_failed_call_is_an_error_and_the_run_continues(self):
        results, calls = run({"GT-LOGIN": {"raise": "ThrottlingException: rate exceeded"}})
        self.assertOnly(results, "GT-LOGIN", "ERROR")
        self.assertEqual(len([c for c in calls if c["op"] == "invoke_harness"]), N)

    def test_stream_broken_mid_way_is_an_error(self):
        evs = events(good_text(case("GT-BUG4")))
        results, _ = run({"GT-BUG4": {"events": evs[:3] + ["RAISE"] + evs[3:]}})
        self.assertOnly(results, "GT-BUG4", "ERROR")

    def test_evidence_needs_any_one_keyword(self):
        # GT-OVERLAY accepts "overlay" or "transparent".
        results, _ = run({"GT-OVERLAY": {"events": events("A transparent div covers the field.\nVERDICT: FAIL")}})
        self.assertEqual(ER.exit_code(results), 0, results["details"])
        results, _ = run({"GT-OVERLAY": {"events": events("Something covers the field.\nVERDICT: FAIL")}})
        self.assertOnly(results, "GT-OVERLAY", "MISMATCH")

    def test_zero_cases_is_a_failure(self):
        with faked(scenario()) as fake:
            results = ER.run_golden_tests(ARN, URL, cases=[])
            self.assertEqual(fake.calls("invoke_harness"), [])
        self.assertEqual(results["total"], 0)
        self.assertEqual(ER.exit_code(results), 1)


class Cli(unittest.TestCase):
    def cli(self, *args, sc=None, script=SCRIPT):
        fake = Fake(sc or scenario())
        self.addCleanup(fake.close)
        env = dict(os.environ, PYTHONPATH=str(fake.dir / "pkg"), FAKE_BOTO3_STATE=str(fake.dir),
                   PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([sys.executable, "-B", str(script), *args], cwd=fake.dir, env=env,
                           capture_output=True, text=True, timeout=60)
        return p, fake

    def test_all_match_exits_0(self):
        p, fake = self.cli("--harness-arn", ARN, "--target-url", URL)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn(f"{N}/{N}", p.stdout)
        calls = fake.calls("invoke_harness")
        self.assertEqual(len(calls), N)
        # 4b looks each session up in aws/spans, so every session ID must be printed.
        for c in calls:
            self.assertIn(c["kwargs"]["runtimeSessionId"], p.stdout)

    def test_one_mismatch_exits_1(self):
        sc = scenario({"GT-BUG2": {"events": events("The error text is green.\nVERDICT: PASS")}})
        p, _ = self.cli("--harness-arn", ARN, "--target-url", URL, sc=sc)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn(f"{N - 1}/{N}", p.stdout)
        self.assertIn("reply ends: 'The error text is green.\\nVERDICT: PASS'", p.stdout)

    def test_qualifier_reaches_every_call(self):
        p, fake = self.cli("--harness-arn", ARN, "--target-url", URL, "--qualifier", "canary")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual([c["kwargs"].get("qualifier") for c in fake.calls("invoke_harness")], ["canary"] * N)

    def test_target_url_reaches_every_call(self):
        p, fake = self.cli("--harness-arn", ARN, "--target-url", OTHER_URL, sc=scenario(url=OTHER_URL))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        texts = [c["kwargs"]["messages"][0]["content"][0]["text"] for c in fake.calls("invoke_harness")]
        self.assertEqual([t.count(OTHER_URL) for t in texts], [1] * N)

    def test_target_url_is_required(self):
        # No default: a default would point every install at one host.
        p, fake = self.cli("--harness-arn", ARN)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("--target-url", p.stderr)
        self.assertEqual(fake.calls("invoke_harness"), [])

    def test_bad_target_url_is_refused_before_any_call(self):
        for url in ("ftp://demo.example.test/index.html", "demo.example.test/index.html", "https://",
                    "https://demo.example.test/a b.html"):
            p, fake = self.cli("--harness-arn", ARN, "--target-url", url)
            self.assertEqual(p.returncode, 2, url + p.stdout + p.stderr)
            self.assertIn("http(s) URL", p.stderr, url)
            self.assertEqual(fake.calls("invoke_harness"), [], url)

    def test_zero_cases_exits_nonzero(self):
        src = SCRIPT.read_text()
        emptied, n = re.subn(r"^GOLDEN_TESTS = \[\n.*?^\]\n", "GOLDEN_TESTS = []\n", src, flags=re.S | re.M)
        self.assertEqual(n, 1, "GOLDEN_TESTS literal not found")
        with tempfile.TemporaryDirectory(prefix="eval-runner-empty-") as d:
            script = pathlib.Path(d) / "eval_runner.py"
            script.write_text(emptied)
            p, fake = self.cli("--harness-arn", ARN, "--target-url", URL, script=script)
        # Exactly 1, the run's own failure. A usage error (2) would also be non-zero without showing anything.
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("No golden case ran", p.stderr)
        self.assertEqual(fake.calls("invoke_harness"), [])

    def test_runtime_arn_is_refused_before_any_call(self):
        p, fake = self.cli("--harness-arn", RUNTIME_ARN, "--target-url", URL)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("harness ARN", p.stderr)
        self.assertEqual([c for c in fake.calls() if c["op"] != "client"], [])

    def test_bad_qualifier_is_refused_before_any_call(self):
        p, fake = self.cli("--harness-arn", ARN, "--target-url", URL, "--qualifier", "1-canary")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("endpoint name", p.stderr)
        self.assertEqual(fake.calls("invoke_harness"), [])

    def test_help_names_the_options(self):
        p, _ = self.cli("--help")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("--qualifier", p.stdout)
        self.assertIn("--target-url", p.stdout)


if __name__ == "__main__":
    unittest.main()
