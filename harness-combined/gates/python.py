from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
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
    run_dir_gates_scheduled,
)
from gates._scope import GateSpec, has_scope_match
from models import GateError, GateResult

try:  # tomllib is stdlib on Python >= 3.11; tomli is the 3.10 backport
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised only on Python < 3.11
    import tomli as tomllib  # type: ignore[import-not-found, no-redef]

# Tools this gate invokes via subprocess. Single source of truth consumed by
# gates/doctor.py to build its probe registry (ticket 0022). Every name here
# must appear in a subprocess argument list below; the doctor CI invariant test
# enforces that structurally (AST), so keep this in sync when tooling changes.
REQUIRED_TOOLS: list[str] = ["mypy", "ruff", "bandit"]


@dataclass
class ExecutionEnvironment:
    root: Path
    implementation_file: Path
    test_file: Path
    pythonpath: list[str]


def _make_env(implementation: str, tests: str, project_root: str) -> ExecutionEnvironment:
    tmpdir = Path(tempfile.mkdtemp(prefix="harness_"))
    impl = tmpdir / "implementation.py"
    test_file = tmpdir / "test_implementation.py"
    impl.write_text(implementation, encoding="utf-8")
    test_file.write_text(
        f"import sys\n"
        f"sys.path.insert(0, '{tmpdir}')\n"
        f"sys.path.insert(0, '{project_root}')\n\n"
        + tests,
        encoding="utf-8",
    )
    return ExecutionEnvironment(
        root=tmpdir,
        implementation_file=impl,
        test_file=test_file,
        pythonpath=[str(tmpdir), project_root],
    )


def _exec(command: list[str], env: ExecutionEnvironment, timeout: int = 60) -> ProcessResult:
    e = os.environ.copy()
    e["PYTHONPATH"] = ":".join(env.pythonpath)
    p = subprocess.run(
        command, capture_output=True, text=True,
        cwd=str(env.root), env=e, timeout=timeout,
    )
    return ProcessResult(p.stdout, p.stderr, p.returncode)


def _exec_dir(command: list[str], directory: str, timeout: int = 60) -> ProcessResult:
    p = subprocess.run(
        command, capture_output=True, text=True,
        cwd=directory, timeout=timeout,
    )
    return ProcessResult(p.stdout, p.stderr, p.returncode)


def _rel(path: str, env: ExecutionEnvironment) -> str:
    try:
        return str(Path(path).relative_to(env.root))
    except ValueError:
        return path


_MYPY_PATTERN = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):\s*(?P<severity>error|warning|note):\s*"
    r"(?P<message>.+?)(?:\s+\[(?P<code>[^\]]+)\])?$"
)


def _parse_mypy_output(output: str, root: Path | None = None) -> list[GateError]:
    errors = []
    for line in output.splitlines():
        m = _MYPY_PATTERN.match(line.strip())
        if not m or m.group("severity") == "note":
            continue
        file_path = m.group("file")
        if root:
            try:
                file_path = str(Path(file_path).relative_to(root))
            except ValueError:
                pass
        errors.append(GateError(
            message=m.group("message").strip(),
            file=file_path,
            line=int(m.group("line")), column=None,
            code=m.group("code"), severity=m.group("severity"),
        ))
    return errors


def _parse_ruff_json(stdout: str, root: Path | None = None) -> list[GateError]:
    errors: list[GateError] = []
    if not stdout.strip():
        return errors
    try:
        lint_results: list[Any] = json.loads(stdout)
        for f in lint_results:
            file_path = f["filename"]
            if root:
                try:
                    file_path = str(Path(file_path).relative_to(root))
                except ValueError:
                    pass
            errors.append(GateError(
                message=f["message"],
                file=file_path,
                line=f["location"]["row"], column=f["location"]["column"],
                code=f["code"],
                severity="error" if f["code"].startswith(("E", "F")) else "warning",
            ))
    except (json.JSONDecodeError, KeyError):
        pass
    return errors


