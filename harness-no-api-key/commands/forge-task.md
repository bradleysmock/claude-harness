Explore the codebase and decompose this feature into a multi-spec task: $ARGUMENTS

## Exploration

Read the relevant files. Understand what the feature touches. Identify natural boundaries where the work can be split into independent, testable specs.

## Decomposition rules

- Each spec must be independently testable (one class, one module, one function group)
- Dependencies between specs flow one way: downstream specs use upstream APIs
- Aim for 2–6 specs per task. One spec is just `/harness:submit`. Ten specs is a project.
- Name specs with the same kebab-case prefix: `auth-login`, `auth-session`, `auth-logout`

## Write the spec files

Write each spec to `.harness/specs/<spec-id>.py` using the same format as `/harness:forge`.

## Write the task file

Write `.harness/tasks/{kebab-case-task-id}.py`:

```python
from harness import Task, TaskSpec

task = Task(
    id="...",
    description="One sentence describing the full feature.",
    specs=[
        TaskSpec(spec_id="...", depends_on=[]),           # no deps: first layer
        TaskSpec(spec_id="...", depends_on=["spec-a"]),   # depends on spec-a
        TaskSpec(spec_id="...", depends_on=["spec-a"]),   # also depends on spec-a (parallel with above)
        TaskSpec(spec_id="...", depends_on=["spec-b", "spec-c"]),  # waits for both
    ]
)
```

`depends_on` lists spec IDs that must pass before this spec executes.
Specs with the same dependencies (or no dependencies) form a layer and execute in order.

## Tell the user

List the specs you wrote and the dependency order, then:
  Task written to `.harness/tasks/<id>.py`. Run `/harness:task <id>` to execute all specs.
