#!/usr/bin/env bash
# .claude/hooks/update-state.sh
# Updates the pipeline state file for a given stage.
# Usage: bash .claude/hooks/update-state.sh <stage> <status> [score] [message]

set -euo pipefail

STAGE="${1:-}"
STATUS="${2:-}"
SCORE="${3:-}"
MESSAGE="${4:-}"
STATE_FILE="${PIPELINE_STATE_FILE:-.claude/state/pipeline.json}"
LOG_FILE="${PIPELINE_LOG_FILE:-.claude/state/pipeline.log}"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

if [[ -z "$STAGE" || -z "$STATUS" ]]; then
  echo "Usage: update-state.sh <stage> <status> [score] [message]" >&2
  exit 1
fi

# Initialise state file if missing
if [[ ! -f "$STATE_FILE" ]]; then
  mkdir -p "$(dirname "$STATE_FILE")"
  bash .claude/hooks/init-pipeline.sh > /dev/null 2>&1
fi

python3 - "$STAGE" "$STATUS" "$SCORE" "$MESSAGE" "$TIMESTAMP" "$STATE_FILE" << 'EOF'
import json, sys

stage, status, score, message, timestamp, state_file = sys.argv[1:]

with open(state_file) as f:
    state = json.load(f)

if stage not in state['stages']:
    state['stages'][stage] = {}

state['stages'][stage].update({
    'status': status,
    'timestamp': timestamp,
    'score': score if score else None,
})

if message:
    findings = state['stages'][stage].get('findings', [])
    findings.append({'timestamp': timestamp, 'message': message})
    state['stages'][stage]['findings'] = findings

with open(state_file, 'w') as f:
    json.dump(state, f, indent=2)

print(f"State updated: {stage} → {status}")
EOF

echo "[$TIMESTAMP] [$STAGE] $STATUS${SCORE:+ (score: $SCORE)}${MESSAGE:+ — $MESSAGE}" >> "$LOG_FILE"
