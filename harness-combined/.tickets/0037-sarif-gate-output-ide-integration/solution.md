# Solution

**Ticket**: 0037
**Title**: SARIF gate output and IDE integration

## Approach

Add a new `sarif.py` module that converts `list[GateResult]` to a SARIF 2.1.0 JSON document using stdlib only. Wire it into `gate_run_on_dir` via an `emit_sarif` parameter, and expose the opt-in in the `/gate` command via a `--sarif` flag and a `_standards.md` config key. The SARIF file is written atomically to `.harness/results.sarif` at the project root after each qualifying gate run.

## Components

| Component | Responsibility | Key interfaces |
|---|---|---|
| `sarif.py` | Convert `list[GateResult]` → SARIF 2.1.0 `SarifDocument` TypedDict; write atomically | `build_sarif(results: list[GateResult], worktree_root: str) -> SarifDocument`; `write_sarif(doc: SarifDocument, out_path: Path) -> bool` |
| `server.py` `gate_run_on_dir` | Accept `emit_sarif: bool = False`; call `write_sarif` after full run; treat write failure as non-fatal warning; include `"sarif_write_failed": true` in JSON response on failure | New optional param, no breaking change |
| `commands/gate.md` | Document `--sarif` flag and `_standards.md` opt-in; specify which `_standards.md` path is authoritative; must be written before integration tests | Prose/spec change |
| `tests/test_sarif.py` | Unit and integration tests for mapping logic, atomic write, and end-to-end gate invocation | Pytest |

## Tech Choices

| Choice | Rationale |
|---|---|
| Stdlib `json` + `pathlib` + `datetime` only | Zero new runtime deps; SARIF is plain JSON; `uuid` removed (no mandatory SARIF field requires it) |
| `TypedDict` with `total=False` for optional sub-structures | Structural SARIF contract is mypy-checkable; optional fields (`region`, `artifactLocation`) use `NotRequired` or `total=False` sub-TypedDicts |
| One `run` per gate tool with `tool.driver.name = GateResult.gate` | Matches SARIF semantics; enables per-tool rule lookup in IDEs |
| Tempfile in same directory as `out_path` (`NamedTemporaryFile(dir=out_path.parent)`) | Prevents cross-device rename failure in Docker/tmpfs environments |
| `write_sarif` creates `out_path.parent` via `mkdir(parents=True, exist_ok=True)` before tempfile | Handles first gate run on new project where `.harness/` does not yet exist |
| Atomic write (tempfile + rename); SARIF write failure is non-fatal | Catches `OSError` internally; logs via project logger; returns `False`; gate result JSON unchanged except for `sarif_write_failed` key |
| `artifactLocation.uri` as POSIX-relative path from `worktree_root` | Prevents absolute CI runner paths from appearing in SARIF uploaded to GitHub Code Scanning |
| `_standards.md` only read from `.tickets/` directory (harness root), never from scanned worktree | Project under analysis cannot enable SARIF emission; only harness operator config does |
| `_standards.md` key matched by `r'^\s*sarif_output\s*:\s*true\s*$'` (case-insensitive on `true`) | No PyYAML dep; Python-capitalized `True`/`yes`/`on` intentionally not matched |
| Bandit `LOW` severity → SARIF `note` (not `warning`) | Avoids inflating warning count; LOW findings are annotations, not actionable warnings |
| `sarif-tools` as dev/test dependency only | Automates AC-5 schema validation; not a runtime dep |
| Overwrite `results.sarif` each run | Consistent with `gate-findings.md` semantics; CI artifact retention handles history |

## Severity Mapping

`GateError.severity` (raw string from tool output) → SARIF `level`:

| Input (case-insensitive) | SARIF level |
|---|---|
| `error` | `error` |
| `warning`, `warn` | `warning` |
| `note`, `info`, `information` | `note` |
| `low` (bandit) | `note` |
| `medium` (bandit) | `warning` |
| `high` (bandit) | `error` |
| anything else | `warning` (fail-safe) |

## Path / Trust Boundary Rules

- **Relative path resolution**: if `GateError.file` is not absolute, resolve as `(Path(worktree_root) / file).resolve()`. If absolute, use `Path(file).resolve()`. Do NOT use `Path(file).resolve()` alone — that anchors to server cwd, not worktree.
- **Containment check**: `resolved_file.is_relative_to(Path(worktree_root).resolve())`. Failures → `artifactLocation` omitted (same as null-file); no absolute path fallback.
- **URI serialization**: `resolved_file.relative_to(worktree_root).as_posix()` — relative path only, never `file://` absolute URI.
- **`_standards.md` authority**: only `.tickets/_standards.md` in the harness project root; a `_standards.md` inside the scanned worktree has no authority to enable SARIF emission.

## `ruleId` Handling

