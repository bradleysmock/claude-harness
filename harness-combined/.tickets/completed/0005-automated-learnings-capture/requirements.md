# Requirements

**Ticket**: 0005
**Title**: Automated Learnings Capture

## Functional Requirements

1. The system must, at the end of `/deliver` (ticket mode), scan `gate-findings.md` for failure patterns and produce up to five formatted candidate lines. When more than five candidates are available, the system must prefer entries with BLOCKER or MAJOR severity; ties are broken by recency (most recent first). Each candidate line must follow the format: `<date> | <gate> | <ticket-number> | <pattern>`, where `<pattern>` is length-capped at 120 characters, stripped of newlines, and limited to printable alphanumeric + punctuation characters.
2. The system must present proposed candidates to the lead in the `/deliver` final report under a "Candidate learnings" section — each as a ready-to-paste line — and prompt the lead to indicate which (if any) to accept.
3. The system must append only lead-accepted entries to `.tickets/_learnings.md`. The model must not construct or execute a write operation using the raw extracted candidate text; it must construct the append string from the validated template fields only.
4. Sanitization before display and before write: strip any occurrence of lines beginning with `##`, XML-like tags (`<...>`), and sentences phrased as imperative directives to Claude. Reject the candidate entirely (do not propose it) if stripping would leave the `pattern` field empty.
5. A standalone `/harvest-learnings` command must query `memory.db` via per-gate-type `memory(action="retrieve", ...)` calls using representative query terms (e.g., `"ruff lint failure"`, `"mypy type error"`) and aggregate results. A pattern is considered recurring if it appears in results for a given gate type at least 2 times; only recurring patterns are proposed as candidates.
6. `/harvest-learnings` must present candidates identically to `/deliver` (FR-2): ready-to-paste lines, accept-or-reject prompt, then append accepted entries. For cross-ticket candidates, the ticket field must be `multi`.
7. The system must deduplicate candidates against existing `_learnings.md` content by lowercased, whitespace-collapsed pattern string before presenting — entries already present must not be re-proposed.
8. If `gate-findings.md` is absent or empty, the learnings-capture step in `/deliver` must be silently skipped with no section in the report.
9. If `.tickets/_learnings.md` does not exist when an accepted entry is to be written, the system must create it as a stub before appending.
10. The system must never overwrite or modify existing `_learnings.md` content — only append accepted entries.
11. `context/harness-reference.md` Memory Contract table must be updated: "Written by" row for `_learnings.md` must read "`/deliver` and `/harvest-learnings` (append-only, after lead approval)". The note "The harness never writes to it" in `deliver-ticket.md` Step 7 must be removed.

## Non-Functional Requirements

1. The learnings-capture step in `/deliver` must add no more than one interactive exchange (present candidates → lead responds) to the delivery flow before the final report is shown.
2. Candidate generation must not call any external service; all input comes from local files and `memory.db`.

## Test Strategy

| Type        | Rationale |
|-------------|---------------------------------------------------------------------------|
| Integration | All scenarios require a `.tickets/` fixture tree and end-to-end flow execution; no unit-test infrastructure exists for `.md` instruction files |

## Acceptance Criteria

- After `/deliver XXXX` where `gate-findings.md` has gate failures, the final report includes a "Candidate learnings" section with 1–5 ready-to-paste entries in format `<date> | <gate> | XXXX | <pattern>`.
- When more than 5 failures are present, BLOCKER/MAJOR entries appear before MINOR/OBS entries in the proposed list.
- After the lead accepts an entry, it appears verbatim in `.tickets/_learnings.md`; the appended string was constructed from template fields, not the raw model-interpreted candidate text.
- After the lead rejects an entry, `_learnings.md` is unchanged for that entry.
- Running `/deliver XXXX` where `gate-findings.md` is empty or absent produces no "Candidate learnings" section.
- A candidate whose lowercased, whitespace-collapsed pattern already exists in `_learnings.md` is not re-proposed.
- A gate message containing `## heading`, `<xml-tag>`, or an imperative directive sentence is sanitized before display; if pattern is empty after sanitization, the candidate is not proposed.
- Running `/harvest-learnings` proposes only patterns that appear at least 2 times in `memory.db` results for the relevant gate type.
- Running `/harvest-learnings` with an empty or sparse `memory.db` (no pattern appearing ≥2 times) reports "No recurring patterns found" and stops.
- Existing `_learnings.md` content is never modified or removed, only appended to.
- `harness-reference.md` Memory Contract and `deliver-ticket.md` Step 7 accurately describe the new append-after-approval behavior.

## Open Questions

- Should `/harvest-learnings` accept an optional gate-name filter (e.g. `/harvest-learnings ruff`)? Safe to default to all gates; lead can decide at implementation time.
