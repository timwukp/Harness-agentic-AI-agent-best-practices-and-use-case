# UI Test Agent Admin Portal — Design Document

> **Version:** 0.2.0  
> **Status:** Design

---

## Purpose

A web dashboard that gives QA leads, managers, and developers visibility and control over the UI Test Agent fleet. Humans can manage test suites, trigger runs, view reports, inspect agent memory, and monitor costs — without touching CLI or code.

---

## User Roles

| Role | Permissions |
|------|-------------|
| **Admin** | Full access: configure agents, manage secrets, edit system prompts |
| **QA Lead** | Manage test suites, trigger runs, view all reports, edit schedules |
| **Developer** | View reports for their PRs, trigger re-runs, view agent reasoning |
| **Viewer** | Read-only: dashboards, reports, trends |

---

## Features (Prioritized)

### P0 — MVP

| Feature | Description |
|---------|-------------|
| **Run Dashboard** | Active/completed runs with status, pass rate, duration |
| **Trigger Run** | One-click test run with URL + suite selector |
| **Report Viewer** | Detailed report with inline screenshots, step-by-step results |
| **Test Suite Manager** | CRUD test suites and test cases |

### P1 — Core

| Feature | Description |
|---------|-------------|
| **Schedule Manager** | Create/edit/delete cron schedules (EventBridge rules) |
| **Memory Inspector** | View what the agent has learned, delete incorrect memories |
| **Trend Dashboard** | Pass rate over time, regression detection, flaky test identification |
| **Cost Dashboard** | Spend per suite, per team, per day |
| **Notifications** | Slack/Teams/email alerts on failures |

### P2 — Advanced

| Feature | Description |
|---------|-------------|
| **Agent Config Editor** | Edit system prompt, tools, limits via UI |
| **Comparison View** | Side-by-side diff of two test runs |
| **Replay Mode** | Step through agent's actions with screenshots (like a video) |
| **Multi-App Support** | Manage multiple applications under one portal |
| **Team Management** | Assign suites to teams, role-based access |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                           │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐      │
│  │ Dashboard │ │  Trigger  │ │  Reports  │ │  Memory   │      │
│  │           │ │           │ │           │ │ Inspector │      │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘      │
│  Tech: React 19, Vite, TailwindCSS, Recharts                    │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST API
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Backend (API Gateway + Lambda)                │
│                                                                   │
│  POST /api/runs              — Trigger a test run                │
│  GET  /api/runs              — List runs (with filters)          │
│  GET  /api/runs/:id          — Get run details                   │
│  GET  /api/runs/:id/report   — Get full report JSON              │
│  GET  /api/suites            — List test suites                  │
│  POST /api/suites            — Create test suite                 │
│  PUT  /api/suites/:id        — Update test suite                 │
│  DELETE /api/suites/:id      — Delete test suite                 │
│  GET  /api/schedules         — List schedules                    │
│  POST /api/schedules         — Create schedule                   │
│  DELETE /api/schedules/:id   — Delete schedule                   │
│  GET  /api/memory            — List agent memories               │
│  DELETE /api/memory/:id      — Delete a memory entry             │
│  GET  /api/metrics           — Cost and usage metrics            │
│                                                                   │
│  Auth: Cognito (JWT)                                             │
└──────────┬──────────────┬──────────────┬────────────────────────┘
           │              │              │
           ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐
