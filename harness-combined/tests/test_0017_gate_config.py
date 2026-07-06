"""Ticket 0017 — _standards.md [gates] override parser (fail-closed)."""
from __future__ import annotations

from pathlib import Path

import pytest

from gates.config import ConfigError, load_gate_overrides


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "_standards.md"
    p.write_text(body, encoding="utf-8")
    return p


def test_config_error_is_value_error() -> None:
    assert issubclass(ConfigError, ValueError)


def test_valid_override_gates_info_fence(tmp_path: Path) -> None:
    p = _write(tmp_path, '```gates\npython.lint = "ruff check . --select E,F"\n```\n')
    assert load_gate_overrides(p) == {
        "python": {"lint": ["ruff", "check", ".", "--select", "E,F"]}
    }


def test_valid_override_marker_line_fence(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        "# Standards\n\n```\n[gates]\ntypescript.test = \"npm test\"\n```\n",
    )
    assert load_gate_overrides(p) == {"typescript": {"test": ["npm", "test"]}}


def test_quoted_inner_arg_survives(tmp_path: Path) -> None:
    p = _write(tmp_path, "```gates\npython.lint = \"ruff check --config 'a b.toml'\"\n```\n")
    assert load_gate_overrides(p) == {
        "python": {"lint": ["ruff", "check", "--config", "a b.toml"]}
    }


def test_comments_and_blank_lines_skipped(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        '```gates\n# a comment\n\npython.test = "pytest -q"\n```\n',
    )
    assert load_gate_overrides(p) == {"python": {"test": ["pytest", "-q"]}}


def test_missing_gates_block_returns_empty(tmp_path: Path) -> None:
    p = _write(tmp_path, "# Standards\n\nNo gates here.\n")
    assert load_gate_overrides(p) == {}


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_gate_overrides(tmp_path / "nope.md") == {}


def test_arg0_path_traversal_rejected(tmp_path: Path) -> None:
    p = _write(tmp_path, '```gates\npython.lint = "../evil check"\n```\n')
    with pytest.raises(ConfigError):
        load_gate_overrides(p)


def test_arg0_absolute_path_rejected(tmp_path: Path) -> None:
    p = _write(tmp_path, '```gates\npython.lint = "/usr/bin/evil check"\n```\n')
    with pytest.raises(ConfigError):
        load_gate_overrides(p)


def test_arg0_backtick_rejected(tmp_path: Path) -> None:
    p = _write(tmp_path, '```gates\npython.lint = "ru`nc` check"\n```\n')
    with pytest.raises(ConfigError):
        load_gate_overrides(p)


def test_too_many_args_rejected(tmp_path: Path) -> None:
    big = " ".join(f"a{i}" for i in range(40))
    p = _write(tmp_path, f'```gates\npython.lint = "ruff {big}"\n```\n')
    with pytest.raises(ConfigError):
        load_gate_overrides(p)


def test_unmatched_inner_quote_rejected(tmp_path: Path) -> None:
    p = _write(tmp_path, "```gates\npython.lint = \"ruff check '\"\n```\n")
    with pytest.raises(ConfigError):
        load_gate_overrides(p)


def test_empty_value_rejected(tmp_path: Path) -> None:
    p = _write(tmp_path, '```gates\npython.lint = ""\n```\n')
    with pytest.raises(ConfigError):
        load_gate_overrides(p)


def test_unknown_language_rejected(tmp_path: Path) -> None:
    p = _write(tmp_path, '```gates\ncobol.lint = "gnucobol"\n```\n')
    with pytest.raises(ConfigError):
        load_gate_overrides(p)


def test_missing_gate_segment_rejected(tmp_path: Path) -> None:
    p = _write(tmp_path, '```gates\npython = "ruff check"\n```\n')
    with pytest.raises(ConfigError):
        load_gate_overrides(p)


def test_unknown_gate_name_rejected(tmp_path: Path) -> None:
    # 'typecheck' is a typo — the real Python gate is 'type_check'. A misspelled
    # gate must fail closed, not silently no-op.
    p = _write(tmp_path, '```gates\npython.typecheck = "mypy --strict ."\n```\n')
    with pytest.raises(ConfigError):
        load_gate_overrides(p)


def test_gate_valid_for_wrong_language_rejected(tmp_path: Path) -> None:
    # 'lint' is a real gate — but not for Go (build/vet/test).
    p = _write(tmp_path, '```gates\ngo.lint = "golangci-lint run"\n```\n')
    with pytest.raises(ConfigError):
        load_gate_overrides(p)


def test_go_build_override_accepted(tmp_path: Path) -> None:
    p = _write(tmp_path, '```gates\ngo.build = "go build ./..."\n```\n')
    assert load_gate_overrides(p) == {"go": {"build": ["go", "build", "./..."]}}


def test_unquoted_value_rejected(tmp_path: Path) -> None:
    p = _write(tmp_path, "```gates\npython.lint = ruff check\n```\n")
    with pytest.raises(ConfigError):
        load_gate_overrides(p)
