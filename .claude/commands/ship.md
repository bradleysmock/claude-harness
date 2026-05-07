# Ship

Run integration tests, verify NFRs, update CHANGELOG, and mark the task complete.

## Instructions

### Step 1: Verify Critique is Complete

Read `.claude/state/state.json`. If `phase` is not `critique` or `phase_status` is not `pass`, stop. Resolve any open findings in `/critique` first.

### Step 2: Run Integration Tests

Run the full test suite end-to-end with real dependencies (not mocks):

```bash
bash .claude/hooks/run-tests.sh
```

All tests must pass. If any fail, fix them before proceeding — do not ship with failing integration tests.

### Step 3: Verify NFRs (if stated in design)

Check `pipeline/design.md` for any non-functional requirements (performance, latency, throughput). If present, verify them:

- **Latency**: run a load test or benchmark and compare to the stated threshold
- **Throughput**: measure under stated load conditions
- **Memory**: profile under peak load if specified

If NFRs are not stated in the design, skip this step.

### Step 4: Write or Update README

Check whether a `README.md` exists in the output directory (typically `src/<project>/`).

- **If it does not exist**: create one with: project name, one-sentence description, how to run it, all commands/flags with examples, any required environment variables, and how to run the tests.
- **If it exists**: verify the running instructions reflect the current interface. Update any commands or options that have changed.

The README must be accurate and sufficient for someone who has never seen the code to run the project.

### Step 5: Update CHANGELOG

Append an entry to `CHANGELOG.md` (create it if it doesn't exist):

```markdown
## [Unreleased] — <date>

### Added / Changed / Fixed
- <one-line description of what changed and why>

### Quality
- Test coverage: XX% line, XX% branch
- SAST: 0 HIGH/CRITICAL findings
```

### Step 6: Update State

```bash
python3 - << 'PYEOF'
import json
from datetime import datetime, timezone

state_file = '.claude/state/state.json'
with open(state_file) as f:
    state = json.load(f)
state['phase'] = 'ship'
state['phase_status'] = 'pass'
state['last_checkpoint'] = datetime.now(timezone.utc).isoformat()
with open(state_file, 'w') as f:
    json.dump(state, f, indent=2)
print('State updated: ship/pass — task complete')
PYEOF
```

### Step 7: Report

Summarize:
- What was built (one paragraph)
- Test results (counts, coverage)
- Any NFR results
- Any findings from review and how they were resolved
- What was explicitly deferred (from the design's Decisions section)
