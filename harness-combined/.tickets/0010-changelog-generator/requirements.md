# Requirements

**Ticket**: 0010
**Title**: Changelog generator

## Functional Requirements

1. The system must provide a `/changelog` command that the harness operator can invoke.
2. The system must determine the "since" boundary as the most recent git tag reachable from HEAD; if no tag exists, it uses the initial commit (all history).
3. The system must collect all ticket titles from `.tickets/completed/*/status.md` whose final commit timestamp falls after the boundary (or, where timestamp is unavailable, whose ticket directory was last modified after the boundary).
4. The system must collect all git commit messages in `git log <tag>..HEAD` (or full history if no tag) whose subject line matches the conventional-commit pattern `type(scope): subject` or `type: subject`.
5. The system must categorize each entry into exactly one section: `feat`, `fix`, `chore`, or `other`.
   - For tickets: infer type from the ticket slug prefix if it begins with `feat-`, `fix-`, or `chore-`; otherwise use `other`.
   - For commits: use the `type` field of the conventional-commit prefix; if not a conventional commit, place in `other`.
6. The system must deduplicate entries: if a commit message subject matches a completed ticket title (case-insensitive, after stripping the conventional-commit prefix), include the entry once under the ticket's section.
7. The system must format the output as a Markdown block using the heading `## [Unreleased] – YYYY-MM-DD` (today's date) followed by `### feat`, `### fix`, `### chore`, `### other` subsections (omit empty subsections).
8. The system must write the formatted block to `CHANGELOG.md` in the project root — prepending it above any existing content if the file exists, or creating it if not.
9. The system must be idempotent: if an `## [Unreleased]` block already exists in `CHANGELOG.md`, it must replace that block rather than appending a duplicate.
10. The system must print the generated block to stdout after writing, so the operator can review it without opening the file.

## Non-Functional Requirements

1. The command must complete in under 5 seconds for repositories with up to 500 commits and 100 completed tickets.
2. The command must not modify any ticket metadata or git history — it is a read-and-write-CHANGELOG-only operation.

## Tech Stack

This is a new harness command (`commands/changelog.md`), not a new application. It follows the established pattern: a Markdown command file that Claude Code interprets. No new runtime dependency is introduced. All git introspection uses `git log`, `git tag`, and filesystem reads — no external changelog libraries.

## Test Strategy

| Type        | Rationale                                                                              |
|-------------|----------------------------------------------------------------------------------------|
| Unit        | Category inference logic (slug prefix, conventional-commit prefix, dedup matching)    |
| Integration | End-to-end: given a repo fixture with tags, completed tickets, and commits, verify the CHANGELOG.md output matches expected content |

## Acceptance Criteria

- Running `/changelog` in a repo with a git tag produces a `## [Unreleased]` block containing all completed ticket titles and conventional commits since that tag, grouped correctly.
- Running `/changelog` in a repo with no git tags produces a block covering all history.
- Running `/changelog` twice does not produce two `## [Unreleased]` blocks.
- An entry that exists as both a completed ticket title and a matching commit appears exactly once.
- Empty sections (`### feat` with no items) are omitted from the output.
- `CHANGELOG.md` is created if absent; existing content below the unreleased block is preserved.

## Open Questions

- Should the operator be able to pass a custom `--since <tag-or-sha>` override? Not required for v1; can be added in a follow-on.
- Ticket "category" is currently inferred from slug prefix only. If a future ticket introduces an explicit `category:` field in `status.md`, this command should prefer it — but that is a follow-on dependency.
