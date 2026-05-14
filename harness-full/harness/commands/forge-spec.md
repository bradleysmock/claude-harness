# /forge-spec

Explore the codebase and produce a task specification for the automated coding harness.

You will be given a plain-language task description. Your job is to understand it
deeply enough to produce a Spec that is complete, unambiguous, and executable by
the harness without further human clarification.

## Exploration protocol

Work through these steps before writing anything:

1. **Find the entry point.** Where does this task attach to the existing system?
   Read those files fully.

2. **Trace dependencies.** What does the entry point import or call that this
   task will touch? Read those too.

3. **Find prior art.** Has the codebase solved a similar problem before?
   Search for analogous patterns — they become your constraints and examples.

4. **Surface implicit constraints.** Every codebase has unstated rules:
   error handling conventions, logging patterns, transaction boundaries,
   config loading patterns. Identify them from what you read.

5. **Construct the test in your head.** Before writing acceptance criteria,
   mentally write the test. If you can't, the spec isn't ready.

## Output

Write a Python file to `.harness/specs/{kebab-case-task-name}.py`.

```python
from harness import Spec

spec = Spec(
    id="...",
    description="One precise paragraph. What, not how.",
    constraints=[
        # Each constraint is a rule the implementation must follow.
        # Be specific: name the class, the method, the pattern.
        # Vague constraints produce vague code.
    ],
    acceptance_criteria=[
        # Each criterion is a testable assertion.
        # "Returns X when Y" — not "handles Y correctly".
    ],
    metadata={
        "target_file": "...",
        "reference_files": [...],   # files the LLM should study
    },
)
```

## Completeness test

Before finishing, ask: could someone who has never seen this codebase implement
this spec correctly? If no, add what's missing.

Do not produce the implementation. Do not modify existing files. Only the spec.
