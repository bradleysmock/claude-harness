# Requirements

**Ticket**: 0028
**Title**: GitHub PR auto-creation

## Functional Requirements

1. The system must accept a `--pr` flag on `/deliver` when run in ticket mode.
2. When `--pr` is present, the system must push the ticket branch to the configured remote before opening a PR and before merging locally.
3. When `--pr` is present, the system must open a GitHub PR using `gh pr create` with the ticket title as the PR title. The title must be passed as a shell-quoted argument — never via string concatenation — so that titles containing `"`, `$`, `` ` ``, or `;` are safe.
4. The PR body must include a summary derived from `solution.md` (the `## Approach` section). If the section is absent or empty, the body must use the placeholder text `"(No Approach section found in solution.md)"` and must not error.
5. The PR body must include the Acceptance Criteria from `requirements.md` rendered as a Markdown checkbox checklist (`- [ ] …`). If the section is absent or empty, the body must use a placeholder and must not error.
6. The PR body must include a reference to the ticket number (e.g. `Ticket: 0012`).
7. When `gh` is not installed (`command -v gh` exits non-zero), the system must skip PR creation, emit a warning, and continue the normal deliver flow without error.
8. When `gh` is installed but not authenticated (`gh auth status` exits non-zero), the system must skip PR creation, emit a warning, and continue the normal deliver flow without error.
9. When `gh pr create` fails for any reason other than FR-7 or FR-8 (e.g. network error, permission denied, missing remote), the system must report the error to the lead and stop.
10. When `--pr` is not passed, the existing deliver flow must be unchanged.
11. The `--pr` flag must be compatible with the standard merge-to-main delivery path (not a replacement). PR creation occurs before the local merge.
12. The confirm prompt (Step 3 of the deliver flow) must include `git push origin <branch>` and `gh pr create ...` in the list of planned actions when `--pr` is present.
13. When the ticket branch already has an open PR (detected by `gh pr view --json state --jq '.state'` returning `"OPEN"`), the system must skip `gh pr create`, print the existing PR URL, and continue to the local merge without error. A closed or merged PR must not be treated as an existing open PR.
14a. If `gh pr create` exits non-zero with stderr indicating a duplicate PR (TOCTOU race), the system must treat this as FR-13: fetch the URL via `gh pr view`, print it, and continue to merge (not a hard stop).
14. When `--pr` is passed in spec mode (non-ticket deliver), the system must emit a warning that `--pr` is only supported in ticket mode and continue the normal spec deliver flow without error.

## gh exit-code classification

The guard must classify `gh` failures as follows:

| Condition | Detection | Action |
|---|---|---|
| `gh` not installed | `command -v gh` exits non-zero | Skip with warning, continue |
| Not authenticated | `gh auth status` exits non-zero | Skip with warning, continue |
| PR already open | `gh pr view <branch>` exits 0 | Skip creation, print existing URL, continue |
| Any other failure | `gh pr create` exits non-zero | Stop and report error |

## Non-Functional Requirements

1. The `gh` CLI detection and authentication check must complete within 5 seconds.
2. The PR creation step must not block or retry — one attempt, report any failure.

## Test Strategy

| Type        | Rationale                                                                              |
|-------------|----------------------------------------------------------------------------------------|
| Unit        | Flag parsing; body assembly (Approach present, Approach absent, AC present, AC absent) |
| Integration | `gh` not installed; `gh` not authenticated; existing PR; unexpected failure; happy path |

## Acceptance Criteria

- `--pr` is accepted by `/deliver` in ticket mode with no argument errors.
- A PR is opened on GitHub with the correct title, body (Approach + checklist + ticket link). PR creation occurs after the branch is pushed but before the local merge.
- When `gh` is absent, a warning is printed and the ticket is still delivered normally.
- When `gh auth status` fails, a warning is printed and the ticket is still delivered normally.
- When a PR is already open for the branch (state `"OPEN"`), the existing URL is printed, no new PR is created, and the merge proceeds normally. A closed/merged PR does not trigger this path.
- A TOCTOU race (PR created between pre-check and `gh pr create`) is caught by stderr pattern and treated the same as an existing-open PR (URL printed, merge proceeds).
- When `gh pr create` fails unexpectedly (not install/auth/duplicate), the flow stops, the error is reported, and recovery instructions (branch already pushed) are printed.
- A title containing `"`, `$`, `` ` ``, or `;` is handled safely (no shell injection).
- When `solution.md` has no `## Approach` section, the PR body uses the placeholder and does not error.
- When `--pr` is omitted, `/deliver` behavior is byte-for-byte identical to today.
- When `--pr` is passed in spec mode, a warning is printed and the spec deliver proceeds normally.

## Open Questions

- None.
