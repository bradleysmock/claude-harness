# Problem Statement

**Ticket**: 0009
**Title**: Gate timeout configuration
**Date**: 2026-06-21

## Problem

Gate runs have no configurable timeout, so a slow or hanging gate (e.g., a test suite waiting on a network resource) blocks all subsequent gates indefinitely. There is no per-gate-type or global ceiling on how long any gate step is allowed to run. Harness operators have no mechanism to enforce a maximum wall-clock duration for individual gate types.

## Impact

- Harness operators are blocked from unblocking their pipeline when a gate hangs — they must kill the process manually.
- Fast lint and typecheck gates are held up by slow test or security gates, defeating the purpose of parallelism or sequential gating.
- There is no audit trail when a gate hangs vs. fails for functional reasons.

## Success Criteria

- Each gate type (lint, typecheck, test, security) has a configurable timeout in seconds.
- A global default timeout applies when no per-gate-type override is set.
- When a gate exceeds its timeout it terminates and fails with a clear, human-readable timeout message (not a generic error).
- Configuration is readable from `_standards.md` or a `.harness.toml` file at the project root.
- No change to gate behavior when no timeout is configured.

## Out of Scope

- Retry logic on timeout (timeout = fail, not retry).
- UI or dashboard changes.
- Timeout configuration per individual gate invocation (only per gate type and global).
