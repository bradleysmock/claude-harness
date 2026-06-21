# Solution

**Ticket**: 0003
**Title**: Conventional-commit lint gate

## Approach

Add a `commit_lint` MCP tool to `server.py` backed by a pure-Python `gates/commit_lint.py`
module. The module runs `git log main..<branch>` via a subprocess argument list, validates
each subject against the conventional-commit regex, and returns structured `GateResult`
objects matching the existing gate interface. The `deliver-ticket.md` flow prose is updated
to invoke `commit_lint` in Step 1.5 (after validation, before confirm).

## Components

| Component                        | Responsibility                                              |
|----------------------------------|-------------------------------------------------------------|
| `gates/commit_lint.py`           | Core logic: git log, regex parse, config read, GateResult   |
|                                  | Exposes `CommitLintConfig` dataclass and `run()` function    |
| `server.py` — `commit_lint` tool | MCP tool wrapper; constructs config, calls `gates.commit_lint.run` |
| `context/flows/deliver-ticket.md`| Updated prose: Step 1.5 — run commit_lint, block on failure |
| `tests/test_commit_lint.py`      | Unit tests (regex, config parse) + integration (temp git repo) |

## Tech Choices

| Choice                              | Rationale                                                   |
|-------------------------------------|-------------------------------------------------------------|
| Pure Python regex, no external tool | No new runtime dependency; commitlint (Node) is heavy       |
| `git log main..<branch> -- `        | Standard idiom; `--` separator prevents branch-name option injection |
| Branch name validated against `^[a-zA-Z0-9_./-]+$` | Prevents git option injection via list args |
| Resolved base branch also validated  | Extracted `symbolic-ref` output validated against same allow-list before use |
| Regex pre-compiled once, type tokens constrained to `[a-z]+` | Eliminates ReDoS backtracking surface |
| Subject truncated to 200 chars before match | Bounds backtracking on `.+` for adversarial inputs |
| `CommitLintConfig` dataclass        | Avoids Data Clumps; makes config override composable        |
| `GateResult` / `GateError` models   | Consistent with all existing gates; caller parses uniformly |
| `_standards.md` for config          | Lead-curated file already read by harness; no new config    |
| Step 1.5 in deliver-ticket.md       | Earliest gate-like check before confirm; matches rebase guard pattern |

## Test Plan

| Requirement | Test Type   | Scenario(s)                                                           |
|-------------|-------------|-----------------------------------------------------------------------|
| FR-3 / D-01 | Unit        | Valid: `feat(ui): add button`; invalid: `wip: stuff`, bare `fix`, empty |
| FR-6        | Unit        | Default type list accepts `feat`, `chore`, `revert`; rejects `wip`   |
| FR-7        | Unit        | `require_scope=True` → `feat: x` fails; `feat(x): x` passes           |
| FR-4        | Unit        | Error `file` field is exactly `sha[:7]` (fixed-length contract)       |
| D-01        | Unit        | 200-char subject with repeated prefix does not breach 100ms           |
| D-04 merge  | Unit        | Subject `Merge branch 'x' into 'y'` excluded from validation          |
| D-04 body   | Integration | Commit with multi-line body: only subject line is checked             |
| D-04 adv    | Unit        | `branch="--format=injected"` → `passed: false`, INVALID_BRANCH error  |
| D2-01       | Unit        | `symbolic-ref` output with unexpected chars → base branch sanitized   |
| D2-02       | Integration | `branch` is syntactically valid but does not exist → `passed: false`, GIT_ERROR |
| FR-2 / FR-5 | Integration | Temp git repo; 3 commits on branch, 2 valid + 1 invalid → 1 error    |
|             |             | (calls `gates.commit_lint.run()` directly — covers standalone CI use)  |
| FR-5        | Integration | 0 commits ahead of `main` → `passed: true`, empty errors              |
| FR-9 happy  | Unit        | `_standards.md` with `allowed_types: [wip, feat]` overrides default   |
| FR-9 bad    | Unit        | Malformed `_standards.md` block → defaults used + warning GateError   |
| D2-04       | Unit        | `allowed_types: []` (empty list) in `_standards.md` → falls back to defaults + warning |
| D-02        | Unit        | Default-branch resolution failure → `passed: false`, BASE_BRANCH_UNKNOWN |
| FR-8        | Unit        | `context/flows/deliver-ticket.md` contains substring `commit_lint`    |

## Tradeoffs

- **Chose inline regex over external commitlint**: zero Node dependency; risk: won't catch every
  commitlint edge case, but spec requires only `type(scope): subject` format enforcement.
- **Chose `_standards.md` config over `.commitlintrc`**: reuses existing lead-curated file.
  Parsing is minimal: a `## Commit Lint` heading with `allowed_types:` and `require_scope:` lines.
- **Chose `file` field for commit SHA**: consistent repurposing of `GateError` model. Comment
  required at construction site: `# file field repurposed as commit SHA reference`.
  `message` field must be `"{sha[:7]}: {subject}"` so callers consuming only `message` get
  a self-contained diagnostic.
- **`allowed_types: []` falls back to defaults + warning**: empty list is not a valid override;
  treat like malformed config to avoid silently blocking all commits.
- **Accepting risk of**: shallow clones and repos without a remote `origin/HEAD` — both handled
  by BASE_BRANCH_UNKNOWN failure (fail closed, not false pass).
- **Merge commits excluded**: subjects matching `^Merge ` are skipped (not flagged).

## Risks

- `main` branch rename breaks `git log main..<branch>`. Mitigation: detect default branch from
  `git symbolic-ref refs/remotes/origin/HEAD` as fallback. Extracted branch name must be
  validated against `^[a-zA-Z0-9_./-]+$` before use. If detection or validation fails, return
  `GateResult(passed=False, errors=[GateError(code="BASE_BRANCH_UNKNOWN", ...)])`. Never
  silently pass when the base branch is unknown.
- `git log` exits non-zero or emits "unknown revision" when `branch` does not exist. Mitigation:
  capture returncode and stderr; any non-zero exit → `GateResult(passed=False, errors=[GateError(
  code="GIT_ERROR", ...)])`. FR-5 (`passed: true` on zero commits) applies only after a
  confirmed successful git invocation.
- `_standards.md` parse failure. Mitigation: fall back to defaults; emit one `GateError`
  with `severity: "warning"` describing the parse failure.
- Shallow clone / detached HEAD. Mitigation: BASE_BRANCH_UNKNOWN path applies; fail closed.

## Implementation Order

1. `tests/test_commit_lint.py` — write unit tests first (TDD): regex validation, config parse,
   branch validation, merge-commit exclusion, ReDoS guard, SHA format
2. `gates/commit_lint.py` — implement `CommitLintConfig`, `_parse_standards_config()`, `run()`
   to pass all unit tests
3. Integration tests in `tests/test_commit_lint.py` — add temp-git-repo tests that call `run()`
   directly; these require working `run()` so follow implementation
4. `server.py` — register `commit_lint` as `@mcp.tool()`
5. `context/flows/deliver-ticket.md` — add Step 1.5 prose block; the grep test from step 1
   will catch if this is omitted
