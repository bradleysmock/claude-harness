# Flow: deliver — ticket mode

Merge the ticket's worktree branch into main, remove the worktree, and record learnings. The diff was already reviewed after `/build`.

<!-- progress-checklist -->
**Progress checklist** — as the first action, create the `TodoWrite` checklist (see "Progress checklist" in `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`):

`Merge worktree · Status → done + archive · Cleanup`

**Sub-flow note:** this flow may run as a sub-flow under `/autopilot`. If a checklist already exists for this run (autopilot created it), follow the convention's one-list-per-run rule — adopt that existing list and advance its delivery stages, do **not** create a second one.

## The `--pr` flag (optional)

`/deliver XXXX --pr` opts into GitHub PR creation. When the flag is present, this flow pushes the ticket branch to the remote and opens a GitHub PR (Step 3.5) **after** the confirmation prompt but **before** the local squash-merge (Step 4). The PR title comes from the ticket title; the PR body is assembled from the ticket's `solution.md` and `requirements.md`. PR creation is a **complement** to the local merge, never a replacement — the squash-merge in Step 4 remains the delivery mechanism.

**When `--pr` is not passed, this flow behaves exactly as before** — no push, no PR, byte-for-byte identical to the standard delivery path. Step 3.5 is skipped entirely, and the Step 3 confirmation prompt does not list the push/PR lines.

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

## Step 1.7 — Refine-touched marker check (fail-closed, independent of the caller)

Before offering delivery, resolve `refine-touched.md` from the **branch's** copy of
the ticket directory — the worktree path
(`.worktrees/XXXX-<slug>/.tickets/XXXX-<slug>/refine-touched.md`) or, equivalently,
`git show <branch>:.tickets/XXXX-<slug>/refine-touched.md` — **never** the root
`.tickets/` stub, matching the Step 1.6 branch-copy resolution pattern.

- **Marker absent** → continue to Step 2; delivery proceeds exactly as before, no
  new gate.
- **Marker present** → the ticket's design scope was machine-adjusted by a
  `/refine` pass and must not merge unseen. Step 3's confirmation prompt is
  **never skipped** for this delivery — this holds even when `/deliver` is
  reached via autopilot's Step B skip-Step-3 override; that override does not
  apply while the marker is present. Print the marker's contents (the `/refine`
  audit trail) as part of the Step 3 confirmation block.

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

## gh_guard (named block)

Availability, authentication, existing-PR, and failure-classification guard for `--pr` delivery. **Input:** the ticket `branch` name and ticket number. **Output:** one of three decisions — `skip` (proceed to merge with no PR), `existing <url>` (an open PR already covers this branch — print the URL and proceed to merge), or `stop <message>` (an unexpected failure — halt delivery). PR creation is **one attempt, no retry** (NFR-2). This block is a documented seam — its input/output contract is testable without running the full deliver flow.

**NFR-1 (5-second bound) is enforced, not merely asserted:** wrap the auth and existing-PR probes in `timeout 5 …` so a hung `gh auth status` (which makes a token-validation network call) or a slow `gh pr view` cannot stall delivery. A `timeout`-killed probe exits non-zero and is treated exactly like the corresponding negative result — for `gh auth status` that means "not authenticated → skip + warn + continue" (fail-safe: a slow network never blocks the local merge).

Run the checks in order; act on the first that matches:

1. **Not installed** — `command -v gh` exits non-zero → **skip** with a warning (`gh not installed — skipping PR creation`) and continue the deliver flow.
2. **Not authenticated** — `timeout 5 gh auth status` exits non-zero (a non-zero status, or a timeout kill) → **skip** with a warning (`gh not authenticated — skipping PR creation`) and **continue** the deliver flow.
3. **PR already open (pre-check)** — read the branch's PR state without failing on absence:
   ```
   pr_state=$(timeout 5 gh pr view "$branch" --json state --jq '.state' 2>/dev/null)
   ```
   If `pr_state` is exactly the literal string `"OPEN"`, an open PR already exists → fetch its url (`timeout 5 gh pr view "$branch" --json url --jq '.url'`), print it, **skip** `gh pr create`, and continue to the merge. A `"CLOSED"` or `"MERGED"` state (or an empty result — no PR) is **not** treated as an existing open PR; fall through to creation.
