# Problem Statement

**Ticket**: 0018
**Title**: SARIF gate output and IDE integration
**Date**: 2026-06-21

## Problem

Gate findings are currently emitted only as a human-readable `gate-findings.md` file. There is no machine-readable output, which prevents integration with standard tooling (VS Code Problems panel, GitHub Code Scanning, SonarQube/Semgrep CI). Harness operators cannot route gate results into the toolchain they already use for code quality triage.

## Impact

- Harness operators must manually cross-reference `gate-findings.md` with their IDE or CI dashboard.
- Gate findings are invisible to GitHub Code Scanning and similar aggregation tools unless manually transcribed.
- Teams using multi-tool quality pipelines (Semgrep, SonarQube) cannot include harness results in unified reports.

## Success Criteria

- Gate run produces a `.harness/results.sarif` file alongside `gate-findings.md` when enabled.
- Each finding maps to a valid SARIF result with `ruleId`, `level`, `message`, and `location` (file and line).
- SARIF output is opt-in via `--sarif` flag or `_standards.md` config key.
- The SARIF file passes SARIF 2.1.0 schema validation.
- VS Code SARIF Viewer extension can open the file and show findings in the Problems panel.
- `gh` can upload the file to GitHub Code Scanning without errors.
- When opt-in is not set, behavior is identical to today (no SARIF file written).

## Out of Scope

- Modifying existing `gate-findings.md` format or content.
- Auto-installing VS Code extensions or configuring GitHub Actions workflows.
- Parsing SARIF output from third-party tools (ingestion is out of scope; emission only).
- Real-time / streaming SARIF output during a gate run.
