# Trigger Mechanisms — Design Document

> **Version:** 0.2.0

## Overview

The UI Test Agent supports 4 trigger mechanisms. Each serves a different use case in the SDLC.

## 1. CI/CD Trigger (GitHub Actions)

**File:** `.github/workflows/ui-test.yml`

**Flow:**
```
Developer pushes frontend code to PR
  → GitHub Actions detects path change (*.tsx, *.css, src/frontend/**)
  → Deploys preview environment (or uses staging)
  → Invokes UI Test Agent via invoke.py
  → Agent tests the UI
  → Results posted as PR comment
  → Merge blocked if CRITICAL/HIGH failures
```

**Trigger conditions:**
- PR created/updated with frontend file changes
- Manual dispatch via `workflow_dispatch`

**Secrets required:**
| Secret | Description |
|--------|-------------|
| `AWS_ROLE_ARN` | IAM role for GitHub OIDC federation |
| `HARNESS_ARN` | AgentCore Harness ARN |
| `STAGING_URL` | Default staging URL |

## 2. Admin Portal Trigger (API)

**Endpoint:** `POST /api/test-runs`

```json
{
  "target_url": "https://staging.example.com",
  "test_suite": "full-regression",
  "test_cases": ["Login flow", "Cart flow", "Checkout flow"],
  "triggered_by": "qa-lead@company.com",
  "priority": "high"
}
```

**Response:**
```json
{
  "run_id": "uuid",
  "status": "STARTED",
  "estimated_duration": "5m",
  "session_id": "uuid"
}
```

## 3. Scheduled Trigger (EventBridge)

**Rule:** Nightly full regression at 2 AM UTC

```json
{
  "source": ["ui-test-agent"],
  "detail-type": ["Scheduled Test Run"],
  "schedule": "cron(0 2 * * ? *)",
  "target": {
    "arn": "arn:aws:lambda:us-west-2:<ACCOUNT_ID>:function:ui-test-orchestrator",
    "input": {
      "target_url": "https://staging.example.com",
      "test_suite": "nightly-full-regression",
      "notify": ["slack:#qa-alerts", "email:qa-team@company.com"]
    }
  }
}
```

## 4. Webhook Trigger (Deployment Events)

**Endpoint:** `POST /api/webhook/deployment`

Called by deployment pipelines (CodePipeline, Vercel, Netlify) after a new version is live.

```json
{
  "event": "deployment_complete",
  "environment": "staging",
  "url": "https://staging.example.com",
  "commit_sha": "abc123def",
  "deployer": "codepipeline"
}
```

**Validation:**
- HMAC signature verification (`X-Webhook-Signature` header)
- Only accepted from registered deployment sources

## Decision Matrix

| Trigger | When | Who | Blocking |
|---------|------|-----|----------|
| CI/CD | PR with frontend changes | Automated | Yes (blocks merge) |
| Admin Portal | On-demand | QA lead | No |
| Scheduled | Nightly/weekly | Cron | No (alerts only) |
| Webhook | After deployment | Deploy pipeline | Optional |
