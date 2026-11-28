"""before_tool_call guard for the QA harnesses: allow or deny each tool call before it runs.

Every rule (control words, patterns, tool and action lists, origins, rule texts) comes from
qa_tool_guard_spec.json next to this file; this module only applies them. The response is
{"decision", "reason"} and the reason is "<rule id>: <rule text>" from the spec, so tool input
(typed text, scripts, code; any of it can hold the QA password) never leaves this function.
The one log line per call carries the fields in spec.logging.fields and nothing else.

Any error decides deny (spec.decisionOnError). The hook's own failureMode is deny too, so a
timeout or a crash also skips the tool call.
"""
import json
import os
import pathlib
import re
from urllib.parse import urlsplit

SPEC = json.loads(pathlib.Path(os.environ.get("QA_TOOL_GUARD_SPEC")
                               or pathlib.Path(__file__).with_name("qa_tool_guard_spec.json")).read_text())
RULES = SPEC["rules"]
_P = SPEC["patterns"]
_I = re.I
WRITE_CONTROL = re.compile(r"\b(?:" + "|".join(map(re.escape, SPEC["forbiddenControls"] + SPEC["dangerousStyles"]))
                           + r")\b", _I)
SIGN_IN = re.compile(_P["signIn"], _I)
CREDENTIAL_FIELD = re.compile(_P["credentialField"], _I)
NON_GET = re.compile(_P["nonGet"], _I)
SCRIPT_CLICK = re.compile(_P["scriptClick"], _I)
URL = re.compile(_P["url"], _I)
BODY_UPLOAD = re.compile(_P["shellBodyUpload"], _I)
STRICT_SESSION = re.compile(SPEC["strictSessionIdPattern"])
BROWSER = SPEC["tools"]["browser"]
SHELL = SPEC["tools"]["shell"]
CODE = SPEC["tools"]["code_interpreter"]
FILE_OPS = SPEC["tools"]["file_operations"]
DEFAULT_PORT = {"http": 80, "https": 443, "ws": 80, "wss": 443}


class Deny(Exception):
    def __init__(self, rule):
        super().__init__(rule)
        self.rule = rule


def origin_of(url):
    """'scheme://host:port' with the default port explicit; None for anything else."""
    try:
        parts = urlsplit(str(url).strip())
        scheme, host, port = parts.scheme.lower(), (parts.hostname or "").lower(), parts.port
    except ValueError:
        return None
    if scheme not in DEFAULT_PORT or not host or parts.username is not None or parts.password is not None:
        return None
    return f"{scheme}://{host}:{port or DEFAULT_PORT[scheme]}"


def allowed_origins():
    raw = os.environ.get(SPEC["origins"]["env"], "")
    return {o for o in (origin_of(x) for x in raw.split(",") if x.strip()) if o}


def is_truncated(value):
    if isinstance(value, dict):
        return value.get("truncated") is True or any(is_truncated(v) for v in value.values())
    if isinstance(value, list):
        return any(is_truncated(v) for v in value)
    return False


def check_navigation(url, origins):
    if url in SPEC["origins"]["alwaysAllowedNavigations"]:
        return
    if origin_of(url) not in origins:
        raise Deny("B05")


def script_urls(text):
    ignore = tuple(SPEC["origins"]["scriptUrlIgnorePrefixes"])
    return [u for u in URL.findall(text) if not u.startswith(ignore)]


