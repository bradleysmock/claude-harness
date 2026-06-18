#!/usr/bin/env bash
# net-guard.sh — PreToolUse hook.
# Blocks Write/Edit/NotebookEdit to any file recorded in .test-harness/frozen-net.txt.
# This is the mechanical enforcement of net immutability: once a characterization
# net is frozen, the generator physically cannot edit it. Reads the tool-call JSON
# from stdin; exit 2 (with a stderr reason) denies the tool call in Claude Code.

set -euo pipefail

MANIFEST="${CLAUDE_PROJECT_DIR:-$PWD}/.test-harness/frozen-net.txt"
[ -f "$MANIFEST" ] || exit 0   # nothing frozen yet → allow

python3 - "$MANIFEST" <<'PY'
import json, os, sys

manifest = sys.argv[1]
try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)  # can't parse → don't block

ti = payload.get("tool_input", {}) or {}
target = ti.get("file_path") or ti.get("path") or ti.get("notebook_path")
if not target:
    sys.exit(0)

def norm(p):
    return os.path.realpath(os.path.expanduser(p))

t = norm(target)
frozen = []
with open(manifest) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        frozen.append(norm(line.split("\t", 1)[0]))

if t in frozen:
    sys.stderr.write(
        f"BLOCKED by test-harness: {os.path.basename(t)} is part of a FROZEN "
        f"characterization net and is immutable. If behavior must change, stop and "
        f"escalate to a human — do not edit the net to make a test pass.\n"
    )
    sys.exit(2)   # deny the tool call

sys.exit(0)
PY
