"""Ticket 0017 — uniform one-level, symlink-safe, manifest-only _detect_stacks."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mcp")

from models import StackName  # noqa: E402 - after importorskip guard
from server import _detect_stacks  # noqa: E402 - after importorskip guard


def test_root_manifests_detected_in_canonical_order(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "package.json").write_text("{}")
    assert _detect_stacks(str(tmp_path)) == [StackName.PYTHON, StackName.TYPESCRIPT]


def test_one_level_subdir_manifests_detected(tmp_path: Path) -> None:
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "tsconfig.json").write_text("{}")
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "Cargo.toml").write_text("")
    detected = set(_detect_stacks(str(tmp_path)))
    assert {StackName.TYPESCRIPT, StackName.RUST}.issubset(detected)


def test_manifest_two_levels_deep_not_detected(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    (deep / "pyproject.toml").write_text("")
    assert _detect_stacks(str(tmp_path)) == []


def test_raw_python_file_without_manifest_not_detected(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n")
    assert _detect_stacks(str(tmp_path)) == []


def test_no_manifests_returns_empty(tmp_path: Path) -> None:
    assert _detect_stacks(str(tmp_path)) == []


def test_symlinked_subdir_escaping_root_is_skipped(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "pyproject.toml").write_text("")
    external = tmp_path / "external"
    external.mkdir()
    (external / "Cargo.toml").write_text("")
    try:
        (root / "vendored").symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported on this platform")
    detected = _detect_stacks(str(root))
    assert StackName.PYTHON in detected
    assert StackName.RUST not in detected  # escaped symlink not followed


def test_node_modules_is_not_scanned(tmp_path: Path) -> None:
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "package.json").write_text("{}")
    assert _detect_stacks(str(tmp_path)) == []
