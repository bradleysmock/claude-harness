# Solution

**Ticket**: 0006
**Title**: _standards.md schema validator

## Approach

Implement a Python module at `.harness/validators/standards_validator.py` exposing a callable `validate(path, config)` API seam for unit tests and a thin `main(argv)` CLI wrapper for invocation from command prose. The CLI is invoked via `python .harness/validators/standards_validator.py .tickets/_standards.md` from `/problem` Phase 0 and both `/build` flow files — inserted **before** the `@.tickets/_standards.md` context load so stub content never bleeds into the agent's context on a failing run. On failure it exits code 1 with a per-section error list to stderr; on success it exits code 0 with no output. Required sections are declared in operator-owned `.harness/validators/standards_config.toml` (falls back to built-in default). Stub detection uses `str.lower()` substring matching for exact tokens and per-line `re.search` for the `(e.g.)` pattern, eliminating ReDoS.

## Components

| Component | Responsibility | Key Interfaces |
|---|---|---|
| `validate(path, config)` | Pure validation logic: parse file, check sections, detect stubs | Returns `None` on pass; raises `StandardsValidationError` on fail |
| `main(argv)` | Thin CLI wrapper: parse arg, load config, call `validate()`, format stderr, `sys.exit` | Invocable from command prose via Bash; exit 0 on pass, exit 1 on fail |
| `StandardsValidationError` | Structured exception with separate file-error and section-failure fields | `.file_error: str \| None`, `.missing_sections: list[str]`, `.stub_sections: list[dict]` |
| `STUB_STRINGS` / `STUB_LINE_PATTERN` | Two-tier stub detection constants | Module-top; docstring cites `/init` stub as authoritative source for updates |
| `.harness/validators/standards_config.toml` | Operator-owned required-sections list | `required_sections = ["language", "test strategy"]`; extends without touching harness source |
| `/problem` hook | `python .harness/validators/standards_validator.py .tickets/_standards.md` at Phase 0 entry | Inserted before `@.tickets/_standards.md` load; halt on non-zero exit |
| `build-ticket.md` hook | Same call at top of Step 1 | Inserted **before** the `@.tickets/_standards.md` context include; halt on non-zero exit |
| `build-spec.md` hook | Same call at equivalent entry point | Inserted before any `_standards.md` context load; halt on non-zero exit |

## Invocation Mechanism

The validator is a Python script invoked via Bash from command prose:

```
python .harness/validators/standards_validator.py .tickets/_standards.md
```

If this exits non-zero, the pipeline halts and shows stderr output. Critically, this call appears **before** any `@.tickets/_standards.md` include in the flow file, so stub content never enters the agent's context on a failing run. On success (exit 0), the flow continues normally and the `@`-include follows.

## Tech Choices

| Choice | Rationale |
|---|---|
| `validate()` callable seam + `main()` CLI wrapper | Unit tests call `validate()` directly (fast, can assert on exception attributes); command prose invokes `main()` via Bash; no duplicate logic |
| CLI script with exit codes | Invocable from Bash in command prose; unambiguous contract; no import bridge needed |
| `str.lower()` substring for stub tokens | Eliminates ReDoS; faster than regex for finite exact strings; false-positive-safe |
| Per-line `re.search` for `(e.g.)` pattern only | Regex only where pattern (not exact string) matching needed; per-line bound eliminates full-body backtracking risk |
| Heading-level-agnostic `#{1,6}\s+<name>` | Prevents silent bypass when operator uses h3; any heading level counts as "section present" |
| `.harness/validators/standards_config.toml` | Operator-owned config outside harness source; fallback to `DEFAULT_REQUIRED_SECTIONS` if absent |
| Max section body 64 KB cap | Timing safety for pathological files; applied before any pattern check |
| Path containment check | Resolve path against `Path.cwd()`; raise hard error if outside project root (McGraw) |

## Stub Detection Design

Canonical predicate: **a section fails if and only if every non-blank line in its body is a stub line. A section with no non-blank lines (empty or whitespace-only body) also fails. One non-blank non-stub line passes the section.**

Two-tier stub check, applied per-line:

1. **Exact-token** (`line.lower()` contains any token in `STUB_STRINGS`): `todo`, `<fill in>`, `placeholder`, `tbd`, `fixme`
2. **Line-pattern** (`re.search(STUB_LINE_PATTERN, line)`): matches `^\s*-\s+\(e\.g\.\)` — the exact `/init` stub example-bullet format

