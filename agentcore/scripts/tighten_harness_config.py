#!/usr/bin/env python3
"""
Keep UITestAgentHarness and BugFixAgentHarness on a known-good tool allow-list,
limits and tags (issue #29, corrected by issue #75).

Managed fields:
  - allowedTools, maxTokens, maxIterations, timeoutSeconds -> update_harness (partial update)
  - tags                                                    -> tag_resource (UpdateHarness has no tags field)

DESIRED is the configuration the live harnesses were running when they last worked
(UITestAgentHarness v8, BugFixAgentHarness v7, read 2026-11-27), except the UI agent's
allowedTools: "*" is replaced by the six tools a QA run uses (issue #80). The earlier
DESIRED (UI allowedTools ["browser", "code_interpreter"], BugFix maxTokens 32768,
environment=production) would have narrowed the UI agent's tools and cut the Bug-Fix
agent's output budget to a quarter, so this script refuses any change that removes
a tool or lowers a limit unless you pass --allow-narrowing.

allowedTools entries of the form "@{<tool type>}" are resolved per harness to "@<name>"
of each configured tool of that type (a configured tool is selected by its tools[].name,
which differs per deployment).

Payload facts (AGENTS.md §3.2):
  - allowedTools / maxTokens / maxIterations / timeoutSeconds are plain list/integer (no optionalValue wrapper)
  - UpdateHarness has no tags field; TagResource is a separate call
  - clientToken min length is 33 chars; secrets.token_hex(20) gives 40

Requires boto3 >= 1.43.18 (older versions silently lack update_harness / tag_resource).

Usage:
  python tighten_harness_config.py --dry-run                  # print live vs desired; change nothing
  python tighten_harness_config.py                            # apply; environment tag defaults to "dev"
  python tighten_harness_config.py --environment staging      # apply with another environment tag
  python tighten_harness_config.py --allow-narrowing          # also apply changes that remove tools / lower limits

Exit codes:
  0  no drift, or every update applied
  1  a harness was not found
  2  boto3 too old (< 1.43.18)
  3  update_harness or tag_resource failed
  4  dry run: drift found, none of it narrows tools or lowers a limit
  5  a change would remove tools or lower a limit (dry run: reported; apply: refused unless --allow-narrowing)
  6  DESIRED names a tool type ("@{<type>}") that a harness has not configured; nothing applied to it
"""
from __future__ import annotations

import argparse
import re
import secrets
import sys
import time
from typing import Any

try:
    import boto3
    import botocore
except ImportError:
    print("ERROR: boto3 not installed. Run: pip install --upgrade boto3 botocore", file=sys.stderr)
    sys.exit(2)


MIN_BOTO3 = (1, 43, 18)
# update_harness took 223-238 s to reach READY on a copy of UITestAgentHarness (6 updates,
# 2026-11-27). At 120 s the apply reported a timeout (exit 3) while the update was still running.
MAX_POLL_SECONDS = 600
POLL_INTERVAL = 5

CONFIG_FIELDS = ("allowedTools", "maxTokens", "maxIterations", "timeoutSeconds")
LIMIT_FIELDS = ("maxTokens", "maxIterations", "timeoutSeconds")

