from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gates._baseline as _bl
from gates import (
    GateTimeoutConfig,
    ProcessResult,
    _timeout_error,
    append_tool_error_if_silent,
    find_config_root,
    run_dir_gates_scheduled,
)
from gates._scope import GateSpec, has_scope_match
from models import GateError, GateResult

# Tools this gate invokes via subprocess (see gates/python.py REQUIRED_TOOLS for
# the doctor contract). Every name must appear in a subprocess argument list.
REQUIRED_TOOLS: list[str] = ["tsc", "eslint"]

# ── Text-mode toolchain pins ───────────────────────────────────────────────────
# Current stable TypeScript compile target for generated code. Raised from ES2020
# so code using post-ES2020 language features (e.g. .at(), Error cause, top-level
# await targets) type-checks. Review cadence: revisit each January against the
# current TypeScript stable release; host-project tsconfig values override these
# (see host_ts_values). ``module`` stays commonjs for ts-jest compatibility.
TS_TARGET = "ES2022"
TS_MODULE = "commonjs"


def _build_tsconfig(target: str, module: str) -> str:
    """Render the text-mode tsconfig JSON for a given target/module pair."""
    return json.dumps({
        "compilerOptions": {
            "target": target,
            "module": module,
            "lib": [target],
            "strict": True,
            "esModuleInterop": True,
            "skipLibCheck": True,
            "outDir": "./dist",
            "rootDir": ".",
            "ignoreDeprecations": "6.0",
        },
        "include": ["./*.ts"],
        "exclude": ["node_modules", "dist"],
    }, indent=2)


_TSCONFIG = _build_tsconfig(TS_TARGET, TS_MODULE)

# ESLint v9+ flat config (ESM). Replaces the removed legacy .eslintrc.json form so
# text-mode lint runs on a current ESLint without --no-eslintrc (which v9 deleted).
# Auto-discovered by eslint when written as eslint.config.mjs in the run cwd.
_ESLINT_FLAT_CONFIG = """\
import tsParser from '@typescript-eslint/parser';
import tsPlugin from '@typescript-eslint/eslint-plugin';

export default [
  {
    files: ['**/*.ts', '**/*.tsx'],
    languageOptions: {
      parser: tsParser,
      ecmaVersion: 2022,
      sourceType: 'module',
    },
    plugins: { '@typescript-eslint': tsPlugin },
    rules: {
      'no-console': 'warn',
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/explicit-function-return-type': 'off',
    },
  },
];
"""

_JEST_CONFIG = json.dumps({
    "preset": "ts-jest",
    "testEnvironment": "node",
    "testMatch": ["**/*.test.ts"],
    "moduleFileExtensions": ["ts", "js"],
}, indent=2)

_PACKAGE_JSON = json.dumps({
    "name": "harness-temp",
    "version": "0.0.1",
    "private": True,
    "scripts": {"test": "jest", "lint": "eslint ."},
    "devDependencies": {
        "typescript": "*", "ts-jest": "*", "jest": "*", "@types/jest": "*",
        "eslint": "*", "@typescript-eslint/parser": "*",
        "@typescript-eslint/eslint-plugin": "*",
    },
}, indent=2)


@dataclass
class TypeScriptEnv:
    root: Path
    impl_file: Path
    test_file: Path


def host_ts_values(project_root: str | Path) -> dict[str, str]:
    """Read ``compilerOptions.target``/``module`` from a host ``tsconfig.json``.

    Returns a dict with whichever of ``target``/``module`` the host project defines
    (empty when there is no host tsconfig.json or it defines neither). Text mode
    prefers these host values over the ``TS_TARGET``/``TS_MODULE`` constants so
    generated code is checked against the project's own compile settings (FR-5). A
    missing, unreadable, or malformed tsconfig degrades to an empty dict.
    """
    path = Path(project_root) / "tsconfig.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    opts = data.get("compilerOptions") if isinstance(data, dict) else None
    if not isinstance(opts, dict):
        return {}
    out: dict[str, str] = {}
    for key in ("target", "module"):
        value = opts.get(key)
        if isinstance(value, str) and value:
            out[key] = value
    return out