4. **Create + classify** — the caller (Step 3.5) runs `gh pr create` once. Classify its exit:
   - Exit 0 → PR created; print the returned url and continue.
   - Non-zero **and** stderr matches the duplicate pattern `already exists` or `already has` (a TOCTOU race — a PR was opened between the pre-check and create) → treat as case 3: fetch the url via `timeout 5 gh pr view`, print it, and continue to the merge (**not** a hard stop).
   - Non-zero with **no** duplicate match → **stop**: report the error and print recovery instructions noting the branch is **already pushed** (`the branch is already pushed to origin; open a PR manually with gh pr create, or re-run /deliver XXXX --pr`). This recovery message must distinguish a PR-creation failure from a push failure (the push is handled in Step 3.5).

| Condition | Detection | Action |
|---|---|---|
| Not installed | `command -v gh` != 0 | skip + warn, continue |
| Not authenticated | `gh auth status` != 0 | skip + warn, continue |
| PR already open | state == `"OPEN"` | print url, skip create, continue |
| TOCTOU duplicate | `gh pr create` != 0, stderr ~ `already exists`/`already has` | fetch + print url, continue |
| Any other failure | `gh pr create` != 0, no dup match | stop + report + recovery |

## pr_body_builder (named block)

Assembles the PR body from the ticket's design artifacts. **Input:** the ticket directory path (`$ticket_dir` = `.tickets/XXXX-<slug>/`) and ticket number. **Output:** the path to a temp file holding the assembled body. The body is built into a `mktemp` file with a `trap` cleanup, eliminating the predictable-name race.

```
BODY_FILE=$(mktemp) || { echo "mktemp failed — aborting before push" >&2; exit 1; }
trap 'rm -f "$BODY_FILE"' EXIT
```

If `mktemp` fails, **abort before the branch is pushed** — nothing has been pushed at this point, so there is nothing to unwind.

**Approach summary** — extract the `## Approach` section from `solution.md` with awk. No `END` block is used: awk's `exit` skips the `END` action in some implementations, so an `END` block is prohibited here.
```
approach=$(awk '/^## Approach$/{found=1;next} found && /^## /{exit} found{print}' "$ticket_dir/solution.md")
```
If `approach` is empty (the section is absent or `solution.md` is missing), use the literal placeholder `(No Approach section found in solution.md)` — do not error.

**Acceptance Criteria checklist** — read the `## Acceptance Criteria` section from `requirements.md` and render each item as a Markdown checkbox `- [ ] …`, taking the **first non-blank line** of each item so a multi-line AC item yields exactly one checklist entry (no malformed indented continuations). If the section is absent or empty, emit a single placeholder line `- [ ] (No Acceptance Criteria section found in requirements.md)` — do not error.

**Ticket reference** — append a `Ticket: XXXX` line so the PR links back to the ticket number.

Write the Approach summary + AC checklist + `Ticket:` reference to `"$BODY_FILE"`, then hand its path to the caller for `gh pr create --body-file "$BODY_FILE"`.

**Same-shell lifetime (important):** the `trap … EXIT` fires when the shell process that registered it exits. `pr_body_builder` and the caller's `gh pr create --body-file "$BODY_FILE"` (Step 3.5 steps 3–4) **must run in the same shell session** — do **not** execute the builder in a command substitution `$( … )` or a separate subshell, or the `EXIT` trap fires and deletes `"$BODY_FILE"` before `gh pr create` can read it. Run steps 2–4 of Step 3.5 (build → push → create) as one shell invocation so cleanup happens only after the PR is created (or after the flow aborts). `mktemp`'s unpredictable name and the `EXIT` trap together guarantee no leaked temp file and no predictable-name race.

## Step 3 — Confirm

**Read smoke-test config once here** (reused in Step 4b — do **not** re-read `_standards.md` there). From `.tickets/_standards.md`: `smoke_test_command` (absent/empty → the whole smoke phase is skipped), `smoke_test_mode` (`auto-revert` default | `warn-only`), and `smoke_test_timeout` (integer seconds, default 60; > 300 → cap at 300 with a visible warning; non-integer/zero/negative → skip the smoke test with a visible warning echoing the invalid value). When a `smoke_test_command` is configured, add its command, mode, and timeout to the confirmation block below so the lead sees what will run before approving.

Surface the Step 2b divergence result on the `Branch:` line — `up to date` when N == 0, or `rebased (was N behind)` when a `--rebase` succeeded. Delivery only reaches Step 3 on those two paths; every Step 2b halt (divergence without `--rebase`, invalid target name, mid-rebase state, or a rebase conflict) stops before this prompt. When a rebase occurred, include the gate-invalidation notice from sub-step 2b-6 immediately below the branch line.

