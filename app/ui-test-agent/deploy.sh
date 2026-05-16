#!/bin/bash
# UI Test Agent — Deployment Script
# Version: 0.1.0
# Prerequisites: npm install -g @aws/agentcore, AWS credentials configured

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
AGENT_NAME="ui-test-agent"
REGION="${AWS_REGION:-us-west-2}"
VERSION=$(cat "$PROJECT_ROOT/VERSION" 2>/dev/null || echo "unknown")

echo "🚀 UI Test Agent Deployment v${VERSION}"
echo "   Agent:  $AGENT_NAME"
echo "   Region: $REGION"
echo ""

# Navigate to project root
cd "$PROJECT_ROOT"

# Create project if not exists
if [ ! -f "agentcore/agentcore.json" ]; then
  echo "📦 Creating AgentCore project..."
  agentcore create --name "$AGENT_NAME" --model-provider bedrock
else
  echo "📦 Project already exists, updating..."
fi

# Deploy (agentcore CLI handles idempotent tool/resource creation from harness.json)
echo "☁️  Deploying to AWS ($REGION)..."
agentcore deploy

echo ""
echo "✅ Deployment complete! (v${VERSION})"
echo ""
echo "Usage:"
echo "  # Interactive testing"
echo "  agentcore dev"
echo ""
echo "  # CLI invocation"
echo "  agentcore invoke --harness $AGENT_NAME \\"
echo "    --session-id \"\$(uuidgen)\" \\"
echo "    \"Test the login page at https://staging.example.com/login\""
echo ""
echo "  # Programmatic invocation"
echo "  python app/$AGENT_NAME/invoke.py \\"
echo "    --harness-arn <ARN> \\"
echo "    --url https://staging.example.com \\"
echo "    --test-cases 'Login with valid credentials' 'Login with invalid password'"
