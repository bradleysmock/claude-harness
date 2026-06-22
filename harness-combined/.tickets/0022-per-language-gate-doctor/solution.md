# Solution

**Ticket**: 0022
**Title**: Per-language gate /doctor

## Approach

Add a `doctor` MCP tool to `server.py` backed by a new `gates/doctor.py` module. The module validates the `project_root` input path (resolve + containment check), scans for language manifests, looks up each detected language in a static tool registry built from per-gate-module `REQUIRED_TOOLS` exports, probes each tool via subprocess with a 5-second timeout, and assembles a structured `DoctorReport`. Formatting lives entirely in `gates/doctor.py` via `format_report(report) -> str`. The MCP tool in `server.py` returns a JSON dict `{"output": str, "any_missing": bool}` so Claude has a machine-readable signal for CI preflight use.

## Data Model

```python
from dataclasses import dataclass, field
from enum import Enum

class ToolStatus(Enum):
    FOUND = "found"
    FOUND_ERROR = "found (error)"   # on PATH, non-zero --version exit
    MISSING = "missing"
    TIMEOUT = "timeout"

@dataclass
class ToolResult:
    name: str
    status: ToolStatus
    version: str | None       # None when missing or timeout
    install_hint: str | None  # non-None only when status == MISSING

@dataclass
class LanguageReport:
    language: str             # e.g. "Python"
    manifest: str             # e.g. "pyproject.toml"
    tools: list[ToolResult] = field(default_factory=list)

@dataclass
class DoctorReport:
    languages: list[LanguageReport] = field(default_factory=list)
    any_missing: bool = False  # True if any required tool has status MISSING or TIMEOUT
```

## Components

| Component | Responsibility | Key Interfaces |
|---|---|---|
| `gates/python.py`, `typescript.py`, `go.py`, `rust.py` | Each exports `REQUIRED_TOOLS: list[str]` listing the tool names it invokes | Module-level constant |
| `gates/doctor.py` | Path validation, language detection, registry (built from `REQUIRED_TOOLS`), tool probing, `DoctorReport` assembly, `format_report`, `run_doctor` | `run_doctor(project_root: str) -> DoctorReport`; `format_report(report: DoctorReport) -> str` |
| `server.py` (new tool) | Thin MCP wrapper; calls `run_doctor` + `format_report`; returns `{"output": str, "any_missing": bool}` | `doctor(project_root: str = "") -> str` (JSON-encoded dict) |
| `commands/doctor.md` | Slash-command spec: default CWD, `project_root` parameter, machine-readable `any_missing` field | Plain markdown |
| `tests/test_doctor.py` | Unit + integration tests written before production code | pytest |

## Tech Choices

| Choice | Rationale |
|---|---|
| `Path(project_root).resolve()` + `is_dir()` + `relative_to(allowed_root)` containment | Validates external input at the trust boundary: rejects non-directories and paths that escape the declared workspace root. `allowed_root` defaults to `/` but is configurable; the MCP server's own `project_root` parameter from existing tools does not implement containment — this tool will be the first to do so, establishing the pattern. |
| `REQUIRED_TOOLS: list[str]` exported from each gate module | Single source of truth for which tools each language gate needs; eliminates knowledge duplication between gate modules and doctor registry; makes drift testable: a CI test can verify each name in `REQUIRED_TOOLS` for a language appears in that module's subprocess invocations as a structured check (not just string grep). |
| `shutil.which` fast-path then `subprocess.run([tool, "--version"], capture_output=True, text=True, timeout=5)` | Avoids subprocess launch for missing tools. Checks `stdout or stderr` for version. `FileNotFoundError` at execution → `MISSING`. Non-zero exit with output → `FOUND_ERROR`. `TimeoutExpired` → `TIMEOUT`. |
| Formatting in `gates/doctor.py` via `format_report(report: DoctorReport) -> str` | Formatting testable without MCP layer; `server.py` remains a thin wrapper. |
| MCP tool returns `dict {"output": str, "any_missing": bool}` JSON-serialized | Gives Claude a machine-readable `any_missing` signal for CI preflight, not prose-parsing. |
| Default `project_root = ""` → resolved to CWD by `run_doctor` when blank | Allows `/doctor` with no arguments; explicit parameter overrides CWD. |
| All public and module-level functions in `gates/doctor.py` carry full type annotations | Consistent with existing gate modules; required so mypy gate passes without suppressions. |

