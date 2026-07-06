# Flow: deliver — ticket mode

Merge the ticket's worktree branch into main, remove the worktree, and record learnings. The diff was already reviewed after `/build`.

<!-- progress-checklist -->
**Progress checklist** — as the first action, create the `TodoWrite` checklist (see "Progress checklist" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`):

`Merge worktree · Status → done + archive · Cleanup`

**Sub-flow note:** this flow may run as a sub-flow under `/autopilot`. If a checklist already exists for this run (autopilot created it), follow the convention's one-list-per-run rule — adopt that existing list and advance its delivery stages, do **not** create a second one.

## Step 1 — Resolve and validate

Scan `.tickets/` for the ticket matching `$ARGUMENTS`; if not found, scan `.tickets/completed/`. Read `status.md`.

Resolve status via the **Ticket resolution** rule in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`: the branch is still unmerged here, so the worktree `.worktrees/XXXX-<slug>` exists and its `.tickets/` copy of `status.md` is authoritative — the root copy still reads `claimed`. Confirm `review-ready` against the worktree copy.

- Confirm `status` is `review-ready`. If not, tell the user to run `/build XXXX` first and stop.
- Extract `branch` (e.g. `ticket/XXXX-<slug>`) and `ticket` number.
- Run `git branch --list <branch>` to confirm the branch exists.
- Run `git status` to confirm the main repo working tree is clean.

## Step 1.5 — Conventional-commit lint gate

Before offering delivery, lint every commit the branch adds on top of `main`. Call the MCP tool:

```
commit_lint(branch, project_root)          # add require_scope=True to also require a (scope)
```

The tool runs `git log main..<branch>` and validates each subject against `type(scope): subject` (allowed types default to the conventional-commit set; merge commits are skipped). It reads `allowed_types` / `require_scope` overrides from a `## Commit Lint` block in `.tickets/_standards.md` when present.

- **`passed: true`** → continue to Step 2.
- **`passed: false`** → **stop before the confirm prompt.** Print each error's `message` (`<short-sha>: <subject>`) so the lead sees exactly which commits are malformed, and tell them to fix the commit messages (e.g. `git rebase -i main` to reword) and re-run `/deliver XXXX`. Do **not** proceed to Step 3. A `BASE_BRANCH_UNKNOWN` or `GIT_ERROR` code also blocks (fail closed) — surface it and stop.

This gate is independent of `/deliver` and can be run standalone (e.g. in CI) by invoking `commit_lint` directly.

## Step 1.6 — Coverage enforcement preflight (fail-closed)

Before offering delivery, verify the coverage gate's verdict. The coverage gate
(`gates/coverage.py`, run as part of `gate_run_on_dir` during `/build`) writes a
machine-readable sidecar at `.tickets/XXXX-<slug>/gate-findings.json`. Because the
branch is still unmerged, read it from the **branch's** copy — the worktree
(`.worktrees/XXXX-<slug>/…/.tickets/XXXX-<slug>/gate-findings.json`) or, equivalently,
`git show <branch>:<path-to>/gate-findings.json`. The root copy on `main` is not
authoritative here.

Parse it with a strict JSON reader and inspect `coverage.passed`:

- **`coverage.passed == true`** → continue to Step 2. (A `status` of `"skipped"` — no
  threshold configured, or the coverage tool is not installed — is a legitimate pass:
  the gate is skip-safe by design.)
- **Sidecar absent, unreadable, not valid JSON, missing the `coverage` object, or
  `coverage.passed != true`** → **stop before the confirm prompt (fail-closed).** An
  absent or malformed sidecar is treated as a **failure**, never as "no coverage data".
  Print the reason (missing file / parse error / `coverage.status` + any `warnings`) and
  tell the lead to re-run `/build XXXX` so the coverage gate re-writes a passing sidecar,
  or to lower/clear the floor in `.tickets/_thresholds.yaml` if the threshold is wrong.
  Do **not** proceed to Step 3.

This preflight is what makes the coverage floor binding at delivery: a formatting change
or a deleted findings file can never silently unblock a merge.

## Step 2 — Check for file conflicts with other review-ready tickets

Get changed files: `git diff --name-only main....<branch>`

Scan `.tickets/` (not `.tickets/completed/`) for any other `review-ready` tickets. For each, get their changed files. If any overlap, warn the user:

```
Warning: the following files are also changed in other review-ready tickets:
  <file> — also in ticket YYYY (<branch>)
Suggested merge order: <reasoning>
```

This is a warning, not a stop.

## Step 2b — Pre-deliver rebase guard

Before the confirmation prompt, verify the ticket branch is not behind its delivery target. This closes the same gap GitHub's "require branch up to date before merging" closes: a gate-clean branch can still merge a stale baseline into `main`. This step runs after Step 2 (file-conflict check) and before Step 3 (Confirm). The `--rebase` flag referenced below is read from the `/deliver` invocation `$ARGUMENTS`. The whole check uses **local git state only** — no network calls.

### Sub-step 2b-1 — Resolve and validate the target branch

Read the delivery target from `status.md` if it names one; otherwise default to `main`. Validate the resolved name against:

```
^[a-zA-Z0-9][a-zA-Z0-9_.-]*(/[a-zA-Z0-9][a-zA-Z0-9_.-]*)*$
```

This permits remote-tracking names like `origin/main` while rejecting path traversal (`../evil`), `.hidden` leading-dot segments, and flag-like leading dashes. If validation fails, **halt before invoking any git command**:

```
Delivery target branch name is invalid — check status.md.
```

### Sub-step 2b-2 — Divergence check

Run, with both refs passed as **discrete quoted positional arguments** (never interpolated into an `eval` string or `bash -c`):

```
git rev-list --count "$target_branch"..."$branch"
```

The three-dot form counts commits on `$target_branch` not reachable from `$branch` — exactly "how far behind." Capture both the output (`N`) and the exit code.

- **git exits non-zero** (ref not found or other git error): halt with `Divergence check failed — confirm that <target> exists locally (git fetch may be required).`
- **exit 0 and N == 0**: mark status `up to date` and proceed to Step 3 — regardless of whether `--rebase` was passed.
- **exit 0 and N > 0 and `--rebase` NOT passed**: print the warning and **halt delivery**:

  ```
  Warning: branch is N commit(s) behind <target>. Pass --rebase to auto-rebase before delivering, or rebase manually.
  ```

- **exit 0 and N > 0 and `--rebase` passed**: continue to sub-step 2b-3.

### Sub-step 2b-3 — Pre-rebase state check

Resolve `$worktree_path` (`.worktrees/XXXX-<slug>`) **once** and reuse the same variable in 2b-4 to avoid a TOCTOU on the path. Before attempting a rebase, check for an in-progress rebase. `$worktree_path` is a **linked** worktree, so its `.git` is a *file* (`gitdir: …/.git/worktrees/<slug>`) and the rebase state dirs live under the resolved per-worktree git dir — **not** at `$worktree_path/.git/`. Ask git to resolve the real marker paths with `rev-parse --git-path` (which dereferences the linked-worktree git dir correctly) and test for the canonical in-progress-rebase directories:

```
rebase_merge="$(git -C "$worktree_path" rev-parse --git-path rebase-merge)"
rebase_apply="$(git -C "$worktree_path" rev-parse --git-path rebase-apply)"
[[ -d "$rebase_merge" || -d "$rebase_apply" ]]
```

`rebase-merge` covers interactive/merge rebases; `rebase-apply` covers am-based rebases — together they are what `git status` uses to detect a rebase in progress. **Do not** test the bare `"$worktree_path/.git/REBASE_HEAD"` path: for a linked worktree `.git` is a file, so that path can never exist and the guard would silently no-op (fail open) — letting 2b-4 collide with the existing rebase and 2b-5 destroy it with a spurious `rebase --abort`.

If either directory exists, **halt delivery** and attempt no rebase:

```
Worktree is already in a mid-rebase state — resolve or abort the existing rebase manually before delivering.
```

This guard is intentionally independent of the Step 7 mid-rebase handling (which rebases *other* in-flight worktrees after merge); do not extract a shared helper.

### Sub-step 2b-4 — Execute the rebase

Run (discrete quoted positional arguments):

```
git -C "$worktree_path" rebase "$target_branch"
```

If rebase exits zero: mark status `rebased (was N behind)` and continue to Step 3, carrying the gate-invalidation notice from 2b-6.

### Sub-step 2b-5 — Conflict-abort path

If the rebase exits non-zero:

1. Run `git -C "$worktree_path" rebase --abort` and capture its exit code.
2. If `rebase --abort` **succeeds** (exit 0):

   ```
   Rebase failed with conflicts — delivery halted. Rebase was aborted; worktree is clean. Resolve conflicts manually then re-deliver.
   ```

3. If `rebase --abort` **fails** (non-zero): report **both** the original rebase error and the abort failure, and instruct the operator: `Run git -C .worktrees/XXXX-<slug> rebase --abort manually to clean up.`

In **all** conflict cases, do **not** proceed to Step 3.

### Sub-step 2b-6 — Gate-invalidation notice

When the rebase succeeded (2b-4 path), pass this note to the Step 3 confirmation block:

```
Note: gates ran on the pre-rebase branch — consider re-running /build XXXX to re-validate before merging.
```

## Step 3 — Confirm

Surface the Step 2b divergence result on the `Branch:` line — `up to date` when N == 0, or `rebased (was N behind)` when a `--rebase` succeeded. Delivery only reaches Step 3 on those two paths; every Step 2b halt (divergence without `--rebase`, invalid target name, mid-rebase state, or a rebase conflict) stops before this prompt. When a rebase occurred, include the gate-invalidation notice from sub-step 2b-6 immediately below the branch line.

```
Ready to deliver ticket XXXX:
  Branch:  up to date | rebased (was N behind)      (from Step 2b)
  [Note: gates ran on the pre-rebase branch — consider re-running /build XXXX to re-validate.]   ← only after a successful rebase
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

## Step 5 — Candidate learnings (present, then append accepted)

`.tickets/_learnings.md` is lead-curated. The harness appends to it **only after the
lead approves**, and only via the template-field-only write path below — it never writes
raw extracted text.

1. Call `${CLAUDE_PLUGIN_ROOT}/context/helpers/parse-gate-findings.md` with the ticket's
   `gate-findings.md`, the ticket number, and today's date. It returns a normalized,
   sanitized candidate list (≤ 5, BLOCKER/MAJOR prioritized).

   **Path note:** by this step the ticket directory has already been archived (Step 4)
   and the worktree removed, so `gate-findings.md` now lives at
   `.tickets/completed/XXXX-<slug>/gate-findings.md` — pass **that** path, not the
   pre-archive `.tickets/XXXX-<slug>/` one, which no longer exists. If it is absent,
   the helper returns no candidates and this step is skipped (below).
2. Call `${CLAUDE_PLUGIN_ROOT}/context/helpers/candidate-learnings-flow.md` with that
   candidate list and `.tickets/_learnings.md`. It deduplicates against existing
   content, presents ready-to-paste lines under a "Candidate learnings" section, runs a
   single accept/reject exchange, and appends only accepted entries — each built from
   the validated template fields (`date | gate | ticket | pattern`), never from raw text.

If `gate-findings.md` is absent or empty (or parse-gate-findings.md returns no
candidates), this step is **silently skipped** — no "Candidate learnings" section
appears in the report.

**Opportunistic by design:** `gate-findings.md` is written by the `/gate` command, not
by the default `/build` gate loop (which calls the gate MCP tool directly). So this
`/deliver` capture fires only when a `gate-findings.md` exists for the ticket (e.g. the
lead ran `/gate` during review). The always-available capture path is
`/harvest-learnings`, which mines the auto-populated `.harness/memory.db` for recurring
cross-ticket patterns between deliveries — run it periodically regardless of whether any
single delivery produced gate findings.

The model's raw per-failure record also lives in `.harness/memory.db` via
`memory(action="record", ...)` calls during the gate/repair loop — that is the
machine-readable layer and stays opaque. The lead's `_learnings.md` is the
human-readable, lead-approved layer, and `/harvest-learnings` mines the same `memory.db`
for recurring cross-ticket patterns between deliveries.

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
