# Solution

**Ticket**: 0007
**Title**: Ticket List Command

## Approach

Implement `/ticket-list` as a markdown slash command (`commands/ticket-list.md`) that instructs Claude to run an inline Python 3.9+ script (stdlib only) which: resolves the `.tickets/` root to an absolute path, globs `status.md` files with path-containment checks, parses fields, applies validated filters, and renders a Markdown table with a summary line. Python is chosen over bash to eliminate shell word-splitting and interpolation injection risks. All `status.md` field values are treated as data and rendered by Python only — never incorporated into Claude instruction text. Also update the `status.md` template in `commands/problem.md` to include an `effort` field.

## Components

| Component | Responsibility | Key Interface |
|---|---|---|
| `commands/ticket-list.md` | Slash command entry; instructs Claude to validate `$ARGUMENTS` flags and invoke inline Python verbatim | User flags via `$ARGUMENTS`; Python stdout printed verbatim |
| Flag interpretation layer | Claude validates `$ARGUMENTS` against allow-lists and mutual-exclusion rule; constructs Python call with safe literal args | `python3 -c '<script>' [--open\|--completed] [--status <stage>]` |
| Inline Python script | Resolves `.tickets/` root; containment-safe glob; parses fields; filters; renders Markdown table + summary | `sys.argv[1:]` for flags; reads `.tickets/` relative to `cwd` |
| `commands/problem.md` (edit) | Adds `effort: small` to the `status.md` template block | Template change only |

## Python Script Invocation Signature

Claude invokes the script as:
```
python3 -c '<inline-script>' [--open|--completed] [--status <stage>]
```
The script reads `sys.argv[1:]` for flags. `<stage>` when present is a single token from the allow-list. Claude prints the Python stdout verbatim — no post-processing of any field content.

## Flag Parsing Contract

`$ARGUMENTS` is validated by Claude before constructing the Python invocation:

1. Check for `--open`, `--completed`, `--status <stage>`.
2. If both `--open` and `--completed` are present: print error, do not run Python, exit 1.
3. If `--status <stage>` is present: validate `<stage>` against the allow-list (canonical source: the Python script constant `VALID_STAGES`; `commands/ticket-list.md` must reference the same list): `problem|requirements|solution|build|review|done|cancelled`. If not in list: print error, do not run Python, exit 1.
4. Valid flag values are passed to the Python script as quoted literals in `sys.argv` — never interpolated into shell strings.

**Allow-list ownership:** The canonical allow-list is the `VALID_STAGES` tuple in the inline Python script. The prose in `commands/ticket-list.md` must reference this constant, not duplicate it, to prevent drift.

## Content Safety Boundary

All field values read from `status.md` files (title, status, effort, updated, ticket) are data-plane content. They must be rendered by the Python script to stdout and must **never** be incorporated into `commands/ticket-list.md` instruction text or re-interpreted as Claude instructions. The Python script is the sole renderer; Claude's role ends after launching the script and printing its stdout verbatim.

## Path Safety Contract

The Python script must:
1. Resolve `tickets_root = Path(".tickets").resolve()`.
2. For each globbed path, use an explicit conditional (not `assert`, which is disabled under `-O`):
   `if not path.resolve().is_relative_to(tickets_root): continue  # skip with warning to stderr`
3. Any path that fails containment is skipped; the command continues and exits 0.

## Tech Choices

| Choice | Rationale |
|---|---|
| Python 3.9+ stdlib over bash | No shell word-splitting; `Path.is_relative_to()` for safe containment; no injection surface; `re` for robust field parsing |
| Claude interprets flags, Python renders data | `$ARGUMENTS` validated by Claude (allow-list + mutual-exclusion); data rendered by Python only — no field content reaches instruction layer |
| Markdown table output | Consistent with `/ticket-status`; matches harness rendering context |
| Truncate titles at `len > 39` → 39 + `…` | Keeps Markdown table header row under 100 chars (NFR-2); unambiguous boundary condition |
| `updated` sourced from `status.md` field | Consistent with `effort`, `title`, `status` field sourcing; avoids filesystem mtime dependency (flaky in CI fixture tests) |
| `VALID_STAGES` tuple as canonical allow-list | Single definition; eliminates drift across `requirements.md`, `solution.md`, and `ticket-list.md` — prose references the constant, not a duplicated list |

