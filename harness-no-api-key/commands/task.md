Run task `$ARGUMENTS` through the harness.

Read `.harness/config.py` if it exists to get PROJECT_ROOT (default: .).

## Step 1 — Load DAG and checkpoint

Call `dag_load("$ARGUMENTS", project_root)` to get the execution layers.
Call `checkpoint_read("$ARGUMENTS", project_root)` to get the list of already-completed specs.

Show the user the layers and which specs (if any) are being skipped due to the checkpoint.

## Step 2 — Execute layers

**Context window note**: Each spec adds implementation, tests, and gate results to context. After each layer completes, strongly consider running `/compact` to compress context before the next layer. For tasks with 4+ specs, suggest `/clear` between layers and re-run `/harness:task` — the checkpoint will resume where you left off.

For each layer (in order):
  For each spec in the layer:

  a. If spec_id is in the checkpoint's `completed` list → skip with "✓ already passed".

  b. Otherwise, use the Agent tool to execute this spec in an isolated sub-context:

     ```
     Agent prompt:
     Run /harness:submit <spec_id> in project at <project_root>.
     Config: language=<language>, project_root=<project_root>, max_repair_attempts=3.
     [If this spec has upstream dependencies]: The following upstream implementations are
     available for import — inject them as additional context before generating:
     <upstream_implementation_code>
     Report back: passed or escalated, and the run_id.
     ```

  c. If passed → call `checkpoint_write(task_id, updated_completed_list, project_root)`.
  d. If escalated → record it. Skip all specs that depend on this one (mark as blocked).
     Continue with specs in the same layer that don't depend on the failed spec.

## Step 3 — Report

Show a table:
- Layer N: spec-id → ✓ passed | ⚠ escalated | ⊘ blocked (by spec-x)

If all passed → tell the user: run `/harness:finish <last-run-id>` for each spec, or commit manually.
If any escalated → list the failed specs and their run IDs. Tell the user: run `/harness:debug` for each.

**Context tip**: If this session is getting long, run `/compact` now to free up context for the finish/debug steps.
