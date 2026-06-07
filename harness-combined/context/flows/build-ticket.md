# Flow: build — ticket mode

Create a worktree, run the spec engine against it, write passing implementations to target files in the worktree, and present a diff for review.

Read `.harness/config.py` if it exists to get `LANGUAGE`, `PROJECT_ROOT`, and `MAX_REPAIR_ATTEMPTS` (defaults: auto-detect, `.`, 3).

## Step 1 — Resolve ticket, ensure specs exist

Scan `.tickets/` for the ticket matching `$ARGUMENTS`. Read `status.md` to get the slug.

If `status` is `changes-requested`, the worktree already exists from a prior `/build`. Skip Step 2; resume with the existing worktree and skip already-passed specs via `checkpoint(action="read", ...)`.

Find the spec or task for this ticket:
- `.harness/tasks/XXXX-<slug>.py` — multi-spec task (preferred if it exists)
- `.harness/specs/XXXX-<slug>*.py` — individual spec(s)

**If specs exist** — continue to the standards/learnings load below.

**If neither exists** — generate them inline before building (this replaces the old "run `/write-spec` first" hand-off):

1. Perform **Steps 1–5** of `${CLAUDE_PLUGIN_ROOT}/context/flows/write-spec-ticket.md` (resolve + score-spec gate → read only the named files → choose single-spec vs DAG → write the spec/task files). **Skip that flow's Step 6 report** — you are continuing into the build, not handing off.
2. **score-spec is a hard stop.** That flow's Step 1 runs the score-spec gate; if its verdict is **BLOCK**, stop here — **before any worktree is created** — show the failing checks, and tell the lead to fix the design artifacts (or run `/refine XXXX`) and re-run `/build XXXX`.
3. **Status precondition** is enforced by that flow's Step 1: if `status` is not `solution`, it stops and directs the lead to run `/problem XXXX` first. Honor that stop.
4. After the files are written, announce in one line: "No specs found — generated N spec(s)/task from `solution.md` (score-spec: PASS|WARN). Continuing to build."

Then load lead-curated context (both the specs-exist and just-generated paths):

If `.tickets/_standards.md` exists, load it via `@.tickets/_standards.md`.
If `.tickets/_learnings.md` exists, load it via `@.tickets/_learnings.md`.

Both are lead-curated. The model treats them as hard constraints, not suggestions. The machine's BM25 failure trail (`.harness/memory.db`) is consulted only by `memory(action="retrieve", ...)` during repair — it never feeds back into these files automatically.

## Step 2 — Create worktree (skip if resuming changes-requested)

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

## Step 3 — Load DAG and checkpoint

If a task file exists: call `dag_load("XXXX-<slug>", project_root)` to get execution layers.
If only spec files: treat each as a single-layer task.

Call `checkpoint(action="read", task_id="XXXX-<slug>", project_root=project_root)` — skip specs already completed.

Show the user the layers and any checkpoint-skipped specs.

## Step 4 — Execute each spec

For each spec in each layer (respecting DAG order):

**a. If already checkpointed** — skip with "✓ already passed".

**b. Load spec and context:**
```
spec_load(spec_id, project_root)
context_fetch(reference_files, target_file, project_root)
```
If upstream specs in this task have already been written to the worktree, include their implementations as additional context so downstream specs can reference the actual interfaces.

**c. Generate implementation and tests** in fenced code blocks (`# implementation` then `# tests`).

**d. Write to worktree:**
- Implementation → `worktree_dir / spec.target_file`
- Tests → appropriate test location (e.g. `worktree_dir/tests/test_<module>.py`)

If the target file already exists, integrate intelligently — don't overwrite unrelated content.

**e. Integration gate (directory mode):**

Call `gate_run_on_dir(".worktrees/XXXX-<slug>", "auto", project_root)`.

If it fails:
1. Call `memory(action="retrieve", errors_text=errors_text, gate=gate, project_root=project_root)`.
2. Fix the specific `file:line` locations in the worktree files directly.
3. Re-run `gate_run_on_dir`. Repeat up to `MAX_REPAIR_ATTEMPTS`.
4. If pass: call `memory(action="record", spec_id=spec_id, gate=gate, errors_text=errors_text, attempt=attempt, outcome="passed", project_root=project_root)`.
5. If still failing after `MAX_REPAIR_ATTEMPTS`: note the failure and continue to the next spec.

**f. Checkpoint:**

Call `checkpoint(action="write", task_id="XXXX-<slug>", completed=updated_completed_list, project_root=project_root)`.

## Step 5 — Commit

```
git -C .worktrees/XXXX-<slug> add .
git -C .worktrees/XXXX-<slug> commit -m "feat: <short description from solution>"
```

Confirm the commit succeeds.

## Step 6 — Update status and show diff

Update `status.md` to `status: review-ready`.

Run and display:
```
git -C .worktrees/XXXX-<slug> diff main
```

Show a summary:
- Files changed, lines added/removed
- Which specs passed, which (if any) had integration failures

## Step 7 — Spawn post-build critic (automatic)

After the diff is shown, spawn the critic subagent (`critic`) with the following parameters:

- **Phase**: `code`
- **Ticket**: `XXXX-<slug>`
- **Round**: 1

The critic loads expert panels per the trigger table in `${CLAUDE_PLUGIN_ROOT}/skills/critique/SKILL.md` (driven by the worktree's file set), reads `gate-findings.md` if present, reads the worktree implementation + tests, reads `problem.md` / `requirements.md` / `solution.md` as the ticket baseline (for the requirements-coverage and solution-alignment checks in `critic-brief.md` Step 2.5), and produces structured BLOCKER / MAJOR / MINOR / OBS findings.

Display the critic's structured report to the user verbatim.

**If the critic surfaces BLOCKER findings:**
- Update `status.md` to `status: changes-requested`.
- Tell the user:
  > The post-build critic surfaced N BLOCKER findings. Options:
  > - Address the BLOCKERs and run `/build XXXX` to re-execute the spec engine.
  > - Run `/review XXXX` for an interactive panel-aware deep-dive on the findings (same panels, conversational delivery, follow-up questions).
  > - For a comprehensive panel review against arbitrary files in the worktree, run `/critique <files>`.

**If the critic surfaces no BLOCKER findings:**
- Keep `status.md` at `status: review-ready`.
- Tell the user:
  > The post-build critic found no BLOCKERs. Options:
  > - Proceed to delivery with `/deliver XXXX`.
  > - For an interactive panel-aware re-review (e.g., to dig into MAJOR / MINOR findings conversationally), run `/review XXXX`.
  > - For a comprehensive panel review of selected files, run `/critique <files>`.
