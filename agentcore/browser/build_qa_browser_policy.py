"""Build the QA custom browser's managed Chrome policy from qa_browser_policy_spec.json.

    python3 build_qa_browser_policy.py --app <TARGET_URL> --api <ApiUrl> --region us-east-1 \
        [--fixture recorded-run.json ...] [--for-deploy] --out managed-policy.json

Prints the policy's sha256 (canonical JSON) and the QA_ALLOWED_ORIGINS value for qa_tool_guard.
With --for-deploy it refuses (exit 2) unless at least one recorded, non-synthetic fixture is given and
every origin those runs requested is on the allow-list. Stdlib only; makes no network call.
"""
import argparse
import hashlib
import json
import pathlib
import re
import sys
from urllib.parse import urlsplit

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_PORT = {"http": 80, "https": 443}
REGION = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z]+-\d$")


def https_origin(url):
    """'https://host[:port]' (default port dropped) for an https URL; ValueError for anything else."""
    try:
        parts = urlsplit(str(url).strip())
        port = parts.port
    except ValueError as e:
        raise ValueError("unparseable origin") from e
    if parts.scheme != "https" or not parts.hostname or parts.username is not None or parts.password is not None:
        raise ValueError("an origin must be https://host with no userinfo")
    host = parts.hostname.lower()
    return f"https://{host}" + (f":{port}" if port and port != 443 else "")


def request_origin(url):
    """Allow-list form of a requested URL's origin, any scheme; None if the scheme has no origin."""
    parts = urlsplit(url)
    scheme, host = parts.scheme.lower(), (parts.hostname or "").lower()
    if not host:
        return None
    port = parts.port
    return f"{scheme}://{host}" + (f":{port}" if port and port != DEFAULT_PORT.get(scheme) else "")


def build_policy(spec, *, app, api, region):
    if not REGION.match(str(region)):
        raise ValueError("bad region")
    values = {"app": app, "api": api}
    origins = set()
    for role, rule in spec["originRoles"].items():
        raw = rule["template"].format(region=region) if "template" in rule else values.get(role)
        if raw is None:
            raise ValueError(f"no value for origin role {role}")
        origins.add(https_origin(raw))
    policy = {k: v for k, v in spec["managedPolicy"].items() if k != "URLAllowlist"}
    policy["URLAllowlist"] = sorted(set(spec["alwaysAllowed"]) | origins)
    return {k: policy[k] for k in spec["managedPolicy"]}


def guard_env(policy):
    """QA_ALLOWED_ORIGINS for qa_tool_guard: the listed origins as scheme://host:port."""
    out = []
    for entry in policy["URLAllowlist"]:
        o = request_origin(entry)
        if o:
            parts = urlsplit(o)
            out.append(f"{parts.scheme}://{parts.hostname}:{parts.port or DEFAULT_PORT[parts.scheme]}")
    return ",".join(sorted(out))


def canonical(policy):
    return json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()


def policy_sha256(policy):
    return hashlib.sha256(canonical(policy)).hexdigest()


def matches_deployed(raw_bytes, policy):
    """True if the bytes of a deployed policy file (e.g. read from S3) are the same policy."""
    try:
        return canonical(json.loads(raw_bytes)) == canonical(policy)
    except (ValueError, TypeError):
        return False


def load_fixture(path):
    doc = json.loads(pathlib.Path(path).read_text())
    urls = [r.get("url") for r in doc.get("requests") or [] if isinstance(r, dict) and isinstance(r.get("url"), str)]
    if not urls:
        raise ValueError(f"{path}: fixture has no requests")
    return doc.get("synthetic") is not False, urls


def unlisted_origins(policy, fixtures, spec):
    listed = set(policy["URLAllowlist"])
    ignored = set(spec["ignoredRequestSchemes"])
    missing = set()
    for path in fixtures:
        _, urls = load_fixture(path)
        for url in urls:
            if urlsplit(url).scheme.lower() in ignored:
                continue
            o = request_origin(url)
            if o is None or o not in listed:
                missing.add(o or "<no origin>")
    return sorted(missing)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--app", required=True)
    ap.add_argument("--api", required=True)
    ap.add_argument("--region", required=True)
    ap.add_argument("--fixture", action="append", default=[])
    ap.add_argument("--for-deploy", action="store_true")
    ap.add_argument("--out", required=True, help="path, or - for stdout")
    ap.add_argument("--spec", default=str(HERE / "qa_browser_policy_spec.json"))
    a = ap.parse_args(argv)
    spec = json.loads(pathlib.Path(a.spec).read_text())
    try:
        policy = build_policy(spec, app=a.app, api=a.api, region=a.region)
        missing = unlisted_origins(policy, a.fixture, spec)
        recorded = [f for f in a.fixture if not load_fixture(f)[0]]
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if missing:
        print(f"ERROR: {len(missing)} requested origin(s) not on the allow-list: {', '.join(missing)}", file=sys.stderr)
        return 2
    if a.for_deploy and not recorded:
        print("ERROR: --for-deploy needs at least one recorded (non-synthetic) fixture of a full viewer run",
              file=sys.stderr)
        return 2
    text = json.dumps(policy, indent=2) + "\n"
    if a.out == "-":
        sys.stdout.write(text)
    else:
        pathlib.Path(a.out).write_text(text)
    print(f"sha256 {policy_sha256(policy)}  QA_ALLOWED_ORIGINS={guard_env(policy)}", file=sys.stderr if a.out == "-" else sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
