"""Tests for the QA custom browser's managed policy (WS4).

Run from this directory:  python3 -m unittest -v test_qa_browser_policy
Stdlib only. Hosts are example.test placeholders; the real values are passed at build time.
"""
import contextlib
import importlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SPEC = json.loads((HERE / "qa_browser_policy_spec.json").read_text())
SYNTHETIC = HERE / "fixtures" / "synthetic-viewer-run.json"
APP, API, REGION = "https://app.example.test", "https://api.example.test/prod/", "us-east-1"
# Written out on purpose: the spec or builder must not drift from these without a test noticing.
EXPECTED_POLICY = {
    "URLBlocklist": ["*"],
    "URLAllowlist": ["about:blank", "https://api.example.test", "https://app.example.test",
                     "https://cognito-idp.us-east-1.amazonaws.com"],
    "PasswordManagerEnabled": False,
    "AutofillAddressEnabled": False,
    "AutofillCreditCardEnabled": False,
}


def load():
    sys.path.insert(0, str(HERE))
    try:
        import build_qa_browser_policy
        return importlib.reload(build_qa_browser_policy)
    finally:
        sys.path.remove(str(HERE))


def recorded(tmp, urls, synthetic=False):
    p = pathlib.Path(tmp) / f"run-{len(urls)}-{int(synthetic)}.json"
    p.write_text(json.dumps({"synthetic": synthetic, "requests": [{"url": u} for u in urls]}))
    return p


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = load()

    def test_generated_policy_is_exactly_the_expected_file(self):
        self.assertEqual(self.b.build_policy(SPEC, app=APP, api=API, region=REGION), EXPECTED_POLICY)

    def test_fixed_keys_come_from_the_spec(self):
        policy = self.b.build_policy(SPEC, app=APP, api=API, region=REGION)
        for k, v in SPEC["managedPolicy"].items():
            if k != "URLAllowlist":
                self.assertEqual(policy[k], v)

    def test_non_default_port_is_kept_and_default_dropped(self):
        p = self.b.build_policy(SPEC, app="https://app.example.test:8443/x", api="https://api.example.test:443/", region=REGION)
        self.assertIn("https://app.example.test:8443", p["URLAllowlist"])
        self.assertIn("https://api.example.test", p["URLAllowlist"])

    def test_rejects_unusable_origins(self):
        for bad in ("http://app.example.test", "https://u.example.com:p@app.example.test", "app.example.test", "", "https://"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.b.build_policy(SPEC, app=bad, api=API, region=REGION)

    def test_rejects_bad_region(self):
        for bad in ("", "us-east-1.evil.com", "US-EAST-1"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.b.build_policy(SPEC, app=APP, api=API, region=bad)

    def test_guard_env_lists_the_same_origins(self):
        policy = self.b.build_policy(SPEC, app=APP, api=API, region=REGION)
        env = self.b.guard_env(policy)
        self.assertEqual(env.split(","), ["https://api.example.test:443", "https://app.example.test:443",
                                          "https://cognito-idp.us-east-1.amazonaws.com:443"])

    def test_policy_hash_is_canonical(self):
        p = self.b.build_policy(SPEC, app=APP, api=API, region=REGION)
        shuffled = dict(reversed(list(p.items())))
        self.assertEqual(self.b.policy_sha256(p), self.b.policy_sha256(shuffled))
        self.assertTrue(self.b.matches_deployed(json.dumps(shuffled, indent=4).encode(), p))
        self.assertFalse(self.b.matches_deployed(json.dumps(dict(p, PasswordManagerEnabled=True)).encode(), p))
        self.assertFalse(self.b.matches_deployed(b"not json", p))


class Fixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = load()
        cls.policy = cls.b.build_policy(SPEC, app=APP, api=API, region=REGION)

    def test_synthetic_run_is_fully_allow_listed(self):
        self.assertEqual(self.b.unlisted_origins(self.policy, [SYNTHETIC], SPEC), [])

    def test_an_unlisted_origin_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = recorded(tmp, [APP + "/", "https://fonts.example.net/a.woff2"])
            self.assertEqual(self.b.unlisted_origins(self.policy, [f], SPEC), ["https://fonts.example.net"])

    def test_deploy_gate_refuses_synthetic_only(self):
        with contextlib.redirect_stderr(io.StringIO()):
            rc = self.b.main(["--app", APP, "--api", API, "--region", REGION, "--fixture", str(SYNTHETIC),
                              "--for-deploy", "--out", "-"])
        self.assertNotEqual(rc, 0)

    def test_deploy_gate_refuses_an_unlisted_origin(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()):
            f = recorded(tmp, [APP + "/", "https://cdn.example.net/x.js"])
            rc = self.b.main(["--app", APP, "--api", API, "--region", REGION, "--fixture", str(f), "--for-deploy",
                              "--out", "-"])
        self.assertNotEqual(rc, 0)

    def test_deploy_gate_refuses_no_fixture(self):
        with contextlib.redirect_stderr(io.StringIO()):
            rc = self.b.main(["--app", APP, "--api", API, "--region", REGION, "--for-deploy", "--out", "-"])
        self.assertNotEqual(rc, 0)

    def test_deploy_gate_passes_a_clean_recording(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = recorded(tmp, [APP + "/", API + "me", "https://cognito-idp.us-east-1.amazonaws.com/", "data:,x"])
            out = pathlib.Path(tmp) / "managed.json"
            with contextlib.redirect_stdout(io.StringIO()):
                rc = self.b.main(["--app", APP, "--api", API, "--region", REGION, "--fixture", str(f), "--for-deploy",
                                  "--out", str(out)])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(out.read_text()), EXPECTED_POLICY)

    def test_fixture_without_requests_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = pathlib.Path(tmp) / "empty.json"
            f.write_text(json.dumps({"synthetic": False, "requests": []}))
            with self.assertRaises(ValueError):
                self.b.unlisted_origins(self.policy, [f], SPEC)


class SpecInvariants(unittest.TestCase):
    def test_fail_closed_defaults(self):
        self.assertEqual(SPEC["managedPolicy"]["URLBlocklist"], ["*"])
        self.assertIs(SPEC["managedPolicy"]["PasswordManagerEnabled"], False)
        self.assertIs(SPEC["recording"]["enabled"], False)
        self.assertEqual(SPEC["guardConsumer"]["env"], "QA_ALLOWED_ORIGINS")

    def test_synthetic_fixture_is_marked_synthetic(self):
        self.assertIs(json.loads(SYNTHETIC.read_text())["synthetic"], True)


if __name__ == "__main__":
    unittest.main()
