# Requirements

**Ticket**: 0049
**Title**: Move /critique output out of cwd into .harness/critiques/

## Functional Requirements

1. skills/critique/SKILL.md must write the report to
   .harness/critiques/ using a target-slug-plus-date filename instead of CRITIQUE.md
   in the current working directory, creating the directory if absent.
2. Harness init/docs must ensure .harness/critiques/ is covered by the same
   git-ignore treatment as other .harness state, and the skill must never write the
   report inside a worktree.
3. When the critique's target files belong to a ticket (path within a ticket worktree
   or its .tickets directory), the skill must append a one-line pointer (date, target,
   verdict, report path) to that ticket's critic-findings.md.
4. skills/status/SKILL.md must list the three most recent critique reports (filename
   and verdict line) when any exist.

## Non-Functional Requirements

1. Filenames must sort chronologically and avoid collisions on same-day re-runs
   (date plus counter or time suffix).

## Test Strategy

| Type | Rationale                                                    |
|------|----------------------------------------------------------------|
| Unit | Docs greps: skill output path, ignore coverage, pointer and status wiring |

## Acceptance Criteria

- The critique skill text contains no CRITIQUE.md-in-cwd instruction.
- Running two critiques the same day produces two distinct files under
  .harness/critiques/.
- A ticket-scoped critique adds the pointer line; status output names recent reports.

## Open Questions

- None.
