#!/usr/bin/env bash
# .claude/hooks/pre-bash.sh
# Safety filter before any bash command executes.
# Hard-blocks destructive patterns and explains why.

set -euo pipefail

COMMAND="${CLAUDE_TOOL_INPUT:-}"
LOG_FILE=".claude/state/pipeline.log"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# ── Hard blocks ───────────────────────────────────────────────
block_if_match() {
  local pattern="$1"
  local reason="$2"
  if echo "$COMMAND" | grep -q "$pattern" 2>/dev/null; then
    echo ""
    echo "❌  BLOCKED: Dangerous command pattern detected"
    echo "    Pattern:  $pattern"
    echo "    Reason:   $reason"
    echo "    Command:  $COMMAND"
    echo "[$TIMESTAMP] [PRE-BASH] BLOCKED: $COMMAND" >> "$LOG_FILE" 2>/dev/null || true
    exit 2
  fi
}

block_if_match 'rm -rf /'            "Deletes the entire filesystem"
block_if_match 'rm -rf \*'           "Recursively deletes everything in the current path"
block_if_match 'mkfs'                "Formats a disk, destroying all data"
block_if_match 'dd if=/dev/zero'     "Overwrites disk with zeros"
block_if_match 'chmod -R 777 /'      "Removes all filesystem permissions"
block_if_match ':(){ :|:& };:'       "Fork bomb — crashes the system via process exhaustion"
block_if_match 'curl.*|.*bash'       "Executes untrusted remote code without inspection"
block_if_match 'wget.*|.*bash'       "Executes untrusted remote code without inspection"
block_if_match 'eval.*base64'        "Executes obfuscated code — classic malware pattern"

# ── Sensitive operation logging ───────────────────────────────
SENSITIVE_PATTERNS=('git push' 'npm publish' 'pip install' 'chmod' 'chown' 'sudo')

for pattern in "${SENSITIVE_PATTERNS[@]}"; do
  if echo "$COMMAND" | grep -q "$pattern" 2>/dev/null; then
    echo "[$TIMESTAMP] [PRE-BASH] Sensitive: $COMMAND" >> "$LOG_FILE" 2>/dev/null || true
    break
  fi
done

exit 0
