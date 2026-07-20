# Requirements

**Ticket**: 0064
**Title**: Critique report slimming

## Functional Requirements

1. `build-ticket.md` Step 7 must keep its existing full append to the
   branch-committed `critic-findings.md` unchanged (the durable,
   `/deliver`-parseable record) and must print only header + verdict +
   finding table to the session — never the full report.
2. `build-dry-run-ticket.md` Steps 4-5 must write the design critic's full
   report to `.harness/critiques/<YYYY-MM-DD>-<NN>-<slug>.md` using 0049's
   naming logic (`skills/critique/SKILL.md`); `render_dry_run_report` must
   render only header+verdict+table plus a pointer to that file, and
   `assemble_dry_run_report`'s signature must stay unchanged.
3. `autopilot-batch.md` Step 3 must write its full combined critic report
   to `.harness/critiques/` using slug `batch-<lead-slug>-<YYYY-MM-DD>`,
   must append a `## Critique pointers` line to **every** member's
   `critic-findings.md`, and must print only header+verdict+table.
4. The trimmed terminal output at all three sites must include verdict,
   BLOCKER/MAJOR/MINOR/OBS counts, and (for sites 2-3) the path to the
   written file.
5. `skills/review/SKILL.md` Step 6 must remain unchanged — file-less and
   interactive.

## Non-Functional Requirements

Path containment under `.harness/critiques/`, no shell interpolation —
per `CLAUDE.md`'s Code Generation Rules.

## Test Strategy

| Type | Rationale |
|------|-----------|
| Unit | Content-verification tests against the three flow docs' markdown (mirroring `tests/test_0049_critique_output_docs.py`): assert the "display verbatim" instruction is replaced with trimmed-output + persistence instructions, at each of the three sites. |
| Unit | `dry_run.py` — `render_dry_run_report` renders header+verdict+table+pointer given a critic-findings file path, without altering `assemble_dry_run_report`'s signature. |

## Acceptance Criteria

- FR-1: `build-ticket.md`'s markdown no longer instructs a verbatim display;
  `critic-findings.md` append instruction is unchanged.
- FR-2: `build-dry-run-ticket.md`'s markdown instructs writing to
  `.harness/critiques/` and trimming the rendered report.
- FR-3: `autopilot-batch.md`'s markdown specifies the batch slug and the
  per-member pointer append.
- FR-4: each of the three trimmed-output instructions names "verdict" and
  all four severity terms (BLOCKER/MAJOR/MINOR/OBS); sites 2-3 also name
  the file path/pointer.
- `/review`'s markdown is untouched.

## Open Questions

None — scope and per-call-site persistence strategy resolved by critic
rounds 1-2.
