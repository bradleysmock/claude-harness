# Solution

**Ticket**: 0017
**Title**: Multi-language polyglot gate

## Approach

The existing `_detect_stacks` and polyglot aggregation in `gate_run_on_dir` already form the detection and execution backbone. This ticket completes the feature: (1) extend `gate-findings.md` format and `/gate` summary line to be multi-language-aware, (2) add a `_standards.md` gate-command override parser with trust-boundary enforcement and fail-closed error handling, (3) wire overrides into each language gate suite's directory-mode entry points, and (4) harden manifest scanning against symlink traversal and inconsistent depth behavior across languages.

## Components

| Component | Responsibility | Key Interfaces |
|---|---|---|
| `StackName` (StrEnum in `models.py`) | Canonical vocabulary for language names alongside `GateResult`/`GateError` | `StackName.PYTHON`, `.TYPESCRIPT`, `.GO`, `.RUST` |
| `LanguageResult` (dataclass in `models.py`) | Typed wrapper around `list[GateResult]` tagged with language | `LanguageResult(language: StackName, results: list[GateResult])` |
| `server._detect_stacks` | Uniform one-level manifest scan for all four stacks with symlink containment; replaces current inconsistent mix of `rglob`/`glob("*/"...)`/root-only | Returns `list[StackName]`; every subdir resolves via `Path.resolve()` + `relative_to(project_root)`; symlinks escaping root are skipped |
| `gates.config` (new module) | Parse `[gates]` fenced shell-quoted key-value block from `_standards.md`; validate; return overrides or raise `ConfigError` | `load_gate_overrides(standards_path: Path) -> dict[str, dict[str, list[str]]]`; uses `shlex.split` for value-to-argv; raises `ConfigError` on malformed input or validation failure |
| `gates.python/typescript/go/rust` | Accept `overrides: dict[str, list[str]] \| None = None` in `run_*_suite_on_dir`; return `LanguageResult` | `run_*_suite_on_dir(directory, fail_fast, overrides=None) -> LanguageResult` |
| `gates.__init__.run_suite_on_dir` | Accept `language: StackName \| str` (StrEnum backward compat); return `LanguageResult` | Updated signature; `run_suite_for` (text mode) is explicitly out of scope |
| `_format_polyglot_findings(results: list[LanguageResult], directory: str) -> str` (in `server.py`) | Pure function: formats aggregated multi-language results as `gate-findings.md` markdown; headings are `## {language} / {gate_name}` | Independently unit-testable; pinned heading format used by critic |
| `server.gate_run_on_dir` | Load overrides, run `_detect_stacks`, run suites, aggregate via `_format_polyglot_findings`; surface `CONFIG_ERROR` finding on parse failure | Fail-closed: `CONFIG_ERROR` exits non-zero |
| `commands/gate.md` | Update `**Language detected**` → `**Languages detected**`; multi-language summary line | Markdown template update |
| `context/critic-brief.md` | Update heading pattern note to reflect `## {language} / {gate_name}` format | Ensures critic correctly reads language-tagged sections |

## Tech Choices

| Choice | Rationale |
|--------|-----------|
| `StackName` / `LanguageResult` in `models.py` | Domain types belong with `GateResult`/`GateError`; avoids circular import between `server.py` and `gates/__init__.py`; consistent with existing architecture |
| Shell-quoted override format (not TOML) | Format name matches implementation (`shlex.split`); operators familiar with shell quoting; avoids requiring `tomllib` or a TOML fenced block parser |
| `shlex.split()` for override text-to-argv | Correctly handles quoted args (e.g., `--python-version "3.11"`); `ValueError` on unmatched quote is caught and re-raised as `ConfigError` |
| Fail-closed on `CONFIG_ERROR` | A misconfigured override that silently falls back to defaults hides operator mistakes; fail loudly so misconfiguration is immediately visible |
| Uniform one-level manifest scan in `_detect_stacks` | Current code has inconsistent depth (Python `rglob`, TS/Rust one-level glob, Go root-only); FR-1 requires uniform root + one-level-deep; rewrite to consistent policy |
| Sequential language execution | Avoids interleaved output and tmp-dir collisions; acceptable because gate runs are already serial |

## Trust Boundary

