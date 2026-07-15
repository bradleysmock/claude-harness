---
description: Ticket velocity report — reads completed ticket artifacts and prints cycle-time trends: a
---
Ticket velocity report — reads completed ticket artifacts and prints cycle-time trends: a per-ticket detail table, a weekly ISO-week summary, and an overall average. Read-only; runs from the harness root with no setup.

Date arithmetic (cycle time, ISO-week grouping, averages) is delegated to `/Users/bradley/workspaces/claude-harness/harness-combined/skills/velocity/compute.py` so the numbers are **deterministic** — the same completed-ticket set always yields the same report. LLM inference is never used for the math.

**Header caveat (always print this above the tables):** Start = the `**Date**` field in each ticket's `problem.md` (the authoring/creation date, a proxy for when the ticket entered active work — *not* a status-transition timestamp). Done = the latest `updated:` value in `status.md` (final delivery date; if a ticket was re-delivered, the longer cycle time is the true signal).

## Step 1 — Scan completed tickets

Glob `.tickets/completed/*/` from the harness root. For each discovered directory:

- **Containment check first.** Resolve the path with `Path.resolve()` and confirm it stays under the harness root before opening anything. Silently skip any path that escapes the root (a crafted slug like `../../etc` or an errant symlink). This is what `compute.is_contained(candidate, root)` and `compute.scan_completed(root)` enforce — mirror that logic; never open a path you have not contained.
- Read `problem.md` and extract the start date with `\*\*Date\*\*:\s*(\d{4}-\d{2}-\d{2})`.
- Read `status.md` and extract the completion date with `updated:\s*(\d{4}-\d{2}-\d{2})` (use the **last** match), and the title with `title:\s*(.+)`.
- Any field that is missing or does not match `YYYY-MM-DD` is **malformed** → skip the ticket and count it.

The importable `compute.scan_completed(<harness-root>)` performs exactly this scan and returns `(entries, skipped_notes)`; you may call it directly or reproduce it.

## Step 2 — Compute (via stdin, never shell args)

Build a JSON array of the discovered entries — `[{"id": "...", "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}, ...]` — and pipe it to the helper over **stdin**:

```
echo "$json_payload" | python3 "/Users/bradley/workspaces/claude-harness/harness-combined/skills/velocity/compute.py"
```

Passing ticket data on stdin (never interpolated into a shell command string) prevents injection from attacker-influenced date or slug values. The helper writes a JSON object to stdout:

```
{"tickets": [{"id","start","end","days","iso_year","iso_week"}],
 "weekly":  [{"iso_year","iso_week","count","avg_days","min_days","max_days"}],
 "overall_avg": <float>, "skipped": <int>}
```

- Entries with a **negative cycle time** (end < start) are skipped by the helper and added to its `skipped` count — note them as "invalid date range".
- Malformed stdin (not a JSON array) makes the helper exit 1 with a structured error object on stderr and nothing on stdout. Do not surface a stack trace or an internal path — report a one-line error only.

## Step 3 — Render

Parse the JSON and print two Markdown tables plus the overall average.

**Per-ticket detail** — columns: `Ticket | Title | Start | Done | Cycle Time (days)`, one row per entry in `tickets`.

**Weekly summary** — columns: `Week | Tickets | Avg Cycle Time (days) | Min | Max`, one row per entry in `weekly`. Render `Week` as ISO `YYYY-Www` from `iso_year` / `iso_week` (e.g. `2020-W53`). ISO 8601 semantics: 2021-01-01 falls in `2020-W53`, 2021-01-04 in `2021-W01`.

**Overall average** — print `overall_avg` across all counted tickets.

Finally, report the total skipped count: the tickets dropped at scan time (missing/malformed `**Date**` or `updated`) plus the helper's `skipped` (negative ranges). Name why each was skipped.

## Edge cases

- **No completed tickets** (empty `.tickets/completed/`, or every ticket skipped) → print exactly `No completed tickets found.` and stop.
- **Zero-day tickets** (same-day problem/done) are valid: cycle time 0, and the Min column may legitimately be 0 — there is no divide-by-zero.
- **No stack traces or internal paths** on any error path — every failure surfaces as a single readable line.
