#!/usr/bin/env bash
# Install harness-no-api-key into a target project.
# Usage: bash setup.sh [project-dir]
# Default project-dir is the current directory.
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${1:-.}" && pwd)"

echo "Installing harness into: $PROJECT_DIR"

# ── Commands ──────────────────────────────────────────────────────────────────
CMD_DIR="$PROJECT_DIR/.claude/commands/harness"
mkdir -p "$CMD_DIR"
cp "$HARNESS_DIR/commands/"*.md "$CMD_DIR/"
echo "  ✓ commands → .claude/commands/harness/"

# ── MCP server ────────────────────────────────────────────────────────────────
MCP_FILE="$PROJECT_DIR/.mcp.json"
if [[ -f "$MCP_FILE" ]]; then
    # Merge: add harness server if not already present
    if grep -q '"harness"' "$MCP_FILE" 2>/dev/null; then
        echo "  ✓ .mcp.json already has harness server — skipped"
    else
        # Insert before the closing } of mcpServers using python
        python3 - "$MCP_FILE" "$HARNESS_DIR" <<'EOF'
import json, sys
path, harness_dir = sys.argv[1], sys.argv[2]
data = json.loads(open(path).read())
data.setdefault("mcpServers", {})["harness"] = {"command": f"{harness_dir}/bin/harness-server"}
open(path, "w").write(json.dumps(data, indent=2) + "\n")
EOF
        echo "  ✓ .mcp.json updated"
    fi
else
    python3 - "$MCP_FILE" "$HARNESS_DIR" <<'EOF'
import json, sys
path, harness_dir = sys.argv[1], sys.argv[2]
data = {"mcpServers": {"harness": {"command": f"{harness_dir}/bin/harness-server"}}}
open(path, "w").write(json.dumps(data, indent=2) + "\n")
EOF
    echo "  ✓ .mcp.json created"
fi

echo ""
echo "Done. Open Claude Code in $PROJECT_DIR and run /harness:init"
