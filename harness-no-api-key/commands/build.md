Build `$ARGUMENTS` through the harness.

Read `.harness/config.py` if it exists to get LANGUAGE, PROJECT_ROOT, and MAX_REPAIR_ATTEMPTS (defaults: python, ., 3).

## Step 0 — Detect spec or task

Check which file exists:
- `.harness/specs/$ARGUMENTS.py` → **spec path** (single spec)
- `.harness/tasks/$ARGUMENTS.py` → **task path** (multi-spec DAG)

If neither exists, tell the user and stop.

---

## Spec path

### Step 1 — Load spec and context

Call `spec_load("$ARGUMENTS", project_root)`.
Call `context_fetch(reference_files, target_file, project_root)` using the spec's reference_files and target_file.

### Step 2 — Generate implementation and tests

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

### Step 3 — First gate run

Call `gate_run(implementation, tests, language, project_root)`.

### Step 4a — All gates pass on first attempt

Call `memory_record(spec_id, "all", "passed", 1, "passed", project_root)`.
Call `artifact_save(spec_id, implementation, tests, "passed", 1, gate_results, project_root)`.
Tell the user: run `/harness:deliver <run-id>`.

### Step 4b — A gate failed — save and enter repair loop

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
   - Tell the user: run `/harness:deliver <run-id>`. **Done.**

6. If result contains `{"error": ..., "fallback": "rewrite"}` (patch mis-applied):
   - Fall back to a full rewrite for this attempt only.
   - Write the revised implementation in a fenced code block.
   - Call `gate_run(implementation, tests, language, project_root)`.
   - If passed: call `artifact_save` with outcome="passed" and tell the user `/harness:deliver`.
   - If failed: update run_id with the new implementation via `artifact_save` (outcome="in_progress") and continue the repair loop using `repair_run` for subsequent attempts.

7. If gate results returned: analyze errors, next attempt.

### Step 4c — Still failing after MAX_REPAIR_ATTEMPTS

Call `artifact_escalate(run_id, project_root)`.
Call `memory_record(spec_id, failing_gate, errors_text, attempt_number, "escalated", project_root)`.
Explain what was tried and what the remaining error is. Tell the user: run `/harness:debug`.

---

## Task path

### Step 1 — Load DAG and checkpoint

Call `dag_load("$ARGUMENTS", project_root)` to get the execution layers.
Call `checkpoint_read("$ARGUMENTS", project_root)` to get the list of already-completed specs.

Show the user the layers and which specs (if any) are being skipped due to the checkpoint.

### Step 2 — Execute layers

**Context window note**: Each spec adds implementation, tests, and gate results to context. After each layer completes, strongly consider running `/compact` to compress context before the next layer. For tasks with 4+ specs, suggest `/clear` between layers and re-run `/harness:build` — the checkpoint will resume where you left off.

For each layer (in order):
  For each spec in the layer:

  a. If spec_id is in the checkpoint's `completed` list → skip with "✓ already passed".

  b. Otherwise, use the Agent tool to execute this spec in an isolated sub-context:

     ```
     Agent prompt:
     Run /harness:build <spec_id> in project at <project_root>.
     Config: language=<language>, project_root=<project_root>, max_repair_attempts=3.
     [If this spec has upstream dependencies]: The following upstream implementations are
     available for import — inject them as additional context before generating:
     <upstream_implementation_code>
     Report back: passed or escalated, and the run_id.
     ```

  c. If passed → call `checkpoint_write(task_id, updated_completed_list, project_root)`.
  d. If escalated → record it. Skip all specs that depend on this one (mark as blocked).
     Continue with specs in the same layer that don't depend on the failed spec.

### Step 3 — Report

Show a table:
- Layer N: spec-id → ✓ passed | ⚠ escalated | ⊘ blocked (by spec-x)

If all passed → tell the user: run `/harness:deliver <run-id>` for each spec, or commit manually.
If any escalated → list the failed specs and their run IDs. Tell the user: run `/harness:debug` for each.

**Context tip**: If this session is getting long, run `/compact` now to free up context for the finish/debug steps.