- `GateError.code` non-null → `ruleId = code`.
- `GateError.code` is `None` → `ruleId` field omitted from the SARIF result entirely (SARIF 2.1.0 makes `ruleId` optional).

## Test Plan

| Requirement | Test Type   | Scenario(s)                                                                                             |
|-------------|-------------|---------------------------------------------------------------------------------------------------------|
| FR-1        | Unit        | `build_sarif` on fixture GateResults produces schema-valid SarifDocument                                |
| FR-4        | Unit        | GateError with file+line maps to correct `physicalLocation.region.startLine`                            |
| FR-4 URI    | Unit        | In-bounds file → `artifactLocation.uri` is a POSIX-relative path (not absolute)                        |
| FR-4 code   | Unit        | `GateError.code=None` → `ruleId` key absent from SARIF result                                          |
| FR-4 rel    | Unit        | Relative `GateError.file` resolved against `worktree_root`, not server cwd                             |
| FR-5        | Unit        | GateError with null file → result present, no `physicalLocation`                                        |
| FR-5 oob    | Unit        | GateError.file outside worktree_root → `artifactLocation` omitted, no absolute path in output          |
| FR-6        | Unit        | `tool.driver.name` equals `GateResult.gate`                                                             |
| Severity    | Unit        | Each severity-mapping row (including bandit LOW/MEDIUM/HIGH) maps to correct SARIF level                |
| FR-9 ok     | Unit        | `write_sarif` uses tempfile in `out_path.parent`; file appears atomically at final path                 |
| FR-9 xdev   | Unit        | Mock `os.rename` to raise `EXDEV` → `write_sarif` returns `False`, does not raise                      |
| FR-9 mkdir  | Unit        | `write_sarif` when `out_path.parent` does not exist → creates directory, writes file                    |
| FR-2        | Unit        | `_standards.md` with `sarif_output: true` → `emit_sarif=True`; missing/malformed/`True` → `False`      |
| FR-2 scope  | Unit        | `_standards.md` from worktree path ignored; only harness tickets dir is authoritative                   |
| FR-3        | Integration | `gate_run_on_dir(..., emit_sarif=False)` produces no `.sarif` file                                      |
| FR-10       | Integration | `gate_run_on_dir(..., emit_sarif=True)` creates `.harness/results.sarif` with valid content             |
| FR-10 fail  | Integration | `gate_run_on_dir(..., emit_sarif=True)` write failure → `sarif_write_failed: true` in JSON response     |
| FR-8        | Integration | `/gate XXXX --sarif` end-to-end: `results.sarif` present, `gate-findings.md` unchanged                  |
| AC-5        | Integration | `sarif-tools validate .harness/results.sarif` exits 0 on fixture output                                 |

## Tradeoffs

- **Chose relative URI over `file://` absolute**: prevents CI runner path leakage in uploaded SARIF; industry-standard SARIF emitters (e.g., ESLint SARIF plugin) use relative paths anchored to `uriBaseId`.
- **Chose `note` for bandit LOW over `warning`**: reduces alert fatigue; LOW findings are informational. Operators who disagree can reconfigure via severity mapping extension.
- **Chose omit-on-containment-failure over absolute fallback**: SARIF files are uploaded to external services; internal path leakage is a trust boundary violation.
- **Removed `uuid` / `automationDetails`**: field is optional; adding a non-deterministic UUID per call would break SARIF diffs in CI.
- **Accepting risk of**: SARIF schema evolution — SARIF 2.1.0 is the stable baseline.

## Risks

- **Cross-device rename**: mitigated by `NamedTemporaryFile(dir=out_path.parent)`.
- **Missing `.harness/` dir**: `write_sarif` calls `out_path.parent.mkdir(parents=True, exist_ok=True)` before tempfile creation.
- **Tool-relative paths anchored to wrong root**: mitigated by the explicit resolution formula `(Path(worktree_root) / file).resolve()` for non-absolute paths.
- **`_standards.md` format drift**: exact regex specified; `True`/`yes`/`on` intentionally excluded; documented in `gate.md`.
- **`write_sarif` failure masking gate success**: non-fatal; `gate_run_on_dir` adds `sarif_write_failed: true` to JSON on failure.

## Implementation Order

1. Write `sarif.py` with `SarifDocument` TypedDicts, `build_sarif`, `write_sarif`; full unit tests including path resolution, containment, URI format, null-code, severity mapping, atomic write, mkdir, EXDEV.
2. Update `commands/gate.md`: document `--sarif` flag, `_standards.md` opt-in regex, scope restriction, `sarif_write_failed` signal.
3. Extend `gate_run_on_dir` in `server.py` with `emit_sarif: bool = False`; add `sarif_write_failed` key on failure.
4. Add integration tests: `gate_run_on_dir emit_sarif=True`, write failure path, `/gate --sarif` end-to-end, `sarif-tools validate`.
