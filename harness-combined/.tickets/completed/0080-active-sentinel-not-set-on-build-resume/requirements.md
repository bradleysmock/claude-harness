# Requirements

**Ticket**: 0080
**Title**: Set .tickets/.active on the normal /build resume path

## Functional Requirements

1. `build-ticket.md` Step 2 must write `.worktrees/XXXX-<slug>/.tickets/.active`
   (containing the bare slug `XXXX-<slug>`, matching the fallback branch's
   existing content convention) unconditionally, on both the normal resume
   path and the fallback recreate-worktree path — not only the fallback.
2. The write must target the path inside the worktree
   (`<worktree>/.tickets/.active`), never the main checkout's `.tickets/.active`
   — this is the exact path `server.py`'s `standards_path` derivation
   (`<directory>/.tickets/_standards.md`) implies for `_active_ticket_dir`.
3. The existing fallback branch's `echo 'XXXX-<slug>' > .tickets/.active`
   line must be removed — it is fully superseded by the new unconditional
   write (FR-1), and its current bare-relative form is itself ambiguous
   about cwd (run from the repo root as most of this doc's other commands
   are, it would write to the wrong file), so retaining a second write is
   both redundant and a second place to get the path wrong.
4. No other Step 2 behavior changes: the cycle check, the `implementing`
   transition, and the branch-only commit/push all stay exactly as they are.
5. `deliver-ticket.md` Step 6's `rm -f .tickets/.active` cleanup and
   `autopilot-batch.md`'s own sentinel handling are unaffected — neither is
   touched by this ticket.

## Non-Functional Requirements

1. This is a documentation-only fix (a model-followed instruction, not
   executable code) — verified by content assertions on the doc, matching
   this repo's existing doc-wiring test convention (e.g. ticket 0078's
   `commands/problem.md` checkpoint tests).

## Test Strategy

| Type        | Rationale                                                          |
|-------------|-----------------------------------------------------------------------|
| Doc-wiring  | Step 2's normal-resume path names the unconditional `.active` write with the correct worktree-relative path; the fallback branch's old `.active` line is gone, not merely re-pathed |
| Doc-wiring  | Preserves the cycle check, the `implementing` transition, and the branch-only push language unchanged |

## Acceptance Criteria

- Step 2's text documents writing `.active` inside the worktree on every
  resume, phrased so it cannot be read as fallback-only.
- The fallback branch's old `.active` write line is removed — the new
  unconditional write is the only place `.active` gets written in Step 2.
- No existing Step 2 content (cycle check, `implementing` transition,
  branch-only push) is removed or reworded.

## Open Questions

None.
