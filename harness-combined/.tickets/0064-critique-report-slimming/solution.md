# Solution

**Ticket**: 0064
**Title**: Critique report slimming

## Approach

Stop displaying full critic reports to the session at three call sites.
Where a durable copy already exists (`build-ticket.md`'s committed
`critic-findings.md`), leave persistence unchanged and only trim the
display. Where none exists today (`build-dry-run-ticket.md`,
`autopilot-batch.md`), add a new write to `.harness/critiques/` reusing
0049's naming/pointer logic, then trim the display there too.

## Components

| Component | Responsibility | Key interfaces |
|---|---|---|
| `context/flows/build-ticket.md` Step 7 | Trim session display only | `critic-findings.md` append unchanged |
| `context/flows/build-dry-run-ticket.md` Steps 4-5 | New persistence + trimmed render | `render_dry_run_report` gains a required `critic_report_path` param; `assemble_dry_run_report`'s own signature is unchanged |
| `context/flows/autopilot-batch.md` Step 3 | New persistence (batch slug) + trimmed display, pointer to every member | Slug `batch-<lead-slug>-<YYYY-MM-DD>` |
| `skills/critique/SKILL.md:108-241` | Reference naming/pointer/summary format — cited, not duplicated | — |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Keep `build-ticket.md`'s existing `critic-findings.md` append as the durable record, don't also write `.harness/critiques/` | It's already committed and branch-portable, and `deliver-ticket.md`'s learnings extraction already parses it; duplicating into a gitignored dir would add a second, less durable copy for no benefit (critic round 1, D-01/D-02) |
| Give dry-run and batch their own `.harness/critiques/` writes, since they persist nothing today | Net-new durability, not a regression; matches 0049's established location for standalone reports (critic round 1, D-02) |
| Resolve batch slug as `batch-<lead-slug>-<YYYY-MM-DD>`; pointer to every member's `critic-findings.md` | Removes the ambiguity flagged in critic round 1 D-03 — every member ticket gets a discoverable trail to the combined report that reviewed its changes |
| `dry_run.py`'s `assemble_dry_run_report` signature unchanged; only `render_dry_run_report` changes what it renders for the critic section | Avoids widening the report-assembly interface; the full structured data still flows through, only the rendering step trims (critic round 1, D-06) |

## Test Plan

| Requirement | Test Type | Scenario(s) |
|-------------|-----------|-------------|
| FR-1 | Unit (content) | `build-ticket.md` markdown: "display verbatim" instruction replaced by trimmed-display instruction; `critic-findings.md` append instruction string unchanged |
| FR-2 | Unit (content) | `build-dry-run-ticket.md` markdown: write-to-`.harness/critiques/` instruction present; `render_dry_run_report` call site documents trimmed rendering + pointer |
| FR-3 | Unit (content) | `autopilot-batch.md` markdown: batch slug pattern and per-member pointer-append instruction present |
| FR-2 | Unit (code) | `render_dry_run_report(report, critic_report_path)` output contains header+verdict+table+pointer, not full finding detail; `assemble_dry_run_report`'s own signature is unchanged |
| FR-4 | Unit (content) | Each of the three trimmed-output instructions names "verdict" and all four severity terms; sites 2-3 also name the path/pointer |
| FR-5 | Unit (content) | `skills/review/SKILL.md` byte-unchanged (regression guard) |

## Tradeoffs

- **Chose doc-level citation over a shared script/template because**: these
  are prose instructions consumed by the model at runtime, not code with a
  natural extraction point; values (path pattern, table columns) are
  already single-sourced per 0058/0062 — only the instruction was un-DRY.
- **Accepting risk of**: flow docs drifting from `skills/critique/SKILL.md`
  if 0049's format changes — mitigated by citing exact line ranges.

## Risks

- `render_dry_run_report` gains a **required** `critic_report_path` param
  (no silent default — a dry run always writes one now).
  `tests/test_dry_run.py`'s `_render_sample()` helper and its 7 dependent
  tests use the current single-arg signature and must be updated together
  (mitigation: step 2 greps all Python importers of `dry_run`).
- Batch slug collisions across same-day batches with different lead
  tickets are avoided by keying on `lead-slug`, not just date.

## Implementation Order

1. Write content-verification tests for all three flow docs (mirroring
   `tests/test_0049_critique_output_docs.py`) and a unit test for
   `render_dry_run_report`'s new trimmed-rendering behavior — red first.
2. Grep all Python importers/callers of `dry_run.render_dry_run_report`
   (including `tests/test_dry_run.py`'s `_render_sample()` helper and its
   7 dependent tests), not just the flow-doc reference.
3. Update `build-ticket.md` Step 7 to trim the display (persistence
   unchanged).
4. Update `dry_run.py`'s `render_dry_run_report` to require
   `critic_report_path` and render trimmed output; update
   `_render_sample()` and its 7 dependent tests; update
   `build-dry-run-ticket.md` Steps 4-5 accordingly.
5. Update `autopilot-batch.md` Step 3 with the batch slug and per-member
   pointer logic.
6. Run the new tests green; verify `/status`'s recent-critiques listing
   picks up the new writes unchanged.