## Test Plan

Tests are written before production code (TDD). `REQUIRED_TOOLS` exports are written first (step 1) so tests can import authoritative constants.

| Requirement | Test Type   | Scenario(s)                                                                                            |
|-------------|-------------|--------------------------------------------------------------------------------------------------------|
| FR-1        | Unit        | Detect Python from `pyproject.toml`; detect TS from `package.json`; detect both; no manifests → empty |
| FR-2        | Unit        | Registry built from `REQUIRED_TOOLS` imports matches expected tool list per language |
| FR-3        | Unit        | `which` miss → `MISSING`; `which` hit + exit 0 + stdout → `FOUND + version`; `which` hit + exit 0 + stderr only → `FOUND + version`; `which` hit + non-zero exit + output → `FOUND_ERROR`; `which` hit + `FileNotFoundError` from subprocess → `MISSING`; `TimeoutExpired` → `TIMEOUT` |
| FR-4        | Integration | `run_doctor` on fixture dir produces table rows with tokens `found`, `missing`, `found (error)` |
| FR-5        | Unit        | Missing required tool produces non-empty `install_hint` string |
| FR-6        | Integration | `any_missing=True` when required tool absent; `any_missing=False` when all present |
| FR-7        | Unit        | `run_doctor(project_root="/tmp/fixture")` scans that directory, not CWD |
| FR-8        | Unit        | No manifests → empty `languages` list, `any_missing=False`, output contains "no supported languages detected" |
| FR-8a       | Unit        | Non-directory `project_root` → structured error returned before any subprocess call; `project_root` outside allowed_root → same |
| REQUIRED_TOOLS CI invariant | Unit | For each language, every name in `REQUIRED_TOOLS` appears in that gate module's subprocess argument list (structural check via AST or import, not string grep) |

## Tradeoffs

- **Chose `REQUIRED_TOOLS` constants over dynamic gate introspection**: gate modules don't expose a machine-readable tool list; parsing their source would be fragile. Explicit exports are authoritative and testable via AST-based CI check.
- **MCP tool returns JSON dict**: deviates from the convention of existing tools returning plain strings. Rationale: machine-readable `any_missing` is a first-class success criterion; prose-parsing by Claude is not reliable for CI use.
- **Accepting risk of**: `allowed_root` defaulting to `/` makes containment vacuous in practice until the harness defines a workspace root convention. Mitigation: document the open question as an explicit follow-on; the `is_dir()` check still rejects non-existent paths and the `resolve()` step prevents `..` injection.

## Risks

- `REQUIRED_TOOLS` drift if a gate module is updated without updating its constant. Mitigation: AST-based CI test (see test plan).
- Version string capture may be empty for tools that produce no output on `--version` (unusual). Mitigation: treat empty output as `version=None`; does not affect `FOUND` status.
- `project_root` is external input. Mitigation: resolve + `is_dir()` + `relative_to(allowed_root)` before all operations.

## Implementation Order

1. Add `REQUIRED_TOOLS: list[str]` exports to `gates/python.py`, `gates/typescript.py`, `gates/go.py`, `gates/rust.py`. These are prerequisite imports for both the tests and `gates/doctor.py`.
2. `tests/test_doctor.py` — write all unit and integration tests (including path validation and the `REQUIRED_TOOLS` CI invariant). All tests run red until step 3.
3. `gates/doctor.py` — path validator, language detector, registry builder, tool prober, `DoctorReport` assembler, `format_report`, `run_doctor`.
4. `server.py` — add `@mcp.tool() def doctor(project_root: str = "") -> str` returning JSON-encoded `{"output": ..., "any_missing": ...}`.
5. `commands/doctor.md` — slash-command spec with default CWD behavior, `project_root` parameter, and `any_missing` field documentation.
