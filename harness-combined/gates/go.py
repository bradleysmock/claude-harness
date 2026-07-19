from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import gates._baseline as _bl
from gates import (
    GateTimeoutConfig,
    ProcessResult,
    _timeout_error,
    run_dir_gates_scheduled,
    tool_skipped,
)
from gates._scope import GateSpec, has_scope_match
from models import GateError, GateResult

# Tools this gate invokes via subprocess (see gates/python.py REQUIRED_TOOLS for
# the doctor contract). Every name must appear in a subprocess argument list.
REQUIRED_TOOLS: list[str] = ["go", "staticcheck"]

# Current stable Go language version for generated code. Raised from 1.21 so
# post-1.21 language features build (range-over-int in 1.22, range-over-func in
# 1.23). Review cadence: revisit each January against the current Go stable
# release; a host go.mod's `go` directive overrides this (see host_go_version).
GO_VERSION = "1.23"

_GO_DIRECTIVE = re.compile(r"^go\s+(?P<version>\d+\.\d+(?:\.\d+)?)\s*$")


def _go_mod(version: str) -> str:
    """Render the temp-module go.mod for a given Go language version."""
    return f"module harness/temp\n\ngo {version}\n"


def host_go_version(project_root: str | Path) -> str | None:
    """Version from a host ``go.mod``'s ``go X.Y`` directive, or None when absent.

    Text mode prefers this over ``GO_VERSION`` so generated code is built against the
    host project's declared language version (FR-5). A missing/unreadable go.mod, or
    one with no ``go`` directive, returns None.
    """
    try:
        text = (Path(project_root) / "go.mod").read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        m = _GO_DIRECTIVE.match(line.strip())
        if m:
            return m.group("version")
    return None


_GO_MOD = _go_mod(GO_VERSION)

_GO_ERROR = re.compile(
    r"^(?:\./)?(?P<file>[^:]+\.go):(?P<line>\d+)(?::(?P<col>\d+))?:\s*(?P<msg>.+)$"
)

_STATICCHECK_PATTERN = re.compile(
    r"^(?P<file>[^:]+\.go):(?P<line>\d+):(?P<col>\d+):\s*(?P<msg>.+?)\s+\((?P<code>S[A-Z]\d+)\)$"
)


@dataclass
class GoEnv:
    root: Path
    impl_file: Path
    test_file: Path


def _make_env(implementation: str, tests: str, project_root: str) -> GoEnv:
    tmpdir = Path(tempfile.mkdtemp(prefix="harness_go_"))
    (tmpdir / "go.mod").write_text(_go_mod(host_go_version(project_root) or GO_VERSION))
    impl = tmpdir / "implementation.go"
    test = tmpdir / "implementation_test.go"
    impl.write_text(implementation, encoding="utf-8")
    test.write_text(tests, encoding="utf-8")
    return GoEnv(root=tmpdir, impl_file=impl, test_file=test)


def _exec(command: list[str], cwd: str | Path, timeout: int = 60) -> ProcessResult:
    p = subprocess.run(
        command, capture_output=True, text=True,
        cwd=str(cwd), timeout=timeout,
    )
    return ProcessResult(p.stdout, p.stderr, p.returncode)


def _parse_go_errors(output: str) -> list[GateError]:
    errors = []
    for line in output.splitlines():
        m = _GO_ERROR.match(line.strip())
        if m:
            errors.append(GateError(
                message=m.group("msg").strip(),
                file=m.group("file"),
                line=int(m.group("line")),
                column=int(m.group("col")) if m.group("col") else None,
                code=None, severity="error",
            ))
    return errors


# ── Text mode gates ───────────────────────────────────────────────────────────

