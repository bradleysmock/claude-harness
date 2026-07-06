# Requirements

**Ticket**: 0020
**Title**: Rollback Skill

## Functional Requirements

1. The system must accept a ticket number as `$ARGUMENTS` and validate it against the pattern `^[0-9]{4}(-[a-z0-9-]+)?$` before any other operation. If the argument does not match, print an error and stop (no git commands are run). The four-digit numeric prefix is extracted by taking the first four characters; the slug suffix is discarded. This extracted prefix is used in all subsequent git log grep strings (e.g., argument `0020-rollback-skill` → grep prefix `0020`).
2. The system must search `.tickets/completed/XXXX-*/status.md` first, then `.tickets/XXXX-*/status.md` as fallback (active ticket). If both exist simultaneously (partial-archive state from an interrupted `/deliver`), warn the operator that the ticket is in a partial-archive state and that the merge may have already occurred even if the status reads `review-ready`; stop and direct the operator to complete the delivery before rolling back. Stop if no status file is found.
3. The system must confirm `status: done` in the resolved status file. If not `done`, warn the operator and stop without executing any git command.
4. The system must run `git log` with `--merges`, `--grep "ticket/XXXX"`, and a format that emits exactly one SHA per output line (e.g. `--pretty=format:"%H"` or equivalent), where XXXX is the four-digit ticket number from FR-1. Emitting one SHA per line (rather than `--oneline`) avoids whitespace-splitting ambiguity in multi-match detection.
5. The system must warn and stop if zero merge commits matching the ticket number are found.
6. The system must warn and stop if more than one merge commit matching the ticket number is found, listing the ambiguous SHAs.
7. The system must verify the found commit SHA actually contains the expected `ticket/XXXX` string in its subject line (fetched separately via `git log -1 --pretty=format:'%s' <SHA>`) before displaying it to the operator. If the subject does not match, report "commit subject does not match expected pattern" and stop — this guards against grep matching commit message bodies rather than subjects.
8. The system must display the identified merge commit SHA and full subject line to the operator before executing any revert.
9. When `--dry-run` is passed, the system must show the commit that would be reverted and exit without executing any git command.
10. When `--dry-run` is not passed, the system must prompt the operator to confirm (yes/no) before executing any git command. If the operator responds with anything other than an affirmative, exit without making any git changes.
11. Immediately before executing `git revert`, the system must run `git status --porcelain` and halt with an error if the output is non-empty ("Working tree is not clean — stash or commit pending changes before rollback"). No git-mutating commands run if the tree is dirty.
12. The system must execute `git revert --no-commit -m 1 <SHA>` then commit with message using this exact format: `revert(ticket): XXXX <title> — reverts merge commit <SHA>` where `—` is the Unicode em-dash character (U+2014), not a hyphen-minus or en-dash.
13. The system must read the ticket title from `status.md` to populate the standardized commit message.
14. If `git revert --no-commit -m 1 <SHA>` exits with a non-zero status (e.g., merge conflict), the system must report the error and instruct the operator to resolve conflicts manually before running `git revert --continue` or `git revert --abort`.

## Non-Functional Requirements

1. The skill must not execute any git-mutating commands before operator confirmation (or in dry-run mode).
2. Git commands must use argument lists, not shell string interpolation (no shell=True / eval / exec).
3. Input validation (FR-1) must be the first step — the skill fails closed on any malformed or unexpected argument.

## Tech Stack

Skill document (Markdown) — no new runtime. Invoked as a Claude Code skill via the existing harness loader.

## Test Strategy

| Type        | Rationale                                                                              |
|-------------|----------------------------------------------------------------------------------------|
| Unit        | Logic branches: input validation, status check, log search (0/1/many matches), subject verification failure, dry-run, operator decline, dirty-tree guard |
| Integration | Full run against a reproducible fixture repo; covers happy path and revert-conflict path |

**Integration fixture spec**: A local git repo (or subdirectory) containing: a `main` branch; a feature branch `ticket/0042-example` that was merged via `git merge --no-ff`; a `.tickets/completed/0042-example/status.md` with `status: done` and `title: Example Feature`; optionally a second commit on top of the merge touching the same file as the feature branch (to trigger a conflict scenario).

## Acceptance Criteria

- `/rollback 0020` on a done ticket with one merge commit prompts for confirmation, then reverts with message `revert(ticket): 0020 <title> — reverts merge commit <SHA>`.
- `/rollback 0020 --dry-run` prints the commit that would be reverted and makes no git changes.
- `/rollback 0020` on a ticket not in `done` status prints a warning and exits without any git operation.
- `/rollback 0020` when no merge commit is found prints a warning and exits.
- `/rollback 0020` when multiple merge commits are found lists ambiguous SHAs and exits.
- `/rollback 0020` when the operator responds "no" at the confirmation prompt exits without executing any git command and leaves the working tree unchanged.
- `/rollback 0020` when the working tree is dirty halts before `git revert` with a clean-tree error.
- `/rollback abc` or `/rollback` with no argument prints a validation error and exits immediately.
- `/rollback 0020` when `git revert --no-commit -m 1 <SHA>` exits non-zero, reports the conflict error, instructs the operator to resolve conflicts and run `git revert --continue` or `git revert --abort`, and leaves the index in the partially-reverted state (does not attempt `git revert --abort` automatically).

## Open Questions

- None.
