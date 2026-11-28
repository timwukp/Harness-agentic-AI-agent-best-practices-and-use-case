# QA custom browser policy

The spec and builder for a custom AgentCore browser whose managed Chrome enterprise policy keeps the QA agent on the
app's origins:
- `URLBlocklist ["*"]` plus a generated `URLAllowlist`;
- the password manager and autofill off;
- session recording off until a masking check passes.

Docs: <https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser-enterprise-policies.html>.

| File | Role |
|---|---|
| `qa_browser_policy_spec.json` | **The one copy**: origin roles (app, api, cognito), the fixed policy keys, recording, network mode, the deploy gate, assumptions |
| `build_qa_browser_policy.py` | Builds the managed-policy JSON from the spec and the deployment's URLs. It prints the canonical sha256 and the matching `QA_ALLOWED_ORIGINS` for `qa_tool_guard`. Makes no network call |
| `fixtures/synthetic-viewer-run.json` | A stand-in request list. It never satisfies the deploy gate |
| `test_qa_browser_policy.py`, `mutate_qa_browser_policy.py` | Stdlib tests and their mutation check |

```bash
cd agentcore/browser
python3 -m unittest test_qa_browser_policy
python3 mutate_qa_browser_policy.py
python3 build_qa_browser_policy.py --app <TARGET_URL> --api <ApiUrl> --region us-east-1 \
    --fixture <recorded-viewer-run.json> --for-deploy --out managed-policy.json
```

**The deploy gate:** `--for-deploy` refuses unless at least one recorded (non-synthetic) request list of a full viewer
run is given and every origin in it is on the allow-list. A missing origin would break the app inside the QA browser,
so the inventory comes from a real run, not from reading code.

**Open, settled live (`agentcore/scripts/VERIFICATION_issue_90.md`, 4a):**
- whether `URLBlocklist` also blocks fetch/XHR to unlisted origins, or only navigations;
- which principal needs `s3:GetObject` on the policy file.

Network mode is the owner's choice: PUBLIC, or VPC, which needs NAT, about $32/month.
