# Flow: write-spec — ticket mode

Read the approved `solution.md` and derive specs directly. The design phase already explored the codebase; do not re-explore.

<!-- progress-checklist -->
**Progress checklist** — as the first action, create the `TodoWrite` checklist (see "Progress checklist" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`):

`Analyze (spec vs task DAG) · Write spec(s)`

## Step 1 — Resolve ticket and score design artifacts

Scan `.tickets/` for the ticket matching `$ARGUMENTS`; if not found, scan `.tickets/completed/`. Read `status.md`, `solution.md`, `requirements.md`, `problem.md`. Use whichever location the ticket is found in for all subsequent file references in this flow.

Resolve status via the **Ticket resolution** rule in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`: when the claim-time worktree `.worktrees/XXXX-<slug>` exists, its `.tickets/` copy of `status.md` and the design artifacts it holds are authoritative; the root copy shows only claim/terminal states.

Confirm `status` is `solution`. If not, tell the user to run `/problem XXXX` first (or `/refine XXXX` if `solution.md` exists but needs work) and stop.

Read `${CLAUDE_PLUGIN_ROOT}/context/score-spec.md` in full and apply the checks against this ticket's `requirements.md` and `solution.md`. If the verdict is BLOCK, show the failing checks and stop — the lead must fix the design artifacts before spec generation can proceed. If WARN, show the warnings and continue.

## Step 2 — Read only the named files

- `solution.md` → Components section names the modules to write.
- `solution.md` → Implementation Order section names the sequence.
- `requirements.md` → Acceptance Criteria become spec acceptance criteria.

Read only the files named in the Components section. Do not explore the full codebase.

## Step 3 — Choose single spec or task DAG

- **Single spec** — if the solution has only one component, or all components can be tested in one file.
- **Task (multi-spec DAG)** — if the solution has 2–6 components with clear one-way dependencies.

Tell the user which path in one sentence.

## Step 4 — Write spec files

Write each spec to `.harness/specs/XXXX-<slug>-<component>.py`:

```python
from harness import Spec

spec = Spec(
    id="XXXX-<slug>-<component>",
    description="One precise paragraph. What, not how.",
    constraints=[
        # Name the class, method, or pattern from solution.md. Be specific.
    ],
    acceptance_criteria=[
        # One testable assertion each. From requirements.md acceptance criteria.
    ],
    target_file="src/module.py",
    reference_files=["src/related.py"],
    language="python",  # python | typescript | go | rust
)
```

## Step 5 — Write task file (if multi-spec)

Write `.harness/tasks/XXXX-<slug>.py`:

```python
from harness import Task, TaskSpec

task = Task(
    id="XXXX-<slug>",
    description="<from solution.md Approach section>",
    specs=[
        TaskSpec(spec_id="XXXX-<slug>-<component-a>", depends_on=[]),
        TaskSpec(spec_id="XXXX-<slug>-<component-b>", depends_on=["XXXX-<slug>-<component-a>"]),
    ]
)
```

## Step 6 — Report

Tell the user: "Specs written. Run `/build XXXX` to implement."