`_standards.md` is **operator-trusted** (lead-authored, committed to git, repo-access-controlled). The argv list passed to `subprocess.run()` is safe by construction — shell metacharacters in argument values are inert. The arg[0] check is defense-in-depth against accidental `shell=True` regressions: arg[0] must not contain `/`, `..`, or `` | ; & > < $ ` ( ) { } \ ! ``. Maximum 32 arguments per override. Parse errors or validation failures raise `ConfigError` → `CONFIG_ERROR` gate finding → fail-closed (no silent fallback to defaults).

## Test Plan

| Requirement | Test Type   | Scenario(s) |
|-------------|-------------|-------------|
| FR-1        | Unit        | `_detect_stacks`: root manifests, subdir manifests (1 level), manifest 2 levels deep NOT detected; symlink outside root skipped |
| FR-1        | Unit        | `_detect_stacks`: no manifest files → empty list; Python detection does NOT use `rglob` fallback |
| FR-2        | Integration | `gate_run_on_dir("auto", ...)` on tmp dir with `pyproject.toml` + `package.json`; both `StackName` values in response |
| FR-3        | Unit        | `_format_polyglot_findings([LanguageResult(python,...), LanguageResult(typescript,...)])`: headings are `## python / lint`; header is `**Languages detected**: python, typescript` |
| FR-3        | Unit        | `_format_polyglot_findings` on single-language result: heading is `## lint` (no language prefix); no `**Languages detected**` plural header |
| FR-4        | Integration | Python all-pass + TypeScript lint fail → `"passed": false` in aggregated JSON |
| FR-5        | Unit        | `load_gate_overrides`: valid (quoted arg OK); missing block → `{}`; malformed/empty/too-many-args/path-in-arg0/backtick-in-arg0 → `ConfigError` each |
| FR-5        | Integration | Override in `_standards.md` replaces default command; mocked `subprocess.run` receives override argv |
| FR-6, FR-7  | Unit        | Multi-language findings: `**Languages detected**` header present; summary line `gate: python=PASS typescript=FAIL: lint` |
| FR-8        | Unit        | Explicit `language="python"` returns same JSON shape as pre-polyglot baseline |
| FR-8        | Integration | `language="auto"` on single-stack repo: single-language-format output (no plural header) |
| Zero-stacks | Unit        | `language="auto"` on directory with no manifest files: falls back to `_detect_language`; behavior is defined and documented |
| FR-9        | Integration | Two-language tmp dir, one toolchain absent: both language sections in output; missing section has `TOOL_ERROR`; run exits non-zero |
| CONFIG_ERROR| Unit        | Malformed `[gates]` block → `gate_run_on_dir` returns `"passed": false` with `CONFIG_ERROR` finding; does not fall back to defaults |

## Tradeoffs

- **Chose shell-quoted format over TOML for `_standards.md` overrides**: format name now matches implementation; eliminates the TOML/shlex naming confusion. Accepting: operators must use shell quoting, not TOML quoting.
- **Chose fail-closed on config parse errors**: operator must fix `_standards.md` before gates pass; misconfiguration is never silent.
- **Chose `LanguageResult` + `StackName` in `models.py`**: consistent with domain-type location, avoids circular import risk. Accepting: `models.py` gains two new types.
- **Chose uniform one-level scan**: eliminates current inconsistency (`rglob` for Python, one-level for TS/Rust, root-only for Go). Accepting: Python `*.py` files two levels deep no longer trigger detection (operators should use `pyproject.toml`).

## Risks

- `shlex.split` `ValueError` on unmatched quotes must be caught in `load_gate_overrides` — if uncaught, it aborts the gate run with an unstructured exception rather than a `CONFIG_ERROR` finding.
- Uniform one-level scan removes the Python `rglob("*.py")` fallback — repos with only raw `.py` files (no `pyproject.toml`) at the root will no longer auto-detect. Document this as a breaking change in the implementation PR.
- Integration tests spawning real lint tools are slow and brittle without toolchains installed; gate behind `pytest.mark.integration`.
- Critic-brief heading pattern update (Step 8) must ship in the same commit as the `_format_polyglot_findings` change.

## Implementation Order

1. Add `StackName` StrEnum and `LanguageResult` dataclass to `models.py`. Update `run_suite_on_dir` in `gates/__init__.py` to accept `StackName | str` and return `LanguageResult`. Tests first.
2. Add `gates/config.py` with `load_gate_overrides` + `ConfigError`; unit tests covering valid, malformed, missing-block, adversarial (path traversal, backtick, too-many-args, unmatched-quote). Tests first.
3. Rewrite `_detect_stacks` in `server.py` as uniform one-level scan with symlink containment; unit tests for all four stacks + symlink + no-manifest + 2-levels-deep NOT detected.
4. Update `run_*_suite_on_dir` in `gates/python.py`, `gates/typescript.py`, `gates/go.py`, `gates/rust.py` to accept `overrides=None` and return `LanguageResult`. Tests first.
5. Add `_format_polyglot_findings` to `server.py`; unit tests pinning `## {language} / {gate_name}` heading format and single-language passthrough.
6. Update `gate_run_on_dir` in `server.py`: load overrides, detect stacks, run suites, aggregate, surface `CONFIG_ERROR`.
7. Update `commands/gate.md`: `**Languages detected**` header; multi-language summary line.
8. Update `context/critic-brief.md`: note `## {language} / {gate_name}` heading format for `gate-findings.md` sections.
9. Integration tests in `tests/test_gate_runner_polyglot.py`: FR-2, FR-4, FR-8, FR-9, zero-stacks, CONFIG_ERROR.
