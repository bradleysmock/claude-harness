from __future__ import annotations
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


def run_suite_on_dir(
    language: str,
    directory: str,
    fail_fast: bool = True,
) -> list[GateResult]:
    """Directory mode: run gates on actual project files (worktree or project dir)."""
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