# Desired config per harness. Tune here, not via CLI (except the environment tag).
#
# UITestAgentHarness allowedTools: a fixed list instead of "*" (issue #80).
#   - "*" means the platform's current recommended built-in set, and that set grows. The same
#     harness version (v8) was offered shell, file_operations, browser, code_interpreter, skills
#     on 2026-10-29/30, and on 2026-11-27 also web_fetch, subagent and todo_write, with
#     file_operations split into read, write and edit.
#   - Tools a QA run calls, from aws/spans (11 sessions, 2026-10-29..11-27): browser 572,
#     shell 60, code_interpreter 23, retrieve_context 6, skills 3, read 3. Kept:
#       shell             reads the login secret (the AWS-managed Code Interpreter has no AWS
#                         credentials; the harness runtime has the execution role)
#       read              returns a saved screenshot as an image the model can look at
#       retrieve_context  reads back a tool result over ~1,500 tokens that the harness moved out
#                         of context (it is not Memory)
#       skills            loads ui-testing/SKILL.md
#       browser, code_interpreter
#   - Dropped (0 calls in the 5 sessions that were offered them): web_fetch, subagent (a child
#     agent that gets shell and web_fetch), write, edit, todo_write.
#   - A plain name matches built-in tools only. A configured tool is selected as
#     "@<its tools[].name>", and that name differs per deployment ("browser" in
#     app/ui-test-agent/deploy_harness.py, "aws_browser_v1" on the live harness). So
#     "@{<tool type>}" below is resolved from the harness's own tools list.
#   - `shell` still reaches the network (network mode PUBLIC), so this list removes the
#     dedicated fetch and delegation tools and stops the set from growing. It does not close
#     exfiltration.
#
# BugFixAgentHarness allowedTools = ["code_interpreter"], unchanged from live. The
# orchestrator (ci-agent/bugfix_agent.py) puts the source in the prompt and reads the diff
# from the reply, so the fix path uses no tool. As AGENTS.md §3.11.3 says, the plain name
# filters the declared tool out: on 2026-11-27 the invoke span's `gen_ai.agent.tools` was
# ["skills"] (the code interpreter is declared as `code_interpreter_1`), and the fix still
# applied. Selecting it takes "@code_interpreter_1" (a `code_interpreter*` glob matches
# nothing, issue #80); that widens the agent's tools and needs its own test.
#
# Limits are sized for the model in `sized_for_model` (both models cap output at 128K tokens;
# AGENTS.md §3.15 has the capacity chain). If the live model differs, the script warns:
# re-size the limits before applying.
DESIRED = {
    "UITestAgentHarness": {
        "sized_for_model": "global.anthropic.claude-sonnet-5-5",
        "allowedTools": ["shell", "read", "retrieve_context", "skills",
                         "@{agentcore_browser}", "@{agentcore_code_interpreter}"],
        "maxTokens": 65536,
        "maxIterations": 100,
        "timeoutSeconds": 3600,
        "tags": {
            "team": "qa-platform",
            "cost-center": "engineering",
            "agent-type": "ui-test",
        },
    },
    "BugFixAgentHarness": {
        "sized_for_model": "global.anthropic.claude-opus-5-5",
        "allowedTools": ["code_interpreter"],
        "maxTokens": 131072,
        "maxIterations": 30,
        "timeoutSeconds": 1800,
        "tags": {
            "team": "qa-platform",
            "cost-center": "engineering",
            "agent-type": "bug-fix",
        },
    },
}


def parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split(".")[:3])


def check_boto3_version() -> None:
    cur = parse_version(boto3.__version__)
    if cur < MIN_BOTO3:
        print(
            f"ERROR: boto3 {boto3.__version__} too old; need >= {'.'.join(map(str, MIN_BOTO3))}.\n"
            f"  Upgrade: pip install --upgrade boto3 botocore",
            file=sys.stderr,
        )
        sys.exit(2)


def redact(s: str) -> str:
    s = re.sub(r"\b\d{12}\b", "<ACCOUNT_ID>", s)
    s = re.sub(r"-[a-zA-Z0-9]{10}\b", "-<ID>", s)
    return s


TOOL_TYPE_REF = re.compile(r"^@\{([a-z_]+)\}$")


def resolve_allowed_tools(desired: list[str], tools: list[dict] | None) -> list[str]:
    """Expand each "@{<tool type>}" entry to "@<name>" for every configured tool of that type.

    A plain allowedTools name matches built-in tools only; a configured tool is selected as
    "@<tools[].name>" (harness-tools.html#allowedtools-patterns), and the name is chosen per
    deployment. Raises ValueError when a referenced type is not configured, so a narrowed list
    can never drop the browser silently."""
    out: list[str] = []
    for entry in desired:
        m = TOOL_TYPE_REF.match(entry)
        if not m:
            out.append(entry)
            continue
        names = [t["name"] for t in tools or [] if t.get("type") == m.group(1) and t.get("name")]
        if not names:
            raise ValueError(f"{entry}: the harness has no configured {m.group(1)} tool")
        out += [f"@{n}" for n in names]
    return out


