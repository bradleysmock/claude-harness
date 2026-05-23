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

## Step 3 — First gate run

Call `gate_run(implementation, tests, language, project_root)`.

## Step 4a — All gates pass on first attempt

Call `memory_record(spec_id, "all", "passed", 1, "passed", project_root)`.
Call `artifact_save(spec_id, implementation, tests, "passed", 1, gate_results, project_root)`.
Tell the user: run `/harness:finish <run-id>`.

## Step 4b — A gate failed — save and enter repair loop

Call `artifact_save(spec_id, implementation, tests, "in_progress", 1, gate_results, project_root)` → run_id.

Repeat up to MAX_REPAIR_ATTEMPTS times:

1. Call `memory_retrieve(errors_text, failing_gate, project_root)` where errors_text is the concatenated error messages from the failing gate result.

2. Identify the root cause from the gate errors and any similar past failures.

3. Generate a unified diff of the minimal changes needed:
   ```diff
   --- implementation
   +++ implementation
   @@ -N,M +N,M @@
    context line
   -old line
   +new line
    context line
   ```
   Only change what's necessary. Context lines must match exactly.

4. Call `repair_run(run_id, diff, language, project_root)`.

5. If result is `{"passed": true, ...}`:
   - Call `memory_record(spec_id, failing_gate, errors_text, attempt_number, "passed", project_root)`.
   - Tell the user: run `/harness:finish <run-id>`. **Done.**

6. If result contains `{"error": ..., "fallback": "rewrite"}` (patch mis-applied):
   - Fall back to a full rewrite for this attempt only.
   - Write the revised implementation in a fenced code block.
   - Call `gate_run(implementation, tests, language, project_root)`.
   - If passed: call `artifact_save` with outcome="passed" and tell the user `/harness:finish`.
   - If failed: update run_id with the new implementation via `artifact_save` (outcome="in_progress") and continue the repair loop using `repair_run` for subsequent attempts.

7. If gate results returned: analyze errors, next attempt.

## Step 4c — Still failing after MAX_REPAIR_ATTEMPTS

Call `artifact_escalate(run_id, project_root)`.
Call `memory_record(spec_id, failing_gate, errors_text, attempt_number, "escalated", project_root)`.
Explain what was tried and what the remaining error is. Tell the user: run `/harness:debug`.
