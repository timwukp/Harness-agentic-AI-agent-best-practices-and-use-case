"""Reference reader for qa_tool_guard's decisions in an InvokeHarness event stream.

Consumers (token-monitoring ci-agent/qa_agent.py, the ops-console's Run QA) implement the same rule and replay
qa_tool_guard_stream_cases.json; this module is the rule's executable statement and the fixture's own check.
It reads only event types, names, decisions and reason prefixes, never tool input or text.
"""
import json
import pathlib
import re
from collections import Counter

SPEC = json.loads(pathlib.Path(__file__).with_name("qa_tool_guard_spec.json").read_text())
RULE_PREFIX = re.compile(r"^([A-Z]\d\d):")


def audit_hook_events(events):
    """{"readonly": ok|violated|unobserved, "toolCalls", "guardDecisions", "denies": {rule: n}} for one pass."""
    tool_calls, decisions, denies = 0, 0, Counter()
    for ev in events:
        if not isinstance(ev, dict):
            continue
        start = (ev.get("contentBlockStart") or {}).get("start") or {}
        if isinstance(start, dict) and "toolUse" in start:
            tool_calls += 1
        hook = ev.get("hookEvent")
        if not isinstance(hook, dict) or hook.get("name") != SPEC["name"] or hook.get("type") != SPEC["event"]:
            continue
        if hook.get("decision") not in ("allow", "deny"):
            continue
        decisions += 1
        if hook["decision"] == "deny":
            m = RULE_PREFIX.match(str(hook.get("reason") or ""))
            denies[m.group(1) if m else "?"] += 1
    if denies:
        readonly = "violated"
    elif tool_calls == 0 or decisions < tool_calls:
        readonly = "unobserved"
    else:
        readonly = "ok"
    return {"readonly": readonly, "toolCalls": tool_calls, "guardDecisions": decisions, "denies": dict(sorted(denies.items()))}