def find_harness(client: Any, name: str) -> dict | None:
    """Return harness summary by name, or None if not found. Follows nextToken."""
    kwargs: dict[str, Any] = {}
    while True:
        page = client.list_harnesses(**kwargs)
        for h in page.get("harnesses", []):
            if h.get("harnessName") == name:
                return h
        token = page.get("nextToken")
        if not token:
            return None
        kwargs["nextToken"] = token


def classify(field: str, live: Any, desired: Any) -> str:
    """same | set | raise | widen | change | LOWER | NARROW. Upper-case verdicts are regressions."""
    if field == "allowedTools":
        cur, want = set(live or []), set(desired)
        if cur == want:
            return "same"
        if not cur:
            return "set"
        if "*" in want:
            return "widen"
        if cur - want:
            # Any entry removed (including "*" replaced by a list) can remove a tool the agent uses.
            return "NARROW"
        return "widen"
    if live is None:
        return "set"
    if desired == live:
        return "same"
    if field in LIMIT_FIELDS:
        return "LOWER" if desired < live else "raise"
    return "change"


def plan_for(detail: dict, desired: dict) -> list[tuple[str, Any, Any, str]]:
    return [(f, detail.get(f), desired[f], classify(f, detail.get(f), desired[f])) for f in CONFIG_FIELDS]


def tag_plan(current: dict, desired_tags: dict) -> list[tuple[str, Any, Any, str]]:
    rows = []
    for k, v in desired_tags.items():
        cur = current.get(k)
        rows.append((f"tag {k}", cur, v, "same" if cur == v else ("set" if cur is None else "change")))
    return rows


def print_rows(rows: list[tuple[str, Any, Any, str]]) -> None:
    print(f"  {'field':<20} {'live':<24} {'desired':<24} verdict")
    for field, live, want, verdict in rows:
        live_s = "<absent>" if live is None else repr(live)
        print(f"  {field:<20} {live_s:<24} {want!r:<24} {verdict}")


def apply_config(client: Any, harness_id: str, rows: list[tuple[str, Any, Any, str]]) -> None:
    payload: dict[str, Any] = {
        "harnessId": harness_id,
        "clientToken": secrets.token_hex(20),  # 40 chars; min validated length is 33
    }
    for field, _, want, verdict in rows:
        if verdict != "same":
            payload[field] = want
    try:
        client.update_harness(**payload)
        print(f"  ✓ update_harness HTTP 200 ({[k for k in payload if k not in ('harnessId', 'clientToken')]})")
    except botocore.exceptions.ClientError as e:
        print(f"ERROR: update_harness failed: {redact(str(e))}", file=sys.stderr)
        sys.exit(3)


def apply_tags(client: Any, arn: str, desired_tags: dict) -> None:
    try:
        client.tag_resource(resourceArn=arn, tags=desired_tags)  # merges; tags not listed here are kept
        print(f"  ✓ tag_resource HTTP 200")
    except botocore.exceptions.ClientError as e:
        print(f"ERROR: tag_resource failed: {redact(str(e))}", file=sys.stderr)
        sys.exit(3)


