"""Replays qa_tool_guard_stream_cases.json through the reference consumer, and checks the SHA256SUMS pins.

Run from this directory:  python3 -m unittest -v test_qa_tool_guard_consumer
"""
import hashlib
import importlib
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
STREAMS = json.loads((HERE / "qa_tool_guard_stream_cases.json").read_text())
PINNED = ["qa_tool_guard_spec.json", "qa_tool_guard_cases.json", "qa_tool_guard_stream_cases.json"]


def load():
    sys.path.insert(0, str(HERE))
    try:
        import qa_tool_guard_consumer
        return importlib.reload(qa_tool_guard_consumer)
    finally:
        sys.path.remove(str(HERE))


class StreamCases(unittest.TestCase):
    def test_every_stream_case(self):
        c = load()
        for case in STREAMS["cases"]:
            with self.subTest(case=case["id"]):
                self.assertEqual(c.audit_hook_events(case["events"]), case["expect"], case["why"])

    def test_all_three_verdicts_are_exercised(self):
        self.assertEqual({c["expect"]["readonly"] for c in STREAMS["cases"]}, {"ok", "violated", "unobserved"})

    def test_fixture_carries_no_tool_input(self):
        for case in STREAMS["cases"]:
            for ev in case["events"]:
                delta = (ev.get("contentBlockDelta") or {}).get("delta") or {}
                if "toolUse" in delta:
                    self.assertEqual(delta["toolUse"].get("input"), "{}", case["id"])


class Pins(unittest.TestCase):
    def test_sha256sums_match_the_files(self):
        lines = (HERE / "SHA256SUMS").read_text().split("\n")
        pins = dict(reversed(ln.split("  ", 1)) for ln in lines if ln.strip())
        self.assertEqual(sorted(pins), sorted(PINNED))
        for name in PINNED:
            with self.subTest(file=name):
                self.assertEqual(pins[name], hashlib.sha256((HERE / name).read_bytes()).hexdigest(),
                                 f"{name} changed: re-pin with `shasum -a 256 {' '.join(PINNED)} > SHA256SUMS` "
                                 "and tell every consumer that vendors it")


if __name__ == "__main__":
    unittest.main()
