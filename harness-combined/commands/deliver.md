Deliver `$ARGUMENTS` — merge the worktree branch and clean up.

**Ticket mode** (argument is a ticket number like `0001` or `0001-add-inventory`):
Merges the ticket's worktree branch into main, removes the worktree, and records learnings. The diff was already reviewed after `/build`.

**Standalone mode** (argument is a run-id or empty):
Writes a passing spec/build artifact to its target file. No branch involved.

---

## Ticket mode

### Step 1 — Resolve and validate

Scan `.tickets/` for the ticket matching `$ARGUMENTS`. Read `status.md`.

- Confirm `status` is `review-ready`. If not, tell the user to run `/build XXXX` first and stop.
- Extract `branch` (e.g. `ticket/XXXX-<slug>`) and `ticket` number.
- Run `git branch --list <branch>` to confirm the branch exists.
- Run `git status` to confirm the main repo working tree is clean.

### Step 2 — Check for file conflicts with other review-ready tickets

Get changed files: `git diff --name-only main....<branch>`

Scan `.tickets/` for any other `review-ready` tickets. For each, get their changed files. If any overlap, warn the user:

```
Warning: the following files are also changed in other review-ready tickets:
  <file> — also in ticket YYYY (<branch>)
Suggested merge order: <reasoning>
```

This is a warning, not a stop.

### Step 3 — Confirm

```
Ready to deliver ticket XXXX:
  git merge --no-ff <branch>
  git worktree remove .worktrees/XXXX-<slug>
  git branch -d <branch>
  status.md → done
Proceed? (yes/no)
```

Stop if the user says no.

### Step 4 — Merge

```
git merge --no-ff <branch>
```

If the merge fails, report the error and stop without continuing to cleanup.

### Step 5 — Clean up

```
git worktree remove .worktrees/XXXX-<slug>
git branch -d <branch>
```

Warn on failure but continue.

### Step 6 — Update ticket status

Set `status.md` to `status: done` and update `updated` date.

### Step 7 — Record learnings

If any gate failures were repaired during `/build` (check gate-findings.md or commit messages containing "repair" or "fix gate"), append one line per pattern to `.tickets/_learnings.md`:

```
YYYY-MM-DD | XXXX | <gate> | <one-line pattern>
```

Create the file if it doesn't exist. Trim to 200 lines if needed.

### Step 8 — Clear sentinel

```
rm -f .tickets/.active
```

### Step 9 — Rebase in-flight worktrees

For each ticket that is not `done` and not XXXX:
1. Read its `branch` from `status.md`. If empty, skip.
2. Check for mid-rebase state: `git -C .worktrees/YYYY-<slug> rev-parse --git-dir`
3. Attempt: `git -C .worktrees/YYYY-<slug> rebase main`
   - Success: record "YYYY: rebased OK". If was `review-ready`, downgrade to `implementing` and note gates are invalidated.
   - Failure: run `git -C .worktrees/YYYY-<slug> rebase --abort`, record failure with manual recovery instructions.

### Step 10 — Report

Summarize what was merged, cleaned up, and any rebase results.

---

## Standalone mode

If $ARGUMENTS is a run-id, use it. Otherwise call `harness_status(project_root)` to find the most recent passed run.

Read `.harness/config.py` if it exists to get PROJECT_ROOT (default: .).

1. Call `artifact_load(run_id, project_root)`.
2. Confirm `outcome` is "passed". Warn and stop if "escalated".
3. Call `spec_load(spec_id, project_root)` to get `target_file`.
4. Write implementation to `target_file`. Integrate intelligently if the file already has other content.
5. Write tests to an appropriate test file alongside the target.
6. Suggest: review the diff, run the tests directly, then commit.
