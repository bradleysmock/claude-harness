# Flow: deliver — ticket mode

Merge the ticket's worktree branch into main, remove the worktree, and record learnings. The diff was already reviewed after `/build`.

## Step 1 — Resolve and validate

Scan `.tickets/` for the ticket matching `$ARGUMENTS`. Read `status.md`.

- Confirm `status` is `review-ready`. If not, tell the user to run `/build XXXX` first and stop.
- Extract `branch` (e.g. `ticket/XXXX-<slug>`) and `ticket` number.
- Run `git branch --list <branch>` to confirm the branch exists.
- Run `git status` to confirm the main repo working tree is clean.

## Step 2 — Check for file conflicts with other review-ready tickets

Get changed files: `git diff --name-only main....<branch>`

Scan `.tickets/` for any other `review-ready` tickets. For each, get their changed files. If any overlap, warn the user:

```
Warning: the following files are also changed in other review-ready tickets:
  <file> — also in ticket YYYY (<branch>)
Suggested merge order: <reasoning>
```

This is a warning, not a stop.

## Step 3 — Confirm

```
Ready to deliver ticket XXXX:
  git merge --no-ff <branch>
  git worktree remove .worktrees/XXXX-<slug>
  git branch -d <branch>
  status.md → done
Proceed? (yes/no)
```

Stop if the user says no.

## Step 4 — Merge

```
git merge --no-ff <branch>
```

If the merge fails, report the error and stop without continuing to cleanup.

## Step 5 — Clean up

```
git worktree remove .worktrees/XXXX-<slug>
git branch -d <branch>
```

Warn on failure but continue.

## Step 6 — Update ticket status

Set `status.md` to `status: done` and update the `updated` date.

Commit the metadata transition to `main` — this is what records a finished ticket (scoped add — see "Committing ticket metadata" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`). It is a separate commit from the Step 4 integration:
```
git add .tickets/XXXX-<slug>/
git commit -m "chore(ticket): XXXX → done"
```

## Step 7 — Suggest candidate learnings (do not write)

`.tickets/_learnings.md` is lead-curated. The harness never writes to it.

Scan `gate-findings.md` and commit messages for repairs ("repair" / "fix gate"). If a pattern stands out, surface up to **three** one-line suggestions to the lead in the final report, framed as:

```
Candidate learnings to consider adding to .tickets/_learnings.md:
  - <date> | <gate> | <pattern>
  - ...
(Edit _learnings.md yourself if any of these are worth keeping. The model reads it at the start of every /problem and /build.)
```

The model's raw per-failure record already lives in `.harness/memory.db` via `memory(action="record", ...)` calls during the gate/repair loop — that is the machine-readable layer and stays opaque. The lead's `_learnings.md` is the human-readable layer.

If `gate-findings.md` is empty or no repair occurred, skip this step.

## Step 8 — Clear sentinel

```
rm -f .tickets/.active
```

## Step 9 — Rebase in-flight worktrees

For each ticket that is not `done` and not XXXX:
1. Read its `branch` from `status.md`. If empty, skip.
2. Check for mid-rebase state: `git -C .worktrees/YYYY-<slug> rev-parse --git-dir`
3. Attempt: `git -C .worktrees/YYYY-<slug> rebase main`
   - Success: record "YYYY: rebased OK". If was `review-ready`, downgrade to `implementing` and note gates are invalidated.
   - Failure: run `git -C .worktrees/YYYY-<slug> rebase --abort`, record failure with manual recovery instructions.

If any ticket was downgraded to `implementing` here, commit those metadata transitions to `main` (scoped add per ticket — see "Committing ticket metadata" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`):
```
git add .tickets/YYYY-<slug>/
git commit -m "chore(ticket): YYYY → implementing (rebased onto main)"
```

## Step 10 — Report

Summarize what was merged, cleaned up, and any rebase results.
