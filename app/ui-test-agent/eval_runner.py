"""
Golden-test runner for the UI Test Agent harness.

Runs each case in GOLDEN_TESTS as its own InvokeHarness session against the in-repo demo
page (app/demo-frontend/index.html, hosted wherever --target-url points) and compares the
verdict the agent reports with the case's expected_status. The page marks five deliberate
bugs (BUG 1 to BUG 5). BUG 1 and BUG 3 are one rendered defect, an overlay on the Password
field, so four cases expect FAIL and the valid sign-in expects PASS. Every expected verdict
and keyword is derived from the page source, and each case cites the lines ("bugs" lists the
page's BUG markers the case covers).

Use it before you promote a harness change (model, system prompt, skill, tools), against
a throwaway copy of the harness or an endpoint that serves the candidate version. Online
evaluation scores live traffic; this checks a known page with known answers.

Usage:
    python eval_runner.py --harness-arn <HARNESS_ARN> --target-url <URL of the hosted demo page>
                          [--qualifier <ENDPOINT_NAME>] [--region us-east-1]

--target-url has no default. Host the demo page on an origin your harness's browser and
guard allow, and serve it unchanged: the expectations hold only for that file.

The request carries only the harness ARN, the endpoint (qualifier), a new session ID,
an actorId and the prompt. It never sends the per-call override fields (model,
systemPrompt, tools, skills, allowedTools, maxTokens, maxIterations, timeoutSeconds),
so the run uses the configuration of the harness version the endpoint serves.

A case passes when the stream ends with stopReason end_turn, the reply's last
"VERDICT: <PASS|FAIL>" line equals expected_status, and the reply names at least one
must_contain keyword.

Exit codes:
    0  every case ran and passed
    1  a case mismatched or errored, or no case ran
    2  bad arguments (not a harness ARN, not an http(s) target URL, or not an endpoint name)

Needs a boto3/botocore with invoke_harness (AGENTS.md section 2); checked against botocore 1.43.120.
"""

__version__ = "0.3.0"

import argparse
import re
import sys
import urllib.parse
import uuid

# The page the expectations are derived from, relative to the repo root. "source" lists
# (line, text on that line) pairs; test_eval_runner checks each one against the file.
TARGET_PAGE = "app/demo-frontend/index.html"
URL_PLACEHOLDER = "{url}"

GOLDEN_TESTS = [
    # index.html:64-66: admin / password123 shows "Login successful! Welcome, admin". Expected PASS.
    {
        "id": "GT-LOGIN",
        "bugs": [],
        "title": "valid sign-in succeeds",
        "prompt": "Open {url}. Type admin in the Username field and password123 in the Password field, then click "
                  "Login. Report PASS if a message says the login succeeded, and quote that message exactly.",
        "expected_status": "PASS",
        "must_contain": ["login successful"],
        "source": [(64, "username === 'admin' && password === 'password123'"),
                   (65, "'Login successful! Welcome, ' + username")],
    },
    # index.html:14, 20 (BUG 1, BUG 3): the comments say the overlay covers the submit button. It doesn't. By the CSS
    # (index.html:21: height 20px, margin-top -25px, z-index 10, transparent; placed after the password group, whose
    # margin-bottom is 15px, index.html:11 and 37) it covers the lower-left of the Password field instead. Measured in a
    # browser at 1280x800 on 2026-11-28: overlay top 306.9 to bottom 326.9, Password field 279.4 to 316.9, Login button
    # 331.9 to 374.4. That is a 5.0 px gap above the button, with no overlap; elementFromPoint hit the button at 81 of
    # 81 points, and hit the overlay at 8 of 81 points on the Password field. So BUG 1 and BUG 3 are one observable
    # defect: clicks on the lower-left of the Password field do not reach the input. Expected FAIL.
    {
        "id": "GT-OVERLAY",
        "bugs": [1, 3],
        "title": "a transparent overlay takes clicks meant for the Password field",
        "prompt": "Open {url} and do not submit anything. Check that every part of the Password field takes a click: "
                  "call document.elementFromPoint at points across the whole field, a few pixels apart and including "
                  "points within 5 pixels of its bottom edge, and note which element each point hits. Report FAIL if "
                  "any point hits an element other than the Password input, because a click there does not reach "
                  "the field. Name that element by its class and say which part of the field it covers.",
        "expected_status": "FAIL",
        "must_contain": ["overlay", "transparent"],
        "source": [(11, ".form-group { margin-bottom: 15px; }"),
                   (14, "BUG 1: Submit button has z-index issue"),
                   (20, "BUG 3: Overlay div partially covers the submit button"),
                   (21, ".overlay-bug { position: absolute; width: 200px; height: 20px; background: transparent; "
                        "z-index: 10; margin-top: -25px; }"),
                   (33, '<label for="password">Password</label>'),
                   (36, "BUG 3: This invisible overlay"), (37, '<div class="overlay-bug"></div>')],
    },
    # index.html:17-18 (BUG 2): .error-message { color: green }. Wrong credentials show it (index.html:69-70).
    # Expected FAIL.
    {
        "id": "GT-BUG2",
        "bugs": [2],
        "title": "the error message is green, not red",
        "prompt": "Open {url}. Type wronguser in the Username field and wrongpass in the Password field, then click "
                  "Login. Read the computed CSS color of the error message text. Report FAIL if the text is not "
                  "red, because an error message should be red. Give the color value you read.",
        "expected_status": "FAIL",
        "must_contain": ["green"],
        "source": [(17, "BUG 2: Error message uses wrong color"),
                   (18, ".error-message { color: green;"),
                   (69, "errorMsg.textContent = "), (70, "errorMsg.style.display = 'block';")],
    },
    # index.html:56-61 (BUG 4): only the username is checked, so admin with an empty password reaches the
    # else branch and shows "Internal server error. Please try again later." (index.html:69). Expected FAIL.
    {
        "id": "GT-BUG4",
        "bugs": [4],
        "title": "an empty password is not rejected",
        "prompt": "Open {url}. Type admin in the Username field, leave the Password field empty, then click Login. "
                  "Report FAIL if the page does not tell you that the password is required. Quote the message the "
                  "page shows, if any.",
        "expected_status": "FAIL",
        "must_contain": ["server error"],
        "source": [(56, "BUG 4: Empty field validation missing for password"),
                   (57, "if (!username) {"),
                   (69, "'Internal server error. Please try again later.'")],
    },
    # index.html:68-69 (BUG 5): wrong credentials show "Internal server error. Please try again later." instead
    # of an invalid-credentials message. Expected FAIL.
    {
        "id": "GT-BUG5",
        "bugs": [5],
        "title": "wrong credentials report a server error, not invalid credentials",
        "prompt": "Open {url}. Type wronguser in the Username field and wrongpass in the Password field, then click "
                  "Login. Report FAIL if the error message does not say that the username or password is invalid. "
                  "Quote the error message exactly.",
        "expected_status": "FAIL",
        "must_contain": ["server error"],
        "source": [(68, "BUG 5: Wrong error message"),
                   (69, "'Internal server error. Please try again later.'")],
    },
]

