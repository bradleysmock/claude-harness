Explore the codebase and write a multi-spec task DAG for: $ARGUMENTS

## Decomposition — do this before writing anything

1. Identify components. What distinct units does this feature require? A component is distinct if it can be implemented and tested in isolation.
2. Draw the dependency graph before writing:
   ```
   component-a ──┐
                 ├──► component-c ──► component-d
   component-b ──┘
   ```
3. Validate independence. Could a developer implement each spec knowing nothing about the others? If not, add a `depends_on`.
4. Size each spec. Each should produce ~50–150 lines. Too large → split. Too small → merge.
5. Maximise parallelism. Specs with no interdependency run concurrently — fewer layers is faster.

## Dependency rules

- `depends_on` lists only direct dependencies, not transitive ones
- The harness propagates public API from upstream specs to downstream specs automatically

## Write the task file

Write `.harness/tasks/{kebab-case-id}.py`:

```python
# Dependency graph:
#   spec-a ──┐
#            ├──► spec-c
#   spec-b ──┘

from harness import Spec
from harness.task_models import Task, TaskSpec

task = Task(
    id="feature-name",
    description="One sentence: what this delivers.",
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

Then tell the user:
  Task written to `.harness/tasks/<id>.py`. Run `/harness:task <id>` to generate code.
