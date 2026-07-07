from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from gates._scope import SKIP_REASON, GateSpec
from models import GateError, GateResult

try:  # tomllib is stdlib on Python >= 3.11; tomli is the 3.10 backport
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised only on Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]


GateType = Literal["lint", "typecheck", "test", "security"]

#: Gate type -> the GateTimeoutConfig field holding its per-gate override.
_TIMEOUT_FIELDS: dict[str, str] = {
    "lint": "lint_timeout_seconds",
    "typecheck": "typecheck_timeout_seconds",
    "test": "test_timeout_seconds",
    "security": "security_timeout_seconds",
}


@dataclass(frozen=True)
class GateTimeoutConfig:
    """Per-gate and global wall-clock ceilings loaded from ``.harness.toml``.

    Fields are ``None`` when unset. Resolution precedence (``timeout_for``):
    per-gate override > ``default_timeout_seconds`` > the caller's hardcoded
    default. The hardcoded default is passed in per call rather than embedded
    here because it varies by gate, language, and text-vs-dir mode; centralising
    it would silently change behaviour when no config is present (FR-5).
    """

    default_timeout_seconds: int | None = None
    lint_timeout_seconds: int | None = None
    typecheck_timeout_seconds: int | None = None
    test_timeout_seconds: int | None = None
    security_timeout_seconds: int | None = None

    def timeout_for(self, gate_type: GateType, default: int) -> int:
        """Resolve the timeout for ``gate_type``: override > global > ``default``."""
        override = getattr(self, _TIMEOUT_FIELDS[gate_type])
        if override is not None:
            return int(override)
        if self.default_timeout_seconds is not None:
            return self.default_timeout_seconds
        return default

    @classmethod
    def load(cls, path: Path) -> GateTimeoutConfig:
        """Parse the ``.harness.toml`` at ``path`` into a config.

        Unknown keys are ignored. Float values are truncated to int. A
        non-positive or non-numeric timeout raises ``ValueError``. Malformed TOML
        raises ``ValueError`` wrapping ``tomllib.TOMLDecodeError`` with the
        filename included.
        """
        try:
            with open(path, "rb") as fh:
                raw = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"Malformed TOML in {path}: {exc}") from exc

        known = ("default_timeout_seconds", *_TIMEOUT_FIELDS.values())
        values: dict[str, int] = {}
        for key in known:
            if key not in raw:
                continue
            value = raw[key]
            # bool is an int subclass in Python but a distinct TOML type — reject it.
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(
                    f"{path}: {key} must be a positive number, got {value!r}"
                )
            truncated = int(value)
            if truncated <= 0:
                raise ValueError(
                    f"{path}: {key} must be a positive integer, got {value!r}"
                )
            values[key] = truncated
        return cls(**values)

    @classmethod
    def from_directory(cls, directory: Path) -> GateTimeoutConfig | None:
        """Load ``<directory>/.harness.toml``; return ``None`` when it is absent."""
        path = directory / ".harness.toml"
        if not path.exists():
            return None
        return cls.load(path)


def _timeout_error(gate: str, timeout_s: int) -> GateResult:
    """Shared failed ``GateResult`` for a gate that exceeded ``timeout_s`` seconds.

    The message ``"<gate> gate timed out after <N> s"`` is a stable operator
    contract; ``code="TIMEOUT"`` is the machine-readable signal. Shared by every
    language module so the format cannot drift between them.
    """
    return GateResult(
        gate=gate, passed=False,
        errors=[GateError(
            message=f"{gate} gate timed out after {timeout_s} s",
            file=None, line=None, column=None, code="TIMEOUT", severity="error",
        )],
        duration_ms=timeout_s * 1000,
    )


@dataclass
class ProcessResult:
    stdout: str
    stderr: str
    returncode: int

    @property
    def output(self) -> str:
        return (self.stdout + "\n" + self.stderr).strip()


def append_tool_error_if_silent(
    errors: list[GateError],
    returncode: int,
    output: str,
    *,
    success_codes: tuple[int, ...] = (0,),
) -> list[GateError]:
    """Enforce the no-silent-failure invariant for a single gate.

    If the tool exited with a code outside ``success_codes`` but produced no
    parsed findings, append exactly one ``TOOL_ERROR`` so the gate can never
    report ``passed=False`` with an empty errors list (and, paired with the
    standard ``passed = returncode in success_codes and not errors`` check,
    never silently pass after a tool crash). No-op when the tool succeeded or
    when real findings were already parsed — so it is safe to call on every
    gate, including those that already pass.

    ``success_codes`` lets a gate declare its own "ran fine" exits — e.g. bandit
    uses ``(0, 1)`` (1 = findings present, surfaced separately), eslint/tsc/ruff
    use ``(0,)`` (non-zero is either parseable findings or a tool fault).
    """
    if returncode not in success_codes and not errors:
        errors.append(GateError(
            message=output[:500] or "tool exited non-zero (it may not be installed)",
            file=None, line=None, column=None, code="TOOL_ERROR", severity="error",
        ))
    return errors


