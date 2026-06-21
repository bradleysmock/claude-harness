# Requirements

**Ticket**: 0015
**Title**: Replan command

## Functional Requirements

1. The system must accept a ticket number argument (`/replan XXXX`) and resolve it to a ticket directory using the same lookup convention as other commands (scan `.tickets/<arg>*/`, then `.tickets/completed/<arg>*/`).
2. The system must reject invocations where the resolved ticket's `status.md` is not one of: `solution`, `implementing`, `review-ready`, or `changes-requested` — statuses where a `solution.md` is expected to exist. The `requirements` and `problem` statuses are explicitly excluded. (NFR-2 handles the edge case where `solution.md` is absent despite the status being valid.)
3. The system must read `problem.md` and `requirements.md` in full from the resolved ticket directory before regenerating the solution.
4. The system must snapshot the current `solution.md` contents before overwriting it, so a diff can be produced.
5. The system must regenerate `solution.md` from scratch using the current `problem.md` and `requirements.md`, following the same structure and constraints as Phase 4 of `/problem`.
6. The system must run the critic loop (up to 2 rounds, same protocol as `/problem` Phase 5) on the regenerated `solution.md`.
7. After the critic loop, the system must produce and display a unified diff of old vs. new `solution.md`.
8. The system must update `status.md` to `status: solution` and the `updated` date.
9. The system must commit the revised `solution.md`, `status.md`, and `requirements.md` to `main` in a single commit after the critic loop completes.
10. If a worktree for the ticket currently exists (`ticket/XXXX-<slug>` branch), the system must warn the lead that in-progress implementation may diverge from the replanned solution, and present a Checkpoint-style prompt (matching the harness's existing interaction pattern — not a bare stdin `read`) requiring an explicit `yes` before proceeding.

## Non-Functional Requirements

1. The command must be idempotent: running `/replan XXXX` twice without changing `requirements.md` between runs produces a functionally equivalent `solution.md` (modulo LLM non-determinism — the structural contract must hold).
2. The snapshot/diff step must not fail if `solution.md` does not yet exist (edge case: ticket in `requirements` status with no solution yet); in this case, the diff is empty and a note is shown.

## Test Strategy

| Type        | Rationale                                                     |
|-------------|---------------------------------------------------------------|
| Unit        | Ticket resolution logic, status guard, snapshot/diff utility  |
| Integration | Full command run against a fixture ticket with known artifacts |

## Acceptance Criteria

- `/replan 0015` on a ticket at `status: solution` produces a new `solution.md`, runs the critic, and prints a unified diff.
- `/replan XXXX` on a ticket at `status: problem` (no existing solution) is rejected with a clear error.
- `/replan XXXX` where a worktree exists displays a warning and waits for explicit confirmation before continuing.
- After the command, `status.md` reads `status: solution` with today's date.
- The commit message follows the harness convention: `chore(ticket): XXXX replan (status: solution)`.
- The unified diff is printed even when there are no changes (shows "no changes" notice).

## Open Questions

- **No-change detection**: Should `/replan` detect that `requirements.md` hasn't changed since the last solution commit and short-circuit with a warning, or always regenerate? (Lean: always regenerate, since LLM output may still improve; warn but proceed.)
- **Status rollback**: When a ticket is `implementing` or `review-ready` and `/replan` is run, should `status` roll back to `solution` after replanning, potentially invalidating the existing worktree specs? (Lean: yes, with a clear warning to the lead.)
