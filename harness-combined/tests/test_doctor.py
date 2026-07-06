"""Tests for gates/doctor.py — the per-language gate `/doctor` (ticket 0022).

Written before the implementation (TDD). Tool probing is exercised via
monkeypatched ``shutil.which`` / ``subprocess.run`` so the suite never depends on
what is actually installed on the machine running it.
"""
from __future__ import annotations

import ast
import subprocess
import types
from pathlib import Path

import pytest

from gates import doctor
from gates.doctor import (
    LANGUAGE_SPECS,
    DoctorError,
    ToolStatus,
    format_report,
    run_doctor,
)
from gates.go import REQUIRED_TOOLS as GO_TOOLS
from gates.python import REQUIRED_TOOLS as PYTHON_TOOLS
from gates.rust import REQUIRED_TOOLS as RUST_TOOLS
from gates.typescript import REQUIRED_TOOLS as TS_TOOLS

REPO_ROOT = Path(__file__).resolve().parent.parent


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> types.SimpleNamespace:
    """Stand in for a subprocess.CompletedProcess with just the fields we read."""
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _probe_env(monkeypatch, *, on_path: bool, run):
    """Wire ``shutil.which`` + ``subprocess.run`` inside gates.doctor."""
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/x" if on_path else None)
    monkeypatch.setattr(doctor.subprocess, "run", run)


# ── FR-1: language detection ──────────────────────────────────────────────────

