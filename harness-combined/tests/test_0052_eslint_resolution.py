"""FR-2: per-write JS/TS lint resolves project-local eslint via npx.

gate_javascript_typescript() must:
  * run `npx --no-install eslint` from the file's project root when
    node_modules/.bin/eslint exists there,
  * fall back to a global eslint on PATH otherwise,
  * skip silently (return []) when neither exists.

run_tool is monkeypatched so the branch selection is tested deterministically
without needing a real node/npx toolchain installed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HOOKS = Path(__file__).parent.parent / "hooks"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = _load("post_write_gate")


def _make_project(tmp_path: Path, local_eslint: bool) -> Path:
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "package.json").write_text("{}\n", encoding="utf-8")
    if local_eslint:
        bindir = root / "node_modules" / ".bin"
        bindir.mkdir(parents=True)
        (bindir / "eslint").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    ts_file = root / "src" / "a.ts"
    ts_file.write_text("const x = 1\n", encoding="utf-8")
    return ts_file


# --- project-root resolver -------------------------------------------------

def test_project_root_found_from_nested_file(tmp_path):
    ts_file = _make_project(tmp_path, local_eslint=False)
    assert gate._js_project_root(str(ts_file)) == (tmp_path / "proj").resolve()


def test_project_root_none_without_package_json(tmp_path):
    deep = tmp_path / "no_pkg" / "a" / "b"
    deep.mkdir(parents=True)
    f = deep / "a.ts"
    f.write_text("const x = 1\n", encoding="utf-8")
    assert gate._js_project_root(str(f)) is None


# --- local eslint via npx --------------------------------------------------

def test_local_eslint_runs_via_npx_from_project_root(tmp_path, monkeypatch):
    ts_file = _make_project(tmp_path, local_eslint=True)
    captured: dict = {}

    def fake_run_tool(executable, args, cwd=None):
        captured["executable"] = executable
        captured["args"] = args
        captured["cwd"] = cwd
        return 1, "a.ts: 1:7 error no-unused-vars"

    monkeypatch.setattr(gate, "run_tool", fake_run_tool)
    findings = gate.gate_javascript_typescript(str(ts_file))

    assert captured["executable"] == "npx"
    assert captured["args"][:2] == ["--no-install", "eslint"]
    assert str(ts_file) in captured["args"]
    assert Path(captured["cwd"]) == (tmp_path / "proj").resolve()
    assert findings and "eslint" in findings[0]


# --- global fallback -------------------------------------------------------

def test_global_eslint_fallback(tmp_path, monkeypatch):
    ts_file = _make_project(tmp_path, local_eslint=False)
    calls: list[str] = []

    def fake_run_tool(executable, args, cwd=None):
        calls.append(executable)
        return 1, "some finding"

    monkeypatch.setattr(gate, "run_tool", fake_run_tool)
    monkeypatch.setattr(gate.shutil, "which", lambda name: "/usr/bin/eslint" if name == "eslint" else None)
    findings = gate.gate_javascript_typescript(str(ts_file))

    assert calls == ["eslint"], "global eslint should be invoked directly when no local install"
    assert findings and "eslint" in findings[0]


# --- silent skip -----------------------------------------------------------

def test_skips_silently_without_any_eslint(tmp_path, monkeypatch):
    ts_file = _make_project(tmp_path, local_eslint=False)
    called = False

    def fake_run_tool(executable, args, cwd=None):
        nonlocal called
        called = True
        return 0, ""

    monkeypatch.setattr(gate, "run_tool", fake_run_tool)
    monkeypatch.setattr(gate.shutil, "which", lambda name: None)
    findings = gate.gate_javascript_typescript(str(ts_file))

    assert findings == []
    assert called is False, "no eslint anywhere → no subprocess, no findings"
