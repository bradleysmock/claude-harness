Submit spec `$ARGUMENTS` through the harness.

Read `.harness/config.py` if it exists to get LANGUAGE, PROJECT_ROOT, and MAX_REPAIR_ATTEMPTS (defaults: python, ., 3).

## Step 1 — Load spec and context

Call `spec_load("$ARGUMENTS", project_root)`.
Call `context_fetch(reference_files, target_file, project_root)` using the spec's reference_files and target_file.

## Step 2 — Generate implementation and tests

Using the spec's description, constraints, acceptance_criteria, and the fetched context:

Write the implementation in a fenced code block:
```python
# implementation
<complete implementation here>
```

Write the tests in a fenced code block:
```python
# tests
<complete test suite here>
```

Cover: happy path, edge cases, error conditions. Tests must be runnable standalone.

## Step 3 — Run gates

Call `gate_run(implementation, tests, language, project_root)`.

## Step 4a — All gates pass

Call `memory_record(spec_id, "all", "passed", attempt_number, "passed", project_root)`.
Call `artifact_save(spec_id, implementation, tests, "passed", attempt_number, gate_results, project_root)`.
Show the gate results summary and tell the user: run `/harness:finish <run-id>`.

## Step 4b — A gate failed (repair loop)

Repeat up to MAX_REPAIR_ATTEMPTS times:

1. Call `memory_retrieve(errors_text, failing_gate, project_root)` where errors_text is the concatenated error messages.
2. Review:
   - The gate errors (file, line, code, message)
   - Similar past failures returned by memory_retrieve
   - Your current implementation
3. Identify the root cause. Revise the implementation (keep tests unchanged unless tests are the bug).
4. Write the revised implementation in a new fenced code block.
5. Call `gate_run(revised_implementation, tests, language, project_root)`.
6. If gates pass → go to Step 4a.
7. If gates fail again → next attempt.

## Step 4c — Still failing after MAX_REPAIR_ATTEMPTS

Call `memory_record(spec_id, failing_gate, errors_text, attempt_number, "escalated", project_root)`.
Call `artifact_save(spec_id, implementation, tests, "escalated", attempt_number, gate_results, project_root)`.
Explain what was tried and what the remaining error is. Tell the user: run `/harness:debug`.
