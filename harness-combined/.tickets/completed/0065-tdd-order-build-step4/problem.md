# Problem Statement

**Ticket**: 0065
**Title**: TDD-order build Step 4: red test gate before implementation; write files directly instead of fenced blocks
**Date**: 2026-07-20

## Problem

`context/flows/build-ticket.md` Step 4 generates implementation and tests in
one model pass ("fenced code blocks (`# implementation` then `# tests`)"),
writes both, then gates them together. This violates the project's TDD rule
("Tests are written before implementation code. No exceptions.", `CLAUDE.md`):
a test authored alongside the code it grades is not independent, and nothing
confirms it fails without the implementation. The fenced-block step is also
overhead — source is generated into the transcript, then copied into a file.

## Impact

- Tests can pass vacuously (tautological, or an already-passing symbol) with
  no signal raised, since red is never observed.
- Every spec pays double token cost: fenced-block generation, then file write.
- Critic and craft polish inherit suites whose independence was never verified,
  weakening drift guards (`repair_integrity.py`, pinned-test-survival).

## Success Criteria

- Step 4 writes a spec's test file before implementation is generated.
- A deterministic red-gate check runs the new test(s) pre-implementation and
  requires at least one failure; a full pass blocks progression and triggers a
  bounded test-revision retry instead of proceeding.
- A collection/import failure from the not-yet-created target module is valid
  red evidence, not a system fault.
- Implementation and tests are written directly to worktree files, not fenced
  blocks; Step 4e's gate (`gate_run_on_dir`) still runs after, unchanged.

## Out of Scope

- Changing `MAX_REPAIR_ATTEMPTS` semantics or the Step 4e repair loop itself.
- Batch-mode / autopilot overrides beyond staying compatible.
- Red-gate parity beyond Python/TypeScript/Go/Rust (the `gates/` languages).
