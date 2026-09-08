# Problem Statement

**Ticket**: 0075
**Title**: Identity-stamped audit log
**Date**: 2026-09-04

## Problem

Approve/reject-type decisions — `/deliver`, `/rollback`, resolving a
`changes-requested` pause — leave no record of who made the call. On a
shared machine, or when a delivered ticket is disputed later, there is
nothing to check against: a grep for `getuser`/`git config user.name`/
`GIT_AUTHOR` across the codebase turns up nothing.

## Impact

Any team using this harness on a shared machine, or auditing a disputed
delivery after the fact, cannot answer "who approved this?" There is no
malicious-actor threat model here — just an accountability gap for
ordinary team use.

## Success Criteria

- Every human-facing decision point appends one line to a local,
  append-only JSONL audit log naming who made the call.
- No new service or database — a flat file under `.harness/`.
- Identity resolves via `git config user.name`, falling back to `$USER`
  then `getpass.getuser()`.
- Concurrent writers never interleave or corrupt a line.
- `read()` supports filtering by ticket for display (`/status`, or a new
  `/audit XXXX`).

## Out of Scope

- A tamper-proof or cryptographically signed log.
- Attributing every ticket status transition — only ones a human actively
  decided (see `solution.md § Decisions` for which transitions qualify).
- A new database or index — direct file scan only.
