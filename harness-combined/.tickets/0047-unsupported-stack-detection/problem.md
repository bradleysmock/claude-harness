# Problem Statement

**Ticket**: 0047
**Title**: Honest handling of unsupported and mis-detected stacks
**Date**: 2026-07-05

## Problem

server.py's language auto-detection has three honesty gaps. _detect_language defaults
to "python" for anything unrecognized (Java, C#, Ruby, shell-only, SQL-only
worktrees), producing confusing mypy/pytest tool errors instead of a clear
"unsupported" verdict. _detect_stacks checks Cargo.toml and package.json one level
down but only a root go.mod, so a Go service in a subdirectory of a polyglot worktree
is silently ungated. Its Python probe (any .py file anywhere) descends into
node_modules and .venv, misclassifying JS projects as Python. Separately,
stop_full_gate.detect_stacks returns an empty list for unsupported worktrees, so the
Stop hook passes silently with zero enforcement.

## Impact

- Unsupported-language tickets fail with misleading Python tool errors or, in the
  hook path, receive no enforcement at all with no trace.
- Subdirectory Go services in polyglot worktrees skip build/vet/test gating entirely.
- Vendored trees trigger spurious Python gating on non-Python projects.

## Success Criteria

- Auto mode returns an explicit unsupported-stack error naming what was found.
- Go detection matches the one-level-down behavior of Rust and TypeScript.
- Vendored directories are excluded from language probes.
- The Stop hook prints a one-line no-coverage warning instead of silence.

## Out of Scope

- Adding gate suites for new languages (JVM, .NET) — separate tickets.
- The polyglot gate mechanism itself (delivered under ticket 0017).
