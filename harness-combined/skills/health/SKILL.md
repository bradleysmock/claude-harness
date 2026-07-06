---
name: health
description: Render a read-only harness health dashboard — cross-ticket gate pass rates, average repair cycles, top recurring failure modes, tickets with the most gate failures, and per-gate trend indicators (improving / declining / stable). TRIGGER when the user asks "how healthy is the harness", "show build health", "which gates are failing most", "what are the recurring failures", "are pass rates improving or declining", or invokes /health. SKIP when the user wants the state of individual tickets or in-flight work (use the status skill), a code review of a diff (use review/critique), or a debug postmortem of one failed run (use the debug skill).
---

# Health skill — cross-ticket build-quality dashboard

Show an aggregated, **read-only** view of build quality across tickets: gate pass
rates over the last 10 builds, average repair cycles per gate, the top recurring
failure-mode error codes, the tickets with the most gate failures, and a trend
indicator per gate. It writes nothing — it only reads `gate-findings.md` files and
`.harness/memory.db`.

## Step 1 — Run the dashboard

Run `health.py` from the project root (where `.tickets/` lives). The module does all
data collection, computation, and formatting; the skill stays thin.

```bash
python3 health.py .
```

`health.py` exposes two functions the CLI wires together:

- `health_report(project_root)` — validates `project_root` (raises `ValueError` if it
  is not an existing directory), discovers up to 10 most-recent `gate-findings.md`
  files (mtime-sorted), parses them defensively, queries `.harness/memory.db`, and
  returns a `HealthReport` dataclass.
- `format_report(report)` — renders that `HealthReport` as the CLI text report.

The `__main__` entry calls `health_report()` then `format_report()` and prints the
result to **stdout**; warnings (e.g. a skipped malformed file) go to **stderr**.

## Step 2 — Report the result

Print the dashboard to stdout verbatim. Exit codes:

- **0** — the dashboard was produced.
- **non-zero** — the `project_root` was invalid or the `.tickets/` directory could
  not be read.

## Notes

- **Strictly read-only.** No file or database is written.
- When `.harness/memory.db` is absent, the average-repair-cycle and recurring-failure
  sections are omitted with an explanatory note; the gate-pass-rate table still renders
  from `gate-findings.md`.
- The pass-rate table header shows an `N of M builds analyzed` annotation where `N` is
  the number of successfully parsed files and `M` is the requested window (10), so a
  skipped malformed file is visible.
