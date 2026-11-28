# Issue #90 Verification — a custom browser keeps the QA agent on the app's origins (WS4)

> 4a and 4b are **pending live**. Both need the
> owner's yes and a sign-in window, so they run only after WS1 (per-run passwords) is live.

## Why
The QA agent's browser is the default `aws.browser.v1`. It can load any URL, and its built-in password manager and
autofill are on.

A custom browser with a managed Chrome enterprise policy enforces three things below the model and the hook:
- `URLBlocklist ["*"]` plus an allow-list of the app's origins;
- `PasswordManagerEnabled false`;
- autofill off.

Recording stays off until a masking check shows the QA password is absent from recording artifacts. Hooks
(`qa_tool_guard`) check what the model asks for; this policy limits what the browser will actually load.

## Pre-merge checks (2026-11-28, offline, on `main@9164aeb` + this change)

**Tests:**
- `test_qa_browser_policy`: 16 tests.
  - The generated policy equals a hand-written expected file.
  - The fixed keys come from the spec.
  - `http`, userinfo, bad regions and empty origins are rejected. The default port is dropped and other ports are
    kept.
  - The hash is canonical, and a deployed file is compared semantically.
  - The guard env lists the same origins.
  - The deploy gate refuses a synthetic-only fixture, a missing fixture, an empty one, and an unlisted origin.
- `mutate_qa_browser_policy.py`: 13 mutants, all killed.

**Inventory, from code** (token-monitoring `main@881ddb1`):
- the app's CloudFront origin;
- the API origin (`ApiUrl`);
- `cognito-idp.<region>.amazonaws.com`. `frontend/src/auth/cognito.ts` configures a user pool only, with no OAuth
  domain and no identity pool.
- `index.html` loads only `/src/main.tsx`, and the frontend references no CDN.

The live run (4a) is the authority. Code reading can miss a host.

**Interop:** the guard (`qa_tool_guard`), fed the builder's `QA_ALLOWED_ORIGINS`, allows the app and API and denies an
off-list origin.

**API shape:** `CreateBrowser.enterprisePolicies[].{type: MANAGED, location.s3.{bucket, prefix}}` (boto3 1.43.68
model; docs: `browser-enterprise-policies.html`). The policy file is a flat JSON object of Chrome policy keys.

## 4a. Pending live: record the inventory, then a throwaway custom browser
1. **Record one full viewer run's requests** (a sign-in window). It covers the same 10 pages as the QA explorer prompt.
   - Record with a local Chromium (Playwright on brew `python3.12`) signed in as the viewer.
   - Save every request URL with `page.on("request", ...)` to `recorded-viewer-run.json` as
     `{"synthetic": false, "requests": [{"url": ...}]}`.
   - Keep the file local: it holds hostnames.
   - The password is typed from the secret and never written to the file. Check that as a boolean before using the
     file.
2. **Build and gate:**
   ```bash
   python3 agentcore/browser/build_qa_browser_policy.py --app "$APP" --api "$API" --region us-east-1 \
     --fixture recorded-viewer-run.json --for-deploy --out managed-policy.json
   ```
   Exit 0 is required. A refusal names each unlisted origin; add a role to the spec for it, or explain why not.
3. **Upload and create a throwaway browser** (the owner picks the bucket; the key is content-addressed):
   ```bash
   SHA=$(shasum -a 256 managed-policy.json | cut -c1-16)
   aws s3 cp managed-policy.json "s3://<policy-bucket>/qa-browser/$SHA/managed-policy.json"
   aws bedrock-agentcore-control create-browser --region us-east-1 --name qa_browser_throwaway \
     --network-configuration networkMode=PUBLIC \
     --enterprise-policies "[{\"type\":\"MANAGED\",\"location\":{\"s3\":{\"bucket\":\"<policy-bucket>\",\"prefix\":\"qa-browser/$SHA/managed-policy.json\"}}}]"
   ```
4. **Test it.** Point a throwaway harness copy (as in `VERIFICATION_issue_89.md`, 4a) at the new `browserArn`, and invoke it once with no sign-in:
   - open `<APP>/`;
   - open `https://example.com/`;
   - run `fetch('https://example.com/')` and `fetch('<API>')` in `evaluate`, and report each result.

| Criterion | Pass when |
|---|---|
| Allowed navigation loads | The `<APP>/` login page renders, and its assets and Cognito calls succeed |
| Off-list navigation blocked | `https://example.com/` shows Chrome's blocked-by-policy page |
| fetch/XHR behaviour | Recorded either way: whether `fetch` to an unlisted origin is blocked. This settles the spec's first assumption |
| S3 principal | Record which identity needed `s3:GetObject` on the policy prefix (spec assumption 2) |
| Policy file | `build_qa_browser_policy.matches_deployed(<bytes from S3>, <built policy>)` is true |

**Tear down:** delete the throwaway harness and browser, and keep the S3 object.

## 4b. Pending live: the real UI harness
1. Narrow sets `browserArn` in `tighten_harness_config.py` DESIRED, runs the dry run, then applies with a READY poll.
2. One token-monitoring `ui-qa-agent.yml` dispatch on `main`, with WS1's per-run passwords.

| Criterion | Pass when |
|---|---|
| No legitimate request blocked | 10 pages tested, and no finding or console error comes from a blocked request |
| Off-list navigation blocked | Shown in 4a, and re-checked by one scripted navigate in the same window |
| Password manager off | No "save password" prompt appears in the screenshots |
| Recording | Still off. Turning it on is a separate change, gated on the masking check |

**Cost:**
- **4a:** a sign-in window plus one short invoke, a few cents.
- **4b:** one QA run, about $0.55 (#84's measured run).
- **Network:** PUBLIC adds nothing. VPC mode would need NAT (about $32/month) and is the owner's choice.

## Results
_Pending live._
