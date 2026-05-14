# /forge-task

Explore the codebase and produce a multi-spec task for the automated harness.

You will be given a feature description. Decompose it into the minimal set of
independently implementable specs with explicit dependencies, then write a task
file the harness can execute as a DAG.

## Decomposition protocol

1. **Identify components.** What distinct units does this feature require?
   A component is distinct if it can be implemented and tested in isolation.

2. **Draw the dependency graph explicitly** before writing anything:
   ```
   component-a ──┐
                 ├──► component-c ──► component-d
   component-b ──┘
   ```

3. **Validate independence.** A spec is truly independent if you could hand it
   to a developer who knows nothing about the other specs and they could
   implement it correctly. Hidden dependency = explicit depends_on.

4. **Size each spec.** Each spec should produce ~50–150 lines of implementation.
   Too large = split it. Too small = merge it.

5. **Maximise parallelism.** Specs with no interdependency run concurrently.
   Fewer layers = faster total execution.

## Dependency rules

- `depends_on` lists only *direct* dependencies, not transitive ones
- The harness resolves transitive dependencies and propagates context automatically
- If C depends on B which depends on A:
  - C's depends_on is `["b-spec-id"]` — not `["a-spec-id", "b-spec-id"]`

## Output

Write `.harness/tasks/{kebab-case-feature-name}.py`:

```python
# Dependency graph:
#
#   spec-a ──┐
#            ├──► spec-c ──► spec-d
#   spec-b ──┘

from harness import Spec
from harness.task_models import Task, TaskSpec

task = Task(
    id="feature-name",
    description="One sentence: what feature this delivers.",
    specs=[
        TaskSpec(
            spec=Spec(
                id="spec-a",
                description="...",
                constraints=[...],
                acceptance_criteria=[...],
                metadata={"target_file": "..."},
            ),
            depends_on=[],
        ),
        TaskSpec(
            spec=Spec(id="spec-c", ...),
            depends_on=["spec-a", "spec-b"],
        ),
    ],
)
```

## Quality check

Before finishing:
- Every `depends_on` references a real spec id in this task
- No spec assumes knowledge from a spec it doesn't declare as a dependency
- Each spec's acceptance criteria are testable without the other specs
- Target file paths match the existing codebase structure

Do not write any implementations. Only the task file.
