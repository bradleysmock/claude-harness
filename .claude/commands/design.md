# Design

Collaboratively clarify requirements and produce `pipeline/design.md`.

## Instructions

### Step 1: Understand the Request

Ask clarifying questions until you can answer all of the following:
- What specific capability or change is needed?
- What does success look like? (acceptance criteria)
- What is explicitly out of scope?
- Are there performance, security, or compatibility constraints?
- What are the interface boundaries? (API endpoints, function signatures, data schemas)

Do not proceed to Step 2 until the above are clear.

### Step 2: Detect High-Risk Patterns

Scan the requirements for patterns that require human review before building:
- Authentication or authorization logic
- Cryptography, key management, or token handling
- PII collection, storage, or transmission
- Payment processing
- External service integrations with credentials

If any are present, flag them in the `## Risk Flags` section of the design artifact and note that human review is required before `/build`.

### Step 3: Produce the Design Artifact

Write `pipeline/design.md` using the template at `.claude/templates/design.md`.

Fill all five sections:
1. **Problem** — task statement and success criteria
2. **Approach** — high-level strategy, module structure, patterns chosen
3. **Interface Contracts** — all public signatures, endpoints, schemas, error types
4. **Decisions** — one entry per meaningful choice: decided / rejected (why) / consequence
5. **Test Plan** — table: acceptance criterion → test case → test type → expected result

The Decisions section is the most valuable for future readers. Be specific about what alternatives were considered and why they were rejected.

### Step 3a: UI Plan (when templates change)

If the design touches `app/templates/**` or class strings in `app/static/js/**`, **read `.claude/docs/ui-style-guide.md` before continuing** and add a `## UI Plan` section to `pipeline/design.md` with:

- **USWDS components used** — list each canonical component (e.g., `usa-button`, `usa-modal`, `usa-summary-box`, `usa-step-indicator`). Confirm each will carry only `.usa-*` classes per Rule 1.
- **Custom (non-USWDS) markup** — list each block of our own markup and the Tailwind utilities planned for it (layout, spacing, color tokens). Confirm Tailwind-only per Rule 2.
- **HTMX/Alpine considerations** — call out any USWDS component delivered via HTMX swap or Alpine that needs a re-init branch in `app/static/js/htmx-uswds-bridge.js`.
- **Confirmation:** state explicitly that the design uses no USWDS utility classes (`margin-y-*`, `padding-*`, `width-tablet-*`, `text-primary` as a USWDS class, `bg-base-*` as a USWDS class, `display-flex`, `flex-align-*`, `font-sans-*`, `text-bold`, `radius-*`), no inline `style="..."` attributes, and no Tailwind clones of USWDS components (Rules 3 and 4).

A diff that doesn't touch templates or class strings can omit this section.

### Step 4: Update State

```bash
python3 - << 'PYEOF'
import json, os
from datetime import datetime, timezone
import uuid

state_file = '.claude/state/state.json'
os.makedirs('.claude/state', exist_ok=True)
os.makedirs('.claude/state/tasks', exist_ok=True)

state = {
    'task_id': str(uuid.uuid4()),
    'started_at': datetime.now(timezone.utc).isoformat(),
    'mode': 'solo',
    'phase': 'design',
    'phase_status': 'pass',
    'last_checkpoint': datetime.now(timezone.utc).isoformat()
}
with open(state_file, 'w') as f:
    json.dump(state, f, indent=2)
print('State updated: design/pass')
PYEOF
```

### Step 5: Request Approval

Present the design to the user and ask for approval before proceeding to `/build`.

If the design contains risk flags, explicitly note that human review of those sections is required before building.
