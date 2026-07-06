# Requirements

**Ticket**: 0017
**Title**: Multi-language polyglot gate

## Functional Requirements

1. The system must detect all language stacks present in a directory by scanning for manifest files (`pyproject.toml`, `setup.py`, `setup.cfg`, `package.json`, `tsconfig.json`, `go.mod`, `Cargo.toml`) at the root and one level deep in subdirectories.
2. The system must run all applicable language-specific gate suites (lint, type-check, test, security) for every detected stack when `language="auto"`, not stopping after the first language.
3. The system must aggregate results from all language suites into a single `gate-findings.md` with a section per language and gate name, clearly identifying which language each finding belongs to.
4. The system must produce a non-zero exit / `"passed": false` result when any gate in any detected language fails.
5. The system must support configurable per-language gate commands via a `[gates]` section in `.tickets/_standards.md` using TOML-like key-value syntax (e.g., `python.lint = "ruff check . --select E,F"`), which overrides the default gate commands for that language.
6. The `gate-findings.md` header must report all detected languages (not just one) in a `**Languages detected**` field when more than one language is found.
7. The `/gate` command summary line must report all languages and their pass/fail status (e.g., `gate: python=PASS typescript=FAIL: lint`).
8. When a single explicit language is passed (not `"auto"`), behavior must remain backward-compatible: the response shape and summary must be identical to the pre-polyglot behavior.
9. The system must handle the case where a detected language's toolchain is not installed by producing a `TOOL_ERROR` finding (not a crash), continuing to gate remaining languages.

## Non-Functional Requirements

1. Gate execution across multiple languages must run sequentially (not in parallel) to avoid interleaved output and temp-dir collisions.
2. The polyglot detection scan must complete in under 500ms for directories with up to 10,000 files.

## Test Strategy

| Type        | Rationale                                                              |
|-------------|------------------------------------------------------------------------|
| Unit        | `_detect_stacks` correctness for various manifest combinations; `_standards.md` gate-command parser; gate-findings.md aggregation format |
| Integration | `gate_run_on_dir` with a synthetic polyglot tmp dir (Python + TypeScript markers); confirm both language suites run and findings are aggregated |

## Acceptance Criteria

- A directory with both `pyproject.toml` and `package.json` triggers Python AND TypeScript gate suites.
- `gate-findings.md` contains sections for both languages when both are detected.
- A TypeScript lint failure in a Python+TypeScript repo causes the overall gate to fail, even if Python passes.
- A `python.lint` override in `_standards.md` replaces the default ruff invocation.
- Explicit `language="python"` on a Python+TypeScript repo runs only Python gates (backward compat).
- Missing toolchain (e.g., `tsc` not installed) produces a `TOOL_ERROR` entry in `gate-findings.md` and does not crash the gate run.

## Open Questions

None. Resolved during solution design:
- Gate overrides apply in **directory mode only** (`gate_run_on_dir`). Text mode (`gate_run`) is ephemeral spec generation with no `_standards.md` in scope.
- Subdir manifest scanning is capped at **1 level deep**. Sufficient for standard monorepo layouts; deeper scanning deferred to a follow-on ticket.
