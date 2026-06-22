# Problem Statement

**Ticket**: 0010
**Title**: Ticket export (JSON/CSV)
**Date**: 2026-06-21

## Problem

Harness operators have no way to extract ticket data from the `.tickets/` directory into a portable format. Reporting on project velocity, auditing completed work, or importing tickets into external tools (Linear, Jira, spreadsheets) requires manual directory traversal and copy-pasting. There is no structured export path.

## Impact

- Harness operators cannot generate status reports without manual effort.
- Teams migrating to or from the harness lose historical ticket data.
- Audits require reading individual markdown files across many ticket directories.

## Success Criteria

- `export` command exists and accepts `--format json|csv`, `--all`, and `--output <file>` flags.
- Exported records include: ticket number, title, status, updated date, problem summary, solution summary, associated commits.
- Default behavior exports only completed tickets; `--all` includes open/in-progress tickets.
- Output is written to a specified file or stdout when `--output` is omitted.
- Command is documented in README and accessible via the harness plugin.

## Out of Scope

- UI or web-based export interfaces.
- Real-time sync with external tools (Linear, Jira, GitHub Issues).
- Exporting gate run logs, spec files, or worktree diffs.
- Authentication or API integration with any external service.
