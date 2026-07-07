"""Ticket 0047 — stop_full_gate honest handling of vendored trees & zero stacks.

Covers FR-3 (recursive source probes exclude vendored dirs) and FR-4 (zero-stack
review-ready worktree emits a one-line stderr warning, exit 0), plus the
exclusion-list consistency guard between the hook and server.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).parent.parent / "hooks"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = _load("stop_full_gate")


# --- FR-3: vendored exclusion in recursive probes ---------------------------

def test_node_modules_only_py_not_detected_as_python(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}\n")
    (tmp_path / "tsconfig.json").write_text("{}\n")
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "shim.py").write_text("x = 1\n")
    stacks = gate.detect_stacks(tmp_path)
    assert "python" not in stacks
    assert "typescript" in stacks


def test_real_top_level_py_still_detected(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n")
    assert gate.detect_stacks(tmp_path) == ["python"]


def test_has_source_file_prunes_vendored_dirs(tmp_path: Path) -> None:
    for skip in (".venv", "node_modules", "__pycache__"):
        d = tmp_path / skip
        d.mkdir()
        (d / "buried.py").write_text("x = 1\n")
    assert gate._has_source_file(tmp_path, ".py") is False
    (tmp_path / "surfaced.py").write_text("x = 1\n")
    assert gate._has_source_file(tmp_path, ".py") is True


# --- exclusion-list consistency guard ---------------------------------------

def test_scan_skip_matches_server() -> None:
    pytest.importorskip("mcp")
    import server  # noqa: E402 - after importorskip guard

    assert gate._SCAN_SKIP == server._SCAN_SKIP


# --- FR-4: zero-stack review-ready worktree warns and exits 0 ---------------

def _make_review_ready_worktree(project_root: Path, slug: str) -> Path:
    tickets = project_root / ".tickets"
    ticket_dir = tickets / slug
    ticket_dir.mkdir(parents=True)
    (ticket_dir / "status.md").write_text(f"status: review-ready\nticket: {slug}\n")
    (tickets / ".active").write_text(slug + "\n")
    worktree = project_root / ".worktrees" / slug
    worktree.mkdir(parents=True)
    return worktree


def test_zero_stack_worktree_warns_and_exits_zero(tmp_path, monkeypatch, capsys) -> None:
    slug = "9999-empty"
    worktree = _make_review_ready_worktree(tmp_path, slug)
    # No manifests and no source files → zero detected stacks.
    assert gate.detect_stacks(worktree) == []

    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"cwd": str(tmp_path)})))
    rc = gate.main()
    err = capsys.readouterr().err
    assert rc == 0
    assert slug in err
    assert "no supported stack" in err.lower()


def test_zero_stack_worktree_still_runs_suppression_gate(tmp_path, monkeypatch, capsys) -> None:
    # The zero-stack warning must NOT disable the stack-independent
    # repair-integrity check: a net-new unexplained suppression in an
    # unsupported worktree still blocks (exit 2), and the warning still prints.
    slug = "9998-empty-but-dirty"
    worktree = _make_review_ready_worktree(tmp_path, slug)
    assert gate.detect_stacks(worktree) == []

    monkeypatch.setattr(
        gate, "unexplained_suppressions",
        lambda wt: ["net-new unexplained suppression pragma(s): 1"],
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"cwd": str(tmp_path)})))
    rc = gate.main()
    err = capsys.readouterr().err
    assert rc == 2  # integrity gate still enforced despite zero stacks
    assert "no supported stack" in err.lower()  # warning still emitted
    assert "suppression" in err.lower()