│  DynamoDB    │ │  S3          │ │  AgentCore APIs      │
│              │ │              │ │                       │
│  • runs      │ │  • reports/  │ │  • invoke_harness    │
│  • suites    │ │  • screenshots│ │  • Memory (read/del) │
│  • schedules │ │              │ │  • get_harness       │
│  • metrics   │ │              │ │                       │
└──────────────┘ └──────────────┘ └──────────────────────┘
```

---

## Data Models

### Test Run

```json
{
  "run_id": "uuid",
  "status": "RUNNING | COMPLETED | FAILED | CANCELLED",
  "target_url": "https://staging.example.com",
  "test_suite_id": "suite-uuid",
  "test_suite_name": "Login Flow Regression",
  "triggered_by": "user@company.com",
  "trigger_type": "manual | ci_cd | scheduled | webhook",
  "session_id": "agentcore-session-uuid",
  "started_at": "2026-05-16T18:00:00Z",
  "completed_at": "2026-05-16T18:04:32Z",
  "duration_seconds": 272,
  "summary": {
    "total": 10,
    "passed": 8,
    "failed": 1,
    "blocked": 1,
    "pass_rate": 0.8
  },
  "report_s3_key": "reports/run-uuid/report.json",
  "cost_estimate_usd": 0.35
}
```

### Test Suite

```json
{
  "suite_id": "uuid",
  "name": "Login Flow Regression",
  "description": "Tests all login-related functionality",
  "target_url_pattern": "https://*.example.com",
  "test_cases": [
    {"id": "TC-001", "name": "Login with valid credentials", "priority": "P0"},
    {"id": "TC-002", "name": "Login with invalid password", "priority": "P0"},
    {"id": "TC-003", "name": "Forgot password flow", "priority": "P1"}
  ],
  "owner": "qa-team",
  "created_at": "2026-05-10T10:00:00Z",
  "last_run_at": "2026-05-16T18:00:00Z",
  "avg_pass_rate": 0.92
}
```

### Schedule

```json
{
  "schedule_id": "uuid",
  "name": "Nightly Full Regression",
  "cron": "cron(0 2 * * ? *)",
  "test_suite_id": "suite-uuid",
  "target_url": "https://staging.example.com",
  "enabled": true,
  "notify": ["slack:#qa-alerts"],
  "eventbridge_rule_arn": "arn:aws:events:..."
}
```

---

## UI Wireframes

### Dashboard (Home)

```
┌─────────────────────────────────────────────────────────────┐
│  UI Test Agent Portal                    [user@co] [Logout] │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐      │
│  │ 24 Runs │  │ 87% Pass│  │ 3 Active│  │ $12.50  │      │
│  │ Today   │  │ Rate    │  │ Now     │  │ Today   │      │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘      │
│                                                              │
│  Pass Rate Trend (7 days)                                    │
│  ┌─────────────────────────────────────────────────┐        │
│  │  100%|      ___                                  │        │
│  │   90%|  ___/   \___    ___                       │        │
│  │   80%| /           \__/   \___                   │        │
│  │   70%|                        \                  │        │
│  │      └──────────────────────────────────────     │        │
│  │       Mon  Tue  Wed  Thu  Fri  Sat  Sun          │        │
│  └─────────────────────────────────────────────────┘        │
│                                                              │
│  Recent Runs                                                 │
│  ┌──────────────────────────────────────────────────┐       │
│  │ ✅ Login Regression    | 100% | 2m ago  | CI/CD  │       │
│  │ ❌ Cart Flow           |  60% | 15m ago | Manual │       │
│  │ ✅ Checkout            |  95% | 1h ago  | Sched  │       │
│  │ ⏳ Full Regression     |  --  | running | Manual │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Report Viewer

```
┌─────────────────────────────────────────────────────────────┐
│  Report: Login Flow Regression — Run #42                     │
│  Status: ❌ 8/10 passed | 2 failures | Duration: 4m 32s     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  TC-001: Login with valid credentials              ✅ PASS  │
│  ├── Navigate to /login                            ✅       │
│  ├── Type email                                    ✅       │
│  ├── Type password + Submit                        ✅       │
│  └── Verify redirect to /dashboard                 ✅       │
│      [📷 Screenshot]                                         │
│                                                              │
│  TC-002: Login with invalid password               ❌ FAIL  │
│  ├── Navigate to /login                            ✅       │
│  ├── Type wrong password + Submit                  ❌       │
│  │   Expected: "Invalid credentials" error message          │
│  │   Actual:   500 Internal Server Error                    │
│  │   Console:  TypeError: Cannot read 'message' of undef   │
│  └── [📷 Screenshot] [🔧 Trigger Fix Agent]                 │
│                                                              │
│  Agent Reasoning:                                            │
│  "The server returned a 500 error instead of a 401.         │
│   This suggests the error handler has a null reference       │
│   when the user object doesn't have a message property."    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Reason |
|-------|-----------|--------|
| Frontend | React 19 + Vite + TailwindCSS | Fast, modern, consistent with team stack |
| Charts | Recharts | Lightweight, React-native |
| Auth | Amazon Cognito | Integrates with IAM, supports MFA |
| API | API Gateway + Lambda (Python) | Serverless, scales to zero |
| Database | DynamoDB | Serverless, fast, pay-per-request |
| Storage | S3 | Reports and screenshots |
| Hosting | CloudFront + S3 | Global CDN for frontend |
| IaC | AWS CDK (Python) | Consistent with project |

---

## Implementation Plan

| Phase | Scope | Timeline |
|-------|-------|----------|
| **Phase 1** | Dashboard + Trigger + Report Viewer | 1 week |
| **Phase 2** | Suite Manager + Schedule Manager | 1 week |
| **Phase 3** | Memory Inspector + Trends + Cost | 1 week |
| **Phase 4** | Config Editor + Replay + Multi-app | 2 weeks |

---

*This portal is optional for MVP. The agent works fully via CLI and CI/CD without it.*
