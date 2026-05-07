#!/usr/bin/env bash
# .claude/hooks/check-gate.sh
# Checks whether a given stage (or all stages) has passed.
# Usage:   bash .claude/hooks/check-gate.sh <stage|all>
# Returns: 0 (pass), 1 (not passed), 2 (state file missing)

set -euo pipefail

TARGET="${1:-all}"
STATE_FILE="${PIPELINE_STATE_FILE:-.claude/state/pipeline.json}"

if [[ ! -f "$STATE_FILE" ]]; then
  echo "❌ Pipeline state file not found at $STATE_FILE"
  echo "   Run /run-pipeline or bash .claude/hooks/init-pipeline.sh to begin."
  exit 2
fi

python3 - "$TARGET" "$STATE_FILE" << 'PYEOF'
import json, sys

target, state_file = sys.argv[1:]

with open(state_file) as f:
    state = json.load(f)

STAGE_ORDER = ['stage1', 'stage2', 'stage3', 'stage4', 'stage5', 'stage6']
STAGE_NAMES = {
    'stage1': 'Intake & Validation',
    'stage2': 'Design Synthesis',
    'stage3': 'Code Generation',
    'stage4': 'Static & Security Analysis',
    'stage5': 'Semantic Review',
    'stage6': 'Integration & Delivery',
}

STATUS_ICON = {
    'PASS': '✅', 'APPROVED': '✅',
    'FAIL': '❌', 'REJECTED': '❌',
    'IN_PROGRESS': '⏳',
    'ESCALATED': '⚠️',
    'NOT_STARTED': '—',
}

def stage_passed(s):
    status = state.get('stages', {}).get(s, {}).get('status', 'NOT_STARTED')
    return status in ('PASS', 'APPROVED')

if target == 'all':
    print(f"\nPIPELINE STATUS  (Run: {state.get('run_id', 'unknown')})")
    print("─" * 58)
    print(f"{'Stage':<8} {'Name':<30} {'Status':<14} {'Time'}")
    print("─" * 58)
    for s in STAGE_ORDER:
        info = state.get('stages', {}).get(s, {})
        status = info.get('status', 'NOT_STARTED')
        icon = STATUS_ICON.get(status, '?')
        ts = info.get('timestamp', '—') or '—'
        ts_short = ts[:16] if ts != '—' else '—'
        num = s.replace('stage', '')
        print(f"  {num:<6} {STAGE_NAMES[s]:<30} {icon} {status:<12} {ts_short}")
    print("─" * 58)
    all_pass = all(stage_passed(s) for s in STAGE_ORDER)
    if all_pass:
        print("\n🎉 Pipeline complete — ready for merge\n")
        sys.exit(0)
    else:
        next_stage = next((s for s in STAGE_ORDER if not stage_passed(s)), None)
        if next_stage:
            print(f"\nNEXT: Run /{next_stage.replace('stage', '')} → {STAGE_NAMES[next_stage]}\n")
        sys.exit(1)
else:
    if stage_passed(target):
        print(f"✅ {target} ({STAGE_NAMES.get(target, target)}): PASSED")
        sys.exit(0)
    else:
        info = state.get('stages', {}).get(target, {})
        status = info.get('status', 'NOT_STARTED')
        print(f"❌ {target} ({STAGE_NAMES.get(target, target)}): {status}")
        findings = info.get('findings', [])
        if findings:
            print("   Findings:")
            for f in findings[-3:]:
                print(f"   • {f.get('message', '')}")
        sys.exit(1)
PYEOF
