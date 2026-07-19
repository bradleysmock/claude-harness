# Problem Statement

**Ticket**: 0053
**Title**: LLM/Python boundary rule in CLAUDE.md
**Date**: 2026-07-12

## Problem

The harness consistently puts pass/fail authority and exactness operations in
Python (`ticket.py` numbering, `ticket_deps.py` cycle checks, `ticket_templates.py`
limits, `gates/`, `validators/standards_validator.py`) while the model supplies
judgment (design, critique, repair strategy). This boundary is an unwritten
convention: CLAUDE.md — the working agreement governing all harness work — never
states it, so each new command or skill re-decides the split ad hoc.

## Impact

- Authors of new commands/skills/gates have no rule to cite; the Python-vs-prose
  decision is re-litigated per ticket, and some flows drift toward
  model-eyeballed checks where a deterministic validator is warranted.
- Model-side "checks" are non-reproducible: two runs can disagree on counts,
  limits, or verdicts, producing silent gate misses.
- The critic has no written standard to flag boundary violations against.

## Success Criteria

- CLAUDE.md contains a named rule section stating: gate authority (pass/fail
  verdicts) and exactness operations (counting, limits, parsing, ID/numbering,
  cycle detection, path containment) are implemented in Python; the model adds
  judgment only and never re-derives or overrides a Python-computed verdict.
- The rule gives a decision test and concrete examples from existing harness code.
- A content-verification test asserts the section and its key phrases exist.

## Out of Scope

- Refactoring existing flows that already violate the boundary (follow-up tickets).
- Changes to `context/harness-reference.md`, per-language rules files, or README.
