#!/bin/bash
# Install all git hooks
# Usage: ./hooks/install.sh

set -e

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIT_HOOK_DIR="$(git rev-parse --show-toplevel)/.git/hooks"

echo "Installing git hooks..."

for hook in pre-commit pre-push commit-msg post-merge; do
  if [ -f "$HOOK_DIR/$hook" ]; then
    cp "$HOOK_DIR/$hook" "$GIT_HOOK_DIR/$hook"
    chmod +x "$GIT_HOOK_DIR/$hook"
    echo "  ✅ $hook"
  fi
done

echo ""
echo "All hooks installed. They will run automatically on:"
echo "  pre-commit  → PII scan on staged files"
echo "  pre-push    → Full repo PII scan"
echo "  commit-msg  → Conventional commit format check"
echo "  post-merge  → Auto-install dependencies"
