Harvest recurring failure patterns from `.harness/memory.db` into `.tickets/_learnings.md` — `$ARGUMENTS` is an optional gate-name filter (e.g. `/harvest-learnings lint`).

Unlike `/deliver` (which mines a single ticket's `gate-findings.md`), this command looks
across the whole failure trail and surfaces only patterns that **recur** — appearing at
least twice for a gate type. Accepted entries are appended after your approval, exactly
as `/deliver` does; cross-ticket patterns are recorded with the ticket field `multi`.

## Step 1 — Resolve the gate filter

If `$ARGUMENTS` names a gate (e.g. `lint`, `type_check`, `test`, `security`), pass it as
the `gate_filter`. If empty, no filter — all gate types are queried.

## Step 2 — Gather recurring candidates

Call `${CLAUDE_PLUGIN_ROOT}/context/helpers/parse-memory-findings.md` with the
`gate_filter` (if any) and today's date. It runs per-gate-type
`memory(action="retrieve", ...)` queries with representative terms, aggregates by
recurrence (threshold ≥ 2), sanitizes each pattern via the `learnings.py sanitize` CLI
(the same `sanitize_pattern()` `/deliver` uses — one tested implementation, not a
second prose copy), and returns normalized candidate records with `ticket = "multi"`.

**If it returns no candidates** (no pattern recurred ≥ 2 times for any queried gate),
report exactly:

```
No recurring patterns found.
```

and stop. Make no changes.

## Step 3 — Present and append

Call `${CLAUDE_PLUGIN_ROOT}/context/helpers/candidate-learnings-flow.md` with the
candidate list and `.tickets/_learnings.md`. It deduplicates via `learnings.py dedupe`,
presents the survivors as ready-to-paste lines under a "Candidate learnings" section,
runs a single accept/reject exchange, and appends only the entries you accept via
`learnings.py append` — each built from the validated template fields (`date | gate |
ticket | pattern`), never from raw text. If `_learnings.md` does not exist, `append`
creates it from the shared stub header first (the same one `/init` writes).

## Step 4 — Report

Summarize which entries were appended and which were skipped. Do not echo the prior
contents of `_learnings.md`.

## Notes

- **Read-only against `memory.db`.** This command never writes to the failure trail; it
  only reads via `memory(action="retrieve", ...)`.
- **Append-only against `_learnings.md`.** Existing content is never modified or removed.
- **No external calls** — `memory.db` and local files only.
- There is no time-window filter in v1: a stale pattern can resurface, so your review is
  the final guard against noise.
