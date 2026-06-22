# Requirements

**Ticket**: 0012
**Title**: Secrets/Credential Gate

## Functional Requirements

1. Provide a `secrets` gate scanning the worktree for credentials using gitleaks (preferred) or trufflehog (fallback).
2. The gate runs first in the `stop_full_gate` pre-deliver suite (before lint/type-check/tests/security).
3. On a detected credential: exit non-zero, `passed=False`, structured `GateError` (file, line, rule name, redacted snippet). Only `RuleID`, `File`, `StartLine`, `EndLine` fields from scanner JSON are used to construct GateErrors; `Match`, `Context`, and all line-content fields are discarded before writing.
4. Write findings to `gate-findings.md`; scanner JSON fields are treated as untrusted: file paths validated via `Path.resolve().relative_to(worktree_root)`, content fields dropped per FR-3.
5. Respect a `.gitleaks.toml` allow-list in the project root for known false positives.
6. When no scanner is installed: `passed=False` (blocking) unless `HARNESS_ALLOW_MISSING_SECRETS_SCANNER=1`, then `passed=True` with a `TOOL_MISSING` warning written to `gate-findings.md` (not just in-memory `GateError.errors`).
7. Scan only git-tracked files; untracked files must not be flagged. For gitleaks: `gitleaks detect --source . --redact`. For trufflehog: pre-filter to `git ls-files` output and pass as an explicit file list.
8. Expose via `run_suite_on_dir` dispatch via a single pre-dispatch insertion point (before language branching) so all languages benefit without per-language edits.
9. When both are installed, gitleaks takes precedence; trufflehog invoked only when gitleaks absent.

## Non-Functional Requirements

1. Complete in under 30 seconds for a typical worktree (< 500 tracked files).
2. `GateError.message` redaction: (a) no raw credential, (b) contains rule name, (c) first 4 chars of match + mask characters. Match/Context fields from scanner output are dropped, not masked.
3. File paths from scanner JSON validated via `Path.resolve().relative_to(worktree_root)` before use.
4. All subprocess calls use argument lists — no shell string concatenation.
5. Unrecognized trufflehog version string (prefix neither `"trufflehog 2."` nor `"trufflehog 3."`) → `passed=False` with a `TOOL_MISSING`-style warning rather than silently selecting a parser.

## Test Strategy

| Type        | Rationale                                                                  |
|-------------|----------------------------------------------------------------------------|
| Unit        | Scanner selection, TOOL_MISSING blocking/opt-out, redaction shape, trufflehog v2/v3 parsers, precedence, unrecognized version |
| Integration | Fixture git worktrees: fake key blocked; allow-list suppresses; untracked file not flagged (both gitleaks and trufflehog paths); TOOL_MISSING writes gate-findings.md |

## Acceptance Criteria

- Worktree with planted obviously-fake key → `passed=False`, correct file+line in GateError.
- Clean worktree → `passed=True`, empty errors.
- Same worktree + `.gitleaks.toml` allow-list entry → `passed=True`.
- Only trufflehog installed → `passed=False` on planted-key fixture; untracked file with fake key NOT flagged.
- Both installed → gitleaks args invoked, not trufflehog.
- Neither installed, env unset → `passed=False`.
- Neither installed, `HARNESS_ALLOW_MISSING_SECRETS_SCANNER=1` → `passed=True`, TOOL_MISSING entry written to `gate-findings.md`.
- Fake key in untracked file (gitleaks path) → NOT flagged.
- GateError message: no raw key; contains rule name; first 4 chars of key + masking chars.
- `secrets` result is index 0 in `run_suite_on_dir` return list for all languages.
- Unrecognized trufflehog version → `passed=False`, warning in findings.

## Open Questions

None.