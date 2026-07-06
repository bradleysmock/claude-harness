# Requirements

**Ticket**: 0015
**Title**: Bisect Helper

## Functional Requirements

1. The system must accept a `--good <ticket-or-ref>` argument. When given a four-digit ticket number, it must locate the merge commit for that ticket's branch. When given any other value, it must treat it as a raw git ref (SHA, HEAD~N, tag, etc.).
2. The system must accept an optional `--bad <ticket-or-ref>` argument (default: HEAD). Same resolution rules as FR-1.
3. The system must validate ticket number arguments against the pattern `^\d{4}$` before any use. Non-conforming values that are also not valid git refs must produce an error before bisect starts.
4. The system must resolve ticket numbers to git merge commits by searching the git log for merge commits whose subject line matches the pattern `Merge.*\bticket/XXXX-` (anchored to the subject, not full body). If no merge commit is found for a given ticket number, the command must error with a clear message before starting bisect.
5. The system must start a `git bisect` session using the resolved good/bad boundaries.
6. The system must determine the test command by: (1) checking `--run` argument if provided; (2) checking `test_command` key in `.claude/settings.json` if present; (3) detecting project type — if `package.json` is present, try `npm test`; if `pyproject.toml` contains a `[tool.pytest.ini_options]` or `[tool.pytest]` section, try `pytest`; (4) if no command can be determined, error with guidance before starting bisect. Detection of `pyproject.toml` without a pytest section must NOT emit `pytest` as the test command.
7. The system must run the resolved test command at each bisect step via `git bisect run`. The test command must be a single executable path. If `--run` contains spaces (indicating a multi-word command), the system must wrap it in a temporary shell script (`mktemp`) and delete the script on cleanup. A single-word command path is passed directly as the `git bisect run` argument.
8. The system must automatically pass `git bisect good` or `git bisect bad` based on the test command's exit code (0 = good, non-zero = bad).
9. The system must report the culprit commit SHA when bisect terminates.
10. The system must map the culprit commit back to a ticket using merge-commit ancestry traversal as the primary mechanism. If the culprit SHA is itself a merge commit targeting a `ticket/XXXX-*` branch, it must be attributed to that ticket directly. If it is not a merge commit, the system must walk `git log --merges --ancestry-path <sha>..HEAD` to find the enclosing merge commit. Branch containment (`git branch -r --contains`) is supplementary only and must not be the sole mechanism.
11. The system must emit the final result as: "Regression introduced in commit <sha> — part of ticket XXXX (<title>)" or "Regression introduced in commit <sha> — not linked to a ticket" when no ticket is found. The title is extracted from the `title:` field in `.tickets/XXXX-*/status.md`. When status.md is absent or the `title:` field is missing, the output must use "XXXX" with no title rather than erroring.
12. The system must run `git bisect reset` to restore the repo to the original HEAD on every exit path: successful culprit identification, no-culprit result, error in setup, error mid-bisect, and user interruption.

## Non-Functional Requirements

1. The command must not leave the repo in a detached-HEAD or mid-bisect state on any exit path, including the normal success path where `git bisect run` exits 1 (culprit found).
2. All shell commands invoked by this command must use argument lists, never string interpolation (per code generation rules). This applies to all git invocations, the test command, and the cleanup step.
3. The command must handle repos with no ticket merge commits gracefully (fall back to reporting the raw SHA without error).

## Test Strategy

| Type        | Rationale                                                             |
|-------------|-----------------------------------------------------------------------|
| Unit        | Ticket-to-merge-commit resolution logic; bisect step result mapping   |
| Integration | Full bisect run against a fixture git repo with known regression commit |

## Acceptance Criteria

- Running `/bisect --good 0010 --bad 0012` in a repo with those ticket merge commits starts bisect between those boundaries.
- The test command is invoked at each bisect step; pass/fail drives `git bisect good/bad` without operator input.
- Multi-word `--run` values (e.g., `pytest -x tests/`) are wrapped in a temporary script and execute correctly.
- The final output names the culprit commit SHA and, when applicable, the ticket that introduced it — correctly attributing commits even when ticket branches have been deleted post-merge.
- When the culprit is the merge commit itself, it is still attributed to the correct ticket.
- The repo HEAD is restored to the pre-bisect ref after the command completes (success or error), including the normal success case where `git bisect run` exits 1. No spurious "We are not bisecting" stderr on the success path.
- When a ticket number is supplied but no merge commit can be found, the command errors with a clear message before starting bisect.
- When `--good` or `--bad` receives a non-4-digit, non-valid-git-ref value, the command errors before starting bisect.
- When no test command can be determined, the command errors with guidance before starting bisect.
- A repo with `pyproject.toml` but no `[tool.pytest]` section does not auto-select `pytest`.

## Open Questions

None. Test command resolution order defined in FR-6; input validation defined in FR-3.
