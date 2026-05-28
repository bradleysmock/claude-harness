# Flow: write-spec — spec mode (standalone)

The argument is a free-form description. Explore the codebase first, then write a spec or task DAG.

## Exploration — do this before writing anything

1. Find the entry point. Where does this task attach to the existing system? Read those files fully.
2. Trace dependencies. What does the entry point import or call that this task will touch? Read those too.
3. Find prior art. Has the codebase solved a similar problem? Those patterns become constraints.
4. Surface implicit constraints. Error handling conventions, logging patterns, config loading — identify them.
5. Assess scope. Can this be implemented as one coherent, independently testable unit? Or does it naturally decompose into 2–6 pieces with one-way dependencies?

## Choose a path

**Single spec** — if all of the following are true:
- One class, one function group, or one module boundary
- Acceptance criteria can be tested in one test file without mocking upstream harness specs
- A single implementation fits in one target file

**Task (multi-spec DAG)** — if any of the following are true:
- The work spans multiple modules that will import each other
- A later piece can't be meaningfully tested without a prior piece existing
- There are 3+ distinct concerns that would make a single spec's acceptance criteria list unwieldy

Tell the user which path you chose and why in one sentence before writing anything.

## Single spec path

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

## Task path

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
