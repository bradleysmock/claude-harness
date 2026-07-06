# Problem Statement

**Ticket**: 0016
**Title**: Build health dashboard
**Date**: 2026-06-21

## Problem

Harness operators currently diagnose quality problems by inspecting individual gate-findings.md files and memory.db records in isolation. There is no aggregated view of build quality trends across tickets, making it difficult to identify systemic or recurring failure patterns until they cause significant rework. Without a cross-ticket perspective, leads cannot distinguish one-off failures from persistent issues that indicate a structural codebase or process problem.

## Impact

- Harness operators (lead engineers) are affected: they cannot see whether gate pass rates are improving or declining across work.
- Recurring failure modes (e.g., a category of lint error or test pattern that repeatedly triggers repair cycles) go unnoticed until a lead manually correlates multiple ticket histories.
- High repair-cycle tickets are not surfaced, so leads cannot prioritize systemic fixes or adjust templates proactively.

## Success Criteria

- `/health` command reads gate-findings.md files and memory.db across recent ticket builds.
- Reports gate pass rate per gate type for the last 10 builds.
- Reports average repair cycles before gate pass per gate type.
- Reports top 5 recurring failure modes from memory.db.
- Reports which tickets had the most gate failures.
- Provides trend indicators (improving / declining / stable) per gate type.
- Output is formatted for CLI readability (tables or structured sections).
- Command runs without arguments and completes in reasonable time (<10s on a typical repo).

## Out of Scope

- No historical storage or database writes — reads existing artifacts only.
- No visualization beyond CLI text output (no HTML, no charts).
- No integration with external monitoring or alerting systems.
- No per-ticket drill-down navigation (navigating to individual ticket detail is out of scope).