def tool_skipped(gate: str, tool: str, install_hint: str) -> GateResult:
    """Canonical *passing* ``GateResult`` for an absent optional tool (ticket 0043).

    The skip-path counterpart to :func:`append_tool_error_if_silent`: an optional
    tool that is not installed must be **visible**, never a silent pass. The gate
    still counts as ``passed=True`` (warn tier — provisioning is an operator choice,
    not a code defect), but it carries exactly one ``TOOL_SKIPPED`` warning naming
    the ``tool``, its ``gate``, and a one-line ``install_hint`` so a lead can tell a
    clean pass from a vacuous one.

    ``TOOL_SKIPPED`` (severity ``warning``, gate still passes) is deliberately
    distinct from ``TOOL_ERROR`` (severity ``error``, gate fails — the tool was
    present but crashed). One wording, one test, mirroring the error-path helper.
    """
    return GateResult(
        gate=gate, passed=True,
        errors=[GateError(
            message=f"{tool} not installed — {gate} gate skipped (install: {install_hint})",
            file=None, line=None, column=None, code="TOOL_SKIPPED", severity="warning",
        )],
        duration_ms=0,
    )


def find_config_root(directory: Path, names: tuple[str, ...]) -> Path:
    """Resolve the directory that owns one of ``names`` (e.g. ``tsconfig.json``).

    Returns ``directory`` itself if it holds a match; otherwise the first
    immediate, non-vendored subdirectory that does (covers monorepo layouts
    where TS lives in ``web/`` while jest config sits at the root); otherwise
    ``directory`` unchanged as a safe fallback.
    """
    _SKIP = {"node_modules", ".git", "dist", "target", ".venv", "venv", "__pycache__"}
    if any((directory / n).exists() for n in names):
        return directory
    try:
        children = sorted(p for p in directory.iterdir() if p.is_dir())
    except OSError:
        return directory
    for child in children:
        if child.name in _SKIP:
            continue
        if any((child / n).exists() for n in names):
            return child
    return directory


