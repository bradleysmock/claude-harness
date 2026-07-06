# Solution

**Ticket**: 0008
**Title**: Pre-deliver rebase guard

## Approach

Add a divergence check as Step 2b in `context/flows/deliver-ticket.md`, placed after the existing file-conflict check (Step 2) and before the confirmation prompt (Step 3). Use `git rev-list --count main...<branch>` to count how many commits `main` has that the ticket branch lacks. If that count is greater than zero and `--rebase` was not passed, halt with a warning. If `--rebase` was passed, validate the target branch name, pre-check for a mid-rebase state, execute `git rebase <target>` in the worktree, and handle conflict abort as a named checked sub-step before proceeding to Step 3.

## Components

| Component | Responsibility | Key interfaces |
|---|---|---|
| `context/flows/deliver-ticket.md` — new Step 2b | Divergence check, `--rebase` execution, conflict-abort path | Reads `$ARGUMENTS` for `--rebase` flag; runs `git rev-list`, `git rebase`, `git rebase --abort` as discrete argument-passing calls |
| Step 3 confirmation block (existing) | Surface branch status when delivery proceeds | Receives "up to date" or "rebased (was N behind — note: re-run /build to re-validate gates)" label from Step 2b; only fires when Step 2b succeeds or was a no-op |

## Tech Choices

| Choice | Rationale |
|---|---|
| `git rev-list --count <target>...<branch>` (three-dot) | Counts commits on `<target>` not reachable from `<branch>` — exactly "how far behind"; completes in O(log N) when commit-graph is built |
| `git -C "$worktree_path" rebase "$target_branch"` | Keeps rebase isolated to worktree; both path and target passed as discrete quoted positional arguments, never interpolated |
| Halt (not warn-and-continue) on divergence without `--rebase` | Fail-closed: prevents silent stale-baseline deliveries; operator must be explicit |
| `--rebase` as explicit opt-in flag | Auto-rebase changes history; operator must choose intentionally |
| Branch-name allowlist `^[a-zA-Z0-9][a-zA-Z0-9_.-]*(/[a-zA-Z0-9][a-zA-Z0-9_.-]*)*$` | Permits remote-tracking names (`origin/main`) while blocking path traversal (`../evil`, `.hidden`) and multi-level traversal; leading dashes excluded to prevent flag injection |

## Step 2b Specification (authoritative for implementer)

### Sub-step 2b-1 — Resolve target branch
Read delivery target from `status.md` if present; default to `main`. Validate the value against `^[a-zA-Z0-9][a-zA-Z0-9_.-]*(/[a-zA-Z0-9][a-zA-Z0-9_.-]*)*$` (permits `origin/main`; blocks `../traversal`, `.hidden`, flag-like leading dashes). If validation fails, halt before invoking any git command: "Delivery target branch name is invalid — check status.md."

### Sub-step 2b-2 — Divergence check
Run `git rev-list --count "$target_branch"..."$branch"` (both names as discrete quoted positional arguments, never interpolated into an `eval` string or `bash -c`). Capture both the output and the exit code.

- If `git rev-list` exits non-zero (ref not found or other git error): halt with "Divergence check failed — confirm that `$target_branch` exists locally (git fetch may be required)."
- If exit code is 0 and N == 0: mark status "up to date" and proceed to Step 3, regardless of whether `--rebase` was passed.
- If exit code is 0 and N > 0 and `--rebase` was NOT passed: print "Warning: branch is $N commit(s) behind $target_branch. Pass --rebase to auto-rebase before delivering, or rebase manually." **Halt delivery.**
- If exit code is 0 and N > 0 and `--rebase` was passed: continue to sub-step 2b-3.

### Sub-step 2b-3 — Pre-rebase state check
Resolve `$worktree_path` from `status.md` branch or the default worktree convention. Before attempting rebase, check: `[[ -f "$worktree_path/.git/REBASE_HEAD" ]]`. If the file exists: "Worktree is already in a mid-rebase state — resolve or abort the existing rebase manually before delivering." **Halt delivery.** Use the same `$worktree_path` variable in the check and in sub-step 2b-4 to eliminate TOCTOU on the path. This guard parallels the mid-rebase check in Step 9 (which handles other in-flight worktrees); they are intentionally independent — Step 2b operates on the current ticket before merge; Step 9 operates on all other tickets after merge. Do not extract these into a shared helper.

