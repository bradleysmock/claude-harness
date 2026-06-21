# Requirements

**Ticket**: 0009
**Title**: Spec diff on refine

## Functional Requirements

1. The system must display a unified diff of pending changes to any ticket artifact file (`.tickets/**/*.md`) before overwriting it, when the file already exists and has non-empty content.
2. The system must show the diff inline in the terminal output before the write is committed, so the harness operator can review the change in context.
3. The system must apply this behavior to all commands that modify existing ticket artifacts after initial creation: `/refine`, `/replan` (when it exists), `/solution`, `/requirements`, and any other command that overwrites a ticket artifact file.
4. The system must not show a diff when the target file does not yet exist (initial creation).
5. The system must not show a diff when the incoming content is identical to the existing content.
6. The diff output must use standard unified-diff format (`--- a/file`, `+++ b/file`, `@@ ... @@` hunks with `+`/`-` line prefixes).
7. Diff display is on by default. Setting the environment variable `HARNESS_NO_DIFF=1` suppresses diff output for the current invocation, enabling CI/non-interactive use without modifying command files.

## Non-Functional Requirements

1. The diff must be generated and printed before the file write, not after — it must describe the pending change, not the committed change.
2. Diff generation must not block or fail the write if the existing file cannot be read (e.g. permissions) — degrade gracefully and proceed with the write.
3. The feature must add no latency beyond the diff computation itself (in-process, no subprocess for diff).

## Test Strategy

| Type        | Rationale                                          |
|-------------|----------------------------------------------------|
| Unit        | `compute_unified_diff` — correct output for identical, added, removed, and modified content; empty result for no-change |
| Unit        | `should_show_diff` guard — file-exists and content-differs conditions                                         |
| Integration | Hook invocation with a real `.tickets/` write — diff appears in stderr/stdout before write completes           |

## Acceptance Criteria

- Running `/refine` on a ticket with an existing `solution.md` prints a unified diff before the overwrite.
- No diff is shown when creating a ticket artifact for the first time.
- No diff is shown when the content is unchanged.
- The diff format is human-readable unified diff.
- The behavior is consistent across `/refine`, `/solution`, `/requirements`, and `/replan`.

## Open Questions

- None.
