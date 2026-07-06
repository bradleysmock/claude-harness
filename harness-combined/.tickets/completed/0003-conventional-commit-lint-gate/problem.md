# Problem Statement

**Ticket**: 0003
**Title**: Conventional-commit lint gate
**Date**: 2026-06-21

## Problem

The harness has no automated enforcement that commits on a delivery branch conform to the
conventional-commit specification (`type(scope): subject`). Non-conforming messages slip
through to `main`, polluting changelogs and breaking any tooling that relies on structured
commit history (release automation, semantic versioning, linear history audits).

## Impact

- Harness operators who run `/deliver` can merge branches with malformed commit messages.
- Downstream tooling (changelog generators, version bumpers, CI parsers) silently mishandles
  non-conforming entries or errors out.
- Reviewers cannot enforce the standard manually at scale; violations accumulate silently.

## Success Criteria

- A gate phase runs before `/deliver` and parses every commit on the current branch that is
  not on `main`.
- Any commit whose message does not match the conventional-commit pattern causes the gate to
  fail with a clear, actionable error listing each offending SHA and message.
- Passing branches (all commits conforming) proceed to delivery unblocked.
- Allowed commit types and optional-vs-required scope are configurable via `_standards.md`.
- The gate can be run standalone (e.g. in CI) independently of `/deliver`.

## Out of Scope

- Automatic rewriting or amending of non-conforming commit messages.
- Enforcing commit message body or footer conventions beyond the first line.
- Integration with external commitlint config files (`.commitlintrc`, etc.).
- Pre-commit hook installation on developer machines.
