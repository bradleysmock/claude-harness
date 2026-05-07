#!/usr/bin/env bash
# .claude/hooks/init-pipeline.sh
# Initialises a new pipeline run, creating the state file and directory structure.

set -euo pipefail

STATE_FILE="${PIPELINE_STATE_FILE:-.claude/state/pipeline.json}"
LOG_FILE="${PIPELINE_LOG_FILE:-.claude/state/pipeline.log}"
RUN_ID=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Create required directories
mkdir -p .claude/state pipeline src tests docs/architecture pipeline

# Check if a pipeline is already in progress
if [[ -f "$STATE_FILE" ]]; then
  EXISTING_STATUS=$(python3 -c "
import json, sys
try:
  with open('$STATE_FILE') as f:
    d = json.load(f)
  completed = all(
    d.get('stages', {}).get(s, {}).get('status') == 'PASS'
    for s in ['stage1','stage2','stage3','stage4','stage5','stage6']
  )
  in_progress = any(
    d.get('stages', {}).get(s, {}).get('status') in ('IN_PROGRESS', 'ESCALATED', 'FAIL')
    for s in ['stage1','stage2','stage3','stage4','stage5','stage6']
  )
  if completed:
    print('COMPLETE')
  elif in_progress:
    print('IN_PROGRESS')
  else:
    print('PARTIAL')
except Exception:
  print('NONE')
" 2>/dev/null || echo "NONE")

  if [[ "$EXISTING_STATUS" == "IN_PROGRESS" || "$EXISTING_STATUS" == "PARTIAL" ]]; then
    echo "⚠️  An existing pipeline run was found."
    echo "    To resume, run: /status"
    echo "    To restart, delete .claude/state/pipeline.json and re-run /run-pipeline"
    exit 0
  fi
fi

# Initialise fresh state
python3 -c "
import json
from datetime import datetime

state = {
  'run_id': '$RUN_ID',
  'started_at': '$TIMESTAMP',
  'pipeline_version': '${PIPELINE_VERSION:-1.0.0}',
  'stages': {
    'stage1': {'status': 'NOT_STARTED', 'timestamp': None, 'score': None, 'findings': []},
    'stage2': {'status': 'NOT_STARTED', 'timestamp': None, 'score': None, 'findings': []},
    'stage3': {'status': 'NOT_STARTED', 'timestamp': None, 'score': None, 'findings': []},
    'stage4': {'status': 'NOT_STARTED', 'timestamp': None, 'score': None, 'findings': []},
    'stage5': {'status': 'NOT_STARTED', 'timestamp': None, 'score': None, 'findings': []},
    'stage6': {'status': 'NOT_STARTED', 'timestamp': None, 'score': None, 'findings': []}
  },
  'metrics': {},
  'component': None
}

with open('$STATE_FILE', 'w') as f:
  json.dump(state, f, indent=2)
print('Pipeline initialised. Run ID: $RUN_ID')
"

# Create log entry
echo "[$TIMESTAMP] [INIT] Pipeline run $RUN_ID started" >> "$LOG_FILE"

echo "✅ Pipeline initialised"
echo "   Run ID: $RUN_ID"
echo "   State:  $STATE_FILE"
echo ""
echo "NEXT: Run /intake to begin Stage 1"
