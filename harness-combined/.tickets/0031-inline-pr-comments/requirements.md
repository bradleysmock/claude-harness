# Requirements

**Ticket**: 0031
**Title**: Inline PR Comment Posting

## Functional Requirements

1. The system must detect whether an open GitHub PR exists for the current branch via `gh pr view --json number,headRefName`.
2. The system must parse `gate-findings.md` and extract file path, line number, severity, and message for each finding that carries a file:line reference.
3. The system must post each gate finding as an inline PR review comment on the correct file and line using `gh api /repos/{owner}/{repo}/pulls/{pr}/reviews` with a JSON `comments` array; findings on lines not present in the diff must fall back to a top-level PR comment.
4. The system must map critic findings by severity: BLOCKER and MAJOR become inline review comments; MINOR and OBS are posted as COMMENT-type inline review comments with the body prefixed `[suggestion]` — they do not use GitHub's code suggestion markdown syntax (which requires a replacement code block).
5. The system must detect duplicate comments before posting by fetching existing PR review comments and comparing a content hash; duplicate findings must be skipped.
6. The system must fall back to terminal-only output when no open PR is found for the current branch, printing a clear fallback notice.
7. The system must fall back to terminal-only output when `gh` is not installed (`command -v gh` fails) or not authenticated (`gh auth status` fails), printing a specific reason.
8. The system must expose a `--comment` flag on the `/gate` and `/critique` commands to opt into PR comment posting; the default behavior remains terminal output only.
9. The system must group all comments into a single `gh pr review` submission per run (not one API call per finding) to avoid GitHub rate-limit and notification spam.
10. The system must report a summary count after posting: "Posted N inline comments (M skipped as duplicates)."

## Non-Functional Requirements

1. The posting step must complete within 10 seconds for up to 50 findings.
2. No credentials or tokens may be logged or written to any artifact file.
3. `gh` subprocess calls must use argument lists, never shell string interpolation.

## Test Strategy

| Type        | Rationale                                                    |
|-------------|--------------------------------------------------------------|
| Unit        | Finding parser, severity mapper, deduplication hash logic    |
| Integration | End-to-end posting against a real or mocked `gh` subprocess  |

## Acceptance Criteria

- Running `/gate --comment` on a branch with an open PR posts findings as inline comments visible in the GitHub PR UI.
- Running `/gate --comment` on a branch with no open PR prints findings to terminal with a fallback notice; no error exit code.
- Running `/gate --comment` when `gh` is not authenticated prints a specific auth-failure message and falls back to terminal; exit code 0.
- Re-running `/gate --comment` on the same unchanged findings posts 0 new comments and reports all as duplicates.
- Running `/critique --comment` posts BLOCKER/MAJOR as inline comments and MINOR/OBS as `[suggestion]`-prefixed comments in the PR (no code replacement block).
- Running `/gate --comment` when `gh` is installed but the dedup comment-fetch fails (network/auth scope error) falls back to terminal with a specific warning; no duplicate comments are posted.

## Open Questions

- None. All decisions can be reasonably inferred from the stated constraints and the `gh` CLI's public API.
