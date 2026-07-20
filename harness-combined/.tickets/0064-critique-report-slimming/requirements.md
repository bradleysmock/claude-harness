# Requirements

**Ticket**: 0064
**Title**: Critique report slimming

## Functional Requirements

1. `build-ticket.md` Step 7 (post-build critic) keeps its existing full
   append to the branch-committed `critic-findings.md` unchanged — it stays
   the durable, `/deliver`-parseable record — but stops displaying the full
   report to the session; it prints only header + verdict + finding table.
2. `build-dry-run-ticket.md` Steps 4-5 (design critic), which today persists
   no critic detail (a dry run writes only `gate-findings.md`), writes its
   full report to `.harness/critiques/<YYYY-MM-DD>-<NN>-<slug>.md` using
   0049's naming logic (`skills/critique/SKILL.md`). `render_dry_run_report`
   receives the file path and renders only header+verdict+table plus a
   pointer to it, in place of full critic detail; `assemble_dry_run_report`'s
   `critic_findings` parameter is unchanged (still the full structured data).
3. `autopilot-batch.md` Step 3 (batch critic), which today persists nothing,
   writes its full combined report to `.harness/critiques/` using a
   resolved batch slug `batch-<lead-slug>-<YYYY-MM-DD>`, appends a
   `## Critique pointers` line to **every** member's `critic-findings.md`
   (not just the lead's), and prints only header+verdict+table.
4. The trimmed terminal output at all three sites includes: verdict,
   BLOCKER/MAJOR/MINOR/OBS counts, and (for 2-3) the path to the written
   file — matching 0049's terminal summary shape.
5. `skills/review/SKILL.md` Step 6 is unchanged — file-less, interactive.

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
