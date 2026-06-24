# Flow: build — ticket mode

Create a worktree, run the spec engine against it, write passing implementations to target files in the worktree, and present a diff for review.

Read `.harness/config.py` if it exists to get `LANGUAGE`, `PROJECT_ROOT`, and `MAX_REPAIR_ATTEMPTS` (defaults: auto-detect, `.`, 3).

## Step 1 — Resolve ticket, ensure specs exist

Scan `.tickets/` for the ticket matching `$ARGUMENTS`; if not found, scan `.tickets/completed/`. Read `status.md` to get the slug. Use whichever location the ticket is found in for all subsequent file references in this flow.

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

First, commit `status: implementing` to `main` and push it. This must happen **before** the worktree is created so the branch forks from the `implementing` commit (keeping the later branch→main merge a clean, conflict-free merge of `status.md`):

```
python3 "${CLAUDE_PLUGIN_ROOT}/ticket.py" set-status XXXX implementing --push
```

The `--push` flag runs `git push` atomically with the commit, publishing the start signal before any branch is forked.

Then create the worktree from the now-updated `main`:

```
git worktree add .worktrees/XXXX-<slug> -b ticket/XXXX-<slug>
echo 'XXXX-<slug>' > .tickets/.active
```

From here, all implementation status churn (`review-ready`, `changes-requested`) is **branch only** — committed inside the worktree, never to `main`. `main` keeps showing `implementing` until `/deliver` merges the branch.

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

Update `status.md` to `status: review-ready`. Commit it **in the worktree** (branch-local — it must not touch `main`):

```
git -C .worktrees/XXXX-<slug> add .tickets/XXXX-<slug>/status.md
git -C .worktrees/XXXX-<slug> commit -m "chore(ticket): XXXX → review-ready"
```

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

**Severity policy** (this is the core of the post-build loop):

- **BLOCKER and MAJOR findings are must-fix.** `/build` does **not** stop for the lead's decision on them — it auto-repairs them in the worktree (Step 7a). The lead is only consulted if auto-repair cannot clear them after `MAX_REPAIR_ATTEMPTS`.
- **MINOR and OBS findings are optional.** Never auto-fix them. List them for the lead to decide on (Step 7c).

### Step 7a — Auto-repair BLOCKER / MAJOR findings

**If the critic surfaces no BLOCKER and no MAJOR findings**, skip to Step 7c.

Otherwise, enter the repair loop. Run up to `MAX_REPAIR_ATTEMPTS` (default 3) attempts:

For each attempt `N` (1 … `MAX_REPAIR_ATTEMPTS`):

1. Announce: "Auto-repair attempt N/`MAX_REPAIR_ATTEMPTS` — addressing M BLOCKER / K MAJOR finding(s)."
2. For each BLOCKER and MAJOR finding, fix the specific `file:line` location in the worktree files directly. Call `memory(action="retrieve", ...)` first when a finding overlaps a known failure pattern. Do **not** touch MINOR / OBS findings.
3. Re-run the integration gate so fixes don't regress: `gate_run_on_dir(".worktrees/XXXX-<slug>", "auto", project_root)`. If it fails, repair the gate failures (same inner loop as Step 4e) before proceeding — a green gate is a precondition for re-review.
4. Commit the repair round: `git -C .worktrees/XXXX-<slug> commit -am "fix: address post-build critic round N findings"`.
5. Re-spawn the critic subagent (**Round**: `N+1`, same Phase/Ticket) to verify. Display its report verbatim.
6. **If the new report has no BLOCKER and no MAJOR findings** → repair succeeded. Go to Step 7b.
7. **If BLOCKER / MAJOR findings remain** and attempts are left → loop to attempt `N+1`.

### Step 7b — Auto-repair succeeded

- Keep `status.md` at `status: review-ready`.
- Tell the user:
  > The post-build critic's BLOCKER/MAJOR findings were auto-repaired in N round(s) and re-verified clean. Options:
  > - Proceed to delivery with `/deliver XXXX`.
  > - For an interactive panel-aware re-review (e.g., to dig into remaining MINOR / OBS findings conversationally), run `/review XXXX`.
  > - For a comprehensive panel review of selected files, run `/critique <files>`.

### Step 7c — No must-fix findings (or only MINOR / OBS remain)

- Keep `status.md` at `status: review-ready`.
- Tell the user:
  > The post-build critic found no BLOCKER/MAJOR findings. Options:
  > - Proceed to delivery with `/deliver XXXX`.
  > - For an interactive panel-aware re-review (e.g., to dig into MINOR / OBS findings conversationally), run `/review XXXX`.
  > - For a comprehensive panel review of selected files, run `/critique <files>`.

### Step 7d — Auto-repair exhausted (ask the lead)

If BLOCKER / MAJOR findings still remain after `MAX_REPAIR_ATTEMPTS`:

- Update `status.md` to `status: changes-requested` and commit it in the worktree:
  ```
  git -C .worktrees/XXXX-<slug> add .tickets/XXXX-<slug>/status.md
  git -C .worktrees/XXXX-<slug> commit -m "chore(ticket): XXXX → changes-requested"
  ```
- Show the lead the residual BLOCKER / MAJOR findings and what each repair round attempted.
- Tell the user:
  > Auto-repair could not clear N BLOCKER / K MAJOR finding(s) after `MAX_REPAIR_ATTEMPTS` attempts — your input is needed. Options:
  > - Advise on the approach, then run `/build XXXX` to resume repair with the existing worktree.
  > - Run `/review XXXX` for an interactive panel-aware deep-dive on the residual findings (same panels, conversational delivery, follow-up questions).
  > - For a comprehensive panel review against arbitrary files in the worktree, run `/critique <files>`.
