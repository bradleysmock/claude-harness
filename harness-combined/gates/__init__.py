from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from models import GateError, GateResult


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


def run_suite_for(
    language: str,
    implementation: str,
    tests: str,
    project_root: str,
) -> list[GateResult]:
    """Text mode: run gates on generated code in a temp dir (fail-fast)."""
    if language == "python":
        from gates.python import run_python_suite
        return run_python_suite(implementation, tests, project_root)
    elif language == "typescript":
        from gates.typescript import run_typescript_suite
        return run_typescript_suite(implementation, tests, project_root)
    elif language == "go":
        from gates.go import run_go_suite
        return run_go_suite(implementation, tests, project_root)
    elif language == "rust":
        from gates.rust import run_rust_suite
        return run_rust_suite(implementation, tests, project_root)
    else:
        raise ValueError(f"Unsupported language: {language!r}")


def _language_suite_on_dir(
    language: str,
    directory: str,
    fail_fast: bool = True,
) -> list[GateResult]:
    """Dispatch to a single language's directory-mode gate suite."""
    if language == "python":
        from gates.python import run_python_suite_on_dir
        return run_python_suite_on_dir(directory, fail_fast=fail_fast)
    elif language == "typescript":
        from gates.typescript import run_typescript_suite_on_dir
        return run_typescript_suite_on_dir(directory, fail_fast=fail_fast)
    elif language == "go":
        from gates.go import run_go_suite_on_dir
        return run_go_suite_on_dir(directory, fail_fast=fail_fast)
    elif language == "rust":
        from gates.rust import run_rust_suite_on_dir
        return run_rust_suite_on_dir(directory, fail_fast=fail_fast)
    else:
        raise ValueError(f"Unsupported language: {language!r}")


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
) -> list[GateResult]:
    """Directory mode: language gates, then a single post-language dep-audit phase.

    The dep-audit phase runs once, after the language-specific phases, with no
    per-language branching. In fail-fast mode a failing language gate
    short-circuits before dep-audit runs. The phase is skipped entirely when
    gate config disables it (FR-10 — selective skip).
    """
    results = _language_suite_on_dir(language, directory, fail_fast=fail_fast)
    if fail_fast and not all(r.passed for r in results):
        return results
    from gates.dep_audit import dep_audit_enabled
    if dep_audit_enabled(directory):
        results.append(_dep_audit_model_result(directory))
    return results
