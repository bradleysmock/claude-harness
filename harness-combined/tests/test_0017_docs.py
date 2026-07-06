"""Ticket 0017 — doc updates for polyglot gate reporting (FR-6/FR-7 surfaces)."""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def test_gate_command_documents_plural_languages_header() -> None:
    text = _read("commands/gate.md")
    assert "**Languages detected**" in text
    assert "## <language> / <gate-name>" in text


def test_gate_command_documents_polyglot_summary_line() -> None:
    text = _read("commands/gate.md")
    assert "python=PASS typescript=FAIL" in text


def test_gate_command_documents_config_error_fail_closed() -> None:
    text = _read("commands/gate.md")
    assert "CONFIG_ERROR" in text


def test_critic_brief_documents_language_gate_heading() -> None:
    text = _read("context/critic-brief.md")
    assert "## <language> / <gate-name>" in text
