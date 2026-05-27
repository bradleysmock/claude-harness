Write specs for `$ARGUMENTS`.

**Ticket mode** (argument is a ticket number like `0001` or `0001-add-inventory`):
Reads the approved `solution.md` and derives specs directly — no codebase re-exploration needed since the design phase already did that.

**Standalone mode** (argument is a plain description, not a ticket number):
Explores the codebase first, then writes a spec or task DAG.

---

## Ticket mode

### Step 1 — Resolve ticket

Scan `.tickets/` for the ticket matching `$ARGUMENTS`. Read `status.md`, `solution.md`, `requirements.md`, `problem.md`.

Confirm `status` is `solution`. If not, tell the user to run `/problem XXXX` first (or `/refine XXXX` if solution exists but needs work) and stop.

### Step 2 — Read only the named files

`solution.md` → Components section names the modules to write.
`solution.md` → Implementation Order section names the sequence.
`requirements.md` → Acceptance Criteria become spec acceptance criteria.

Read only the files named in the Components section. Do not explore the full codebase.

### Step 3 — Choose single spec or task DAG

**Single spec** — if the solution has only one component, or all components can be tested in one file.

**Task (multi-spec DAG)** — if the solution has 2–6 components with clear one-way dependencies.

Tell the user which path in one sentence.

### Step 4 — Write spec files

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

### Step 5 — Write task file (if multi-spec)

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

### Step 6 — Report

Tell the user: "Specs written. Run `/build XXXX` to implement."

---

## Standalone mode

### Exploration — do this before writing anything

1. Find the entry point. Where does this task attach to the existing system? Read those files fully.
2. Trace dependencies. What does the entry point import or call that this task will touch? Read those too.
3. Find prior art. Has the codebase solved a similar problem? Those patterns become constraints.
4. Surface implicit constraints. Error handling conventions, logging patterns, config loading — identify them.
5. Assess scope. Can this be implemented as one coherent, independently testable unit? Or does it naturally decompose into 2–6 pieces with one-way dependencies?

### Choose a path

**Single spec** — if all of the following are true:
- One class, one function group, or one module boundary
- Acceptance criteria can be tested in one test file without mocking upstream harness specs
- A single implementation fits in one target file

**Task (multi-spec DAG)** — if any of the following are true:
- The work spans multiple modules that will import each other
- A later piece can't be meaningfully tested without a prior piece existing
- There are 3+ distinct concerns that would make a single spec's acceptance criteria list unwieldy

Tell the user which path you chose and why in one sentence before writing anything.

### Single spec path

Write `.harness/specs/{kebab-case-id}.py`:

```python
from harness import Spec

spec = Spec(
    id="...",
    description="One precise paragraph. What, not how.",
    constraints=[
        # Name the class, method, or pattern. Be specific.
    ],
    acceptance_criteria=[
        # One testable assertion each. "Returns X when Y" — not "handles Y correctly".
    ],
    target_file="src/module.py",
    reference_files=["src/related.py", "src/types.py"],
    language="python",  # python | typescript | go | rust
)
```

Review before finishing:
- Every referenced class/method/path actually exists in the codebase
- Every acceptance criterion is a single falsifiable assertion
- Error paths are covered, not just the happy path
- The implementation would know what to import from where
- `target_file` and `reference_files` use paths relative to project root

Tell the user: "Spec written to `.harness/specs/<id>.py`. Run `/build <id>` to generate code."

### Task path

Write each spec to `.harness/specs/<spec-id>.py` using the same format.

Decomposition rules:
- Each spec must be independently testable (one class, one module, one function group)
- Dependencies between specs flow one way: downstream specs use upstream APIs
- Aim for 2–6 specs. One spec means use the single spec path.
- Name specs with the same kebab-case prefix: `auth-login`, `auth-session`, `auth-logout`

Write the task file to `.harness/tasks/{kebab-case-task-id}.py`:

```python
from harness import Task, TaskSpec

task = Task(
    id="...",
    description="One sentence describing the full feature.",
    specs=[
        TaskSpec(spec_id="...", depends_on=[]),
        TaskSpec(spec_id="...", depends_on=["spec-a"]),
        TaskSpec(spec_id="...", depends_on=["spec-a"]),
        TaskSpec(spec_id="...", depends_on=["spec-b", "spec-c"]),
    ]
)
```

Tell the user the specs written and the dependency order, then: "Task written to `.harness/tasks/<id>.py`. Run `/build <id>` to execute all specs."
