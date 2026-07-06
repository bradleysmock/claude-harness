# Problem Statement

**Ticket**: 0017
**Title**: Multi-language polyglot gate
**Date**: 2026-06-21

## Problem

The gate engine currently assumes a single-language project: it detects one language and runs that language's gates. In mixed-language repositories (e.g., Python backend + TypeScript frontend), it either fails on a language mismatch or silently runs only one language's gates, leaving the other language unchecked. Harness operators working on monorepos or full-stack projects have no way to enforce quality gates across all languages in a single gate run.

## Impact

- Harness operators on polyglot projects get incomplete gate results, creating blind spots in lint, type-checking, and test enforcement.
- A Python-only gate run on a Python+TypeScript repo means all TypeScript issues pass through undetected — undermining the gate contract.
- Without aggregated findings, operators must manually run each language gate and reconcile results, defeating the automation purpose.

## Success Criteria

- Gate engine detects all languages present in the repository from standard project files (pyproject.toml, package.json, go.mod, etc.).
- All applicable language-specific gate commands are collected and run (not just the first match).
- Findings from all languages are aggregated into a single `gate-findings.md`.
- Per-language gate commands are configurable and can be overridden in `_standards.md`.
- A gate run that has failures in any language exits non-zero and surfaces those failures in the aggregated report.
- A clean run across all languages produces a unified passing `gate-findings.md`.

## Out of Scope

- IDE or editor integration for polyglot support.
- Automatic installation of missing language toolchains.
- Language detection beyond project manifest files (no heuristics based on file extensions alone).
- Cross-language dependency analysis or inter-language type checking.
