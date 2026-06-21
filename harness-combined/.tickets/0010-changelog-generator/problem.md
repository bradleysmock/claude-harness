# Problem Statement

**Ticket**: 0010
**Title**: Changelog generator
**Date**: 2026-06-21

## Problem

The harness operator has no automated way to produce a formatted CHANGELOG entry after completing a batch of tickets. Today this requires manually inspecting `git log`, reading completed ticket titles, and hand-authoring a CHANGELOG section — a slow, error-prone process that tends to be skipped. The result is either no changelog or one that is incomplete and inconsistently formatted.

## Impact

- Harness operators lack a repeatable release-notes workflow, making it hard to communicate changes to downstream consumers.
- Without a command, releases accumulate undocumented changes or the operator must reconstruct history from git manually.
- Inconsistent changelog formats increase review burden and reduce changelog value over time.

## Success Criteria

- A `/changelog` command exists and can be invoked from the harness.
- The command collects all completed ticket titles since the last git tag (or all history if no tag exists).
- The command collects conventional-commit messages since the last git tag.
- Entries are grouped into sections: `feat`, `fix`, `chore` (and an `other` bucket for uncategorized commits).
- Ticket category drives section placement when available; conventional-commit prefix drives it for raw commits.
- Output is written or appended to `CHANGELOG.md` in the project root using a standard heading format (e.g. `## [Unreleased] – YYYY-MM-DD`).
- Duplicate entries (ticket + matching commit) are deduplicated.
- The command is idempotent: running it twice does not double-append the same unreleased block.

## Out of Scope

- Automatic git tagging or version bumping (no semver inference).
- Pushing or committing the CHANGELOG.md — operator does this manually.
- Parsing ticket bodies or commit bodies beyond the first line.
- Integration with external changelog services (GitHub Releases, etc.).
