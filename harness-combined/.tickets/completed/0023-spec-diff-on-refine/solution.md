# Solution

**Ticket**: 0023
**Title**: Spec diff on refine

## Approach

Add a new `PreToolUse` hook (`pre_ticket_diff.py`) that intercepts `Write`/`Edit`/`MultiEdit` calls targeting files under `.tickets/`, reads the current file content, computes a unified diff against the incoming content, and prints it to stderr before the write proceeds. The hook is registered alongside the existing `pre_write_guard.py` in `plugin.json`. The hook is the sole enforcement mechanism — command-file updates are documentation only. `pre_write_guard.py` is not refactored; only `extract_file_path` is shared via a minimal `_common.py`.

## Components

| Component | Responsibility | Key interface |
|---|---|---|
| `hooks/pre_ticket_diff.py` | Detect ticket artifact writes; reconstruct full proposed content; compute unified diff; print to stderr | `PreToolUse` stdin; exits 0 always (never blocks) |
| `hooks/_common.py` | Shared `extract_file_path` utility only — no patch logic | Imported by `pre_write_guard.py` and `pre_ticket_diff.py` |
| `plugin.json` hook registration | Add new hook to `PreToolUse` matcher alongside existing `pre_write_guard` | JSON config |
| Command `.md` updates (informational) | One-sentence note that diff is shown automatically by the hook | `refine.md`, `solution.md`, `requirements.md` |
| `tests/test_pre_ticket_diff.py` | Unit + integration coverage for diff logic, patch reconstruction, path containment, and hook dispatch | pytest |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| Python stdlib `difflib.unified_diff` | Zero dependencies; already in all hooks; correct unified-diff format |
| `PreToolUse` hook (not `PostToolUse`) | Diff must appear before the write, not after |
| Hook approach (not command-prose-only) | Enforces behavior across all commands; not fragile to LLM drift; "any other command" coverage is automatic |
| Print to stderr (not stdout) | Claude Code SDK `PreToolUse` stdout may carry protocol semantics; stderr is safe for free-form output; consistent with `pre_write_guard.py` |
| Exit 0 always | Diff display must never block a write |
| Env var `HARNESS_NO_DIFF=1` suppression | Hooks receive JSON payloads, not CLI flags — env var is the only reliable suppression path; CI-friendly |
| `Path.resolve().is_relative_to()` for path containment (Python ≥ 3.9) | Guards against relative traversal and absolute paths string-containing `.tickets/`. Requires Python 3.9+; note this as a stated minimum in `pyproject.toml`. |
| `reconstruct_proposed_content` is diff-hook-only (not shared with guard) | `pre_write_guard.py` correctly scans only the incoming changed fragment for violations — scanning the full reconstructed file would produce false positives on pre-existing code. The two hooks have irreconcilable needs; only `extract_file_path` is shared. |
| `apply_patches(edits: list[dict])` for `Edit`/`MultiEdit` reconstruction | For `Write`, use `content` field directly. For `Edit`, read current file, call `apply_patches([{"old_string":…, "new_string":…}])`. For `MultiEdit`, call `apply_patches(edits)` sequentially. On `old_string` not found: return `None` and skip diff (graceful degradation). |

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1        | Unit        | `compute_diff` returns non-empty output when old ≠ new |
| FR-1        | Unit        | `compute_diff` returns empty when old == new |
| FR-4        | Unit        | `should_show_diff` returns False when file does not exist |
| FR-5        | Unit        | `should_show_diff` returns False when content identical |
| FR-1        | Unit        | Diff output contains `---`, `+++`, and `@@` markers |
| FR-6        | Unit        | Diff lines prefixed with `+`/`-` correctly |
| FR-7        | Unit        | `HARNESS_NO_DIFF=1` in environment causes hook to produce no output and exit 0 |
| NFR-2       | Unit        | Hook exits 0 and produces no output when file is unreadable (mocked `PermissionError`) |
| NFR-2       | Unit        | Hook exits 0 gracefully when `CLAUDE_PLUGIN_ROOT` is unset or resolves to non-existent path |
| FR-1        | Unit        | Path outside `.tickets/` root (absolute or traversal) is skipped — no diff output |
| FR-2        | Integration | Hook stderr includes diff text when invoked with `Write` to a `.tickets/` path with differing content |
| FR-2        | Integration | Hook produces no output for `Write` when target file does not exist |
| FR-2        | Integration | Hook produces diff reflecting net file change when invoked with `Edit` tool call on a `.tickets/` file |
| FR-3 | — | xref requirements.md FR-3 |

## Tradeoffs

- **Chose hook over LLM-instruction-only because**: LLM instructions drift; a hook fires mechanically for every command that touches `.tickets/`. FR-3's "any other command" clause is satisfied without enumerating command files.
- **Chose stderr over stdout because**: `PreToolUse` stdout may carry protocol semantics in the Claude Code SDK; stderr is safe and consistent with the existing guard hook.
- **Chose not to refactor `pre_write_guard.py` because**: the guard needs only the incoming fragment, not full reconstructed content; merging the two functions into one shared utility would corrupt the guard's violation-detection semantics. Only `extract_file_path` is shared.
- **Accepting risk of**: one-line diffs on `status.md` writes — low-signal but harmless; a filename filter can be added later if noise is a problem.
- **Accepting risk of**: verbose output on large rewrites — mitigated by unified diff's hunk compression.

## Risks

- Hook fires on every `Write`/`Edit` to `.tickets/` including `status.md`. Accepted; see tradeoff above.
- `Edit` reconstruction fails silently if `old_string` doesn't match — hook skips the diff and proceeds (no error). This is the correct failure mode since the subsequent write will also fail.
- Python ≥ 3.9 required for `Path.is_relative_to()`. Must be declared in `pyproject.toml` and checked in CI.
- `difflib.unified_diff` does not colorize output. ANSI color is out of scope.

## Implementation Order

1. Write `tests/test_pre_ticket_diff.py` with all unit and integration test cases (TDD — tests first, all failing).
1b. Run existing `pre_write_guard` tests to establish a green baseline before touching any existing code.
2. Create `hooks/_common.py` with `extract_file_path` only. Update `pre_write_guard.py` to import `extract_file_path` from `_common.py` (no behavioral change). Verify `pre_write_guard` tests still green.
3. Implement `hooks/pre_ticket_diff.py` with `apply_patches`, `compute_diff`, `should_show_diff`, `reconstruct_proposed_content`, and `main` entrypoint.
4. Register the hook in `plugin.json` under `PreToolUse` alongside `pre_write_guard.py`.
5. Add one-sentence diff-awareness note to `commands/refine.md`, `commands/solution.md`, and `commands/requirements.md`.
6. Run all tests — all green.
7. Manual smoke test: `/refine` on a ticket with an existing `solution.md`; confirm diff appears in terminal.