**When `--pr` is present**, include the two PR lines below (`git push origin <branch>` and `gh pr create …`) in the planned-actions list so the lead sees that the branch will be pushed and a GitHub PR opened (Step 3.5) **before** the local merge. When `--pr` is absent, omit both lines — the prompt is unchanged from the standard path.

```
Ready to deliver ticket XXXX:
  Branch:  up to date | rebased (was N behind)      (from Step 2b)
  [Note: gates ran on the pre-rebase branch — consider re-running /build XXXX to re-validate.]   ← only after a successful rebase
  [git push origin <branch>                                       ← only with --pr (Step 3.5): push before opening the PR]
  [gh pr create --title "<ticket title>" --body-file <tmp-body>   ← only with --pr (Step 3.5): open the GitHub PR before the local merge]
  git merge --squash <branch>      (one squashed commit — no per-branch-commit history, no merge commit)
  status.md → done
  mv .tickets/XXXX-<slug>/ .tickets/completed/XXXX-<slug>/   (archive)
  ↑ status → done and the archive are both folded into the single squash commit
  [smoke test: <smoke_test_command>  (mode <smoke_test_mode>, timeout <smoke_test_timeout>s)]   ← only when configured (Step 4b)
  git push      (main first — the durable product record)
  append {"event":"delivered","number":XXXX,"sha":<squash sha>} to the harness-tickets ledger (pushed; idempotent)
  git worktree remove .worktrees/XXXX-<slug>
  git branch -D <branch>      (-D, not -d: a squash leaves the branch without merge ancestry)
Proceed? (yes/no)
```

> **This is the ticket's only `main` commit.** Under the harness-tickets model nothing about the ticket touched `main` before now — the number claim and coarse lifecycle lived on the `harness-tickets` ledger, and the ticket dir lived on its feature branch. `deliver_squash()` pushes `main` first, then appends the `delivered` ledger event (idempotent by `(event, number)`, so a ledger race never blocks delivery), then removes the worktree + branch.

Stop if the user says no.

## Step 3.5 — Push branch and open PR (`--pr` only)

Runs **only when `--pr` was passed**, after the Step 3 confirmation and **before** the Step 4 squash-merge. When `--pr` is absent, **skip this entire step** — delivery proceeds directly from Step 3 to Step 4, unchanged. PR creation is a complement to the local merge, never a replacement.

**Source the PR title first.** Read the ticket title into `TICKET_TITLE` from the branch's `status.md` `title:` field (authoritative), falling back to the `**Title**:` line in `problem.md` if `status.md` has no title. Keep it as a shell variable — it is passed to the PR-create call as a double-quoted argument in step 4, never interpolated into a command string. If no title can be read, use the ticket number (`Ticket 0028`) as the title rather than passing an empty `--title`.

1. **Run the `gh_guard` availability + auth pre-checks.** If the guard returns **skip** (gh missing or unauthenticated), print its warning and go straight to Step 4 — the ticket still delivers normally. If it returns **existing `<url>`** (an open PR already covers the branch), print the url and go to Step 4.
2. **Build the PR body** with the `pr_body_builder` named block, producing `"$BODY_FILE"`. This is done **before the push** so that a `mktemp` failure aborts while the branch is still unpushed — matching the spec's "mktemp fails → abort before push" and leaving nothing to unwind. Steps 2–4 run in one shell session (the `pr_body_builder` `EXIT` trap must survive until step 4 — see its Same-shell lifetime note).
3. **Push the branch.** The PR must reference the pushed branch, so the push happens before PR creation and before the local merge:
   ```
   git push origin "$branch"
   ```
   If the push fails, **stop** and report it as a **push failure** — distinct from a PR-creation failure. No PR was attempted and the local merge has not run, so the operator can retry `/deliver XXXX --pr` after resolving the remote issue.
4. **Create the PR — one attempt** (`gh_guard` case 4). Pass the ticket title as a double-quoted shell variable — **never** assembled via string concatenation (CLAUDE.md "No shell concatenation"), so a title containing `"`, `$`, `` ` ``, or `;` is safe:
   ```
   gh pr create --title "$TICKET_TITLE" --body-file "$BODY_FILE" --head "$branch"
   ```
   Classify the exit via the `gh_guard` create-and-classify rules: exit 0 → print the PR url; a TOCTOU duplicate (stderr matches `already exists`/`already has`) → fetch and print the existing url and continue; any other non-zero exit → **stop** with recovery instructions (the branch is already pushed). A PR-creation failure here is reported differently from the push failure in step 2.
5. On **skip / existing / created**, continue to Step 4 (the local squash-merge).

## Step 4 — Squash-merge: fold `→ done` + archive into one commit

A delivered ticket adds **exactly one** commit to `main`. Run the sequence below — encapsulated and unit-tested as `ticket.py deliver_squash()` (it asserts the one-commit invariant). It mirrors the archive pattern (OS `mv` + `git rm -r --cached` + `git add`, **never** `git mv`, which is unsound against the index `merge --squash` leaves):

```
# 0. Record the pre-merge SHA (used by Step 4b's smoke-test revert report; distinct from the merge-commit SHA)
pre_merge_sha=$(git rev-parse HEAD)

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

