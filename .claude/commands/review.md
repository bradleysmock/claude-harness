# Review

Launch a fresh review context to adversarially evaluate the implementation against the design.

## Instructions

### Step 1: Verify Build is Complete

Read `.claude/state/state.json`. If `phase` is not `build` or `phase_status` is not `pass`, stop and run `/build` first.

### Step 2: Launch Fresh Review Context

The review runs in a separate context with no implementation history — this eliminates anchoring bias.

**Option A — Subagent (faster):**

Spawn a review subagent with the following context and instructions:

> You are conducting an adversarial code review. You have no prior knowledge of implementation decisions. Your job is to find problems, not validate choices.
>
> Read these files:
> - `pipeline/design.md` — the approved design (source of truth)
> - All changed files in `src/` and `tests/`
> - Test results (run `bash .claude/hooks/run-tests.sh` if not available)
>
> Evaluate against seven dimensions:
> 1. **Correctness** — does it satisfy every acceptance criterion? unhandled inputs? off-by-one errors?
> 2. **Robustness** — input validation at boundaries? all failures explicit? no null dereferences? resource cleanup?
> 3. **Security** — access control? mass assignment? insecure defaults? error info leakage?
> 4. **Performance** — O(n²) operations? N+1 queries? synchronous blocking? unbounded loops?
> 5. **Maintainability** — single responsibility? self-documenting? duplication? magic numbers?
> 6. **Test quality** — tests verify behavior, not implementation? mocks at boundaries only? deterministic?
> 7. **UI consistency** — *only when the diff touches `app/templates/**` or class strings in `app/static/js/**`.* Read `.claude/docs/ui-style-guide.md` first. Verify: (a) USWDS components carry only `.usa-*` classes — no Tailwind utilities mixed onto `usa-button`, `usa-input`, `usa-tag`, `usa-alert`, `usa-modal`, `usa-accordion`, etc.; (b) no USWDS utility classes in our templates (`margin-y-*`, `padding-*`, `width-tablet-*`, `display-flex`, `flex-align-*`, `font-sans-*`, `text-bold`, `radius-*`, USWDS `text-primary` / `bg-base-*` utility classes — Tailwind equivalents exist via `tailwind.config.js`); (c) no inline `style="..."` attributes; (d) no Tailwind clones of existing USWDS components (custom cards that duplicate `usa-summary-box`, `usa-alert`, `usa-tag`, etc.); (e) any USWDS component delivered via HTMX swap that DOM-transforms (combo-box, file-input, date-picker, time-picker, character-counter) has a corresponding re-init branch in `app/static/js/htmx-uswds-bridge.js`. Read the output of `.claude/hooks/analyze/ui-consistency.sh` (in the build's analysis report) — each warning line names a file:line and a violation; cite them as findings.
>
> Produce `pipeline/review-report.md` with:
> - A finding table (severity: CRITICAL / HIGH / MEDIUM / LOW)
> - For each CRITICAL or HIGH finding: file, line, what's wrong, why it matters, suggested fix
> - A recommendation: APPROVE / APPROVE_WITH_CHANGES / REJECT
>
> CRITICAL findings block shipping. HIGH findings require acknowledgment. MEDIUM/LOW are advisory.

**Option B — Fresh session:**

Open a new Claude Code session in this project directory. Paste the review instructions above as the first message.

### Step 3: Resolve Findings

- **CRITICAL**: must be fixed before `/ship`
- **HIGH**: must be acknowledged; fix or document accepted risk
- **MEDIUM / LOW**: advisory; address at discretion

After resolving CRITICAL/HIGH findings, re-run `bash .claude/hooks/analyze/run-all.sh` to confirm fixes don't introduce new issues.

### Step 4: Update State

On approval:
```bash
python3 - << 'PYEOF'
import json
from datetime import datetime, timezone

state_file = '.claude/state/state.json'
with open(state_file) as f:
    state = json.load(f)
state['phase'] = 'review'
state['phase_status'] = 'pass'
state['last_checkpoint'] = datetime.now(timezone.utc).isoformat()
with open(state_file, 'w') as f:
    json.dump(state, f, indent=2)
print('State updated: review/pass')
PYEOF
```

On escalation (CRITICAL findings unresolved):
```bash
python3 - << 'PYEOF'
import json
from datetime import datetime, timezone

state_file = '.claude/state/state.json'
with open(state_file) as f:
    state = json.load(f)
state['phase'] = 'review'
state['phase_status'] = 'escalated'
state['last_checkpoint'] = datetime.now(timezone.utc).isoformat()
with open(state_file, 'w') as f:
    json.dump(state, f, indent=2)
print('State updated: review/escalated — resolve CRITICAL findings before /ship')
PYEOF
```

### Step 5: Proceed to Critique

Once state is `review/pass`, run `/critique`.
