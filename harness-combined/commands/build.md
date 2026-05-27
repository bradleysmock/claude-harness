Build `$ARGUMENTS` — generate, validate, and write implementation to a worktree.

**Ticket mode** (argument is a ticket number like `0001` or `0001-add-inventory`):
Creates a worktree, runs the spec engine against it, writes passing implementations to target files in the worktree, and presents a diff. Run `/write-spec XXXX` first to generate the specs.

**Standalone mode** (argument is a spec-id or task-id):
Generates and validates code in a temp dir, stores the result as an artifact. No worktree. Run `/deliver <run-id>` to write to the project when done.

---

## Ticket mode

Read `.harness/config.py` if it exists to get LANGUAGE, PROJECT_ROOT, and MAX_REPAIR_ATTEMPTS (defaults: auto-detect, ., 3).

### Step 1 — Resolve ticket and find specs

Scan `.tickets/` for the ticket matching `$ARGUMENTS`. Read `status.md` to get the slug.

Find the spec or task for this ticket:
- `.harness/tasks/XXXX-<slug>.py` — multi-spec task (preferred if it exists)
- `.harness/specs/XXXX-<slug>*.py` — individual spec(s)

If neither exists, tell the user to run `/write-spec XXXX` first and stop.

If `.tickets/_learnings.md` exists, load it via @.tickets/_learnings.md.
If `.tickets/_conventions.md` exists, load it via @.tickets/_conventions.md.

### Step 2 — Create worktree

```
git branch ticket/XXXX-<slug>
mkdir -p .worktrees
git worktree add .worktrees/XXXX-<slug> ticket/XXXX-<slug>
```

Confirm the worktree directory exists. If git fails, stop and report the error.

Update `status.md` to `status: implementing`.

Write the active-ticket sentinel:
```
echo 'XXXX-<slug>' > .tickets/.active
```

### Step 3 — Load DAG and checkpoint

If a task file exists: call `dag_load("XXXX-<slug>", project_root)` to get execution layers.
If only spec files: treat each as a single-layer task.

Call `checkpoint_read("XXXX-<slug>", project_root)` — skip specs already completed.

Show the user the layers and any checkpoint-skipped specs.

### Step 4 — Execute each spec

For each spec in each layer (respecting DAG order):

**a. If already checkpointed** — skip with "✓ already passed".

**b. Load spec and context:**
```
spec_load(spec_id, project_root)
context_fetch(reference_files, target_file, project_root)
```
If upstream specs in this task have already been written to the worktree, include their implementations as additional context so downstream specs can reference the actual interfaces.

**c. Generate implementation and tests:**

Write the implementation:
```python
# implementation
<complete implementation here>
```

Write the tests:
```python
# tests
<complete test suite here covering happy path, edge cases, error conditions>
```

**d. First gate run (text mode — validates before writing to disk):**

Call `gate_run(implementation, tests, language, project_root)`.

**e. If text-mode gates fail — repair loop (up to MAX_REPAIR_ATTEMPTS):**

1. Call `memory_retrieve(errors_text, failing_gate, project_root)` — surface similar past failures.
2. Generate a unified diff of the minimal fix:
   ```diff
   --- implementation
   +++ implementation
   @@ -N,M +N,M @@
    context
   -old
   +new
    context
   ```
3. Call `repair_run(run_id, diff, language, project_root)`.
   - If `{"passed": true}`: proceed to step f.
   - If `{"error": ..., "fallback": "rewrite"}`: do a full rewrite and call `gate_run` again.
   - If gate result: analyze structured errors (file, line, column), next attempt.

**f. Write to worktree:**

Once text-mode gates pass, write files to the worktree:
- Implementation → `worktree_dir / spec.target_file`
- Tests → appropriate test location (e.g., `worktree_dir/tests/test_<module>.py`)

If the target file already exists, integrate intelligently — don't overwrite unrelated content.

**g. Integration gate (directory mode — validates in real project context):**

Call `gate_run_on_dir(".worktrees/XXXX-<slug>", "auto", project_root)`.

If this fails (import errors, integration conflicts, etc.):
1. Call `memory_retrieve(errors_text, gate, project_root)`.
2. Fix the specific `file:line` locations in the worktree files directly.
3. Re-run `gate_run_on_dir`. Repeat up to MAX_REPAIR_ATTEMPTS.
4. If pass: call `memory_record(spec_id, gate, errors_text, attempt, "passed", project_root)`.
5. If still failing after MAX_REPAIR_ATTEMPTS: note the failure and continue to the next spec.

**h. Checkpoint:**

Call `checkpoint_write("XXXX-<slug>", updated_completed_list, project_root)`.

### Step 5 — Commit

```
git -C .worktrees/XXXX-<slug> add .
git -C .worktrees/XXXX-<slug> commit -m "feat: <short description from solution>"
```

Confirm the commit succeeds.

### Step 6 — Update status and show diff

Update `status.md` to `status: review-ready`.

Run and display:
```
git -C .worktrees/XXXX-<slug> diff main
```

Show a summary:
- Files changed, lines added/removed
- Which specs passed, which (if any) had integration failures

Then tell the user:
> Review the diff above. Optionally run `/review XXXX` for a structured code review. When satisfied, run `/deliver XXXX` to merge.

---

## Standalone mode

Read `.harness/config.py` if it exists to get LANGUAGE, PROJECT_ROOT, and MAX_REPAIR_ATTEMPTS (defaults: python, ., 3).

### Step 0 — Detect spec or task

- `.harness/specs/$ARGUMENTS.py` → **spec path**
- `.harness/tasks/$ARGUMENTS.py` → **task path**

If neither exists, tell the user to run `/write-spec <description>` first.

### Spec path

**Load:**
Call `spec_load("$ARGUMENTS", project_root)`.
Call `context_fetch(reference_files, target_file, project_root)`.

**Generate:**
Write implementation and tests in fenced code blocks.

**Gate + repair loop:**
Call `gate_run(implementation, tests, language, project_root)`.

If fail: save via `artifact_save` → run_id. Then repeat up to MAX_REPAIR_ATTEMPTS:
1. `memory_retrieve(errors_text, gate, project_root)`
2. Generate unified diff → `repair_run(run_id, diff, language, project_root)`
3. If `{"fallback": "rewrite"}`: full rewrite → `gate_run`

On pass: `memory_record`, `artifact_save` with outcome="passed". Tell user: run `/deliver <run-id>`.

On exhaustion: `artifact_escalate`, `memory_record` with outcome="escalated". Tell user: run `/debug`.

### Task path

Call `dag_load` and `checkpoint_read`. For each spec in each layer, run the spec path above in an isolated subagent. Call `checkpoint_write` after each pass. Report a layer-by-layer table on completion.