def test_detect_python_from_pyproject(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    _probe_env(monkeypatch, on_path=False, run=lambda *a, **k: _completed(0))
    report = run_doctor(str(tmp_path))
    assert [lr.language for lr in report.languages] == ["Python"]
    assert report.languages[0].manifest == "pyproject.toml"


def test_detect_typescript_from_package_json(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text("{}\n")
    _probe_env(monkeypatch, on_path=False, run=lambda *a, **k: _completed(0))
    report = run_doctor(str(tmp_path))
    assert [lr.language for lr in report.languages] == ["TypeScript"]


def test_detect_both_python_and_typescript(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    (tmp_path / "package.json").write_text("{}\n")
    _probe_env(monkeypatch, on_path=False, run=lambda *a, **k: _completed(0))
    report = run_doctor(str(tmp_path))
    assert {lr.language for lr in report.languages} == {"Python", "TypeScript"}


def test_detect_none_when_no_manifest(tmp_path, monkeypatch):
    _probe_env(monkeypatch, on_path=False, run=lambda *a, **k: _completed(0))
    report = run_doctor(str(tmp_path))
    assert report.languages == []


# ── FR-2: registry built from REQUIRED_TOOLS imports ──────────────────────────

def test_registry_matches_required_tools_exports():
    by_lang = {spec.language: tuple(spec.tools) for spec in LANGUAGE_SPECS}
    assert by_lang["Python"] == tuple(PYTHON_TOOLS)
    assert by_lang["TypeScript"] == tuple(TS_TOOLS)
    assert by_lang["Go"] == tuple(GO_TOOLS)
    assert by_lang["Rust"] == tuple(RUST_TOOLS)


def test_every_required_tool_has_an_explicit_probe():
    """Durability guard for the clippy fix: every REQUIRED_TOOLS name must have
    an explicit `_PROBES` entry. Without one it falls back to a bare
    `[name, "--version"]` probe, silently reintroducing the bug where a tool the
    gate invokes indirectly (a subcommand shim, a python module) is probed as a
    non-existent bare PATH executable and always reported missing."""
    all_required = set(PYTHON_TOOLS) | set(TS_TOOLS) | set(GO_TOOLS) | set(RUST_TOOLS)
    unmapped = all_required - set(doctor._PROBES)
    assert not unmapped, f"REQUIRED_TOOLS with no explicit _PROBES entry: {sorted(unmapped)}"


# ── FR-3: probe result parsing (status matrix) ────────────────────────────────

def test_probe_missing_when_not_on_path(monkeypatch):
    # A DIRECT tool (bare PATH executable) absent from PATH is MISSING without
    # ever launching a subprocess.
    _probe_env(monkeypatch, on_path=False, run=lambda *a, **k: pytest.fail("must not run"))
    result = doctor._probe_tool("cargo")
    assert result.status is ToolStatus.MISSING
    assert result.version is None


def test_probe_found_from_stdout(monkeypatch):
    _probe_env(monkeypatch, on_path=True, run=lambda *a, **k: _completed(0, stdout="ruff 0.5.0\n"))
    result = doctor._probe_tool("ruff")
    assert result.status is ToolStatus.FOUND
    assert result.version == "ruff 0.5.0"
    assert result.install_hint is None


def test_probe_found_from_stderr_only(monkeypatch):
    _probe_env(monkeypatch, on_path=True, run=lambda *a, **k: _completed(0, stderr="go version go1.21\n"))
    result = doctor._probe_tool("go")
    assert result.status is ToolStatus.FOUND
    assert result.version == "go version go1.21"


def test_probe_found_error_on_nonzero_with_output(monkeypatch):
    # A DIRECT executable present on PATH but exiting non-zero is FOUND_ERROR.
    _probe_env(monkeypatch, on_path=True, run=lambda *a, **k: _completed(2, stderr="boom\n"))
    result = doctor._probe_tool("staticcheck")
    assert result.status is ToolStatus.FOUND_ERROR


def test_probe_missing_on_filenotfound(monkeypatch):
    def _raise(*a, **k):
        raise FileNotFoundError

    _probe_env(monkeypatch, on_path=True, run=_raise)
    result = doctor._probe_tool("cargo")
    assert result.status is ToolStatus.MISSING


def test_probe_timeout(monkeypatch):
    def _raise(*a, **k):
        raise subprocess.TimeoutExpired(cmd="cargo --version", timeout=5)

    _probe_env(monkeypatch, on_path=True, run=_raise)
    result = doctor._probe_tool("cargo")
    assert result.status is ToolStatus.TIMEOUT
    assert result.version is None


def test_probe_uses_five_second_timeout(monkeypatch):
    captured: dict[str, object] = {}

    def _run(cmd, **kwargs):
        captured.update(kwargs)
        captured["cmd"] = cmd
        return _completed(0, stdout="cargo 1.75\n")

    _probe_env(monkeypatch, on_path=True, run=_run)
    doctor._probe_tool("cargo")
    assert captured["timeout"] == 5
    assert captured["cmd"] == ["cargo", "--version"]


def test_probe_clippy_targets_cargo_clippy_shim(monkeypatch):
    # Regression: bare `clippy` is never on PATH — the rustup shim is
    # `cargo-clippy` (the gate runs `cargo clippy`). The probe must target it.
    which_calls: list[str] = []

    def _which(name):
        which_calls.append(name)
        return "/usr/bin/cargo-clippy" if name == "cargo-clippy" else None

    captured: dict[str, object] = {}

    def _run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _completed(0, stdout="clippy 0.1.75\n")

    monkeypatch.setattr(doctor.shutil, "which", _which)
    monkeypatch.setattr(doctor.subprocess, "run", _run)
    result = doctor._probe_tool("clippy")
    assert "cargo-clippy" in which_calls
    assert captured["cmd"] == ["cargo-clippy", "--version"]
    assert result.status is ToolStatus.FOUND


def test_probe_module_tool_missing_when_not_importable(monkeypatch):
    # `python -m mypy` exiting non-zero means the module is not installed in the
    # gate's interpreter — genuinely MISSING, not FOUND_ERROR.
    def _run(cmd, **kwargs):
        assert cmd[:3] == [doctor.sys.executable, "-m", "mypy"]
        return _completed(1, stderr="No module named mypy\n")

    monkeypatch.setattr(doctor.subprocess, "run", _run)
    result = doctor._probe_tool("mypy")
    assert result.status is ToolStatus.MISSING
    assert result.install_hint == "pip install mypy"


def test_probe_npx_tool_missing_when_not_resolvable(monkeypatch):
    # `npx --no-install tsc` exiting non-zero means tsc is not locally
    # resolvable (and npx is forbidden from fetching it) — MISSING.
    def _run(cmd, **kwargs):
        assert cmd == ["npx", "--no-install", "tsc", "--version"]
        return _completed(1, stderr="npx: could not determine executable\n")

    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/npx")
    monkeypatch.setattr(doctor.subprocess, "run", _run)
    result = doctor._probe_tool("tsc")
    assert result.status is ToolStatus.MISSING


# ── FR-4: integration — table tokens ──────────────────────────────────────────

def test_run_doctor_table_contains_status_tokens(tmp_path, monkeypatch):
    # Use DIRECT-probed languages (Go, Rust) so all three tokens are reachable:
    # a healthy binary (found), a present-but-erroring binary (found (error)),
    # and one absent from PATH (missing).
    (tmp_path / "go.mod").write_text("module x\n")
    (tmp_path / "Cargo.toml").write_text("[package]\n")

    present = {"go", "cargo", "cargo-clippy"}  # staticcheck deliberately absent

    def _which(name):
        return "/usr/bin/x" if name in present else None

    def _run(cmd, **kwargs):
        exe = cmd[0]
        if exe == "cargo-clippy":
            return _completed(101, stderr="clippy: toolchain error\n")  # found (error)
        return _completed(0, stdout=f"{exe} 1.0\n")                     # found

    monkeypatch.setattr(doctor.shutil, "which", _which)
    monkeypatch.setattr(doctor.subprocess, "run", _run)
    text = format_report(run_doctor(str(tmp_path)))
    assert "found (error)" in text  # clippy, probed via cargo-clippy
    assert "missing" in text        # staticcheck, not on PATH
    assert any(line.strip().endswith("1.0") for line in text.splitlines())  # found + version


# ── FR-5: install hints ───────────────────────────────────────────────────────

def test_missing_tool_has_install_hint(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    # Python tools are module-probed; a non-zero `python -m <tool>` marks them
    # MISSING (not importable), which must carry an install hint.
    _probe_env(monkeypatch, on_path=False,
               run=lambda *a, **k: _completed(1, stderr="No module named x\n"))
    report = run_doctor(str(tmp_path))
    hints = [t.install_hint for t in report.languages[0].tools]
    assert all(h for h in hints), "every missing tool must carry a non-empty install hint"


# ── FR-6: any_missing signal ──────────────────────────────────────────────────

def test_any_missing_true_when_tool_absent(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    _probe_env(monkeypatch, on_path=False,
               run=lambda *a, **k: _completed(1, stderr="No module named x\n"))
    assert run_doctor(str(tmp_path)).any_missing is True


def test_any_missing_false_when_all_present(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    _probe_env(monkeypatch, on_path=True, run=lambda *a, **k: _completed(0, stdout="1.0\n"))
    assert run_doctor(str(tmp_path)).any_missing is False


def test_any_missing_true_on_timeout(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\n")

    def _raise(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=5)

    _probe_env(monkeypatch, on_path=True, run=_raise)
    assert run_doctor(str(tmp_path)).any_missing is True


# ── FR-7: project_root override ───────────────────────────────────────────────

def test_project_root_scans_given_dir_not_cwd(tmp_path, monkeypatch):
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "go.mod").write_text("module x\n")
    # CWD (tmp_path) has no manifest; the explicit root does.
    monkeypatch.chdir(tmp_path)
    _probe_env(monkeypatch, on_path=False, run=lambda *a, **k: _completed(0))
    report = run_doctor(str(other))
    assert [lr.language for lr in report.languages] == ["Go"]


# ── FR-8: no supported languages ──────────────────────────────────────────────

def test_no_languages_message_and_clean_signal(tmp_path, monkeypatch):
    _probe_env(monkeypatch, on_path=False, run=lambda *a, **k: _completed(0))
    report = run_doctor(str(tmp_path))
    assert report.languages == []
    assert report.any_missing is False
    assert "no supported languages detected" in format_report(report)


# ── FR-8a: path validation before any probe ───────────────────────────────────

def test_non_directory_raises_before_subprocess(tmp_path, monkeypatch):
    bogus = tmp_path / "nope.txt"
    bogus.write_text("x")

    def _boom(*a, **k):
        raise AssertionError("no subprocess may run for an invalid root")

    monkeypatch.setattr(doctor.subprocess, "run", _boom)
    with pytest.raises(DoctorError):
        run_doctor(str(bogus))


def test_path_outside_allowed_root_raises(tmp_path):
    inside = tmp_path / "proj"
    inside.mkdir()
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    with pytest.raises(DoctorError):
        run_doctor(str(inside), allowed_root=str(allowed))


# ── REQUIRED_TOOLS CI invariant (structural AST check, not string grep) ────────

def _subprocess_arg_literals(module_path: Path) -> set[str]:
    """String literals that are elements of any list in the module *except* the
    REQUIRED_TOOLS declaration itself — i.e. the tool names actually handed to
    subprocess argument lists."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    excluded_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            targets: list[ast.expr] = [node.target]
            value = node.value
        elif isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        else:
            continue
        if value is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "REQUIRED_TOOLS":
                excluded_ids.add(id(value))
    literals: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.List) and id(node) not in excluded_ids:
            for element in node.elts:
                if isinstance(element, ast.Constant) and isinstance(element.value, str):
                    literals.add(element.value)
    return literals


@pytest.mark.parametrize(
    "module_name, required",
    [
        ("python", PYTHON_TOOLS),
        ("typescript", TS_TOOLS),
        ("go", GO_TOOLS),
        ("rust", RUST_TOOLS),
    ],
)
def test_required_tools_appear_in_subprocess_args(module_name, required):
    module_path = REPO_ROOT / "gates" / f"{module_name}.py"
    invoked = _subprocess_arg_literals(module_path)
    missing = [tool for tool in required if tool not in invoked]
    assert not missing, (
        f"gates/{module_name}.py declares REQUIRED_TOOLS {missing} that never "
        f"appear in a subprocess argument list — the registry has drifted."
    )
