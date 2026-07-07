"""FR-4: stop_full_gate reports net-new unexplained suppression pragmas.

Builds a real git repo with a `main` branch, adds bare pragmas in the working
tree, and asserts stop_full_gate's suppression section counts them. Reasoned
markers produce no section; non-git dirs fail safe.
"""

from __future__ import annotations

import importlib.util
import subprocess
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


gate = _load("stop_full_gate")


def _repo_with_change(tmp_path: Path, changed_body: str) -> Path:
    repo = tmp_path / "wt"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "d@x.c"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "d"], cwd=repo, check=True)
    (repo / "m.py").write_text("a = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)
    (repo / "m.py").write_text(changed_body, encoding="utf-8")
    return repo


def test_two_net_new_bare_pragmas_are_reported(tmp_path: Path) -> None:
    repo = _repo_with_change(tmp_path, "a = 1\nb = risky()  # noqa\nc = run()  # nosec\n")
    section = gate.unexplained_suppressions(repo)
    assert section, "expected a suppression section"
    assert "net-new unexplained suppression pragma(s): 2" in section[0]


def test_reasoned_markers_produce_no_section(tmp_path: Path) -> None:
    repo = _repo_with_change(
        tmp_path, "a = 1\nb = risky()  # noqa: E501 url\nc = run()  # nosec: needs shell\n"
    )
    assert gate.unexplained_suppressions(repo) == []


def test_no_change_produces_no_section(tmp_path: Path) -> None:
    repo = _repo_with_change(tmp_path, "a = 1\n")
    assert gate.unexplained_suppressions(repo) == []


def test_non_git_dir_fails_safe(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert gate.unexplained_suppressions(plain) == []


def test_suppression_section_surfaces_in_collect_failures(tmp_path: Path) -> None:
    repo = _repo_with_change(tmp_path, "a = 1\nb = risky()  # noqa\n")
    failures = gate.collect_failures(repo)
    assert any("repair-integrity" in f and "suppression" in f for f in failures)


def test_repair_integrity_loads_without_gates_package(tmp_path: Path) -> None:
    module = gate._load_repair_integrity()
    assert module is not None
    assert hasattr(module, "added_suppressions")
