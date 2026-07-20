# Requirements

**Ticket**: 0066
**Title**: Autopilot mode flag: build-ticket.md branches explicitly; shrink autopilot-ticket.md to mode plus steps S/A/B

## Functional Requirements

1. `autopilot-ticket.md` sets an explicit mode signal (`MODE=autopilot`) before
   delegating to `build-ticket.md`, mirroring `build-dry-run-ticket.md`'s
   `DRY_RUN=true`.
2. `build-ticket.md` Step 1's score-spec BLOCK stop branches explicitly on the
   signal: `MODE=autopilot` → continue at `autopilot-ticket.md` Step S; any other
   value keeps today's stop-and-report-to-lead behavior.
3. `build-ticket.md` Step 7d's repair-exhaustion stop branches explicitly on the
   signal: `MODE=autopilot` → continue at Step A; any other value keeps today's
   `changes-requested` + ask-the-lead behavior.
4. `build-ticket.md` Steps 7b/7c (clean/repaired build) branch explicitly on the
   signal: `MODE=autopilot` → continue at Step B; any other value keeps today's
   "tell the lead, list options" behavior.
5. `autopilot-ticket.md`'s "Steps 1–7c — Build" interception prose ("Spec-BLOCK
   interception", "Divergence condition", "Clean-build interception") is removed;
   the file retains only the mode announcement, signal assignment, delegation
   line, and Steps S/A/B.
6. The three branch points use an actual unit-tested Python predicate — e.g.
   `is_autopilot_mode(mode: str) -> bool` — the same real (not prose-only) shape
   as the existing `should_auto_repair(dry_run)` function in `dry_run.py`. Each
   preserved non-autopilot behavior (FR-2/3/4's "any other value" branch) remains
   verbatim in `build-ticket.md` alongside its new branch.
7. No change to `autopilot-batch.md`'s per-member override block or conditions.

## Non-Functional Requirements

1. Backward compatibility: callers that never set `MODE=autopilot` exhibit the
   same stop behavior as today (fail-closed default unchanged).
2. Branch text must be unambiguous enough for a content-verification test to
   assert its presence via plain string match, not just narrative intent.

## Test Strategy

| Type | Rationale |
|------|-----------|
| Unit | `is_autopilot_mode()` returns `True` only for `"autopilot"`; `False` for unset/other values. |
| Content-verification | `build-ticket.md` shows the predicate call at Step 1, 7d, 7b/7c naming Step S/A/B, with each preserved non-autopilot text present verbatim. |
| Content-verification | `autopilot-ticket.md` sets `MODE=autopilot`, drops the removed interception phrases, keeps Steps S/A/B. |
| Regression | Existing `test_autopilot_batch_docs.py`, `test_0014_build_flow.py`, `test_spec_remediation_flow.py` pass unmodified. |

## Acceptance Criteria

- `build-ticket.md`'s three stop points each show an explicit `MODE`-conditioned
  branch, not "the condition that would normally…" phrasing.
- `autopilot-ticket.md` no longer contains the "Steps 1–7c — Build" section and is
  shorter than the current version.
- All existing flow-doc tests pass unmodified; new explicit-branch tests pass.
- Reading `build-ticket.md` alone (no cross-reference) is sufficient to know
  autopilot behavior at each of the three decision points.

## Open Questions

None — flag name (`MODE`) and values (`autopilot` / unset-interactive) are
inferred from the existing `DRY_RUN` precedent.
