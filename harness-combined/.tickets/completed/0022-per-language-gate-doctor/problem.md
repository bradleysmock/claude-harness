# Problem Statement

**Ticket**: 0022
**Title**: Per-language gate /doctor
**Date**: 2026-06-21

## Problem

Harness operators onboarding a new project or debugging gate failures have no way to inspect whether the required gate tools are installed and on PATH for the languages present in the project. When `/build` fails because `mypy`, `ruff`, `tsc`, or `eslint` is missing, the error is opaque — the operator must manually trace which language was detected and which tooling was expected. There is no single command that answers "is this project ready to gate?"

## Impact

- Operators waste time diagnosing gate tool installation errors when onboarding a project to the harness.
- New contributors cannot verify their local environment is complete before running `/build`.
- Gate failures caused by missing tools appear as cryptic errors rather than actionable diagnostics.
- Without clear installation hints, resolving missing-tool failures requires consulting external documentation.

## Success Criteria

- A `/doctor` command exists that detects all languages present in the project from manifest files (pyproject.toml, package.json, Cargo.toml, go.mod, etc.).
- For each detected language, a table of expected gate tools is printed with per-tool status: found (with version), missing, or version-unknown.
- Missing tools that `/build` would require are flagged with installation hints (e.g. `pip install ruff`, `npm install -g typescript`).
- The command exits non-zero if any required tool is missing, so it can be used in CI preflight.
- Output is human-readable in the terminal and parseable (structured exit code).

## Out of Scope

- Auto-installing missing tools.
- Configuring or modifying gate configuration files.
- Detecting tools for languages not covered by the existing gate suite.
- Fixing or running gates — `/doctor` is diagnostic only.