def _parse_bandit_json(stdout: str, root: Path | None = None) -> list[GateError]:
    errors: list[GateError] = []
    if not stdout.strip():
        return errors
    try:
        bandit_out: dict[str, Any] = json.loads(stdout)
        for r in bandit_out.get("results", []):
            file_path = r["filename"]
            if root:
                try:
                    file_path = str(Path(file_path).relative_to(root))
                except ValueError:
                    pass
            errors.append(GateError(
                message=f"{r['test_name']}: {r['issue_text']}",
                file=file_path,
                line=r["line_number"], column=None,
                code=r["test_id"], severity="error",
            ))
    except (json.JSONDecodeError, KeyError):
        pass
    return errors


# ── Text mode gates ───────────────────────────────────────────────────────────

def _syntax_gate(implementation: str, tests: str) -> GateResult:
    start = time.monotonic()
    errors = []
    for label, source in [("implementation", implementation), ("tests", tests)]:
        try:
            ast.parse(source)
        except SyntaxError as e:
            errors.append(GateError(
                message=e.msg, file=label, line=e.lineno,
                column=e.offset, code="SyntaxError", severity="error",
            ))
    return GateResult(
        gate="syntax", passed=not errors, errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def _type_check_gate(env: ExecutionEnvironment, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("typecheck", 60) if config else 60
    try:
        result = _exec([
            sys.executable, "-m", "mypy",
            str(env.implementation_file),
            "--ignore-missing-imports", "--no-error-summary",
            "--show-column-numbers", "--no-color-output",
        ], env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("type_check", timeout)
    errors = _parse_mypy_output(result.output, env.root)
    if result.returncode != 0 and not errors:
        errors.append(GateError(
            message=result.output[:500] or "mypy exited non-zero (tool may not be installed)",
            file=None, line=None, column=None, code="TOOL_ERROR", severity="error",
        ))
    return GateResult(
        gate="type_check",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def _lint_gate(env: ExecutionEnvironment, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("lint", 60) if config else 60
    try:
        result = _exec([
            sys.executable, "-m", "ruff", "check",
            str(env.implementation_file),
            "--output-format", "json",
            "--select", "E,F,W,I",
            "--ignore", "E501",
        ], env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("lint", timeout)
    errors = _parse_ruff_json(result.stdout, env.root)
    if result.returncode != 0 and not errors:
        errors.append(GateError(
            message=result.output[:500] or "ruff exited non-zero (tool may not be installed)",
            file=None, line=None, column=None, code="TOOL_ERROR", severity="error",
        ))
    return GateResult(
        gate="lint",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def _test_gate(env: ExecutionEnvironment, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("test", 120) if config else 120
    try:
        result = _exec([
            sys.executable, "-m", "pytest",
            str(env.test_file), "--tb=short", "--no-header", "-q",
        ], env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("test", timeout)
    if result.returncode == 0:
        return GateResult(gate="test", passed=True, errors=[],
                          duration_ms=int((time.monotonic() - start) * 1000))
    errors: list[GateError] = []
    current: str | None
    lines: list[str]
    current, lines = None, []
    for line in result.output.splitlines():
        if line.startswith("FAILED"):
            if current and lines:
                errors.append(GateError(
                    message=f"{current}: {' | '.join(lines)}",
                    file="tests", line=None, column=None,
                    code="TEST_FAILURE", severity="error",
                ))
            current = line.split("::")[1].split(" ")[0] if "::" in line else line
            lines = []
        elif line.startswith("E ") and current:
            lines.append(line[2:].strip())
    if current and lines:
        errors.append(GateError(
            message=f"{current}: {' | '.join(lines)}",
            file="tests", line=None, column=None,
            code="TEST_FAILURE", severity="error",
        ))
    if not errors:
        errors.append(GateError(
            message=result.output[:800], file="tests",
            line=None, column=None, code="TEST_FAILURE", severity="error",
        ))
    return GateResult(gate="test", passed=False, errors=errors,
                      duration_ms=int((time.monotonic() - start) * 1000))


def _security_gate(env: ExecutionEnvironment, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("security", 60) if config else 60
    try:
        result = _exec([
            sys.executable, "-m", "bandit",
            str(env.implementation_file),
            "-f", "json", "--severity-level", "medium",
        ], env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("security", timeout)
    errors = _parse_bandit_json(result.stdout, env.root)
    if result.returncode not in (0, 1) and not errors:
        errors.append(GateError(
            message=result.output[:500] or "bandit exited non-zero (tool may not be installed)",
            file=None, line=None, column=None, code="TOOL_ERROR", severity="error",
        ))
    return GateResult(
        gate="security",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def run_python_suite(
    implementation: str, tests: str, project_root: str,
    config: GateTimeoutConfig | None = None,
) -> list[GateResult]:
    """Text mode: syntax → type_check → lint → tests → security (temp dir)."""
    results = []
    syntax = _syntax_gate(implementation, tests)
    results.append(syntax)
    if not syntax.passed:
        return results

    env = _make_env(implementation, tests, project_root)
    try:
        for gate_fn in [_type_check_gate, _lint_gate, _test_gate, _security_gate]:
            result = gate_fn(env, config)
            results.append(result)
            if not result.passed:
                return results
    finally:
        shutil.rmtree(env.root, ignore_errors=True)

    return results


# ── Directory mode config detection ───────────────────────────────────────────

def has_ruff_config(directory: Path) -> bool:
    """True when *directory* carries its own ruff configuration.

    Recognised sources: ``ruff.toml``, ``.ruff.toml``, or a ``[tool.ruff]`` table in
    ``pyproject.toml``. When a project config exists the directory-mode lint runs
    bare ``ruff check .`` so the project's (often stricter) rule selection wins over
    the harness floor. A ``pyproject.toml`` that cannot be read/parsed is treated as
    having no ruff config (the floor then applies) rather than raising.
    """
    if (directory / "ruff.toml").exists() or (directory / ".ruff.toml").exists():
        return True
    pyproject = directory / "pyproject.toml"
    if not pyproject.exists():
        return False
    try:
        with open(pyproject, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    tool = data.get("tool")
    return isinstance(tool, dict) and "ruff" in tool


def _ruff_dir_argv(directory: Path) -> list[str]:
    """Directory-mode ruff argv: project config wins, hardcoded floor is the fallback.

    Always requests JSON output (an output format, not a rule selection). The
    ``--select E,F,W,I --ignore E501`` floor is appended ONLY when the project ships
    no ruff config, so a project's own (stricter) config is never overridden and a
    config-less project still gets baseline linting.
    """
    argv = [sys.executable, "-m", "ruff", "check", ".", "--output-format", "json"]
    if not has_ruff_config(directory):
        argv += ["--select", "E,F,W,I", "--ignore", "E501"]
    return argv


# ── Directory mode gates ──────────────────────────────────────────────────────

def _lint_gate_dir(directory: str, config: GateTimeoutConfig | None = None) -> GateResult:
    """Directory mode lint — also catches syntax errors via ruff E999."""
    start = time.monotonic()
    root = Path(directory)
    timeout = config.timeout_for("lint", 60) if config else 60
    try:
        result = _exec_dir(_ruff_dir_argv(root), directory, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("lint", timeout)
    errors = _parse_ruff_json(result.stdout, root)
    append_tool_error_if_silent(errors, result.returncode, result.output)
    return GateResult(
        gate="lint",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def _type_check_gate_dir(directory: str, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    root = Path(directory)
    timeout = config.timeout_for("typecheck", 60) if config else 60
    try:
        # No --ignore-missing-imports here (FR-2): a wrong/nonexistent import path
        # (import-not-found) is a genuine defect and must be flagged. We DO disable
        # import-untyped so a valid third-party dependency that merely lacks type
        # stubs is not a false failure — only genuinely unresolvable modules fail.
        #
        # Precondition (by design): dir-mode mypy runs via ``sys.executable`` — the
        # interpreter running the harness — so the project's dependencies must be
        # resolvable by that interpreter (i.e. the harness is invoked from within the
        # project's environment). A dependency present only in a separate project
        # venv resolves to import-not-found and will fail; using a detected project
        # venv interpreter is a future enhancement, tracked separately. Text mode
        # keeps --ignore-missing-imports (temp dirs can't resolve project imports).
        result = _exec_dir([
            sys.executable, "-m", "mypy", ".",
            "--disable-error-code=import-untyped",
            "--no-error-summary",
            "--show-column-numbers", "--no-color-output",
        ], directory, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("type_check", timeout)
    errors = _parse_mypy_output(result.output, root)
    append_tool_error_if_silent(errors, result.returncode, result.output)
    return GateResult(
        gate="type_check",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


# ── Directory-mode test gate: full run + baseline-delta ────────────────────────
#
# Like the TypeScript gate (ticket 0041), the directory-mode pytest gate runs the
# *entire* suite and fails only on failures absent from the cached merge-base
# baseline (plus any previously-passing test now deleted). The shared machinery
# lives in ``gates/_baseline.py``; this module supplies the pytest-specific run and
# ID parser. When no baseline is available it falls back to full-suite strictness.

#: One line of ``pytest -rA`` short-summary output: ``STATUS <node-id>[ - reason]``.
_PYTEST_LINE = re.compile(
    r"^(?P<status>PASSED|FAILED|ERROR|XPASS|XFAIL|SKIPPED)\s+"
    r"(?P<id>\S+)(?:\s+-\s+(?P<reason>.*))?$"
)
#: Statuses that count as a test having run to a pass/fail conclusion.
_PYTEST_PRESENT = {"PASSED", "FAILED", "ERROR", "XPASS"}
_PYTEST_FAILING = {"FAILED", "ERROR"}


def _run_pytest_collect_dir(directory: str | Path, timeout: int) -> ProcessResult:
    """Run the full pytest suite with the per-test short summary (``-rA``) enabled.

    ``-rA`` prints one ``PASSED``/``FAILED``/``ERROR`` line per test regardless of
    ``-q``, giving stable ``path::test`` node IDs without needing the optional
    ``pytest-json-report`` plugin.
    """
    return _exec_dir([
        sys.executable, "-m", "pytest", "-rA", "-q", "--tb=no",
        "-p", "no:cacheprovider",
    ], str(directory), timeout=timeout)


def _parse_pytest_report(
    output: str, returncode: int,
) -> tuple[bool, set[str], dict[str, GateError]]:
    """Parse ``pytest -rA`` output into ``(parsed_ok, present_ids, {failing_id: err})``.

    ``present_ids`` is every test that ran to a pass/fail conclusion; the failing dict
    holds only failures/errors. ``parsed_ok`` is False when nothing parsed and pytest
    exited non-zero (a crash / collection blow-up with no per-test lines) so the
    caller falls back to exit-code strictness.
    """
    present: set[str] = set()
    failing: dict[str, GateError] = {}
    for raw in output.splitlines():
        m = _PYTEST_LINE.match(raw.strip())
        if not m:
            continue
        status = m.group("status")
        tid = m.group("id")
        if status in _PYTEST_PRESENT:
            present.add(tid)
        if status in _PYTEST_FAILING:
            reason = (m.group("reason") or "test failed").strip()
            failing[tid] = GateError(
                message=f"{tid}: {reason}"[:600],
                file=tid.split("::")[0] if "::" in tid else None,
                line=None, column=None, code="TEST_FAILURE", severity="error",
            )
    parsed_ok = bool(present) or returncode == 0
    return parsed_ok, present, failing


def _merge_base_sha(root: Path, base: str) -> str | None:
    return _bl.merge_base_sha(root, base)


def _collect_baseline(root: Path, sha: str, timeout: int) -> _bl.SuiteCollection | None:
    """Run the full pytest suite at ``sha`` in a throwaway detached worktree."""
    def _run(base_root: Path) -> _bl.SuiteCollection | None:
        try:
            result = _run_pytest_collect_dir(base_root, timeout)
        except subprocess.TimeoutExpired:
            return None
        ok, present, failing = _parse_pytest_report(result.output, result.returncode)
        if not ok:
            return None
        return _bl.SuiteCollection.of(set(failing), present)

    return _bl.run_in_detached_baseline_worktree(
        root, sha, _run, tmp_prefix="harness_py_baseline_",
    )


def _baseline(directory: Path, base: str = "main", timeout: int = 180) -> _bl.SuiteCollection | None:
    """Present+failing baseline at the merge base; None → run strict full-suite."""
    return _bl.load_baseline(
        directory, base, timeout,
        merge_base_fn=_merge_base_sha, compute_fn=_collect_baseline,
        read_cache=_bl.read_collection_cache, write_cache=_bl.write_collection_cache,
    )


def _removed_error(tid: str) -> GateError:
    return GateError(
        message=f"{tid}: previously-passing test removed (present at baseline, absent now)",
        file=tid.split("::")[0] if "::" in tid else None,
        line=None, column=None, code="TEST_REMOVED", severity="error",
    )


def _test_gate_dir(directory: str, config: GateTimeoutConfig | None = None) -> GateResult:
    """Directory-mode pytest gate: full suite run + baseline-delta comparison.

    Runs the entire suite, then fails only on failures absent from the cached
    merge-base baseline (and any previously-green test now deleted). Falls back to
    full-suite strictness when the baseline is unavailable (git absent / unknown base
    / dirty cache). Reports ``mode`` and ``baseline_excluded`` on the result.
    """
    start = time.monotonic()
    root = Path(directory)
    timeout = config.timeout_for("test", 180) if config else 180
    try:
        result = _run_pytest_collect_dir(root, timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("test", timeout)
    ok, present, failing = _parse_pytest_report(result.output, result.returncode)
    if not ok:
        return _bl.strict_exit_result(
            "test", start, result.returncode, result.output,
            fallback_msg="pytest produced no parseable output",
        )
    baseline = _baseline(root, timeout=timeout)
    return _bl.build_delta_result(
        "test", start, present, failing, baseline, removed_error=_removed_error,
    )


def _security_gate_dir(directory: str, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    root = Path(directory)
    timeout = config.timeout_for("security", 60) if config else 60
    bandit_cmd = [
        sys.executable, "-m", "bandit", "-r", ".",
        "-f", "json", "--severity-level", "medium",
        "--exclude", ".venv,venv,node_modules,.git",
    ]
    if (root / "pyproject.toml").exists():
        bandit_cmd += ["-c", str(root / "pyproject.toml")]
    try:
        result = _exec_dir(bandit_cmd, directory, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("security", timeout)
    errors = _parse_bandit_json(result.stdout, root)
    append_tool_error_if_silent(errors, result.returncode, result.output, success_codes=(0, 1))
    return GateResult(
        gate="security",
        passed=result.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


#: Source globs that make the Python suite relevant — a change touching none of
#: these lets each Python gate be skipped when ``changed_files`` is supplied.
_PY_SCOPE = ["*.py", "*.pyi"]


def run_python_suite_on_dir(
    directory: str, fail_fast: bool = True,
    config: GateTimeoutConfig | None = None,
    overrides: dict[str, list[str]] | None = None,
    changed_files: list[str] | None = None,
    max_workers: int | None = None,
    log_dir: Path | None = None,
) -> list[GateResult]:
    """Directory mode: lint / type_check / test / security via ``GateScheduler``.

    Independent gates (lint, type_check, security) run concurrently; ``test`` waits
    on ``type_check`` per :data:`PYTHON_GATE_GRAPH`. ``max_workers=None`` (default)
    is auto: concurrent when ``fail_fast`` is False, sequential when True; the server
    overrides it from ``parallel_gate_limit``. An ``overrides`` entry (gate-name ->
    argv) replaces that gate's default command. When ``changed_files`` is supplied, a
    gate whose scope patterns do not overlap it is skipped — a passing
    ``skipped=True`` result — keeping ``passed=True`` so it never trips fail-fast
    (ticket 0030).
    """
    from gates.gate_graph import PYTHON_GATE_GRAPH

    gate_defs: list[tuple[str, GateSpec]] = [
        ("lint", GateSpec(_lint_gate_dir, _PY_SCOPE)),
        ("type_check", GateSpec(_type_check_gate_dir, _PY_SCOPE)),
        ("test", GateSpec(_test_gate_dir, _PY_SCOPE)),
        ("security", GateSpec(_security_gate_dir, _PY_SCOPE)),
    ]
    return run_dir_gates_scheduled(
        gate_defs, PYTHON_GATE_GRAPH, directory, log_namespace="python",
        scope_check=has_scope_match,
        fail_fast=fail_fast, config=config, overrides=overrides,
        changed_files=changed_files, max_workers=max_workers, log_dir=log_dir,
    )
