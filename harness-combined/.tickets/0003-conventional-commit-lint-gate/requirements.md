# Requirements

**Ticket**: 0003
**Title**: Conventional-commit lint gate

## Functional Requirements

1. The system must expose a `commit_lint` MCP tool (in `server.py`) that accepts a `branch`
   name and `project_root` string, and returns structured pass/fail results.
2. The tool must enumerate every commit on `branch` that is not reachable from `main` using
   `git log main..<branch> --format="%H %s"`.
3. Each commit subject must be validated against the conventional-commit pattern:
   `^(type)(\(scope\))?: .+` where `type` is drawn from an allowed-types list.
4. If any commit fails validation, the tool must return `passed: false` with one `GateError`
   per offending commit, including the commit SHA (truncated to 7 chars) as `file` and the
   raw subject as `message`.
5. If all commits pass (or the branch has no new commits), the tool must return `passed: true`
   with an empty errors list.
6. Allowed types must default to the standard conventional-commit set: `feat`, `fix`, `docs`,
   `style`, `refactor`, `perf`, `test`, `chore`, `build`, `ci`, `revert`.
7. An optional `require_scope` flag (default `false`) must cause commits without a scope
   (`type: subject` without parenthetical) to fail validation.
8. The `deliver-ticket.md` flow must be updated to call `commit_lint` after Step 1 (validation)
   and before Step 3 (confirm), blocking delivery if any commit fails.
9. Configuration overrides (`allowed_types`, `require_scope`) must be readable from
   `.tickets/_standards.md` if present, via a simple YAML-like block under a
   `## Commit Lint` heading.

## Non-Functional Requirements

1. The gate must complete in under 5 seconds for branches with up to 200 commits.
2. The tool must not shell out with user-supplied string interpolation — use argument lists
   only (consistent with existing no-shell-concat harness rule).
3. The error output must be human-readable: each failing entry shows `<short-sha> <subject>`.

## Test Strategy

| Type        | Rationale                                                    |
|-------------|--------------------------------------------------------------|
| Unit        | Regex pattern validation: valid types, missing colon,        |
|             | missing subject, scope required vs optional, edge cases       |
|             | (empty message, merge commits, revert subjects)               |
| Integration | Git subprocess call with a temp repo fixture: commits on a   |
|             | branch, pass/fail assertions on full tool output              |

## Acceptance Criteria

- Given a branch where all commits match `type(scope): subject`, `commit_lint` returns `passed: true`.
- Given a branch with one commit `"wip: broken thing"` (unknown type), `commit_lint` returns
  `passed: false` with one error referencing that commit's SHA.
- Given `require_scope=true`, a commit `"feat: add widget"` fails; `"feat(ui): add widget"` passes.
- Given no commits ahead of `main`, `commit_lint` returns `passed: true`.
- The `/deliver` flow surfaces the lint failure before the confirm prompt and stops.
- `allowed_types` parsed from `_standards.md` overrides the default set.

## Open Questions

- None — all decisions can be reasonably inferred from the feature description and existing
  harness patterns.
