# Problem Statement

**Ticket**: 0046
**Title**: Gate config modernization — respect project configs, ESLint flat config, current toolchain pins
**Date**: 2026-07-05

## Problem

The gate implementations carry hardcoded, dated configuration that can make harness
gating weaker than the project's own CI. Python directory-mode lint forces
"--select E,F,W,I --ignore E501", overriding stricter project ruff configs; mypy always
gets --ignore-missing-imports, hiding wrong import paths even in directory mode where
the real environment exists. TypeScript gates use legacy ESLint config (.eslintrc.json,
--no-eslintrc, dir-mode --ext) that ESLint v9+ flat config removed — on a current
ESLint every dir-mode lint run exits as TOOL_ERROR. Text-mode environments pin go 1.21,
Rust edition 2021, and TS target ES2020/commonjs, failing generated code that
legitimately uses newer language features.

## Impact

- Projects with strict ruff configs get weaker gating inside the harness than outside.
- All TypeScript builds on modern ESLint fail lint with an opaque tool error.
- Import-path bugs in generated Python pass the type gate.
- Text-mode gates reject valid modern Go/Rust/TS output for environmental reasons.

## Success Criteria

- Project lint/type configs take precedence when present; hardcoded settings are the
  fallback floor only.
- TypeScript lint works on both flat-config and legacy ESLint installations.
- Text-mode toolchain pins reflect current stable versions or are detected from the
  host project.

## Out of Scope

- Adding new SAST tools (ticket 0025) or audit gates (ticket 0012).
- Adding new lint rule categories beyond the existing floor.
