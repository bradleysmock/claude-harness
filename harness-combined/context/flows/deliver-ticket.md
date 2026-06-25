# Flow: deliver — ticket mode

Merge the ticket's worktree branch into main, remove the worktree, and record learnings. The diff was already reviewed after `/build`.

<!-- progress-checklist -->
**Progress checklist** — as the first action, create the `TodoWrite` checklist (see "Progress checklist" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`):

`Merge worktree · Status → done + archive · Cleanup`

**Sub-flow note:** this flow may run as a sub-flow under `/autopilot`. If a checklist already exists for this run (autopilot created it), follow the convention's one-list-per-run rule — adopt that existing list and advance its delivery stages, do **not** create a second one.

## Step 1 — Resolve and validate

Scan `.tickets/` for the ticket matching `$ARGUMENTS`; if not found, scan `.tickets/completed/`. Read `status.md`.

- Confirm `status` is `review-ready`. If not, tell the user to run `/build XXXX` first and stop.
- Extract `branch` (e.g. `ticket/XXXX-<slug>`) and `ticket` number.
- Run `git branch --list <branch>` to confirm the branch exists.
- Run `git status` to confirm the main repo working tree is clean.

## Step 2 — Check for file conflicts with other review-ready tickets

Get changed files: `git diff --name-only main....<branch>`

Scan `.tickets/` (not `.tickets/completed/`) for any other `review-ready` tickets. For each, get their changed files. If any overlap, warn the user:

```
Warning: the following files are also changed in other review-ready tickets:
  <file> — also in ticket YYYY (<branch>)
Suggested merge order: <reasoning>
```

This is a warning, not a stop.

## Step 3 — Confirm

```
Ready to deliver ticket XXXX:
  git merge --squash <branch>      (one squashed commit — no per-branch-commit history, no merge commit)
  status.md → done
  mv .tickets/XXXX-<slug>/ .tickets/completed/XXXX-<slug>/   (archive)
  ↑ status → done and the archive are both folded into the single squash commit
  git push
  git worktree remove .worktrees/XXXX-<slug>
  git branch -D <branch>      (-D, not -d: a squash leaves the branch without merge ancestry)
Proceed? (yes/no)
```

Stop if the user says no.

## Step 4 — Squash-merge: fold `→ done` + archive into one commit

A delivered ticket adds **exactly one** commit to `main`. Run the sequence below — encapsulated and unit-tested as `ticket.py deliver_squash()` (it asserts the one-commit invariant). It mirrors the archive pattern (OS `mv` + `git rm -r --cached` + `git add`, **never** `git mv`, which is unsound against the index `merge --squash` leaves):

```
# 1. Stage the whole branch diff (code + the branch's .tickets/XXXX-<slug>/) — no commit, no merge commit
git merge --squash <branch>

# 2. Archive: OS-move the squash-staged ticket dir into completed/
mkdir -p .tickets/completed
mv .tickets/XXXX-<slug>/ .tickets/completed/XXXX-<slug>/

# 3. Rewrite .tickets/completed/XXXX-<slug>/status.md → status: done (+ updated: <today>) at the NEW path

# 4. Clear the squash-staged old path; stage the archived path (code changes stay squash-staged)
git rm -r --cached .tickets/XXXX-<slug>/
git add -- .tickets/completed/XXXX-<slug>/

# 5. ONE commit: full code diff + completed/XXXX-<slug>/ at done, and no .tickets/XXXX-<slug>/ entry
git commit -m "feat: XXXX <title> (squash)"

# 6. Publish FIRST; only on a successful push remove the worktree + delete the branch
#    (-D, not -d: a squash leaves the branch without merge ancestry, so git never
#     treats it as "fully merged"). On a rejected push, stop with both intact and retry.
git push
git worktree remove .worktrees/XXXX-<slug>
git branch -D <branch>
```

If the `git merge --squash` reports a conflict, report the error and stop without committing or cleaning up.

> **Squash status resolution:** because `main` carried only the `claimed` stub for this ticket and never re-touched `.tickets/XXXX-<slug>/` after the claim, the squash merge's merge base for that path is the claim stub and only the branch changed it — so it resolves cleanly with no conflict. The branch's `review-ready` `status.md` is squash-staged, then overwritten in place to `done` before the single commit. There is **no `--no-ff` merge commit and no separate `→ done` / archive commit** — `→ done` and the archive are folded into the one squash commit. A reopened ticket repeats this, adding a further squashed commit.

**Idempotency:** If `.tickets/completed/XXXX-<slug>/` already exists and `.tickets/XXXX-<slug>/` is absent, the ticket is already archived — skip the mv and continue with the commit.

**Partial-move guard:** If both `.tickets/XXXX-<slug>/` and `.tickets/completed/XXXX-<slug>/` exist simultaneously, warn the lead — treat the root copy as authoritative and proceed with the mv from root.

## Step 5 — Suggest candidate learnings (do not write)

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

## Step 6 — Clear sentinel

```
rm -f .tickets/.active
```

## Step 7 — Rebase in-flight worktrees

For each active ticket in `.tickets/` (not `.tickets/completed/`) that is not XXXX:
1. Read its `branch` from `status.md`. If empty, skip.
2. Check for mid-rebase state: `git -C .worktrees/YYYY-<slug> rev-parse --git-dir`
3. Attempt: `git -C .worktrees/YYYY-<slug> rebase main`
   - Success: record "YYYY: rebased OK". If was `review-ready`, downgrade to `implementing` and note gates are invalidated.
   - Failure: run `git -C .worktrees/YYYY-<slug> rebase --abort`, record failure with manual recovery instructions.

If any ticket was downgraded to `implementing` here, commit that transition **on its own branch** (inside its worktree — the `implementing` state is branch-only, never committed to `main`), and push:
```
git -C .worktrees/YYYY-<slug> add .tickets/YYYY-<slug>/status.md
git -C .worktrees/YYYY-<slug> commit -m "chore(ticket): YYYY → implementing (rebased onto main)"
git -C .worktrees/YYYY-<slug> push
```

## Step 8 — Report

Summarize what was delivered (the single squash commit), cleaned up, and any rebase results.