def _make_env(implementation: str, tests: str, project_root: str) -> TypeScriptEnv:
    tmpdir = Path(tempfile.mkdtemp(prefix="harness_ts_"))
    host = host_ts_values(project_root)
    target = host.get("target", TS_TARGET)
    module = host.get("module", TS_MODULE)
    (tmpdir / "tsconfig.json").write_text(_build_tsconfig(target, module))
    (tmpdir / "eslint.config.mjs").write_text(_ESLINT_FLAT_CONFIG)
    (tmpdir / "jest.config.json").write_text(_JEST_CONFIG)
    (tmpdir / "package.json").write_text(_PACKAGE_JSON)

    project_nm = Path(project_root) / "node_modules"
    tmp_nm = tmpdir / "node_modules"
    if project_nm.exists() and not tmp_nm.exists():
        tmp_nm.symlink_to(project_nm.resolve())

    impl = tmpdir / "implementation.ts"
    test = tmpdir / "implementation.test.ts"
    impl.write_text(implementation, encoding="utf-8")

    test_content = tests
    if "from './implementation'" not in test_content and 'from "./implementation"' not in test_content:
        test_content = "import * as impl from './implementation';\n\n" + test_content
    test.write_text(test_content, encoding="utf-8")

    return TypeScriptEnv(root=tmpdir, impl_file=impl, test_file=test)


def _exec(command: list[str], cwd: str | Path, timeout: int = 60) -> ProcessResult:
    p = subprocess.run(
        command, capture_output=True, text=True,
        cwd=str(cwd), timeout=timeout,
    )
    return ProcessResult(p.stdout, p.stderr, p.returncode)


def _rel(path: str, root: Path) -> str:
    try:
        return str(Path(path).relative_to(root))
    except ValueError:
        return path


_TSC_PATTERN = re.compile(
    r"^(?P<file>[^(]+)\((?P<line>\d+),(?P<col>\d+)\):\s*"
    r"(?P<severity>error|warning)\s+(?P<code>TS\d+):\s*(?P<msg>.+)$"
)


def _parse_tsc_errors(output: str, root: Path) -> list[GateError]:
    errors = []
    for line in output.splitlines():
        m = _TSC_PATTERN.match(line.strip())
        if not m:
            continue
        errors.append(GateError(
            message=m.group("msg").strip(),
            file=_rel(m.group("file"), root),
            line=int(m.group("line")), column=int(m.group("col")),
            code=m.group("code"), severity=m.group("severity"),
        ))
    return errors


def _parse_eslint_json(stdout: str, root: Path) -> list[GateError]:
    errors = []
    try:
        lint_results: list[Any] = json.loads(stdout or "[]")
        for file_result in lint_results:
            for msg in file_result.get("messages", []):
                sev = "error" if msg.get("severity", 1) == 2 else "warning"
                errors.append(GateError(
                    message=msg.get("message", ""),
                    file=_rel(file_result.get("filePath", ""), root),
                    line=msg.get("line"), column=msg.get("column"),
                    code=msg.get("ruleId"), severity=sev,
                ))
    except json.JSONDecodeError:
        pass
    return errors


# ── Text mode gates ───────────────────────────────────────────────────────────

