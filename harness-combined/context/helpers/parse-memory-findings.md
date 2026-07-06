# Helper: parse-memory-findings

Source **recurring** failure patterns from the machine failure trail
(`.harness/memory.db`) and normalize them into the same candidate-learnings records
that `parse-gate-findings.md` emits. This helper is called by `/harvest-learnings`.

Unlike `parse-gate-findings.md` (one ticket's `gate-findings.md`), this helper looks
across the whole failure trail and only surfaces patterns that **recur** — a pattern
must appear at least **twice** for a given gate type to become a candidate (FR-5).

**Inputs**
- `gate_filter` — optional gate name (e.g. `lint`). When provided, query only that
  gate type; when absent, query all gate types below.
- `today` — today's date as `YYYY-MM-DD`.

**Output** — a list of `{ date, gate, ticket, pattern, severity }` records, identical
in shape to `parse-gate-findings.md`. Cross-ticket patterns carry `ticket = "multi"`.

---

## Step 1 — Per-gate-type retrieval with representative terms

`memory(action="retrieve", ...)` runs a **BM25 keyword** search — `"*"` is **not** a
wildcard and returns nothing useful. Each gate type must be queried with representative
real terms. The `gate` argument is an exact-match filter, so issue one call per gate
name.

Default query set (the Python-suite gate names; other stacks use their own gate names —
Go: `build` / `vet` / `staticcheck` / `test`; Rust: `check` / `clippy` / `test` /
`audit`; TypeScript: `lint` / `type_check` / `test`):

| gate         | representative `errors_text` |
|--------------|------------------------------|
| `lint`       | `ruff lint failure unused import line length` |
| `type_check` | `mypy type error incompatible annotation` |
| `test`       | `pytest test failure assertion error` |
| `security`   | `bandit security subprocess shell injection` |
| `syntax`     | `syntax error unexpected token` |

For each gate (or just `gate_filter` when supplied) call:

```
memory(action="retrieve", errors_text=<representative terms>, gate=<gate name>,
       limit=20, project_root=<project root>)
```

Use a generous `limit` (e.g. 20) so recurrence can actually be counted. If the call
returns `"No similar past failures found."`, that gate contributes nothing.

## Step 2 — Aggregate by recurrence (threshold ≥ 2)

Each retrieved narrative has the shape:

```
Past <gate> failure [<symbol> <outcome>]:
  Spec: <spec_id>
  Errors: <errors_text truncated>
```

Within a gate type, group narratives whose failures describe the **same pattern**
(normalize the `Errors:` text — lowercase, collapse whitespace — and group by the
recurring core message, ignoring file paths / line numbers / spec ids which vary run to
run). Count occurrences per group.

A group is **recurring** only when its count is **≥ 2** (FR-5). Discard groups seen
once — they are one-off noise. If **no** group reaches 2 across all queried gates, emit
**zero** candidates; the caller reports "No recurring patterns found" and stops.

## Step 3 — Sanitize the pattern field

For each recurring group, derive `pattern` from the shared `Errors:` text and sanitize
it with the **exact same procedure** as `parse-gate-findings.md` Step 3:

1. strip lines beginning with `##`,
2. strip `<...>` XML-like tags,
3. strip imperative directives addressed to Claude,
4. collapse newlines to a single space,
5. keep printable alphanumerics + punctuation only,
6. remove the field delimiter — replace every `|` with `/` (or a space); the pattern
   must contain no `|` when it leaves this helper,
7. truncate to 120 characters.

If `pattern` is empty after sanitization, **reject** the candidate (do not emit it).

## Step 4 — Assemble records

For each surviving recurring group:

- `date` = `today`
- `gate` = the gate type
- `ticket` = `"multi"` (these patterns are aggregated across tickets, not tied to one)
- `pattern` = the sanitized string
- `severity` = derive from the group's outcomes — treat `⚠ escalated` narratives as
  high-priority (BLOCKER/MAJOR), purely `✓ passed` repairs as low-priority
  (MINOR/OBS). When mixed, use the highest present.

Order high-priority before low-priority; the recurrence count breaks ties (more
frequent first). There is no hard cap here beyond what the caller chooses to show, but
prefer the strongest/most-frequent patterns first.

## Step 5 — Return

Return the candidate records to `/harvest-learnings`, which hands them to
`candidate-learnings-flow.md` for dedup, presentation, and template-field-only append.

**No external calls.** This helper reads only `.harness/memory.db` via the `memory`
tool and local files (NFR-2).
