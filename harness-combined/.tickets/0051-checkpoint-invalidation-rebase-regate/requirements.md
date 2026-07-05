# Requirements

**Ticket**: 0051
**Title**: Checkpoint invalidation on spec edits and post-rebase re-gating

## Functional Requirements

1. checkpoint(action="write") must store, per completed spec, a content hash of the
   spec file (and of the task file when present) alongside the spec ID.
2. checkpoint(action="read") must omit entries whose stored hash no longer matches the
   current spec file, reporting them separately as invalidated so the flow can
   announce them.
3. build-ticket.md Step 3 must announce invalidated checkpoints ("spec edited since
   last pass — will re-run") instead of skipping those specs.
4. deliver-ticket.md Step 7 must run gate_run_on_dir on each successfully rebased
   worktree; a review-ready ticket must be downgraded to implementing only when that
   gate run fails, and kept review-ready (with a "re-gated clean after rebase" note)
   when it passes.
5. Checkpoint files written by older versions (no hashes) must be treated as fully
   invalidated with a clear announcement, never as passed.

## Non-Functional Requirements

1. Hashing must add no perceptible latency (single small file per spec).
2. Backward-compatible JSON: new fields added, existing readers unaffected.

## Test Strategy

| Type        | Rationale                                                 |
|-------------|-------------------------------------------------------------|
| Unit        | Hash write/read round-trip, mismatch invalidation, legacy-file handling |
| Integration | Edited-spec fixture: resumed run re-executes the spec       |
| Unit        | Docs greps: Step 3 announcement, Step 7 conditional downgrade |

## Acceptance Criteria

- Editing a completed spec's file causes checkpoint read to exclude it and the build
  flow to re-run it.
- A legacy checkpoint file yields zero skips and an announcement.
- deliver Step 7 text re-gates and downgrades only on failure.

## Open Questions

- None.