def _type_check_gate_text(env: TypeScriptEnv, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("typecheck", 60) if config else 60
    try:
        result = _exec(["npx", "--yes", "tsc", "--noEmit", "--pretty", "false"], env.root, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("type_check", timeout)
    errors = _parse_tsc_errors(result.output, env.root)
    return GateResult(
        gate="type_check",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def _lint_gate_text(env: TypeScriptEnv, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("lint", 60) if config else 60
    try:
        # ESLint v9+: no --no-eslintrc (removed) and no legacy --config path. The
        # flat eslint.config.mjs written into env.root is auto-discovered from cwd.
        result = _exec([
            "npx", "--yes", "eslint",
            str(env.impl_file),
            "--format", "json",
        ], env.root, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("lint", timeout)
    errors = _parse_eslint_json(result.stdout, env.root)
    return GateResult(
        gate="lint",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def _test_gate_text(env: TypeScriptEnv, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("test", 120) if config else 120
    try:
        result = _exec([
            "npx", "--yes", "jest",
            "--no-coverage",
            "--testPathPattern", "implementation.test.ts",
            "--config", str(env.root / "jest.config.json"),
        ], env.root, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("test", timeout)
    if result.returncode == 0:
        return GateResult(gate="test", passed=True, errors=[],
                          duration_ms=int((time.monotonic() - start) * 1000))
    errors = []
    current_test: str | None = None
    fail_lines: list[str] = []
    for line in result.output.splitlines():
        if line.strip().startswith("●"):
            if current_test and fail_lines:
                errors.append(GateError(
                    message=f"{current_test}: {' | '.join(fail_lines[:3])}",
                    file="implementation.test.ts", line=None, column=None,
                    code="TEST_FAILURE", severity="error",
                ))
            current_test = line.strip().lstrip("●").strip()
            fail_lines = []
        elif current_test and ("expect(" in line or "Expected" in line or "Received" in line):
            fail_lines.append(line.strip())
    if current_test and fail_lines:
        errors.append(GateError(
            message=f"{current_test}: {' | '.join(fail_lines[:3])}",
            file="implementation.test.ts", line=None, column=None,
            code="TEST_FAILURE", severity="error",
        ))
    if not errors:
        errors.append(GateError(
            message=result.output[:600], file="implementation.test.ts",
            line=None, column=None, code="TEST_FAILURE", severity="error",
        ))
    return GateResult(gate="test", passed=False, errors=errors,
                      duration_ms=int((time.monotonic() - start) * 1000))


def run_typescript_suite(
    implementation: str, tests: str, project_root: str,
    config: GateTimeoutConfig | None = None,
) -> list[GateResult]:
    """Text mode: type_check → lint → tests (temp dir)."""
    env = _make_env(implementation, tests, project_root)
    results = []
    try:
        for gate_fn in [_type_check_gate_text, _lint_gate_text, _test_gate_text]:
            result = gate_fn(env, config)
            results.append(result)
            if not result.passed:
                return results
    finally:
        shutil.rmtree(env.root, ignore_errors=True)
    return results


# ── Directory mode gates ──────────────────────────────────────────────────────

_TSCONFIG_NAMES = ("tsconfig.json",)
# ESLint v9+ flat config filenames (project config wins; no --ext, which v9 removed).
_ESLINT_FLAT_NAMES = (
    "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", "eslint.config.ts",
)
# Pre-v9 legacy config filenames (still linted with the --ext invocation).
_ESLINT_LEGACY_NAMES = (
    ".eslintrc.json", ".eslintrc.js", ".eslintrc.cjs",
    ".eslintrc.yml", ".eslintrc.yaml", ".eslintrc",
)
_ESLINT_CONFIG_NAMES = _ESLINT_FLAT_NAMES + _ESLINT_LEGACY_NAMES


def eslint_config_kind(root: Path) -> str:
    """Classify the ESLint config in *root*: 'flat', 'legacy', or 'none'.

    Flat config (eslint.config.*) is preferred over legacy (.eslintrc*) when both are
    present — flat is what ESLint v9 uses by default, so it reflects the active config.
    """
    if any((root / n).exists() for n in _ESLINT_FLAT_NAMES):
        return "flat"
    if any((root / n).exists() for n in _ESLINT_LEGACY_NAMES):
        return "legacy"
    return "none"


def _eslint_dir_argv(root: Path) -> list[str]:
    """Directory-mode eslint argv, keyed on the config kind found in *root*.

    ESLint v9 removed ``--ext``; passing it on a flat-config (or config-less v9)
    project makes eslint exit as a TOOL_ERROR. So ``--ext .ts,.tsx`` is appended ONLY
    for legacy-config projects, where the flag is still required to widen the default
    file set. Flat/none projects rely on the config's own ``files`` globs.
    """
    argv = ["npx", "--yes", "eslint", ".", "--format", "json"]
    if eslint_config_kind(root) == "legacy":
        argv += ["--ext", ".ts,.tsx"]
    return argv
_JEST_CONFIG_NAMES = (
    "jest.config.js", "jest.config.cjs", "jest.config.mjs",
    "jest.config.ts", "jest.config.json",
)


def _changed_test_files(jest_root: Path, base: str = "main") -> list[str] | None:
    """Test files changed vs the merge-base with ``base``, relative to ``jest_root``.

    Returns a list of changed ``*.test.ts(x)`` paths, or ``None`` when scoping
    cannot be determined (git missing, not a repo, base unknown).

    As of ticket 0041 this helper no longer gates pass/fail — the directory-mode
    test gate runs the full suite and uses baseline-delta comparison instead
    (scoping let a change that broke an *untouched* test pass). It is retained only
    for callers/tests that inspect the changed-test set directly.
    """
    if shutil.which("git") is None:
        return None
    try:
        mb = subprocess.run(
            ["git", "-C", str(jest_root), "merge-base", "HEAD", base],
            capture_output=True, text=True, timeout=30,
        )
        ref = mb.stdout.strip() if mb.returncode == 0 and mb.stdout.strip() else base
        diff = subprocess.run(
            ["git", "-C", str(jest_root), "diff", "--name-only", ref],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if diff.returncode != 0:
        return None
    return [
        line.strip() for line in diff.stdout.splitlines()
        if line.strip().endswith((".test.ts", ".test.tsx"))
    ]


def _type_check_gate_dir(directory: str, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    root = find_config_root(Path(directory), _TSCONFIG_NAMES)
    timeout = config.timeout_for("typecheck", 60) if config else 60
    try:
        result = _exec(["npx", "--yes", "tsc", "--noEmit", "--pretty", "false"], root, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("type_check", timeout)
    errors = _parse_tsc_errors(result.output, root)
    append_tool_error_if_silent(errors, result.returncode, result.output)
    return GateResult(
        gate="type_check",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def _lint_gate_dir(directory: str, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    root = find_config_root(Path(directory), _ESLINT_CONFIG_NAMES)
    timeout = config.timeout_for("lint", 60) if config else 60
    try:
        result = _exec(_eslint_dir_argv(root), root, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("lint", timeout)
    errors = _parse_eslint_json(result.stdout, root)
    append_tool_error_if_silent(errors, result.returncode, result.output)
    return GateResult(
        gate="lint",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


# ── Directory-mode test gate: full run + baseline-delta (ticket 0041) ──────────
#
# The gate runs the *entire* Jest suite and fails only on failures that are not
# already present at the merge base. Changed-file scoping (``_changed_test_files``,
# retained above for its own contract test) no longer gates pass/fail — a change
# that breaks an untouched test must fail the gate, which scoping silently allowed.
#
# As of the baseline-delta follow-up the SHA cache, merge-base resolution, detached
# worktree runner and delta math live in ``gates/_baseline.py`` (shared with Python /
# Go / Rust). This module keeps only the jest-specific run/parse seams and thin
# wrappers so behaviour — and every 0041 test seam — is preserved byte-for-byte.


def _run_jest_json_dir(root: Path, timeout: int) -> ProcessResult:
    """Run the full Jest suite in ``root`` with machine-readable JSON on stdout."""
    return _exec(["npx", "--yes", "jest", "--no-coverage", "--json"], root, timeout=timeout)


def _first_line(text: str) -> str:
    stripped = (text or "").strip()
    return stripped.splitlines()[0].strip() if stripped else ""


def _test_id(rel_file: str, assertion: dict[str, Any]) -> str:
    """Stable, run-independent identifier for one Jest assertion.

    ``<file relative to the config root>::<fullName>`` — the ``::`` separator lets
    the flakiness detector split path from test name (see ``flaky_detect``), and the
    config-root-relative path makes the id identical between the HEAD run and the
    merge-base baseline run (which happen in different temp directories).
    """
    full = assertion.get("fullName") or " ".join(
        (assertion.get("ancestorTitles") or []) + [assertion.get("title", "")]
    ).strip()
    return f"{rel_file}::{full}"


def _parse_jest_json(stdout: str, root: Path) -> tuple[bool, dict[str, GateError]]:
    """Parse ``jest --json`` stdout into ``(parsed_ok, {test_id: GateError})``.

    ``parsed_ok`` is False when ``stdout`` is not a Jest JSON report (crash, config
    error, empty output) so the caller can fall back to exit-code strictness. Only
    failed assertions produce entries.
    """
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return False, {}
    if not isinstance(data, dict) or "testResults" not in data:
        return False, {}
    failures: dict[str, GateError] = {}
    for file_result in data.get("testResults") or []:
        name = file_result.get("name") or ""
        rel = _rel(name, root) if name else "?"
        for a in file_result.get("assertionResults") or []:
            if a.get("status") != "failed":
                continue
            tid = _test_id(rel, a)
            msgs = a.get("failureMessages") or []
            detail = _first_line(msgs[0]) if msgs else (a.get("fullName") or a.get("title") or "")
            failures[tid] = GateError(
                message=f"{tid}: {detail}"[:600],
                file=rel, line=None, column=None,
                code="TEST_FAILURE", severity="error",
            )
    return True, failures


# ── Merge-base baseline: compute, cache, invalidate ────────────────────────────
#
# These are thin jest-specific adapters over ``gates/_baseline.py``. They stay as
# module-level names with unchanged signatures because ticket 0041's tests
# monkeypatch them as seams (``_merge_base_sha``, ``_compute_baseline_at``,
# ``_baseline``) and assert on the SHA-keyed cache layout they produce.

def _merge_base_sha(jest_root: Path, base: str) -> str | None:
    """Merge-base SHA between HEAD and ``base``, or None when it cannot be resolved."""
    return _bl.merge_base_sha(jest_root, base)


def _compute_baseline_at(jest_root: Path, sha: str, timeout: int) -> set[str] | None:
    """Run the full jest suite at ``sha`` in a throwaway detached worktree.

    Never touches the ticket worktree (see
    :func:`gates._baseline.run_in_detached_baseline_worktree`). Returns the
    failing-test-ID set, or None when the baseline run cannot be established
    (worktree add fails, jest emits no parseable JSON, timeout, …) so the caller
    falls back to full-suite strictness.
    """
    def _prepare(src_root: Path, base_root: Path) -> None:
        # A fresh checkout has no ``node_modules`` (git-ignored), so ``npx jest``
        # there cannot resolve the project's jest/ts-jest deps — it errors before
        # emitting a JSON report, which would silently force permanent strict mode
        # and defeat the baseline entirely. Mirror the text-mode env (_make_env) by
        # symlinking the HEAD checkout's already-installed deps into the base run.
        src_nm = src_root / "node_modules"
        base_nm = base_root / "node_modules"
        if src_nm.exists() and not base_nm.exists():
            try:
                base_nm.symlink_to(src_nm.resolve())
            except OSError:
                pass  # best effort — a missing symlink degrades to strict, never crashes

    def _run(base_root: Path) -> set[str] | None:
        result = _run_jest_json_dir(base_root, timeout)
        ok, failures = _parse_jest_json(result.stdout, base_root)
        return set(failures) if ok else None

    return _bl.run_in_detached_baseline_worktree(
        jest_root, sha, _run, prepare=_prepare, tmp_prefix="harness_ts_baseline_",
    )


def _baseline(jest_root: Path, base: str = "main", timeout: int = 180) -> set[str] | None:
    """Failing-test-ID set at the merge base with ``base``; None → run strict.

    Cached per merge-base SHA under ``jest_root/.harness/test-baselines/`` so the
    expensive baseline run happens at most once per SHA across a repair loop
    (NFR-1). Returns None — the "fall back to full-suite strictness" signal — when
    git is absent, the merge base is unknown, the cache for the SHA is dirty
    (present but corrupt), or the baseline run itself fails. ``_merge_base_sha`` and
    ``_compute_baseline_at`` are resolved as module globals so 0041's monkeypatches
    on those seams take effect.
    """
    return _bl.load_baseline(
        jest_root, base, timeout,
        merge_base_fn=_merge_base_sha,
        compute_fn=_compute_baseline_at,
        read_cache=_bl.read_failing_cache,
        write_cache=_bl.write_failing_cache,
    )


def _unparsed_test_result(result: ProcessResult, start: float) -> GateResult:
    """Strict fallback when Jest emitted no parseable JSON (crash / config error)."""
    dur = int((time.monotonic() - start) * 1000)
    if result.returncode == 0:
        return GateResult(gate="test", passed=True, errors=[], duration_ms=dur, mode="full")
    err = GateError(
        message=(result.output[:600] or "jest produced no parseable output"),
        file=None, line=None, column=None, code="TEST_FAILURE", severity="error",
    )
    return GateResult(gate="test", passed=False, errors=[err], duration_ms=dur, mode="full")


def _test_gate_dir(directory: str, config: GateTimeoutConfig | None = None) -> GateResult:
    """Directory-mode Jest gate: full suite run + baseline-delta comparison (0041).

    Runs the *entire* suite (no changed-file scoping), then fails only on failures
    absent from the cached merge-base baseline. When the baseline is unavailable the
    gate falls back to full-suite strictness: every failure fails. The ``GateResult``
    reports which ``mode`` ran and enumerates any ``baseline_excluded`` failures.
    """
    start = time.monotonic()
    root = find_config_root(Path(directory), _JEST_CONFIG_NAMES)
    timeout = config.timeout_for("test", 180) if config else 180
    try:
        result = _run_jest_json_dir(root, timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("test", timeout)

    ok, failures = _parse_jest_json(result.stdout, root)
    if not ok:
        return _unparsed_test_result(result, start)

    def _finish(passed: bool, errors: list[GateError], mode: str, excluded: list[str]) -> GateResult:
        return GateResult(
            gate="test", passed=passed, errors=errors,
            duration_ms=int((time.monotonic() - start) * 1000),
            mode=mode, baseline_excluded=excluded,
        )

    failing = set(failures)
    if not failing:
        # Green run — nothing can gate, so skip the costly baseline computation.
        return _finish(True, [], "full", [])

    baseline = _baseline(root, timeout=timeout)
    if baseline is None:
        errors = [failures[t] for t in sorted(failing)]
        return _finish(not errors, errors, "full", [])

    delta = _bl.compute_delta(failing, baseline)
    errors = [failures[t] for t in delta.new_failures]
    return _finish(not errors, errors, "baseline-delta", delta.baseline_excluded)


#: Source globs that make the TypeScript/JavaScript suite relevant.
_TS_SCOPE = ["*.ts", "*.tsx", "*.js", "*.jsx"]


def run_typescript_suite_on_dir(
    directory: str, fail_fast: bool = True,
    config: GateTimeoutConfig | None = None,
    overrides: dict[str, list[str]] | None = None,
    changed_files: list[str] | None = None,
    max_workers: int | None = None,
    log_dir: Path | None = None,
) -> list[GateResult]:
    """Directory mode: type_check / lint / test via ``GateScheduler``.

    ``type_check`` and ``lint`` run concurrently; ``test`` waits on ``type_check``
    per :data:`TYPESCRIPT_GATE_GRAPH`. ``max_workers=None`` (default) is auto:
    concurrent when ``fail_fast`` is False, sequential when True. An ``overrides``
    entry replaces that gate's default command. When ``changed_files`` is supplied, a
    gate whose scope patterns do not overlap it is skipped — a passing
    ``skipped=True`` result (ticket 0030).
    """
    from gates.gate_graph import TYPESCRIPT_GATE_GRAPH

    gate_defs: list[tuple[str, GateSpec]] = [
        ("type_check", GateSpec(_type_check_gate_dir, _TS_SCOPE)),
        ("lint", GateSpec(_lint_gate_dir, _TS_SCOPE)),
        ("test", GateSpec(_test_gate_dir, _TS_SCOPE)),
    ]
    return run_dir_gates_scheduled(
        gate_defs, TYPESCRIPT_GATE_GRAPH, directory, log_namespace="typescript",
        scope_check=has_scope_match,
        fail_fast=fail_fast, config=config, overrides=overrides,
        changed_files=changed_files, max_workers=max_workers, log_dir=log_dir,
    )
