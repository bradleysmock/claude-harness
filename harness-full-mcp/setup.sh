#!/usr/bin/env bash
# Install the harness-full-mcp Claude plugin.
# Run once from the repo root or from the harness-full-mcp/ directory.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HARNESS_DIR="$REPO_ROOT/harness-full"
MCP_DIR="$SCRIPT_DIR"
VENV="$MCP_DIR/.venv"

# ── Python ────────────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 not found" >&2
    exit 1
fi
echo "Python: $(python3 --version)"

# ── Venv ──────────────────────────────────────────────────────────────────────
echo "==> Creating venv at $VENV"
python3 -m venv "$VENV"

# ── Dependencies ──────────────────────────────────────────────────────────────
echo "==> Installing mcp"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet "mcp>=1.0"

echo "==> Installing harness-full"
"$VENV/bin/pip" install --quiet -e "$HARNESS_DIR"

# ── Plugin registration ───────────────────────────────────────────────────────
if command -v claude &>/dev/null; then
    echo "==> Registering marketplace"
    claude plugin marketplace add "$REPO_ROOT" 2>/dev/null \
        || echo "  (already registered)"

    echo "==> Installing plugin"
    claude plugin install harness-full-mcp@bradleysmock-plugins 2>/dev/null \
        || echo "  (already installed)"
else
    echo ""
    echo "Note: 'claude' CLI not found. Register manually inside Claude Code:"
    echo "  /plugin marketplace add $REPO_ROOT"
    echo "  /plugin install harness-full-mcp@bradleysmock-plugins"
fi

echo ""
echo "Done."
echo "Test locally: claude --plugin-dir $MCP_DIR"