def check_browser(tool_input, strict, origins):
    body = tool_input.get(BROWSER["inputKey"])
    action = body.get("action") if isinstance(body, dict) else None
    if not isinstance(action, dict) or not isinstance(action.get("type"), str):
        raise Deny("G00")
    kind = action["type"]
    if kind not in BROWSER["allowedActions"]:
        raise Deny("B01")
    if strict and kind not in BROWSER["strictAllowedActions"]:
        raise Deny("B09")
    if "url" in action:
        check_navigation(action["url"], origins)
    if kind == "click":
        target = str(action.get("selector") or "")
        if WRITE_CONTROL.search(target) and not SIGN_IN.search(target):
            raise Deny("B02")
        if strict and not SIGN_IN.search(target):
            raise Deny("B03")
    elif kind == "type":
        if strict and not CREDENTIAL_FIELD.search(str(action.get("selector") or "")):
            raise Deny("B04")
    elif kind == "press_key":
        if action.get("key") not in BROWSER["allowedKeys"]:
            raise Deny("B06")
    elif kind == "evaluate":
        script = action.get("script")
        if not isinstance(script, str):
            raise Deny("G00")
        if NON_GET.search(script) or (SCRIPT_CLICK.search(script) and WRITE_CONTROL.search(SIGN_IN.sub(" ", script))):
            raise Deny("B07")
        if any(origin_of(u) not in origins for u in script_urls(script)):
            raise Deny("B08")
    elif kind == "execute_cdp":
        if action.get("method") not in BROWSER["cdpReadOnlyMethods"]:
            raise Deny("B10")
    return kind


def check_code(text, origins):
    if NON_GET.search(text) or BODY_UPLOAD.search(text):
        raise Deny("S01")
    for url in URL.findall(text):
        origin = origin_of(url)
        host = (urlsplit(url).hostname or "").lower() if origin else ""
        if origin in origins:
            continue
        if origin and origin.startswith("https://") and host.endswith(tuple(SPEC["shellAllowedHostSuffixes"])):
            continue
        raise Deny("S02")


def decide(event):
    """(rule id, browser action type or None) for one hook payload; raises Deny for a deny."""
    if not isinstance(event, dict) or not isinstance(event.get("context"), dict):
        raise Deny("G00")
    if event.get("event") != SPEC["event"]:
        raise Deny("G01")
    ctx = event["context"]
    if SPEC["denyOnTruncation"] and is_truncated(ctx):
        raise Deny("G02")
    tool, tool_input = ctx.get("toolName"), ctx.get("toolInput")
    if not isinstance(tool, str) or not isinstance(tool_input, dict):
        raise Deny("G00")
    strict = bool(STRICT_SESSION.search(str(event.get("sessionId") or "")))
    origins = allowed_origins()
    tools = SPEC["tools"]
    if tool in tools["readOnlyTools"]:
        return "A00", None
    if tool == "file_operations":
        if tool_input.get("command") not in FILE_OPS["allowedCommands"]:
            raise Deny("G05")
        return "A00", None
    if tool == "browser":
        return "A00", check_browser(tool_input, strict, origins)
    if tool == "shell":
        text = tool_input.get(SHELL["inputKey"])
    elif tool == "code_interpreter":
        body = tool_input.get(CODE["inputKey"])
        action = body.get("action") if isinstance(body, dict) else None
        text = next((action[k] for k in CODE["codeKeys"] if isinstance(action, dict) and isinstance(action.get(k), str)),
                    None)
    else:
        raise Deny("G03")
    if not isinstance(text, str):
        raise Deny("G00")
    check_code(text, origins)
    return "A00", None


def _safe(event, key):
    value = event.get(key) if isinstance(event, dict) else None
    return value if isinstance(value, str) and len(value) <= 128 else None


def lambda_handler(event, _context):
    action, strict, tool = None, False, None
    try:
        ctx = event.get("context") if isinstance(event, dict) else None
        tool = _safe(ctx, "toolName")
        strict = bool(STRICT_SESSION.search(str(_safe(event, "sessionId") or "")))
        rule, action = decide(event)
    except Deny as d:
        rule = d.rule
    except Exception:  # noqa: BLE001 - any error fails closed and its text (may hold input) is dropped
        rule = "G09"
    decision = "allow" if rule == "A00" else SPEC["decisionOnError"] if rule == "G09" else "deny"
    record = {"hookEventId": _safe(event, "hookEventId"), "toolName": tool, "action": action,
              "strict": strict, "decision": decision, "rule": rule}
    print(json.dumps({k: record[k] for k in SPEC["logging"]["fields"]}))
    return {"decision": decision, "reason": f"{rule}: {RULES[rule]}"[:SPEC["reasonMaxChars"]]}
