# Problem Statement

**Ticket**: 0085
**Title**: Reorganize harness-combined's flat root Python modules into a subpackage
**Date**: 2026-09-17

## Problem

17 core Python modules (`server.py`, `ticket.py`, `models.py`, `memory.py`, `dag.py`, and 12 more) sit flat at `harness-combined/` root, indistinguishable at a glance from the config/tooling files (`pyproject.toml`, `conftest.py`) and docs (`README.md`, `CLAUDE.md`) that belong there. Every other concern in the plugin — gates, hooks, commands, skills, agents — already lives in its own subdirectory; the implementation modules are the one exception.

## Impact

A new contributor scanning `harness-combined/` can't tell "this is the harness's actual implementation" from "this is a stray script" without opening files. Code review and onboarding both pay a small, recurring tax for it. The flat layout is intentional today for a specific reason (16 files under `commands/`, `context/flows/`, `context/helpers/`, and `skills/` invoke several of these modules by a hardcoded `${CLAUDE_PLUGIN_ROOT}/<module>.py` path, and `conftest.py`/`pyproject.toml` assume root-level imports) — not neglect, but the reason isn't visible from the directory listing itself.

## Success Criteria

- All 17 modules live under one new subpackage directory; only `conftest.py` remains as a `.py` file at `harness-combined/` root.
- Every hardcoded reference to a moved module's old path is updated — CLI invocations from markdown flows, `server.py`'s imports, `conftest.py`'s `sys.path` setup, and `pyproject.toml`'s `mypy_path`.
- The full existing gate/test suite passes unchanged after the move — no behavior change, only location.

## Out of Scope

- Restructuring `gates/`, `hooks/`, `commands/`, `skills/`, `context/`, `agents/`, `validators/`, or `bin/` — already well organized.
- Any change to a module's internal logic or public behavior.
- Splitting the 17 modules into multiple subpackages by concern — one new directory is enough for now.
