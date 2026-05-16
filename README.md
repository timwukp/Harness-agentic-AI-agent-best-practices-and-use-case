# AWS Bedrock AgentCore Harness — Use Cases & Best Practices

Production-ready reference for building AI agents with **Amazon Bedrock AgentCore Harness** (Public Preview).

## What is AgentCore Harness?

A fully managed agent orchestration layer within AgentCore. You declare what your agent does (model, tools, instructions) via configuration — AWS handles the compute, memory, identity, networking, and observability.

**Key differentiator:** Config change, not code rewrite.

## Applications

### UI Test Agent

An AI agent that replaces human QA testers in the SDLC. It navigates web UIs, interacts with elements, observes results, and produces structured test reports.

- [Design Document](docs/DESIGN_UI_TEST_AGENT.md)
- [Harness Config](app/ui-test-agent/harness.json)
- [Invoke Script](app/ui-test-agent/invoke.py)
- [Deploy Script](app/ui-test-agent/deploy.sh)

## Documentation

- [Best Practices (English)](docs/BEST_PRACTICES.md)
- [Best Practices (中文)](docs/BEST_PRACTICES_zh-TW.md)

## Project Structure

```
aws-harness-agentcore-use-case/
├── README.md
├── docs/
│   ├── BEST_PRACTICES.md
│   ├── BEST_PRACTICES_zh-TW.md
│   └── DESIGN_UI_TEST_AGENT.md
└── app/
    └── ui-test-agent/
        ├── harness.json              # Harness configuration
        ├── invoke.py                 # Orchestrator script (boto3)
        ├── deploy.sh                 # Deployment script
        └── skills/
            └── ui-testing/
                └── SKILL.md          # Domain knowledge for the agent
```

## Quick Start

```bash
# Install CLI
npm install -g @aws/agentcore

# Deploy the UI test agent
cd app/ui-test-agent
./deploy.sh

# Or test locally
agentcore dev
```

## Prerequisites

- Node.js 20+
- Python 3.10+ (for invoke script)
- AWS credentials configured
- Preview region access (us-east-1, us-west-2, eu-central-1, ap-southeast-2)

## License

Apache-2.0
