# Requirements

**Ticket**: 0022
**Title**: Per-language gate /doctor

## Functional Requirements

1. The system must scan the project root for language manifest files (pyproject.toml, setup.py, setup.cfg → Python; package.json → Node/TypeScript; Cargo.toml → Rust; go.mod → Go) to detect which languages are present.
2. The system must maintain a static registry mapping each detected language to its required and optional gate tools (e.g. Python → mypy, ruff, bandit; TypeScript → tsc, eslint; Rust → cargo clippy, cargo fmt; Go → go vet, staticcheck).
3. For each tool in the registry for a detected language, the system must probe the tool by running `<tool> --version` and record one of four statuses: `found` (on PATH, exit 0, version captured from stdout or stderr), `found (error)` (on PATH, non-zero exit but output present), `missing` (not on PATH or FileNotFoundError at execution), or `timeout` (probe exceeded 5-second limit).
4. The system must print a formatted table per language: columns are tool name, status token (one of `found` / `found (error)` / `missing` / `timeout`), and version string or installation hint.
5. The system must print an installation hint for each missing required tool (e.g. `pip install ruff`, `npm install -g typescript`).
6. The system must signal `any_missing=True` if any required tool has status `missing` or `timeout`; `any_missing=False` otherwise. The MCP tool returns this signal so Claude can communicate non-zero status to the operator.
7. The system must accept an optional `project_root` parameter (default: CWD resolved at call time) to point at a project root other than the current working directory.
8a. The system must validate `project_root` with `Path.resolve()` + `is_dir()` before any filesystem or subprocess operation; return a structured error if the path is not a real directory.
8. The system must handle the case where no recognized manifest files are found by printing a clear "no supported languages detected" message and exiting 0.

## Non-Functional Requirements

1. Each tool probe must time out after 5 seconds to prevent hangs from broken tool installations.
2. The command must complete in under 10 seconds for a project with up to 4 detected languages.
3. Tool probing must not modify the project or install anything.
4. All public and module-level functions in `gates/doctor.py` must carry complete type annotations so the existing mypy gate passes without suppressions.

## Test Strategy

| Type        | Rationale                                                              |
|-------------|------------------------------------------------------------------------|
| Unit        | Language detection logic, registry lookup, tool-probe result parsing   |
| Integration | Full doctor run against a fixture project with known manifest files and mocked tool stubs |

## Acceptance Criteria

- Running `/doctor` on a Python project with ruff installed prints a table row with status token `found` and ruff's version string.
- Running `/doctor` on a project where mypy is absent shows status token `missing` with a `pip install mypy` install hint; `any_missing=True`.
- Running `/doctor` on a project with both pyproject.toml and package.json reports both Python and TypeScript tool tables.
- Running `/doctor` in a directory with no recognized manifests prints "no supported languages detected" and `any_missing=False`.
- Providing `project_root` pointing at a non-directory path returns an error before any tool probe is attempted.
- `project_root` parameter overrides CWD for manifest scanning.

## Open Questions

- None. Required tool lists per language can be inferred directly from the existing gate suite definitions.