`STUB_LINE_PATTERN` is a single pattern (a list for future extensibility); its docstring states: "Update when `/init` stub changes."

## Test Plan

| Requirement | Test Type | Scenario(s) |
|---|---|---|
| FR-1: file existence | Unit | Missing file → `StandardsValidationError.file_error = "not found"`, no section entries |
| FR-1: path containment | Unit | Path outside `Path.cwd()` → hard error before file open |
| FR-2: section presence | Unit | File missing `language` heading → `.missing_sections = ["language"]`; all required headings → pass |
| FR-2: h3 heading variant | Unit | `### language` (h3) → section detected as present |
| FR-3: stub token detection | Unit | Body = `TODO` → stub; `<fill in>` → stub; `(e.g.) Python: black` → stub |
| FR-3: mixed valid+stub line | Unit | Body = `Python — see TODO for details` → pass (one non-stub non-blank line) |
| FR-3: empty / whitespace body | Unit | Heading present, body whitespace-only → stub; body blank lines only → stub |
| FR-3: short valid content | Unit | Body = `  Python  ` (stripped non-blank non-stub) → pass; `Go` → pass |
| FR-4: halt — CLI exit code | Unit | `validate()` raises `StandardsValidationError` on stub fixture; `main()` exits 1; no stdout |
| FR-4: hook position — `/problem` | Prose check | Assert hook call appears before `@.tickets/_standards.md` in `commands/problem.md` Phase 0 |
| FR-4: hook position — `build-ticket.md` | Prose check | Assert hook call appears before `@.tickets/_standards.md` in `build-ticket.md` Step 1 |
| FR-4: hook position — `build-spec.md` | Prose check | Assert hook call appears before any `_standards.md` load in `build-spec.md` |
| FR-5: per-section error message | Unit | Two failing sections → stderr lists both with section name and reason |
| FR-6: silent pass | Unit | `validate()` returns `None`, no exception; `main()` exits 0, empty stdout+stderr |
| FR-6: NFR-2 (no side effects) | Unit | Passing run: no files written, no stdout, no stderr (assert via captured streams + tmpdir scan) |
| FR-7: configurable section list | Unit | Config adds `security`; file lacks `security` → failure |
| FR-7: config absent fallback | Unit | Config file missing → default list used, validation proceeds |
| NFR-1: latency | Unit | 1 KB `_standards.md` → `validate()` completes in < 50 ms |
| NFR-3: no false positives | Unit | `Go`, `Python`, single-word bodies → pass |

## Tradeoffs

- **Chose `validate()` + `main()` split because**: unit tests need to assert on exception attributes, not subprocess exit codes; `main()` is a one-liner wrapper that costs nothing.
- **Chose validator call before `@`-include because**: if the include fires first, stub content enters the agent's context even when the guard fires — fail-closed requires no content reads before the halt.
- **Chose heading-level-agnostic matching because**: h3 bypass would silently invalidate the entire feature; any heading level matching is correct behavior.
- **Chose `str.lower()` substring over compiled regex for tokens because**: eliminates ReDoS; finite exact strings.

## Risks

- **Risk**: `standards_config.toml` absent (fresh install or not committed).
  **Mitigation**: Fallback to `DEFAULT_REQUIRED_SECTIONS`; absence is not an error.
- **Risk**: `/init` stub gains new placeholder patterns not in `STUB_STRINGS`.
  **Mitigation**: `STUB_STRINGS` docstring states "update when `/init` stub changes"; `DEFAULT_REQUIRED_SECTIONS` changes are semver-significant.
- **Risk**: Operator uses heading-level inconsistency in `_standards.md`.
  **Mitigation**: Heading-agnostic detection handles transparently.

## Implementation Order

1. Write unit tests (all Unit and Prose check rows in Test Plan).
2. Write `standards_validator.py`: `validate()`, `main()`, `StandardsValidationError`, `STUB_STRINGS`, `STUB_LINE_PATTERN`.
3. Create `.harness/validators/__init__.py` (empty) and `.harness/validators/standards_config.toml`.
4. Add validator hook to `commands/problem.md` Phase 0 — before `@.tickets/_standards.md` load.
5. Add validator hook to `context/flows/build-ticket.md` Step 1 — before `@.tickets/_standards.md` include.
6. Add validator hook to `context/flows/build-spec.md` — before any `_standards.md` context load.
7. Write integration tests (FR-6 passing-path end-to-end via temp dirs for `/problem` and `/build` spec mode).
