# Stage 2: Build

TDD implementation. Tests may be written and run at any time. The design gate applies only before generating the ruleset.

## Instructions

### Step 1: Determine Mode

**Solo mode** (default): implement in the current working directory.

**Parallel mode**: use when the design's test plan has multiple independent sub-tasks that can be built simultaneously. In parallel mode:
1. Generate a task ID: `python3 -c "import uuid; print(uuid.uuid4())"`
2. For each agent, create a worktree:
   ```bash
   git worktree add .claude/worktrees/<task-slug> -b <task-slug>
   ```
3. Each agent writes its status to `.claude/state/tasks/<agent-id>.json` — not a shared file
4. When all agents complete, merge worktrees back and proceed to Step 4

### Step 2: Write Tests

Tests may be written and run at any time — no design approval required.

- Write test cases that define the expected behavior of the ruleset
- Tests must fail at this point (implementation doesn't exist yet)
- Verify tests fail: `bash .claude/hooks/run-tests.sh --expect-fail`

### Step 3: Generate the Ruleset

The design gate applies here. Before generating any ruleset output:
- Read `pipeline/design.md` — if it doesn't exist, run `/design` first.
- Read `.claude/state/state.json` — if `phase` is not `design` or `phase_status` is not `pass`, stop and confirm the design is complete.

Then implement only what is needed to make the tests pass:
- No speculative features, no dead code
- All functions must have full type annotations
- No silent failures — all error paths must be explicit

**If the implementation touches `app/templates/**` or class strings in `app/static/js/**`:**
- Read `.claude/docs/ui-style-guide.md` **before writing any HTML or class strings**.
- Apply the decision tree to every element: USWDS component → only `.usa-*` classes; our own markup → Tailwind utilities only with USWDS tokens via the theme.
- Do not use USWDS utility classes (`margin-y-*`, `padding-*`, `width-tablet-*`, `display-flex`, `flex-align-*`, `font-sans-*`, `text-bold`, `radius-*`, USWDS `text-primary` / `bg-base-*` utility classes).
- Do not write inline `style="..."` attributes.
- Do not build Tailwind clones of USWDS components (`usa-alert`, `usa-summary-box`, `usa-tag`, `usa-card`, `usa-modal`, `usa-accordion`, …).
- If a needed token is missing from `tailwind.config.js`, extend the Tailwind theme rather than reaching for a USWDS utility class.

Verify all tests pass:

```bash
bash .claude/hooks/run-tests.sh
```

All tests must pass before proceeding to Step 4. Fix any failures before continuing.

### Step 4: Run Analysis Suite

```bash
bash .claude/hooks/analyze/run-all.sh
```

This runs: syntax, type checking, secrets detection, injection patterns, dependency CVEs, SAST, test coverage, complexity (warning only), and UI consistency (warning only — flags USWDS/Tailwind mixing in `app/templates/**`).

**If any gate blocks:** resolve the finding and re-run the failing check before proceeding. Do not proceed to `/review` with open blockers.

Gate failures include an explanation of what was found and how to resolve it. Read the explanation before attempting a fix.

### Step 5: Update State

On success:
```bash
python3 - << 'PYEOF'
import json
from datetime import datetime, timezone

state_file = '.claude/state/state.json'
with open(state_file) as f:
    state = json.load(f)
state['phase'] = 'build'
state['phase_status'] = 'pass'
state['last_checkpoint'] = datetime.now(timezone.utc).isoformat()
with open(state_file, 'w') as f:
    json.dump(state, f, indent=2)
print('State updated: build/pass')
PYEOF
```

On failure (blocked gate):
```bash
python3 - << 'PYEOF'
import json
from datetime import datetime, timezone

state_file = '.claude/state/state.json'
with open(state_file) as f:
    state = json.load(f)
state['phase'] = 'build'
state['phase_status'] = 'fail'
state['last_checkpoint'] = datetime.now(timezone.utc).isoformat()
with open(state_file, 'w') as f:
    json.dump(state, f, indent=2)
print('State updated: build/fail')
PYEOF
```

### Step 6: Proceed to Review

Once state is `build/pass`, run `/review`.