## Test Plan

| Requirement | Test Type   | Scenario(s) | Exit Code |
|-------------|-------------|-------------|-----------|
| FR-1        | Integration | Fixture with 3 open + 2 completed; all 5 rows, all fields present | 0 |
| FR-2        | Integration | Table has columns: #, Status, Title, Effort, Updated | 0 |
| FR-3        | Integration | `--open`: 3 rows, no completed rows | 0 |
| FR-4        | Integration | `--completed`: 2 rows, no open rows | 0 |
| FR-5a       | Integration | `--status solution`: only matching rows | 0 |
| FR-5b       | Integration | `--status invalid_stage`: error message printed | 1 |
| FR-5c       | Integration | `--status solution --open`: only open-solution rows | 0 |
| FR-6        | Integration | Rows sorted ascending by ticket number | 0 |
| FR-7        | Integration | `status.md` with missing `effort` → `—` in Effort column | 0 |
| FR-8a       | Integration | Ticket directory with no `status.md` → skipped, other rows present | 0 |
| FR-8b       | Integration | Zero-byte `status.md` → all-`—` row, no crash | 0 |
| FR-9        | Integration | Summary line counts match fixture (open vs completed) | 0 |
| FR-10       | Integration | `--status build` with no matching tickets → "No tickets found." | 0 |
| FR-11       | Integration | `--open --completed` → error message | 1 |
| FR-12       | Integration | `.tickets/` absent → "No tickets found." | 0 |
| NFR-3       | Integration | Title of 45 chars → 39 chars + `…` in output | 0 |
| NFR-3b      | Integration | Title of exactly 39 chars → displayed as-is (no truncation) | 0 |
| extra-pipe  | Integration | Title containing `\|` → rendered as `\\\|`, table structure intact | 0 |
| extra-nl    | Integration | Title containing embedded newline → newline replaced with space | 0 |

## Tradeoffs

- **Chose Python over bash**: eliminates shell word-splitting on slug paths and string-interpolation injection; `Path.resolve()` + `is_relative_to()` provides deterministic containment.
- **Chose `--completed` over `--done`**: `--done` implies only `status: done`; the completed directory also contains cancelled tickets; `--completed` matches the directory name.
- **Chose integration-only tests**: no callable Python module boundary in a prose command file; unit tests are not applicable without extracting a separate script.
- **Chose `status.md` field for `updated`**: avoids filesystem mtime dependency that causes flaky test fixtures in CI.
- **Newlines in title replaced with space**: deterministic; preserves title readability; alternative (strip) loses information.

## Risks

- **Python 3.9 minimum**: `is_relative_to()` requires 3.9+. Mitigated by stating the version floor in `requirements.md § Tech Stack`. If the harness shell has an older Python, the implementer must use the str-prefix fallback `str(p.resolve()).startswith(str(tickets_root) + os.sep)`.
- **Allow-list drift**: mitigated by declaring `VALID_STAGES` in Python as canonical; prose in `ticket-list.md` references the constant.
- **Prompt injection via `status.md` content**: mitigated by the Content Safety Boundary — all field values rendered by Python stdout only, never re-fed to Claude instruction layer.
- **`assert` vs. explicit conditional**: `assert` is disabled under `-O`; path-containment check uses `if not ... : continue` unconditionally.

## Implementation Order

1. Update `commands/problem.md`: add `effort: small` to the `status.md` template block.
2. Write `commands/ticket-list.md` with: flag-validation prose (allow-list, mutual-exclusion check, content safety boundary note), inline Python script (path-safe glob, `VALID_STAGES` constant, field parse, filter, Markdown table render with title truncation + pipe/newline sanitization, summary line, explicit containment check).
3. Write integration tests against a fixture `.tickets/` directory tree covering all test plan rows above.