VERDICT_INSTRUCTION = ("\n\nEnd your reply with a line of its own that reads exactly VERDICT: PASS or VERDICT: FAIL, "
                       "with nothing else on that line.")
# A verdict is a whole line: Markdown emphasis around it is allowed, other words are not. So the instruction
# restated ("VERDICT: PASS or VERDICT: FAIL") is not read as a verdict.
VERDICT_RE = re.compile(r"^[ \t>*_#`-]*VERDICT[ \t]*:[ \t]*[*_`]*[ \t]*(PASS|FAIL|BLOCKED|SKIPPED)[*_`.! \t\r]*$",
                        re.IGNORECASE | re.MULTILINE)
# Error events an InvokeHarness stream can carry (InvokeHarnessStreamOutput, botocore 1.43.120).
STREAM_ERRORS = ("internalServerException", "validationException", "runtimeClientError")
# Patterns from the InvokeHarness request model (HarnessArn, HarnessEndpointName).
HARNESS_ARN_RE = re.compile(
    r"arn:([^:]+)?:bedrock-agentcore:[a-z0-9-]+:[0-9]{12}:harness/[a-zA-Z][a-zA-Z0-9_]{0,39}-[a-zA-Z0-9]{10}")
QUALIFIER_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]{0,47}")
# A new actorId per run keeps Memory from recalling an earlier run's answers into this one.
ACTOR_PREFIX = "golden-eval-"
# A case is a whole agent run. botocore's default 60 s read timeout cuts long turns off (AGENTS.md 3.12, 3.15).
READ_TIMEOUT_SECONDS = 900


def render_prompt(case: dict, target_url: str) -> str:
    """The case's prompt for the page at target_url, with the verdict instruction appended."""
    return case["prompt"].replace(URL_PLACEHOLDER, target_url) + VERDICT_INSTRUCTION


def build_request(harness_arn: str, case: dict, target_url: str, session_id: str, actor_id: str,
                  qualifier: str | None = None) -> dict:
    """InvokeHarness arguments for one case. Only these keys: no per-call override field."""
    request = {
        "harnessArn": harness_arn,
        "runtimeSessionId": session_id,
        "actorId": actor_id,
        "messages": [{"role": "user", "content": [{"text": render_prompt(case, target_url)}]}],
    }
    if qualifier:
        request["qualifier"] = qualifier
    return request


def read_stream(stream) -> dict:
    """Reply text, last stopReason and first error event of one InvokeHarness event stream.

    Only text deltas are the reply. Tool input, tool results, reasoning and hook events are not.
    Text from a new content block starts on a new line, so a verdict in a block of its own is a line.
    """
    text, stop_reason, error = [], None, None
    run = None  # (contentBlockIndex,) of the text run the previous event belongs to; None after any other event
    for event in stream:
        for name in STREAM_ERRORS:
            if name in event and error is None:
                error = f"{name}: {(event[name] or {}).get('message', '')}"
        block = event.get("contentBlockDelta") or {}
        delta = block.get("delta") or {}
        if "text" in delta:
            if text and run != (block.get("contentBlockIndex"),):
                text.append("\n")
            text.append(delta["text"])
            run = (block.get("contentBlockIndex"),)
        else:
            run = None
        if "messageStop" in event:
            stop_reason = (event["messageStop"] or {}).get("stopReason")
    return {"text": "".join(text), "stop_reason": stop_reason, "error": error}


