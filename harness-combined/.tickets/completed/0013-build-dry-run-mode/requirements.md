# Requirements

**Ticket**: 0013
**Title**: Build --dry-run mode

## Functional Requirements

1. The system must accept a `--dry-run` flag on the `/build` command in ticket mode (e.g. `/build --dry-run 0013`).
2. The system must run all gate phases (lint, type-check, tests, security) in full during a dry run.
3. The system must produce a `gate-findings.md` file in the ticket directory during a dry run.
4. The system must spawn the critic agent in full during a dry run and display its structured output.
5. The system must produce a "plan" listing every implementation file that would be created or modified, with one "would write: <file>" line per planned change.
6. The system must NOT write any implementation files to the worktree during a dry run.
7. The system must NOT create a worktree branch or worktree directory during a dry run.
8. The system must NOT update `status.md` to `implementing` during a dry run.
9. The system must present dry-run output clearly labelled as a dry run (not a build result).
10. The system must generate specs from `solution.md` (if absent) during dry run, but must not persist those specs to `.harness/specs/` or `.harness/tasks/`.
11. The system must return an explicit prompt asking whether to proceed with the live build after dry-run output is shown.

## Non-Functional Requirements

1. Dry-run mode must not leave any worktree artifacts or partial state if interrupted mid-run.
2. Dry-run output must be deterministic given the same `solution.md` input across runs.

## Test Strategy

| Type        | Rationale                                                                      |
|-------------|--------------------------------------------------------------------------------|
| Unit        | Flag parsing; "would write" plan generation from spec metadata; no-write guard |
| Integration | Full dry-run flow on a fixture ticket; assert no worktree created, gate-findings.md written, plan lines emitted |

## Acceptance Criteria

- Running `/build --dry-run XXXX` against a `status: solution` ticket completes without creating a worktree directory.
- `gate-findings.md` exists in the ticket directory after the dry run.
- Critic output is displayed in the session.
- At least one "would write: <file>" line appears in the dry-run output for each spec.
- `status.md` remains `status: solution` after a dry run.
- No files are written under `.worktrees/` during or after the dry run.

## Open Questions

- Should the generated-but-not-persisted specs be shown to the lead in the dry-run output (to allow manual review of what `/write-spec` would produce)?