def poll_until_ready(client: Any, harness_id: str) -> None:
    deadline = time.time() + MAX_POLL_SECONDS
    while time.time() < deadline:
        status = client.get_harness(harnessId=harness_id)["harness"].get("status")
        if status == "READY":
            print(f"  ✓ status=READY")
            return
        if status in ("UPDATE_FAILED", "FAILED", "DELETE_FAILED"):
            print(f"ERROR: harness reached terminal failure: {status}", file=sys.stderr)
            sys.exit(3)
        print(f"  status={status} (waiting {POLL_INTERVAL}s)")
        time.sleep(POLL_INTERVAL)
    print(f"ERROR: timeout waiting for READY", file=sys.stderr)
    sys.exit(3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--environment", default="dev",
                        help="Value of the `environment` tag on both harnesses (default: dev)")
    parser.add_argument("--dry-run", action="store_true", help="Print live vs desired without mutating")
    parser.add_argument("--allow-narrowing", action="store_true",
                        help="Apply changes that remove tools or lower a limit (refused by default)")
    args = parser.parse_args()
    if not args.environment.strip():
        parser.error("--environment must not be empty")

    check_boto3_version()
    print(f"boto3 {boto3.__version__} OK")
    print(f"Region:      {args.region}")
    print(f"Account:     <ACCOUNT_ID>")
    print(f"Environment: {args.environment}")
    print(f"Mode:        {'DRY RUN' if args.dry_run else 'APPLY'}\n")

    session = boto3.Session(region_name=args.region)
    session.client("sts").get_caller_identity()  # validates creds
    control = session.client("bedrock-agentcore-control")

    missing, unresolved, any_drift, regressions = [], [], False, []
    for name, desired in DESIRED.items():
        print(f"=== {name} ===")
        harness = find_harness(control, name)
        if not harness:
            print(f"  ✗ not found")
            missing.append(name)
            print()
            continue
        detail = control.get_harness(harnessId=harness["harnessId"])["harness"]
        model = (detail.get("model") or {}).get("bedrockModelConfig", {}).get("modelId")
        print(f"  arn:     {redact(harness['arn'])}")
        print(f"  version: {detail.get('harnessVersion')}   status: {detail.get('status')}")
        print(f"  model:   {model}")
        if model != desired["sized_for_model"]:
            print(f"  ⚠ limits below were sized for {desired['sized_for_model']}; re-size them before applying "
                  f"(AGENTS.md §3.15)")

        try:
            desired = {**desired, "allowedTools": resolve_allowed_tools(desired["allowedTools"], detail.get("tools"))}
        except ValueError as e:
            print(f"  ✗ {e}; nothing checked or applied for this harness")
            unresolved.append(name)
            print()
            continue
        rows = plan_for(detail, desired)
        tags = {**desired["tags"], "environment": args.environment}
        current_tags = control.list_tags_for_resource(resourceArn=harness["arn"]).get("tags", {}) or {}
        trows = tag_plan(current_tags, tags)
        print_rows(rows + trows)

        config_drift = any(v != "same" for *_, v in rows)
        tag_drift = any(v != "same" for *_, v in trows)
        bad = [(name, f, v) for f, _, _, v in rows if v in ("LOWER", "NARROW")]
        regressions += bad
        any_drift = any_drift or config_drift or tag_drift

        if args.dry_run:
            print()
            continue
        if bad and not args.allow_narrowing:
            print(f"  ✗ refused: {', '.join(f'{f} {v}' for _, f, v in bad)} (pass --allow-narrowing to apply)")
            print()
            continue
        if config_drift:
            apply_config(control, harness["harnessId"], rows)
            poll_until_ready(control, harness["harnessId"])
        if tag_drift:
            apply_tags(control, harness["arn"], tags)
        if not (config_drift or tag_drift):
            print(f"  ✓ no changes needed")
        print()

    print(f"regressions: {len(regressions)}" + (f" ({', '.join(f'{n}.{f} {v}' for n, f, v in regressions)})"
                                                 if regressions else ""))
    if missing:
        print(f"✗ not found: {', '.join(missing)} — nothing was checked for them", file=sys.stderr)
        return 1
    if unresolved:
        print(f"✗ tool type not configured on: {', '.join(unresolved)}", file=sys.stderr)
        return 6
    if regressions and (args.dry_run or not args.allow_narrowing):
        return 5
    if args.dry_run:
        if any_drift:
            print("⚠ Dry run: drift found (no tool removed, no limit lowered). Re-run without --dry-run to apply.")
            return 4
        print("✓ Dry run: both harnesses match the desired config.")
        return 0
    print("✓ Done" if any_drift else "✓ No changes needed (idempotent re-run safe)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