def _run_override_gate(
    gate_name: str,
    argv: list[str],
    directory: str,
    config: GateTimeoutConfig | None = None,
) -> GateResult:
    """Run an operator-supplied override command for one gate.

    ``argv`` is a validated argument list (see :mod:`gates.config`) run **without a
    shell**, so the default gate command is replaced wholesale. Because the command
    is arbitrary, its pass/fail is driven by the exit code: a non-zero exit yields a
    single ``TOOL_ERROR`` finding (via :func:`append_tool_error_if_silent`) rather
    than a silent pass. A missing executable degrades to the same ``TOOL_ERROR``
    contract instead of crashing the suite (FR-9).
    """
    start = time.monotonic()
    timeout = 180
    if config is not None and config.default_timeout_seconds is not None:
        timeout = config.default_timeout_seconds
    try:
        p = subprocess.run(
            argv, cwd=directory, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _timeout_error(gate_name, timeout)
    except OSError as exc:  # e.g. the override's executable is not installed
        return GateResult(
            gate=gate_name, passed=False,
            errors=[GateError(
                message=f"override command failed to start: {exc}",
                file=None, line=None, column=None, code="TOOL_ERROR", severity="error",
            )],
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    output = (p.stdout + "\n" + p.stderr).strip()
    errors: list[GateError] = []
    append_tool_error_if_silent(errors, p.returncode, output)
    return GateResult(
        gate=gate_name,
        passed=p.returncode == 0 and not errors,
        errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


#: Sentinel: the caller did not specify ``max_workers``. Distinct from ``None``
#: (which the scheduler reads as "unlimited"), so the parallelism knob is forwarded
#: down the suite chain *only* when a caller set it — legacy fakes and direct callers
#: that omit it keep the sequential default and never receive an unexpected kwarg.
_WORKERS_UNSET: object = object()


def _make_default_gate_fn(
    gate_fn: Callable[..., GateResult],
    config: GateTimeoutConfig | None,
) -> Callable[[str], GateResult]:
    """Bind ``config`` to a default gate function, exposing an ``fn(directory)`` shape."""
    return lambda directory: gate_fn(directory, config)


def _make_override_gate_fn(
    name: str, argv: list[str], config: GateTimeoutConfig | None,
) -> Callable[[str], GateResult]:
    """Bind an operator override command to an ``fn(directory)`` shape."""
    return lambda directory: _run_override_gate(name, argv, directory, config)


def _make_skipped_gate_fn(name: str) -> Callable[[str], GateResult]:
    """A gate fn that instantly returns a scoped-out skip result (ticket 0030).

    A scope-skipped gate is modelled as a gate that "runs" but does no work and
    passes, so it flows through the scheduler unchanged: ``passed=True`` satisfies
    any dependent's prerequisite (a skipped ``type_check`` still lets ``test`` run)
    and never trips the fail-fast latch — exactly the pre-0036 skip contract.
    """
    return lambda directory: GateResult(
        gate=name, passed=True, errors=[], duration_ms=0,
        skipped=True, skip_reason=SKIP_REASON,
    )


def run_dir_gates_scheduled(
    gate_defs: list[tuple[str, GateSpec]],
    gate_graph: dict[str, list[str]],
    directory: str,
    *,
    log_namespace: str,
    scope_check: Callable[[list[str] | None, list[str] | None], bool],
    fail_fast: bool,
    config: GateTimeoutConfig | None,
    overrides: dict[str, list[str]] | None,
    changed_files: list[str] | None,
    max_workers: int | None,
    log_dir: Path | None,
) -> list[GateResult]:
    """Run a language's directory-mode gates through :class:`GateScheduler` (0036).

    ``gate_defs`` is the ordered ``(name, GateSpec)`` list — the ``GateSpec`` carries
    the gate function and its file-scope patterns (ticket 0030). It defines the
    scheduler's declaration order (and thus the returned result order). ``gate_graph``
    supplies the prerequisite edges (e.g. ``test`` -> ``type_check``) that keep
    dependent gates ordered while independent gates run concurrently.

    Per-gate function selection:

    * ``scope_check`` (the caller's ``has_scope_match``) is called once per gate, in
      declaration order, with ``(changed_files, spec.scope_patterns)`` — the runner
      passes its own module-local reference so a test can monkeypatch scope matching
      on the language module (ticket 0030).
    * A gate whose scope does not overlap ``changed_files`` becomes a skip-pass
      (``skipped=True``) result and does no work (ticket 0030).
    * Otherwise an ``overrides`` entry replaces the gate's default command with the
      operator's argv; absent that, the default gate function runs.

    Concurrency (``max_workers``):

    * ``None`` (the runner default) means **auto**: run independent gates
      concurrently when ``fail_fast`` is False (the ``/gate`` path — FR-5's "no
      explicit limit" default), but stay strictly sequential when ``fail_fast`` is
      True (the ``/build`` repair path, preserving the old early-return exactly).
    * An explicit integer (the operator's ``parallel_gate_limit``) always wins and
      caps in-flight gates at that value.

    Logs (``log_dir``): when unset, per-gate logs are written under
    ``<directory>/.harness/gate-logs/<log_namespace>/`` (FR-3). The
    ``<log_namespace>`` (the language) keeps a polyglot run's same-named gates —
    e.g. python and typescript ``test`` — in separate files (NFR-2).
    """
    from gates.scheduler import GateScheduler

    gate_fns: dict[str, Callable[[str], GateResult]] = {}
    for name, spec in gate_defs:
        if not scope_check(changed_files, spec.scope_patterns):
            gate_fns[name] = _make_skipped_gate_fn(name)
        elif overrides and name in overrides:
            gate_fns[name] = _make_override_gate_fn(name, overrides[name], config)
        else:
            gate_fns[name] = _make_default_gate_fn(spec.fn, config)

    effective_workers = max_workers
    if max_workers is None:
        # Auto: concurrent for non-fail-fast (/gate), sequential for fail-fast (/build).
        effective_workers = None if not fail_fast else 1
    if log_dir is None:
        log_dir = Path(directory) / ".harness" / "gate-logs" / log_namespace

    order = [name for name, _ in gate_defs]
    scheduler = GateScheduler(
        order, gate_graph, gate_fns,
        max_workers=effective_workers, log_dir=log_dir, fail_fast=fail_fast,
    )
    return scheduler.run(directory)


def run_suite_for(
    language: str,
    implementation: str,
    tests: str,
    project_root: str,
    config: GateTimeoutConfig | None = None,
) -> list[GateResult]:
    """Text mode: run gates on generated code in a temp dir (fail-fast)."""
    if language == "python":
        from gates.python import run_python_suite
        return run_python_suite(implementation, tests, project_root, config=config)
    elif language == "typescript":
        from gates.typescript import run_typescript_suite
        return run_typescript_suite(implementation, tests, project_root, config=config)
    elif language == "go":
        from gates.go import run_go_suite
        return run_go_suite(implementation, tests, project_root, config=config)
    elif language == "rust":
        from gates.rust import run_rust_suite
        return run_rust_suite(implementation, tests, project_root, config=config)
    else:
        raise ValueError(f"Unsupported language: {language!r}")


# Languages the coverage gate can measure (Python, Node.js, Rust — FR-1).
_COVERAGE_LANGUAGES = ("python", "typescript", "rust")


def _append_coverage_gate(
    results: list[GateResult],
    language: str,
    directory: str,
    standards_path: str | None,
    base_ref: str,
) -> None:
    """Append one coverage GateResult after the language gates, when applicable.

    Runs only when a ``standards_path`` was supplied, the language supports coverage,
    and every prior gate passed (coverage runs *after* the test gate — FR-1). The
    coverage gate is skip-safe by construction; the narrow guard here is defence in
    depth so a filesystem/config/runtime fault degrades to a warning entry instead of
    breaking the whole suite (mirrors the dep-audit phase precedent), preserving NFR-2.
    """
    if standards_path is None or language not in _COVERAGE_LANGUAGES:
        return
    if not all(r.passed for r in results):
        return
    from gates.coverage import run_coverage_gate
    try:
        results.append(run_coverage_gate(directory, language, standards_path, base_ref))
    except (OSError, ValueError, RuntimeError) as exc:
        results.append(GateResult(
            gate="coverage", passed=True,
            errors=[GateError(
                message=f"coverage gate degraded: {exc}", file=None, line=None,
                column=None, code="COVERAGE_GATE_ERROR", severity="warning",
            )],
            duration_ms=0,
        ))


def _language_suite_on_dir(
    language: str,
    directory: str,
    fail_fast: bool = True,
    config: GateTimeoutConfig | None = None,
    overrides: dict[str, list[str]] | None = None,
    changed_files: list[str] | None = None,
    max_workers: int | None | object = _WORKERS_UNSET,
    log_dir: Path | None = None,
) -> list[GateResult]:
    """Dispatch to a single language's directory-mode gate suite.

    Newer parameters are forwarded to the language suite only when the caller set
    them, so a suite stand-in that predates a parameter is never handed an
    unexpected keyword: ``overrides`` (gate-name -> replacement argv) when
    non-empty; ``changed_files`` (0030 scope skipping) when not ``None``;
    ``max_workers`` (0036 parallel gate limit) when the caller passed it (not
    :data:`_WORKERS_UNSET`); ``log_dir`` (0036 per-gate log destination) when
    non-``None``.
    """
    extra: dict[str, Any] = {}
    if overrides:
        extra["overrides"] = overrides
    if changed_files is not None:
        extra["changed_files"] = changed_files
    if max_workers is not _WORKERS_UNSET:
        extra["max_workers"] = max_workers
    if log_dir is not None:
        extra["log_dir"] = log_dir
    if language == "python":
        from gates.python import run_python_suite_on_dir
        results = run_python_suite_on_dir(directory, fail_fast=fail_fast, config=config, **extra)
    elif language == "typescript":
        from gates.typescript import run_typescript_suite_on_dir
        results = run_typescript_suite_on_dir(directory, fail_fast=fail_fast, config=config, **extra)
    elif language == "go":
        from gates.go import run_go_suite_on_dir
        results = run_go_suite_on_dir(directory, fail_fast=fail_fast, config=config, **extra)
    elif language == "rust":
        from gates.rust import run_rust_suite_on_dir
        results = run_rust_suite_on_dir(directory, fail_fast=fail_fast, config=config, **extra)
    else:
        raise ValueError(f"Unsupported language: {language!r}")
    return results


def _dep_audit_model_result(directory: str) -> GateResult:
    """Run the dependency-audit gate and adapt its module-local result into the
    shared ``models.GateResult`` shape the suite consumers expect.

    The dep-audit gate is advisory infrastructure — if it faults it degrades to a
    passing warning, never breaking the whole suite.
    """
    start = time.monotonic()
    try:
        from gates.dep_audit import run_dep_audit_gate
        local = run_dep_audit_gate(directory)
        errors = [
            GateError(
                message=f"{f.package + ': ' if f.package else ''}{f.message}",
                file="gate-findings.md", line=None, column=None,
                code=f.advisory_id,
                severity="error" if f.severity == "BLOCKER" else "warning",
            )
            for f in local.findings
        ]
        return GateResult(
            gate="dep-audit", passed=local.passed, errors=errors,
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except (ImportError, OSError, ValueError, RuntimeError, TypeError, AttributeError) as exc:
        # dep-audit is advisory infrastructure; a fault in it degrades to a
        # passing warning rather than breaking the whole gate suite.
        return GateResult(
            gate="dep-audit", passed=True,
            errors=[GateError(
                message=f"dependency audit degraded ({exc})",
                file=None, line=None, column=None,
                code="DEP_AUDIT_ERROR", severity="warning",
            )],
            duration_ms=int((time.monotonic() - start) * 1000),
        )


def run_suite_on_dir(
    language: str,
    directory: str,
    fail_fast: bool = True,
    *,
    standards_path: str | None = None,
    base_ref: str = "main",
    config: GateTimeoutConfig | None = None,
    overrides: dict[str, list[str]] | None = None,
    changed_files: list[str] | None = None,
    max_workers: int | None | object = _WORKERS_UNSET,
    log_dir: Path | None = None,
) -> list[GateResult]:
    """Directory mode: language gates, then coverage and dep-audit phases.

    After the language-specific phases pass, a coverage gate is appended when
    ``standards_path`` is provided (see :func:`_append_coverage_gate`), followed by
    a single post-language dep-audit phase. In fail-fast mode a failing language
    gate short-circuits before either extra phase runs. Callers that omit
    ``standards_path`` keep the pre-coverage behaviour. ``config`` carries the
    optional per-gate timeout overrides threaded into the language suites;
    ``overrides`` carries the operator's per-gate *command* overrides.
    ``changed_files`` (ticket 0030) is forwarded to the language suite so a gate
    whose scope does not overlap the diff is skipped; the coverage/dep-audit/SAST
    phases are unaffected — they still run only after the language gates pass.

    The secrets gate runs first, before language dispatch, via a single
    pre-dispatch insertion (ticket 0029, FR-2/FR-8) so every language inherits it
    with no per-language edit. Unlike the advisory coverage/dep-audit/sast phases
    it is a *hard* gate — its ``passed`` flag is used as-is. In fail-fast mode a
    detected credential short-circuits the whole suite before any language gate
    runs (a leaked secret is the highest-severity defect — fail as early as
    possible); the returned list then holds only the secrets result.
    """
    from gates.secrets import run_secrets_gate
    secrets_result = run_secrets_gate(Path(directory))
    if fail_fast and not secrets_result.passed:
        return [secrets_result]
    results = _language_suite_on_dir(
        language, directory, fail_fast=fail_fast, config=config,
        overrides=overrides, changed_files=changed_files,
        max_workers=max_workers, log_dir=log_dir,
    )
    results.insert(0, secrets_result)
    if fail_fast and not all(r.passed for r in results):
        return results
    # Coverage runs after the language/test gates pass (FR-1), before dep-audit.
    _append_coverage_gate(results, language, directory, standards_path, base_ref)
    from gates.dep_audit import dep_audit_enabled
    if dep_audit_enabled(directory):
        results.append(_dep_audit_model_result(directory))
    # SAST runs last so it never blocks lint/typecheck (ticket 0025, FR-7). In
    # fail-fast mode a failing prior gate already short-circuited above — the
    # solution's documented fail-fast bypass.
    _append_sast_gate(results, directory)
    return results


def _append_sast_gate(results: list[GateResult], directory: str) -> None:
    """Append the SAST phase (Semgrep + Bandit) as the final directory-mode gate.

    In directory mode the scanned worktree also owns its ``.semgrep.yml`` /
    ``bandit.ini`` configs, so ``project_root`` and the scan target are the same
    path. Mirrors the dep-audit precedent: an unexpected infrastructure fault
    degrades to a passing warning rather than breaking the whole suite; a genuine
    BLOCKER finding or tool invocation error still fails the gate via
    ``run_sast_gate``'s own ``passed`` flag.
    """
    try:
        from gates.sast import run_sast_gate
        results.append(run_sast_gate(directory, directory))
    except (ImportError, OSError, ValueError, RuntimeError, TypeError, AttributeError) as exc:
        results.append(GateResult(
            gate="sast", passed=True,
            errors=[GateError(
                message=f"sast gate degraded ({exc})",
                file=None, line=None, column=None,
                code="SAST_GATE_ERROR", severity="warning",
            )],
            duration_ms=0,
        ))
