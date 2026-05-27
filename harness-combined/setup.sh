#!/usr/bin/env bash
# Install harness-combined into a target project.
# Usage: bash setup.sh [project-dir]
# Default project-dir is the current directory.
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${1:-.}" && pwd)"

echo "Installing harness-combined into: $PROJECT_DIR"

# ── Commands ──────────────────────────────────────────────────────────────────
CMD_DIR="$PROJECT_DIR/.claude/commands"
mkdir -p "$CMD_DIR"
cp "$HARNESS_DIR/commands/"*.md "$CMD_DIR/"
echo "  ✓ commands → .claude/commands/"

# ── MCP server ────────────────────────────────────────────────────────────────
MCP_FILE="$PROJECT_DIR/.mcp.json"
if [[ -f "$MCP_FILE" ]]; then
    if grep -q '"harness"' "$MCP_FILE" 2>/dev/null; then
        echo "  ✓ .mcp.json already has harness server — skipped"
    else
        python3 - "$MCP_FILE" "$HARNESS_DIR" <<'EOF'
import json, sys
path, harness_dir = sys.argv[1], sys.argv[2]
data = json.loads(open(path).read())
data.setdefault("mcpServers", {})["harness"] = {
    "command": "python3",
    "args": [f"{harness_dir}/server.py"]
}
open(path, "w").write(json.dumps(data, indent=2) + "\n")
EOF
        echo "  ✓ .mcp.json updated"
    fi
else
    python3 - "$MCP_FILE" "$HARNESS_DIR" <<'EOF'
import json, sys
path, harness_dir = sys.argv[1], sys.argv[2]
data = {"mcpServers": {"harness": {
    "command": "python3",
    "args": [f"{harness_dir}/server.py"]
}}}
open(path, "w").write(json.dumps(data, indent=2) + "\n")
EOF
    echo "  ✓ .mcp.json created"
fi

# ── Hooks ─────────────────────────────────────────────────────────────────────
SETTINGS_FILE="$PROJECT_DIR/.claude/settings.json"
mkdir -p "$PROJECT_DIR/.claude"
if [[ -f "$SETTINGS_FILE" ]]; then
    if grep -q "pre_write_guard" "$SETTINGS_FILE" 2>/dev/null; then
        echo "  ✓ .claude/settings.json already has hooks — skipped"
    else
        python3 - "$SETTINGS_FILE" "$HARNESS_DIR" <<'EOF'
import json, sys
path, harness_dir = sys.argv[1], sys.argv[2]
data = json.loads(open(path).read()) if open(path).read().strip() else {}
data.setdefault("hooks", {})
data["hooks"].setdefault("PreToolUse", []).append({
    "matcher": "Write|Edit|MultiEdit",
    "hooks": [{"type": "command", "command": f"python3 {harness_dir}/hooks/pre_write_guard.py"}]
})
data["hooks"].setdefault("PostToolUse", []).append({
    "matcher": "Write|Edit|MultiEdit",
    "hooks": [{"type": "command", "command": f"python3 {harness_dir}/hooks/post_write_gate.py"}]
})
data["hooks"].setdefault("Stop", []).append({
    "hooks": [{"type": "command", "command": f"python3 {harness_dir}/hooks/stop_full_gate.py"}]
})
open(path, "w").write(json.dumps(data, indent=2) + "\n")
EOF
        echo "  ✓ .claude/settings.json updated with hooks"
    fi
else
    python3 - "$SETTINGS_FILE" "$HARNESS_DIR" <<'EOF'
import json, sys
path, harness_dir = sys.argv[1], sys.argv[2]
data = {"hooks": {
    "PreToolUse": [{"matcher": "Write|Edit|MultiEdit", "hooks": [
        {"type": "command", "command": f"python3 {harness_dir}/hooks/pre_write_guard.py"}
    ]}],
    "PostToolUse": [{"matcher": "Write|Edit|MultiEdit", "hooks": [
        {"type": "command", "command": f"python3 {harness_dir}/hooks/post_write_gate.py"}
    ]}],
    "Stop": [{"hooks": [
        {"type": "command", "command": f"python3 {harness_dir}/hooks/stop_full_gate.py"}
    ]}]
}}
open(path, "w").write(json.dumps(data, indent=2) + "\n")
EOF
    echo "  ✓ .claude/settings.json created with hooks"
fi

# ── CLAUDE.md ─────────────────────────────────────────────────────────────────
if [[ -f "$PROJECT_DIR/CLAUDE.md" ]]; then
    echo "  ✓ CLAUDE.md already exists — skipped (not overwriting)"
else
    cp "$HARNESS_DIR/CLAUDE.md" "$PROJECT_DIR/CLAUDE.md"
    echo "  ✓ CLAUDE.md copied to project root"
fi

# ── Python dependencies ───────────────────────────────────────────────────────
echo ""
echo "Checking Python tool dependencies..."
for tool in python3 mypy ruff bandit pytest; do
    if command -v "$tool" >/dev/null 2>&1; then
        echo "  ✓ $tool"
    else
        echo "  ✗ $tool — not found (install with: pip install $tool)"
    fi
done

echo ""
echo "Done. Open Claude Code in $PROJECT_DIR and run /init"
