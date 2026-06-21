# Solution

**Ticket**: 0020
**Title**: Rollback Skill

## Approach

Add a `/rollback` command as a harness skill document (`skills/rollback/SKILL.md`). The skill is a pure Markdown procedure that performs strict input validation, validates ticket status, searches git log for the unambiguous merge commit, performs a clean-tree pre-flight, confirms with the operator, and executes `git revert -m 1` with a standardized message. Rollback performs a `git revert` (a new forward commit that inverts the changes) — not a `git reset` — so history is preserved and the rollback itself is reversible.

## Components

| Component | Responsibility | Key interfaces |
|---|---|---|
| `skills/rollback/SKILL.md` | Full procedure: validate input → status check → log search → verify commit → dry-run/confirm → clean-tree check → revert | Reads `.tickets/**/status.md`; runs `git log`, `git status --porcelain`, `git revert` |
| `commands/rollback.md` | Thin entry-point dispatch; reads `$ARGUMENTS`; loads skill | Passes `$ARGUMENTS` to skill; no logic of its own |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Skill document (Markdown) | Consistent with all other harness commands; no new runtime dependency |
| Allow-list input validation as Step 0 | Security boundary: `^[0-9]{4}(-[a-z0-9-]+)?$` — fail closed before any git command |
| `git log --merges --grep "ticket/XXXX"` with one-SHA-per-line format | Targets only merge commits; `XXXX` is the validated four-digit prefix extracted from the argument (slug suffix discarded); one SHA per line avoids whitespace-splitting ambiguity in multi-match detection |
| Commit-subject verification via `git log -1 --pretty=format:'%s' <SHA>` | Confirms the subject (not just the grep-matched body) contains `ticket/XXXX` before presenting to operator — guards against grep matching commit bodies |
| `git revert --no-commit -m 1 <SHA>` + manual commit | `-m 1` is required for merge commits (selects mainline/first-parent); `--no-commit` allows a standardized commit message; em-dash (U+2014) in message format is canonical |
| `git status --porcelain` pre-flight immediately before revert | Fail closed on dirty working tree — guards against partial-state failures after confirmation |
| Argument-list git calls (no shell interpolation) | Complies with CLAUDE.md no-shell-concatenation rule |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1 / NFR-3 | Unit | Invalid argument (`abc`, empty) → validation error, no git ops |
| FR-2 / FR-3 | Unit | Ticket not done → warning, no git ops |
| FR-4 / FR-5 | Unit | No merge commit found → warning and exit |
| FR-6        | Unit | Two merge commits found → list both SHAs, exit |
| FR-7 (subject verification fails) | Unit | SHA found by grep; subject check fails → "commit subject does not match expected pattern", stop |
| FR-8 / FR-9 | Unit | Dry-run: prints commit info, no git state change |
| FR-10 (operator declines) | Unit | Operator responds "no" → no git state change |
| FR-11 / NFR-1 | Unit | Dirty working tree detected → halt before revert |
| FR-8 / FR-10 / FR-12 / FR-13 | Integration | Done ticket, clean tree, operator confirms → revert commit with correct message format |
| FR-14 | Integration | Done ticket, clean tree, revert conflicts → error reported, operator instructed to resolve |

## Tradeoffs

- **Chose `--merges --grep` over full log scan because**: limits results to merge commits with the ticket pattern, giving an unambiguous result in the common case.
- **Chose `--no-commit -m 1` revert + manual commit over plain `git revert` because**: `-m 1` is required for merge commits; `--no-commit` avoids editor spawn and allows a standardized message.
- **Chose fail-closed on all ambiguity because**: rollback is a destructive-adjacent action; false positives are worse than false negatives. An operator can always revert manually if the skill stops; a bad revert is harder to undo.
- **Accepting risk of**: non-standard merge messages (e.g. squash-and-merge) produce zero matches. The zero-match warning path handles this and directs the operator to manual revert.

## Risks

- **Merge commit message format coupling**: The skill depends on `/deliver` producing a merge commit with `ticket/XXXX` in the subject. If ticket 0003 (changelog / conventional-commit lint) changes the merge commit format, this skill silently degrades to zero-match errors. Mitigation: commit-subject verification step (FR-7) catches mismatches; coordinate with ticket 0003 if its scope touches merge commit messages.
- **status.md schema coupling**: The skill reads the `title:` field from `status.md` as defined in harness-reference.md. If the field name or format changes, the commit message is silently malformed. Mitigation: SKILL.md must cite `harness-reference.md § Tickets` as the normative schema source and validate that the extracted title is non-empty before committing.
- **Partial-archive state**: If `/deliver` is interrupted after the merge but before archiving, both `.tickets/XXXX-slug/status.md` (status: review-ready) and `.tickets/completed/XXXX-slug/status.md` may exist. FR-2 handles this by warning the operator and directing them to complete delivery before rolling back.
- **Revert conflicts**: `git revert -m 1` may hit conflicts if subsequent commits touched the same files. Mitigation: FR-14 explicitly handles the non-zero exit; the skill instructs the operator to resolve and run `git revert --continue` or `git revert --abort`.
- **Revert commit as future grep target**: The revert commit message (containing `revert(ticket): XXXX`) is observable by downstream tooling parsing git log. The revert commit is not a merge commit so `--merges` filtering correctly excludes it from future rollback searches, but this coupling surface should be noted in SKILL.md.
- **Multiple worktrees**: Running from a non-main worktree may give an unexpected `git log` scope. Mitigation: SKILL.md includes a note to run from the main repo root.

## Implementation Order

1. Write `skills/rollback/SKILL.md` — the full procedure (validation → status check → log search → verify → dry-run/confirm → pre-flight → revert).
2. Write `commands/rollback.md` — thin dispatch layer that loads the skill.
3. Set up the integration fixture (local git repo as described in the Test Strategy) and run both the happy path and the conflict scenario manually.
4. Verify the generated commit message format matches `revert(ticket): XXXX <title> — reverts merge commit <SHA>` exactly.
