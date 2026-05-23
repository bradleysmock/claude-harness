Explore the codebase and write a spec for: $ARGUMENTS

## Exploration — do this before writing anything

1. Find the entry point. Where does this task attach to the existing system? Read those files fully.
2. Trace dependencies. What does the entry point import or call that this task will touch? Read those too.
3. Find prior art. Has the codebase solved a similar problem? Those patterns become constraints.
4. Surface implicit constraints. Error handling conventions, logging patterns, config loading — identify them.
5. Construct the test in your head. If you can't mentally write the test, the spec isn't ready.

## Write the spec

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

## Review before finishing

Check the spec you just wrote:
- Every referenced class/method/path actually exists in the codebase
- Every acceptance criterion is a single falsifiable assertion
- Error paths are covered, not just the happy path
- The implementation would know what to import from where
- `target_file` and `reference_files` use paths relative to project root

Fix anything that fails, then tell the user:
  Spec written to `.harness/specs/<id>.py`. Run `/harness:submit <id>` to generate code.
