#!/usr/bin/env bash
# .claude/hooks/on-stop.sh
# Updates last_checkpoint in state.json when the session ends.

set -euo pipefail

STATE_FILE=".claude/state/state.json"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

if [[ -f "$STATE_FILE" ]]; then
  python3 - "$STATE_FILE" "$TIMESTAMP" << 'PYEOF'
import json, sys
state_file, timestamp = sys.argv[1], sys.argv[2]
with open(state_file) as f:
    state = json.load(f)
state['last_checkpoint'] = timestamp
with open(state_file, 'w') as f:
    json.dump(state, f, indent=2)
PYEOF
fi

exit 0
