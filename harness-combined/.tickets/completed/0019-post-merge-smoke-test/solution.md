# Solution

**Ticket**: 0019
**Title**: Post-merge smoke test

## Approach

Extend `deliver-ticket.md` with a new Step 4b that reads smoke-test config once at Step 3
(reused in Step 4b — not re-read), checks the `.active` sentinel for concurrent delivery,
runs the command via `shlex.split` + `shell=False` with an explicit env allowlist, a hard
timeout, SIGTERM + SIGKILL escalation, and branches on exit code. On failure in `auto-revert`
mode the merge commit is reverted (`git revert -m 1`); if revert fails, delivery halts with
explicit recovery instructions. In `warn-only` mode delivery completes with the failure signal
stored before cleanup and emitted in the Step 10 report. Changes land in `deliver-ticket.md`
and `init.md` (to seed three config keys in the `_standards.md` template).

## Components

| Component | Responsibility | Key interface |
|---|---|---|
| `deliver-ticket.md` Step 3 | Read config once; display smoke details in confirmation | Reads `_standards.md`; stores cmd/mode/timeout for Step 4b |
| `deliver-ticket.md` Step 4b | Check `.active`; run smoke; branch on result; SIGTERM+SIGKILL; revert | `shlex.split`; `os.setsid`/`os.killpg`; `git revert -m 1`; status transition |
| `_standards.md` template (init.md) | Seed three commented-out config keys with inline docs | Lead opts in by uncommenting; no-pipes note included |

## Tech Choices

| Choice | Rationale |
|---|---|
| `shlex.split` + `shell=False` | Prevents shell-injection; metacharacter warning for UX |
| Config read once at Step 3 | Avoids duplicate `_standards.md` reads; single source of truth for cmd/mode/timeout |
| `os.setsid()` + `os.killpg(SIGTERM)` + SIGKILL after 5 s | Kills child processes; handles SIGTERM-ignoring scripts; process-independent of `shell=False` |
| Explicit `env=` allowlist (`PATH`, `HOME`, `SHELL`, `TERM`, `USER`, `LANG`, all `LC_*`) | Secure-by-default; `LC_*` keys materialized via `re.match(r'^LC_', k)` over `os.environ` |
| `git revert -m 1 --no-edit` | Non-destructive; `-m 1` required for merge commits; halts on revert failure |
| Preserve branch+worktree on auto-revert | Lead can fix and re-run `/build` + `/deliver` |
| Store warn-only failure flag before cleanup | Ensures `SMOKE TEST FAILED` appears in Step 10 report even after branch deletion |
| `.active` sentinel check at Step 4b start | Detects concurrent delivery before smoke test fires; fails closed |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|---|---|---|
| FR-1 | Unit | Missing `_standards.md` → skip; key absent → skip; key empty → skip |
| FR-2 | Unit | Defaults applied; value=301 → cap+warn; value=0 → skip+warn; value=-1 → skip+warn; value="banana" → skip+warn |
| FR-3 | Unit | `shlex.split` used; `shell=False` asserted; metacharacter tokens → warning emitted |
| FR-3 trust | Unit | No additional validation beyond `shlex.split` (confirmed by design — trusted operator input) |
| FR-4 (config read once) | Unit | `_standards.md` parse called exactly once per deliver run |
| FR-5 (.active) | Integration | `.active` = other ticket → halt before smoke; no revert; no cleanup |
| FR-6 | Integration | Exit 0 → delivery completes; all Steps 5–10 execute |
| FR-7a | Integration | Exit 1, auto-revert succeeds: main reverted, branch intact, status=implementing, commit on main |
| FR-7a revert-fail | Integration | Exit 1, revert exits non-zero: halt with `AUTO-REVERT FAILED`; no cleanup; main in merged state. Fixture: amend target file on main post-merge to cause conflict; OR mock `git revert` at process boundary (documented mock) |
| FR-7b | Integration | Exit 1, warn-only: delivery completes incl. cleanup; `SMOKE TEST FAILED` survives to final Step 10 output |
| FR-8 | Integration | Cmd sleeps > timeout → SIGTERM sent; if not dead after 5 s → SIGKILL sent; treated as failure |
| FR-9 | Integration | Worktree accessible when smoke cmd runs (ordering verified) |
| FR-10 | Integration | Confirmation includes cmd, mode, timeout |
| FR-11 | Unit | Output truncated at 2000 chars; pre-merge SHA ≠ merge-commit SHA; correct SHA in `git revert` arg |
| NFR-1 | Unit | `env` kwarg is explicit dict; `LC_*` materialized via `re.match`; `AWS_SECRET_ACCESS_KEY` excluded |
| NFR-2 | Unit | `os.killpg` used with SIGTERM then SIGKILL; no sleep calls |

## Tradeoffs

- **Chose `shlex.split` + `shell=False` over `shell=True`**: eliminates shell injection;
  accepts no-pipes constraint for `smoke_test_command`. Metacharacter warning closes UX gap.
- **Chose trusted-operator assumption for `smoke_test_command`**: `_standards.md` is
  committed to main and lead-curated; no allow-list validation beyond `shlex.split` required.
- **Chose `git revert` over `git reset --hard`**: preserves history; safe on shared repos.
- **Chose `.active` check (not a lock)**: detects concurrent delivery without blocking
  single-operator workflows. A proper delivery lock is a separate ticket.
- **Accepting risk of**: concurrent deliver in the window before `.active` is set — mitigated
  by short default timeout; full lock is out of scope.

## Risks

- **Flaky smoke test causes false reverts**: Mitigate with `warn-only` mode; document that
  `smoke_test_command` should be stable and deterministic.
- **`git revert -m 1` conflict**: Surfaces as revert-fail halt path (FR-7a); explicit manual-
  recovery instructions; does not silently leave main broken.
- **SIGKILL fails** (e.g., zombie process): Extremely rare; delivery blocks up to
  `smoke_test_timeout + 10 s` maximum by design.

## Implementation Order

1. Write unit tests for config parsing (FR-1, FR-2), `shlex.split` safety (FR-3), and env
   allowlist (NFR-1, NFR-2) — tests first per CLAUDE.md working agreement.
2. Write integration tests for all seven scenarios (FR-5 through FR-11) using a synthetic
   git repo fixture; include revert-fail fixture recipe.
3. Update `deliver-ticket.md` Step 3 to read config once and display smoke-test details
   conditionally in the confirmation block.
4. Add Step 4b to `deliver-ticket.md`: `.active` check, `shlex.split` subprocess with env
   allowlist + SIGTERM/SIGKILL timeout, exit-code branch (auto-revert path incl. revert-fail
   halt; warn-only with pre-cleanup flag storage).
5. Update `init.md` `_standards.md` template with three commented-out smoke-test keys and
   inline documentation (no-pipes note; trust note; mode descriptions).
