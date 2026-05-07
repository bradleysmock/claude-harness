# Status

Display the current state of the active task.

## Instructions

### Step 1: Read State

```bash
python3 - << 'PYEOF'
import json, os, glob

state_file = '.claude/state/state.json'
tasks_dir = '.claude/state/tasks'

if not os.path.exists(state_file):
    print('No active task. Run /design to start.')
else:
    with open(state_file) as f:
        state = json.load(f)

    phase = state.get('phase', '—')
    phase_status = state.get('phase_status', '—')
    mode = state.get('mode', '—')
    task_id = state.get('task_id', '—')
    started = state.get('started_at', '—')
    checkpoint = state.get('last_checkpoint', '—')

    status_icon = {'pass': '✅', 'fail': '❌', 'escalated': '⚠️', 'in_progress': '⏳'}.get(phase_status, '—')

    print(f'''TASK STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Task ID:    {task_id}
Mode:       {mode}
Started:    {started}
Checkpoint: {checkpoint}

Phase:      {phase} {status_icon} {phase_status}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━''')

    # Next action hint
    next_actions = {
        ('design', 'pass'): 'NEXT: /build',
        ('build', 'pass'): 'NEXT: /review',
        ('build', 'fail'): 'NEXT: Resolve gate failures, then re-run /build',
        ('review', 'pass'): 'NEXT: /critique',
        ('review', 'escalated'): 'NEXT: Resolve CRITICAL findings, then re-run /review',
        ('critique', 'pass'): 'NEXT: /ship',
        ('critique', 'fail'): 'NEXT: Resolve BLOCKERs, return to /build',
        ('ship', 'pass'): 'Task complete.',
    }
    hint = next_actions.get((phase, phase_status), '')
    if hint:
        print(hint)

    # Show parallel agent status if tasks exist
    if os.path.isdir(tasks_dir):
        task_files = glob.glob(f'{tasks_dir}/*.json')
        if task_files:
            print(f'\nPARALLEL AGENTS ({len(task_files)})')
            print('─' * 48)
            for task_file in sorted(task_files):
                with open(task_file) as tf:
                    agent = json.load(tf)
                agent_id = agent.get('agent_id', '?')[:8]
                branch = agent.get('branch', '?')
                status = agent.get('status', '?')
                icon = {'pass': '✅', 'fail': '❌', 'in_progress': '⏳'}.get(status, '—')
                print(f'  {icon} [{agent_id}] {branch} — {status}')
PYEOF
```

### Step 2: Show Design Summary (if available)

If `pipeline/design.md` exists, display the **Problem** section header to confirm what is being built.

### Step 3: Show Open Findings (if build failed)

If phase_status is `fail` or `escalated`, check `pipeline/review-report.md` for any CRITICAL or HIGH findings and list them.