# 6. Record the merge-commit SHA (the revert target for a smoke-test failure in Step 4b)
merge_commit_sha=$(git rev-parse HEAD)
```

Publish and cleanup (the old sub-step: `git push`, `git worktree remove`, `git branch -D`) are deferred to **Step 4c** so they run only after Step 4b's smoke test passes — leaving the branch and worktree intact if it fails.

If the `git merge --squash` reports a conflict, report the error and stop without committing or cleaning up.

> **Squash status resolution:** because `main` carried only the `claimed` stub for this ticket and never re-touched `.tickets/XXXX-<slug>/` after the claim, the squash merge's merge base for that path is the claim stub and only the branch changed it — so it resolves cleanly with no conflict. The branch's `review-ready` `status.md` is squash-staged, then overwritten in place to `done` before the single commit. There is **no `--no-ff` merge commit and no separate `→ done` / archive commit** — `→ done` and the archive are folded into the one squash commit. A reopened ticket repeats this, adding a further squashed commit.

**Marker cleanup:** if the ticket carried a `refine-touched.md` marker (Step 1.7),
`_fold_archive` deletes it from the archived ticket directory as part of the fold
in step 2 above — the squash commit lands with no `refine-touched.md` under
`completed/<slug>/`, so the marker never survives into the archive.

**Idempotency:** If `.tickets/completed/XXXX-<slug>/` already exists and `.tickets/XXXX-<slug>/` is absent, the ticket is already archived — skip the mv and continue with the commit.

**Partial-move guard:** If both `.tickets/XXXX-<slug>/` and `.tickets/completed/XXXX-<slug>/` exist simultaneously, warn the lead — treat the root copy as authoritative and proceed with the mv from root.

## Step 4b — Post-merge smoke test

Runs after the Step 4 commit (both SHAs captured) and **before Step 4c publish/cleanup**, so the branch and worktree survive a failure for rework. Uses the config read once in Step 3 — do **not** re-read `_standards.md`. Skip this whole step when `smoke_test_command` is absent/empty, or when `smoke_test_timeout` is non-integer/zero/negative (skip + visible warning echoing the invalid value; cap at 300 with a warning when higher, default 60).

**Concurrency guard first:** read `.tickets/.active`; if it names a ticket other than this one, halt with `DELIVERY HALTED — another delivery is in progress (<active-ticket>); resolve before retrying` — run no smoke test and no revert.

**Run** `shlex.split(smoke_test_command)` as a subprocess with `shell=False` in the repo root, started in its own process group (`os.setsid()`), capturing stdout+stderr. If the split contains shell metacharacters (`|`, `>`, `<`, `&&`, `;`), warn that they are passed as **literal arguments** — do not abort. Pass an explicit env allowlist dict (never `None`): the keys `PATH`, `HOME`, `SHELL`, `TERM`, `USER`, `LANG`, plus every `os.environ` key matching `re.match(r"^LC_", k)` — sensitive vars like `AWS_SECRET_ACCESS_KEY` / `DATABASE_URL` are excluded.

**Timeout:** after `smoke_test_timeout` seconds, `os.killpg(os.getpgid(proc.pid), signal.SIGTERM)`, wait ≤ 5 s for the group to exit, then escalate to `SIGKILL` — no `sleep`-polling; total window ≤ `timeout + 10` s. Treat a timeout as a non-zero exit.

**Exit 0** → continue to Step 4c; Steps 5–10 proceed unchanged.

**Non-zero exit / timeout** — branch on `smoke_test_mode`:

- **auto-revert** (default): `git revert -m 1 --no-edit <merge_commit_sha>`. Only after it exits 0: set `status: implementing`, commit that transition to main, **leave the branch and worktree intact (skip Step 4c)**, and emit `SMOKE TEST FAILED — main reverted to <pre_merge_sha>` plus the captured output truncated to 2000 chars. If `git revert` exits non-zero, emit `AUTO-REVERT FAILED — main is in merged state; manual intervention required: git revert -m 1 --no-edit <merge_commit_sha>` and halt without proceeding to Steps 5–10.
- **warn-only**: store the failure signal in a local variable **before** cleanup, then run Step 4c and Steps 5–10 normally, and append a `SMOKE TEST FAILED` block (with the captured output) to the Step 8 report so it survives the branch and worktree deletion.

## Step 4c — Publish and clean up

Reached when Step 4b passed, was skipped (no smoke test configured), or ran in `warn-only` mode. It is **not** run on an `auto-revert` failure (branch + worktree stay intact for rework). Publish first; only on a successful push remove the worktree and delete the branch (`-D`, not `-d`: a squash leaves the branch without merge ancestry). On a rejected push, stop with both intact and retry.

```
git push
git worktree remove .worktrees/XXXX-<slug>
git branch -D <branch>
```

## Step 5 — Candidate learnings (present, then append accepted)

`.tickets/_learnings.md` is lead-curated. The harness appends to it **only after the
lead approves**, and only via the template-field-only write path below — it never writes
raw extracted text.

1. Call `${CLAUDE_PLUGIN_ROOT}/context/helpers/parse-gate-findings.md` with the ticket's
   `gate-findings.md`, the ticket number, and today's date. It returns a normalized,
   sanitized candidate list (≤ 5, BLOCKER/MAJOR prioritized).

   **Also scan `critic-findings.md`** — the persisted per-round critic reports and
   escalation diagnoses (see "Critic findings file" in
   `${CLAUDE_PLUGIN_ROOT}/context/harness-reference.md`). Call the same helper a second
   time **with `source_kind="critic"`** so it uses the critic-report parser (Step 2c)
   rather than the gate parser — the gate parser would return nothing, because
   `critic-findings.md` has no `**Status**: FAIL` sections. Its records come back tagged
   `gate="critic"`. Merge them with the gate candidates, then **dedup** on
   `(gate, pattern)` and re-apply the ≤ 5 cap with BLOCKER/MAJOR prioritized, so
   recurring critic-level patterns (not just gate findings) can reach `_learnings.md`.

   **Path note:** by this step the ticket directory has already been archived (Step 4)
   and the worktree removed, so `gate-findings.md` and `critic-findings.md` now live at
   `.tickets/completed/XXXX-<slug>/` — pass **those** paths, not the pre-archive
   `.tickets/XXXX-<slug>/` ones, which no longer exist. If a file is absent, the helper
   returns no candidates for it, and this step is skipped when **both** are absent
   (below).
2. Call `${CLAUDE_PLUGIN_ROOT}/context/helpers/candidate-learnings-flow.md` with that
   candidate list and `.tickets/_learnings.md`. It deduplicates against existing
   content, presents ready-to-paste lines under a "Candidate learnings" section, runs a
   single accept/reject exchange, and appends only accepted entries — each built from
   the validated template fields (`date | gate | ticket | pattern`), never from raw text.

If **both** `gate-findings.md` and `critic-findings.md` are absent or empty (or the
helper returns no candidates from either), this step is **silently skipped** — no
"Candidate learnings" section appears in the report.

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
   - Success: record "YYYY: rebased OK", then **re-gate before deciding status** — a clean rebase must not downgrade a ticket by ceremony alone. Call `gate_run_on_dir(".worktrees/YYYY-<slug>", "auto", project_root)`:
     - **Gate passes**: keep the ticket at `review-ready` and record "YYYY: re-gated clean after rebase". No status change, no branch commit.
     - **Gate fails**: the rebase introduced a semantic conflict the merge did not flag. If the ticket was `review-ready`, downgrade it to `implementing` (record the failing gate). Only an actual gate failure downgrades a ticket.
   - Failure: run `git -C .worktrees/YYYY-<slug> rebase --abort`, record failure with manual recovery instructions.

If any ticket was downgraded to `implementing` here (i.e. its post-rebase re-gate failed), commit that transition **on its own branch** (inside its worktree — the `implementing` state is branch-only, never committed to `main`), and push:
```
git -C .worktrees/YYYY-<slug> add .tickets/YYYY-<slug>/status.md
git -C .worktrees/YYYY-<slug> commit -m "chore(ticket): YYYY → implementing (rebased onto main)"
git -C .worktrees/YYYY-<slug> push
```

## Step 8 — Report

Summarize what was delivered (the single squash commit), cleaned up, and any rebase results.
