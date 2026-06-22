# Requirements

**Ticket**: 0019
**Title**: Post-merge smoke test

## Functional Requirements

1. The system must read `smoke_test_command` from `.tickets/_standards.md` at the start of
   `/deliver` (ticket mode). If absent or empty, the smoke-test phase is skipped entirely.
2. The system must read `smoke_test_mode` from `_standards.md` (`auto-revert` or `warn-only`;
   default `auto-revert`) and `smoke_test_timeout` (integer seconds; default 60, max 300).
   If `smoke_test_timeout` exceeds 300, cap at 300 and emit a visible warning. If the value
   is non-integer, zero, or negative, skip the smoke test and emit a visible warning including
   the invalid value.
3. After a successful `git merge --no-ff`, the system must run `smoke_test_command` as a
   subprocess via `shlex.split(smoke_test_command)` with `shell=False`, in the repository
   root, capturing stdout/stderr. The subprocess must be started in its own process group
   (`os.setsid()`) so that timeout kill reaches all child processes. `smoke_test_command` is
   a lead-curated value committed to `_standards.md`; it is treated as a trusted operator
   value. No allow-list validation beyond `shlex.split` + `shell=False` is required. If the
   split result contains shell metacharacters (`|`, `>`, `<`, `&&`, `;`), emit a visible
   warning that these will be passed as literal arguments (not interpreted as shell operators),
   but do not abort — the operator's intent may be valid.
4. Config is read once at the top of Step 3's conditional block and reused in Step 4b;
   `_standards.md` is not re-read in Step 4b.
5. At the start of Step 4b (before running the smoke command), the system must check
   `.tickets/.active`. If it names a ticket other than the current ticket, halt immediately
   with: `DELIVERY HALTED — another delivery is in progress (<active-ticket>); resolve before
   retrying`. Do not proceed to the smoke test or revert.
6. If the command exits zero within the timeout, the smoke test passes and delivery continues
   normally (Steps 5–10 of deliver-ticket.md proceed unchanged).
7. If the command exits non-zero, the system must:
   a. In `auto-revert` mode: the pre-merge SHA (`git rev-parse HEAD` before merge) and the
      merge-commit SHA (`git rev-parse HEAD` after merge) are two distinct values — both must
      be captured. Run `git revert -m 1 --no-edit <merge-commit-sha>`. Only after confirming
      the revert exits zero: set `status: implementing` and commit the status transition to
      main. Leave the branch and worktree intact. Report the failure with the captured output.
      If `git revert` itself exits non-zero, emit:
      `AUTO-REVERT FAILED — main is in merged state; manual intervention required:
      git revert -m 1 --no-edit <merge-commit-sha>` and halt without proceeding to Steps 5–10.
      Fixture for the revert-fail integration test: after the synthetic merge, amend the
      target file on main directly to create a conflict that makes `git revert -m 1` exit
      non-zero. Alternatively, mock the `git revert` subprocess return code at the process
      boundary (not an internal seam) — document the mock as intentional.
   b. In `warn-only` mode: continue delivery (Steps 5–10, including cleanup) but store the
      failure signal in a local variable before cleanup and append a `SMOKE TEST FAILED`
      warning block to the Step 10 report after cleanup. The warning must appear in the final
      report even after branch and worktree deletion. Cleanup proceeds normally.
8. If the command exceeds `smoke_test_timeout`, the system must send `SIGTERM` to the process
   group (`os.killpg(os.getpgid(proc.pid), signal.SIGTERM)`), wait up to 5 seconds for the
   process group to exit, then escalate to `SIGKILL` if any process remains. Treat the
   timeout as a non-zero exit (applying the same auto-revert or warn-only path). No
   `sleep`-polling. Total timeout + kill window must not exceed `smoke_test_timeout + 10 s`.
9. The smoke test must run after Step 4 (merge) and before Step 5 (worktree cleanup) so that
   the worktree and branch still exist on failure for rework.
10. The Step 3 confirmation prompt must display the smoke-test command, mode, and timeout when
    a smoke test is configured, so the lead knows what will run before approving.
11. On auto-revert, the system must emit a clearly formatted failure report:
    `SMOKE TEST FAILED — main reverted to <pre-merge-sha>` plus the captured output (truncated
    to 2000 chars). Both SHAs are recorded before the merge executes (pre-merge SHA) and after
    (merge-commit SHA).

## Non-Functional Requirements

1. The smoke-test subprocess must run with a minimal safe environment. Pass only: `PATH`,
   `HOME`, `SHELL`, `TERM`, `USER`, `LANG`, and all keys whose names start with `LC_`
   (materialized by iterating `os.environ` and including keys matching `re.match(r'^LC_', k)`).
   The subprocess `env=` kwarg must be an explicit allowlist dict, not `None`.
2. Timeout enforcement must use process-group kill (`os.killpg`), with SIGKILL escalation
   after 5 s if SIGTERM does not terminate the process group. No `sleep`-polling.
3. The flow document changes must not exceed 35 additional lines.

## Test Strategy

| Type        | Rationale                                                       |
|-------------|-----------------------------------------------------------------|
| Unit        | Config parsing: absent, empty, non-integer, zero, negative,    |
|             | above-max (300+); `shlex.split` parsing; metacharacter warning; |
|             | output truncation at 2000 chars; SIGKILL escalation after SIGTERM|
|             | (unit-test via mock); env allowlist: `LC_*` iteration is correct,|
|             | sensitive vars (`AWS_SECRET_ACCESS_KEY`, `DATABASE_URL`) excluded|
| Integration | Synthetic git repo: (1) no config → skip; (2) exit 0 → passes; |
|             | (3) exit 1 auto-revert → main reverted, branch/worktree intact, |
|             | status=implementing; (4) exit 1 warn-only → completes incl.     |
|             | cleanup, SMOKE TEST FAILED survives to final report; (5) timeout|
|             | → SIGTERM+SIGKILL fired, treated as failure; (6) revert fails → |
|             | halt with error, no cleanup; (7) `.active` set to other ticket  |
|             | → halt before smoke test fires                                  |

## Acceptance Criteria

- Delivering a ticket with no `smoke_test_command` defined behaves identically to today.
- Delivering with a passing smoke test (exit 0) completes delivery as normal.
- Delivering with a failing smoke test (exit 1) in `auto-revert` mode: merge commit is
  reverted on main (`git revert -m 1 --no-edit <merge-sha>`), branch and worktree are
  preserved, `status.md` shows `implementing`.
- If `git revert` itself fails, `/deliver` halts with `AUTO-REVERT FAILED` message and
  does not proceed to cleanup. Main remains in the merged state with recovery instructions.
- Delivering with a failing smoke test in `warn-only` mode: delivery completes including
  cleanup; the `SMOKE TEST FAILED` warning appears in the final Step 10 report.
- A smoke test exceeding `smoke_test_timeout` is killed (SIGTERM then SIGKILL) and treated
  as failure.
- If `.tickets/.active` names a different ticket at Step 4b start, delivery halts immediately
  with a clear message; no smoke test or revert fires.
- The confirmation prompt (Step 3) shows smoke-test details when configured.
- The subprocess does not inherit sensitive environment variables from the operator's session.

## Open Questions

- None.
