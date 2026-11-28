"""Replays qa_tool_guard_cases.json through the guard handler and checks the spec's own invariants.

Run from this directory:  python3 -m unittest -v test_qa_tool_guard
Stdlib only, so it runs wherever the Lambda's Python runs. QA_TOOL_GUARD_SPEC points the handler
at a spec file; the mutation script uses it to run this suite against a mutated spec.
"""
import contextlib
import datetime
import importlib
import io
import json
import os
import pathlib
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
SPEC_PATH = pathlib.Path(os.environ.get("QA_TOOL_GUARD_SPEC") or HERE / "qa_tool_guard_spec.json")
CASES = json.loads((HERE / "qa_tool_guard_cases.json").read_text())
SPEC = json.loads(SPEC_PATH.read_text())
# The 14 forbidden control words of SAFETY_RULES (token-monitoring ci-agent/qa_agent.py), plus the
# danger style. Written out here on purpose: the spec must not lose one without this test noticing.
SAFETY_RULES_WORDS = {"save", "submit", "add", "create", "update", "apply", "edit", "remove", "delete",
                      "sync", "confirm", "approve", "reset", "override"}


def load_guard():
    sys.path.insert(0, str(HERE))
    try:
        import qa_tool_guard
        return importlib.reload(qa_tool_guard)
    finally:
        sys.path.remove(str(HERE))


def call(guard, case):
    env = dict(CASES["env"], **case.get("env", {}))
    out = io.StringIO()
    with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out):
        result = guard.lambda_handler(json.loads(json.dumps(case["event"])), None)
    return result, out.getvalue()


class ReplayCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = load_guard()

    def test_every_case(self):
        for case in CASES["cases"]:
            with self.subTest(case=case["id"]):
                result, _ = call(self.guard, case)
                want = case["expect"]
                self.assertEqual(result.get("decision"), want["decision"], case["why"])
                self.assertEqual(result.get("reason", "").split(":", 1)[0], want["rule"], case["why"])

    def test_response_is_decision_and_reason_only(self):
        for case in CASES["cases"]:
            with self.subTest(case=case["id"]):
                result, _ = call(self.guard, case)
                self.assertEqual(set(result), {"decision", "reason"})
                self.assertIn(result["decision"], ("allow", "deny"))
                rule = result["reason"].split(":", 1)[0]
                # The reason is the rule text and nothing else: it never echoes tool input.
                self.assertEqual(result["reason"], f"{rule}: {SPEC['rules'][rule]}")
                self.assertLessEqual(len(result["reason"]), SPEC["reasonMaxChars"])

    def test_one_log_line_with_spec_fields_and_no_input(self):
        markers = CASES["secretMarkers"]
        for case in CASES["cases"]:
            with self.subTest(case=case["id"]):
                result, log = call(self.guard, case)
                lines = [ln for ln in log.splitlines() if ln.strip()]
                self.assertEqual(len(lines), 1)
                rec = json.loads(lines[0])
                self.assertEqual(list(rec), SPEC["logging"]["fields"])
                self.assertEqual(rec["decision"], result["decision"])
                for m in markers:
                    self.assertNotIn(m, log)
                    self.assertNotIn(m, result["reason"])

    def test_error_fails_closed(self):
        case = next(c for c in CASES["cases"] if c["id"] == "browser-screenshot")
        with mock.patch.object(self.guard, "decide", side_effect=RuntimeError("boom " + CASES["secretMarkers"][0])):
            result, log = call(self.guard, case)
        self.assertEqual(result, {"decision": "deny", "reason": f"G09: {SPEC['rules']['G09']}"})
        self.assertNotIn(CASES["secretMarkers"][0], log)
        self.assertNotIn("boom", log)

    def test_non_dict_event_fails_closed(self):
        for event in (None, [], "x", 3):
            with self.subTest(event=repr(event)):
                with contextlib.redirect_stdout(io.StringIO()):
                    result = self.guard.lambda_handler(event, None)
                self.assertEqual(result["decision"], "deny")
                self.assertEqual(result["reason"].split(":", 1)[0], "G00")