def verdict_of(text: str) -> str | None:
    """The verdict on the reply's last VERDICT line, upper-cased, or None."""
    found = VERDICT_RE.findall(text)
    return found[-1].upper() if found else None


def judge(case: dict, reply: dict) -> tuple[str, str | None, str]:
    """(status, verdict, reason) for one case. status is ok, MISMATCH or ERROR."""
    if reply["error"]:
        return "ERROR", None, reply["error"]
    if reply["stop_reason"] != "end_turn":
        return "ERROR", None, f"stopReason {reply['stop_reason']} (the run did not finish its turn)"
    verdict = verdict_of(reply["text"])
    if verdict is None:
        return "ERROR", None, "no VERDICT line in the reply"
    if verdict != case["expected_status"]:
        return "MISMATCH", verdict, "wrong verdict"
    lowered = reply["text"].lower()
    if not any(kw in lowered for kw in case["must_contain"]):
        return "MISMATCH", verdict, f"reply names none of {case['must_contain']}"
    return "ok", verdict, ""


def is_target_url(url: str) -> bool:
    """An absolute http(s) URL with a host."""
    parts = urllib.parse.urlsplit(url)
    return parts.scheme in ("http", "https") and bool(parts.hostname) and not any(c.isspace() for c in url)


def run_golden_tests(harness_arn: str, target_url: str, region: str = "us-east-1", qualifier: str | None = None,
                     cases: list | None = None, client=None) -> dict:
    """Run the cases (default: GOLDEN_TESTS) and return the results."""
    cases = GOLDEN_TESTS if cases is None else cases
    if client is None:
        import boto3
        from botocore.config import Config
        client = boto3.client("bedrock-agentcore", region_name=region,
                              config=Config(read_timeout=READ_TIMEOUT_SECONDS))
    actor_id = ACTOR_PREFIX + uuid.uuid4().hex[:12]
    results = {"total": len(cases), "passed": 0, "failed": 0, "actor_id": actor_id, "details": []}

    for case in cases:
        session_id = str(uuid.uuid4())
        request = build_request(harness_arn, case, target_url, session_id, actor_id, qualifier)
        reply = {"text": ""}
        try:
            reply = read_stream(client.invoke_harness(**request)["stream"])
            status, verdict, reason = judge(case, reply)
        except Exception as e:
            status, verdict, reason = "ERROR", None, f"{type(e).__name__}: {e}"

        results["passed" if status == "ok" else "failed"] += 1
        print(f"{case['id']}: {status} (expected {case['expected_status']}, got {verdict or '-'}) "
              f"session {session_id}" + (f" {reason}" if reason else ""), flush=True)
        if status != "ok":
            print(f"    reply ends: {reply['text'][-200:]!r}", flush=True)
        results["details"].append({
            "id": case["id"],
            "status": status,
            "verdict": verdict,
            "reason": reason,
            "session_id": session_id,
            "response_preview": reply["text"][:200],
        })

    return results


def exit_code(results: dict) -> int:
    """0 only when at least one case ran and every case passed."""
    return 0 if results["total"] > 0 and results["passed"] == results["total"] else 1


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"UI Test Agent golden-test runner v{__version__}")
    parser.add_argument("--harness-arn", required=True,
                        help="Harness ARN (arn:aws:bedrock-agentcore:<region>:<account>:harness/<name>-<id>), "
                             "not the runtime ARN")
    parser.add_argument("--target-url", required=True,
                        help="URL of the hosted demo page (a copy of app/demo-frontend/index.html) on an origin "
                             "the harness's browser may open")
    parser.add_argument("--qualifier", default=None,
                        help="Harness endpoint name to invoke (for example a canary endpoint); "
                             "omit it to use the default endpoint")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    if not HARNESS_ARN_RE.fullmatch(args.harness_arn):
        parser.error(f"--harness-arn must be a harness ARN (...:harness/<name>-<id>), got {args.harness_arn!r}")
    if not is_target_url(args.target_url):
        parser.error(f"--target-url must be an http(s) URL with a host, got {args.target_url!r}")
    if args.qualifier is not None and not QUALIFIER_RE.fullmatch(args.qualifier):
        parser.error(f"--qualifier must be an endpoint name ([a-zA-Z][a-zA-Z0-9_]{{0,47}}), got {args.qualifier!r}")

    results = run_golden_tests(args.harness_arn, args.target_url, args.region, args.qualifier)
    print(f"\nResults: {results['passed']}/{results['total']} passed (actorId {results['actor_id']})")
    if results["total"] == 0:
        print("No golden case ran.", file=sys.stderr)
    return exit_code(results)


if __name__ == "__main__":
    sys.exit(main())