def _build_gate(cwd: str | Path, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("typecheck", 60) if config else 60
    try:
        result = _exec(["go", "build", "./..."], cwd, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("build", timeout)
    errors = _parse_go_errors(result.output)
    return GateResult(gate="build", passed=result.returncode == 0 and not errors,
                      errors=errors, duration_ms=int((time.monotonic() - start) * 1000))


def _vet_gate(cwd: str | Path, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("lint", 60) if config else 60
    try:
        result = _exec(["go", "vet", "./..."], cwd, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("vet", timeout)
    errors = _parse_go_errors(result.output)
    return GateResult(gate="vet", passed=result.returncode == 0 and not errors,
                      errors=errors, duration_ms=int((time.monotonic() - start) * 1000))


def _staticcheck_gate(cwd: str | Path, config: GateTimeoutConfig | None = None) -> GateResult:
    import shutil as _shutil
    if not _shutil.which("staticcheck"):
        # Absent optional tool: warn-and-pass, never a silent pass (ticket 0043).
        return tool_skipped(
            "staticcheck", "staticcheck",
            "go install honnef.co/go/tools/cmd/staticcheck@latest",
        )
    start = time.monotonic()
    timeout = config.timeout_for("lint", 60) if config else 60
    try:
        result = _exec(["staticcheck", "./..."], cwd, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("staticcheck", timeout)
    errors = []
    for line in result.output.splitlines():
        m = _STATICCHECK_PATTERN.match(line.strip())
        if m:
            errors.append(GateError(
                message=m.group("msg").strip(), file=m.group("file"),
                line=int(m.group("line")), column=int(m.group("col")),
                code=m.group("code"), severity="error",
            ))
        elif line.strip() and not line.startswith("#"):
            errors.extend(_parse_go_errors(line))
    return GateResult(gate="staticcheck", passed=result.returncode == 0 and not errors,
                      errors=errors, duration_ms=int((time.monotonic() - start) * 1000))


def _test_gate(cwd: str | Path, config: GateTimeoutConfig | None = None) -> GateResult:
    start = time.monotonic()
    timeout = config.timeout_for("test", 120) if config else 120
    try:
        result = _exec(["go", "test", "-race", "-v", "./..."], cwd, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("test", timeout)
    if result.returncode == 0:
        return GateResult(gate="test", passed=True, errors=[],
                          duration_ms=int((time.monotonic() - start) * 1000))
    errors = []
    current_test: str | None = None
    fail_lines: list[str] = []
    for line in result.output.splitlines():
        if line.startswith("--- FAIL:"):
            current_test = line.split(":")[1].strip().split(" ")[0]
            fail_lines = []
        elif line.startswith("    ") and current_test:
            fail_lines.append(line.strip())
        elif line.startswith("FAIL") and current_test:
            errors.append(GateError(
                message=f"{current_test}: {' | '.join(fail_lines[:3])}",
                file=None, line=None, column=None,
                code="TEST_FAILURE", severity="error",
            ))
            current_test = None
    if current_test and fail_lines:
        errors.append(GateError(
            message=f"{current_test}: {' | '.join(fail_lines[:3])}",
            file=None, line=None, column=None,
            code="TEST_FAILURE", severity="error",
        ))
    if not errors:
        compile_errs = _parse_go_errors(result.output)
        errors = compile_errs or [GateError(
            message=result.output[:600], file=None,
            line=None, column=None, code="BUILD_FAILURE", severity="error",
        )]
    return GateResult(gate="test", passed=False, errors=errors,
                      duration_ms=int((time.monotonic() - start) * 1000))


def run_go_suite(
    implementation: str, tests: str, project_root: str,
    config: GateTimeoutConfig | None = None,
) -> list[GateResult]:
    """Text mode: build → vet → staticcheck → test (temp dir)."""
    env = _make_env(implementation, tests, project_root)
    results = []
    try:
        for gate_fn in [_build_gate, _vet_gate, _staticcheck_gate, _test_gate]:
            result = gate_fn(env.root, config)
            results.append(result)
            if not result.passed:
                return results
    finally:
        shutil.rmtree(env.root, ignore_errors=True)
    return results


# ── Directory mode gates ──────────────────────────────────────────────────────

#: Source globs that make the Go suite relevant.
_GO_SCOPE = ["*.go", "go.mod", "go.sum"]


# ── Directory-mode test gate: full run + baseline-delta ────────────────────────
#
# Like the TypeScript gate (ticket 0041), the directory-mode ``go test`` gate runs
# the entire suite via ``-json`` and fails only on failures absent from the cached
# merge-base baseline (plus any previously-passing test now deleted). Shared
# machinery lives in ``gates/_baseline.py``. Text mode keeps the human ``go test -v``
# gate (``_test_gate``) — temp-dir builds have no git baseline to diff against.

def _run_go_test_json_dir(directory: str | Path, timeout: int) -> ProcessResult:
    """Run the full Go suite with machine-readable per-test JSON events.

    Keeps ``-race`` so the directory-mode gate preserves the race-detection parity
    documented for the Go MCP gate (a data race must not pass here while failing the
    ``-race`` Stop hook).
    """
    return _exec(["go", "test", "-json", "-race", "./..."], directory, timeout=timeout)


def _parse_go_test_json(
    output: str, returncode: int,
) -> tuple[bool, set[str], dict[str, GateError]]:
    """Parse ``go test -json`` events into ``(parsed_ok, present_ids, {failing: err})``.

    Each per-test ``pass``/``fail`` action yields the stable ID ``<package>.<Test>``.
    Package-level events (no ``Test`` key) and non-terminal actions (``run``,
    ``output``) are ignored. ``parsed_ok`` is False when no per-test result parsed and
    the run exited non-zero (a compile failure emits diagnostics but no test events),
    so the caller falls back to exit-code strictness surfacing the build error.
    """
    present: set[str] = set()
    failing: dict[str, GateError] = {}
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(obj, dict):
            continue
        test = obj.get("Test")
        action = obj.get("Action")
        if not test or action not in ("pass", "fail"):
            continue
        tid = f"{obj.get('Package', '?')}.{test}"
        present.add(tid)
        if action == "fail":
            failing[tid] = GateError(
                message=f"{tid}: test failed", file=None, line=None, column=None,
                code="TEST_FAILURE", severity="error",
            )
    parsed_ok = bool(present) or returncode == 0
    return parsed_ok, present, failing


def _merge_base_sha(root: Path, base: str) -> str | None:
    return _bl.merge_base_sha(root, base)


def _collect_baseline(root: Path, sha: str, timeout: int) -> _bl.SuiteCollection | None:
    """Run the full Go suite at ``sha`` in a throwaway detached worktree."""
    def _run(base_root: Path) -> _bl.SuiteCollection | None:
        try:
            result = _run_go_test_json_dir(base_root, timeout)
        except subprocess.TimeoutExpired:
            return None
        ok, present, failing = _parse_go_test_json(result.output, result.returncode)
        if not ok:
            return None
        return _bl.SuiteCollection.of(set(failing), present)

    return _bl.run_in_detached_baseline_worktree(
        root, sha, _run, tmp_prefix="harness_go_baseline_",
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
        file=None, line=None, column=None, code="TEST_REMOVED", severity="error",
    )


def _test_gate_dir(directory: str, config: GateTimeoutConfig | None = None) -> GateResult:
    """Directory-mode ``go test`` gate: full suite run + baseline-delta comparison.

    Fails only on failures absent from the cached merge-base baseline (and any
    previously-green test now deleted); falls back to full-suite strictness when the
    baseline is unavailable. Reports ``mode`` and ``baseline_excluded``.
    """
    start = time.monotonic()
    root = Path(directory)
    timeout = config.timeout_for("test", 180) if config else 180
    try:
        result = _run_go_test_json_dir(root, timeout)
    except subprocess.TimeoutExpired:
        return _timeout_error("test", timeout)
    ok, present, failing = _parse_go_test_json(result.output, result.returncode)
    if not ok:
        return _bl.strict_exit_result(
            "test", start, result.returncode, result.output,
            fallback_msg="go test produced no parseable output",
        )
    baseline = _baseline(root, timeout=timeout)
    return _bl.build_delta_result(
        "test", start, present, failing, baseline, removed_error=_removed_error,
    )


def run_go_suite_on_dir(
    directory: str, fail_fast: bool = True,
    config: GateTimeoutConfig | None = None,
    overrides: dict[str, list[str]] | None = None,
    changed_files: list[str] | None = None,
    max_workers: int | None = None,
    log_dir: Path | None = None,
) -> list[GateResult]:
    """Directory mode: build / vet / test via ``GateScheduler``.

    ``build`` and ``vet`` run concurrently; ``test`` waits on ``build`` per
    :data:`GO_GATE_GRAPH`. ``max_workers=None`` (default) is auto: concurrent when
    ``fail_fast`` is False, sequential when True. An ``overrides`` entry replaces
    that gate's default command. When ``changed_files`` is supplied, a gate whose
    scope patterns do not overlap it is skipped — a passing ``skipped=True`` result
    (ticket 0030).
    """
    from gates.gate_graph import GO_GATE_GRAPH

    gate_defs: list[tuple[str, GateSpec]] = [
        ("build", GateSpec(_build_gate, _GO_SCOPE)),
        ("vet", GateSpec(_vet_gate, _GO_SCOPE)),
        ("test", GateSpec(_test_gate_dir, _GO_SCOPE)),
    ]
    return run_dir_gates_scheduled(
        gate_defs, GO_GATE_GRAPH, directory, log_namespace="go",
        scope_check=has_scope_match,
        fail_fast=fail_fast, config=config, overrides=overrides,
        changed_files=changed_files, max_workers=max_workers, log_dir=log_dir,
    )
