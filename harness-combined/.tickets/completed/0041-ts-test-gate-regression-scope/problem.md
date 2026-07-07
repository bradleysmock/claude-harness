# Problem Statement

**Ticket**: 0041
**Title**: TypeScript test gate must catch regressions in unchanged tests
**Date**: 2026-07-05

## Problem

gates/typescript.py directory mode scopes the Jest run to the ticket's changed
*.test.ts files when git scoping succeeds. An implementation change that breaks an
existing, untouched test therefore passes the gate — precisely the regression class a
test gate exists to catch. The code comment frames the None-fallback as fail-closed,
but a successful scoping is the fail-open case. Python, Go, and Rust directory gates
run full suites, so TypeScript is silently held to a lower bar.

## Impact

- TypeScript tickets can merge with regressions in pre-existing behavior that the
  suite would have caught.
- The stated motivation (unrelated pre-existing failures must not fail the ticket) is
  legitimate but the current mechanism sacrifices regression safety to get it.
- Cross-language gate inconsistency undermines the polyglot quality guarantee.

## Success Criteria

- The TypeScript test gate exercises the full suite for every gate run.
- Pre-existing failures on the merge base do not fail the ticket, via deterministic
  baseline-delta comparison instead of scoping.
- Gate output states which mode ran and which failures were baseline-excluded.

## Out of Scope

- Applying baseline-delta to other languages (follow-up once proven for TS).
- Test-suite performance work (sharding, caching).