class SpecInvariants(unittest.TestCase):
    def test_forbidden_controls_keep_every_safety_rule_word(self):
        self.assertTrue(SAFETY_RULES_WORDS <= set(SPEC["forbiddenControls"]),
                        SAFETY_RULES_WORDS - set(SPEC["forbiddenControls"]))

    def test_fail_closed_settings(self):
        self.assertIs(SPEC["denyOnTruncation"], True)
        self.assertEqual(SPEC["failureMode"], "deny")
        self.assertEqual(SPEC["decisionOnError"], "deny")

    def test_hook_config_is_one_before_tool_call_lambda_that_fails_closed(self):
        cfg = SPEC["hookConfig"]
        self.assertIsInstance(cfg, list)
        self.assertEqual(len(cfg), 1)
        self.assertEqual(set(cfg[0]), {"beforeToolCall"})
        hook = cfg[0]["beforeToolCall"]
        self.assertEqual(set(hook), {"name", "target"})
        self.assertLessEqual(len(hook["name"]), 64)
        self.assertEqual(hook["name"], SPEC["name"])
        target = hook["target"]
        self.assertEqual(set(target), {"lambda"})
        self.assertEqual(target["lambda"]["failureMode"], "deny")
        self.assertTrue(1 <= target["lambda"]["timeoutSeconds"] <= 900)

    def test_origin_allowlist_comes_from_env(self):
        self.assertTrue(SPEC["origins"]["env"])
        self.assertTrue(CASES["env"].get(SPEC["origins"]["env"]))

    def test_every_rule_has_a_case(self):
        used = {c["expect"]["rule"] for c in CASES["cases"]}
        self.assertEqual(used - set(SPEC["rules"]), set(), "a case names an unknown rule")
        # G09 (guard error) is covered by test_error_fails_closed.
        self.assertEqual(set(SPEC["rules"]) - used - {"G09"}, set(), "a rule no case exercises")

    def test_case_ids_unique_and_both_decisions_present(self):
        ids = [c["id"] for c in CASES["cases"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual({c["expect"]["decision"] for c in CASES["cases"]}, {"allow", "deny"})

    # The docs' cutover for deprecated file_operations events. Written out on purpose, so that moving
    # removeAfter in the spec cannot quietly extend the allowance.
    FILE_OPS_CUTOVER = datetime.datetime(2026, 12, 12, tzinfo=datetime.timezone.utc)

    @staticmethod
    def file_ops_allowance_overdue(spec, now):
        fo = spec["tools"].get("file_operations")
        return fo is not None and now >= SpecInvariants.FILE_OPS_CUTOVER

    def test_file_operations_allowance_sunset(self):
        """Fails from 2026-12-12T00:00Z until the file_operations allowance, G05 and its cases are removed."""
        now = datetime.datetime.now(datetime.timezone.utc)
        self.assertFalse(self.file_ops_allowance_overdue(SPEC, now),
                         "deprecated file_operations events ended 2026-12-12: remove tools.file_operations, rule G05 "
                         "and the file-ops-* cases from the spec and cases file")

    def test_file_operations_sunset_fires_on_time(self):
        self.assertEqual(SPEC["tools"]["file_operations"]["removeAfter"], "2026-12-12T00:00:00Z")
        utc = datetime.timezone.utc
        self.assertFalse(self.file_ops_allowance_overdue(SPEC, datetime.datetime(2026, 12, 11, 23, 59, 59, tzinfo=utc)))
        self.assertTrue(self.file_ops_allowance_overdue(SPEC, datetime.datetime(2026, 12, 12, 0, 0, 0, tzinfo=utc)))
        gone = json.loads(json.dumps(SPEC))
        del gone["tools"]["file_operations"]
        self.assertFalse(self.file_ops_allowance_overdue(gone, datetime.datetime(2027, 1, 1, tzinfo=utc)))

    def test_handler_carries_no_copy_of_the_rules(self):
        src = (HERE / "qa_tool_guard.py").read_text()
        for word in SPEC["forbiddenControls"] + SPEC["dangerousStyles"]:
            for quoted in (f'"{word}"', f"'{word}'", f"|{word}|", f"({word}|", f"|{word})"):
                self.assertNotIn(quoted, src, f"{word} is written in the handler; it belongs in the spec")
        for pattern in SPEC["patterns"].values():
            self.assertNotIn(pattern, src)


if __name__ == "__main__":
    unittest.main()