### Sub-step 2b-4 — Execute rebase
Run `git -C "$worktree_path" rebase "$target_branch"` (both paths and branch names passed as discrete quoted positional arguments). If rebase exits zero: mark status "rebased (was N behind)" and continue to Step 3.

### Sub-step 2b-5 — Conflict abort path (FR-5)
If rebase exits non-zero:
1. Run `git -C "$worktree_path" rebase --abort` and capture its exit code.
2. If `rebase --abort` succeeds (exit 0): report "Rebase failed with conflicts — delivery halted. Rebase was aborted; worktree is clean. Resolve conflicts manually then re-deliver."
3. If `rebase --abort` fails (non-zero): report both the original rebase error and the abort failure. Instruct the operator: "Run `git -C .worktrees/XXXX-<slug> rebase --abort` manually to clean up." **In all cases, do not proceed to Step 3.**

### Sub-step 2b-6 — Gate-invalidation notice
When rebase succeeded (sub-step 2b-4 path), pass the following note to the Step 3 confirmation block: "Note: gates ran on the pre-rebase branch — consider re-running /build XXXX to re-validate."

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|---|---|---|
| FR-1, FR-6 | Unit | Branch at same commit as target → count = 0 → no warning, proceed |
| FR-2, FR-3 | Unit | Branch 2 commits behind target, no `--rebase` → warning printed, delivery halted |
| FR-4, FR-7 | Integration | `--rebase` passed, no conflicts → rebase succeeds; Step 3 confirmation shows "rebased (was 2 behind)" + gate-invalidation notice |
| FR-5 | Integration | `--rebase` passed, conflict exists → `git rebase --abort` succeeds; command exits cleanly, Step 3 not reached |
| FR-5 (abort fail) | Integration | `--rebase` passed, conflict + `rebase --abort` fails → both errors reported, operator instructed to clean up manually |
| FR-6 + `--rebase` | Integration | `--rebase` passed but N == 0 → no rebase attempted, confirmation shows "up to date" (negative: assert no `git rebase` subprocess was spawned) |
| D-06 gate warning | Integration | `--rebase` succeeds → Step 3 confirmation block includes gate-invalidation notice visibly |
| Mid-rebase guard | Integration | Worktree already in mid-rebase state when `--rebase` passed → halt with named error, no rebase attempted |
| Input validation | Unit | Invalid branch name in `status.md` → halt before any git call; assert no git subprocess spawned (instrument or mock `git` calls) |
| FR-8 | — | xref requirements.md FR-8 |
| FR-9 | — | xref requirements.md FR-9 |

## Tradeoffs

- **Chose halt-by-default over warn-and-continue**: warn-and-continue replicates the current silent behavior; fail-closed is the correct default for a safety guard.
- **Chose not to auto-re-run gates after rebase**: out of scope; operator is warned to re-run /build manually.
- **Accepting risk of**: operator skipping /build after a successful rebase. Mitigated by gate-invalidation notice in the Step 3 confirmation block (D-06 fix).

## Risks

- `git rev-list` three-dot syntax returns the count on the `target` side of the asymmetric difference; this is correct for "how far behind."
- NFR-2 (under one second for divergence check) holds when the commit graph cache (`.git/objects/info/commit-graph`) is built; on repos where the cache is absent, `git rev-list` traverses the full DAG and may exceed 1 second on large repos. The NFR is scoped to commit-graph-enabled repos; operators on bare repos without the cache should run `git commit-graph write` once.
- Step 2b inserts between Steps 2 and 3; subsequent step numbers (3–10) remain unchanged, preserving the existing monotonic flow numbering.

## Implementation Order (TDD — tests before implementation)

1. Write unit tests for divergence-count helper logic (N=0 and N>0 cases, and input-validation rejection).
2. Write Step 2b divergence-check and halt logic (sub-steps 2b-1, 2b-2) to pass unit tests.
3. Write integration tests for `--rebase` success path, conflict-abort path, abort-failure path, mid-rebase guard, and gate-invalidation notice.
4. Write Step 2b rebase execution and conflict-abort sub-steps (2b-3 through 2b-6) to pass integration tests.
5. Update Step 3 confirmation block template to conditionally include branch-status line and gate-invalidation notice.
