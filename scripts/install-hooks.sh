#!/bin/sh
# Installs Kavach's git hooks (currently: pre-push) into .git/hooks/.
# Run once after cloning: sh scripts/install-hooks.sh
# Works on Windows Git Bash, Linux, and macOS.

set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"

cp "$REPO_ROOT/scripts/pre-push" "$HOOKS_DIR/pre-push"
chmod +x "$HOOKS_DIR/pre-push"

echo "Installed pre-push hook -> $HOOKS_DIR/pre-push"
echo "See VALIDATION_PROTOCOL.md for what it runs and when."
