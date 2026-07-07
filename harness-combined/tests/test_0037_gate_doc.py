"""Ticket 0037 — content verification that commands/gate.md documents SARIF output.

The `/gate` command is a markdown instruction file, so its contract is verified by
asserting the doc names the flag, the opt-in key, the scope restriction, and the
non-fatal signal — the structural substrings a reader (or the model executing the
command) relies on.
"""
from __future__ import annotations

from pathlib import Path

import pytest

GATE_DOC = Path(__file__).resolve().parent.parent / "commands" / "gate.md"


@pytest.fixture(scope="module")
def doc_text() -> str:
    return GATE_DOC.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "token",
    [
        "--sarif",
        "sarif_output",
        "results.sarif",
        "_standards.md",
        "sarif_write_failed",
        "emit_sarif=True",
        "2.1.0",
    ],
)
def test_gate_doc_mentions_sarif_token(doc_text: str, token: str) -> None:
    assert token in doc_text, f"commands/gate.md must document {token!r}"


def test_gate_doc_documents_standards_scope_restriction(doc_text: str) -> None:
    # The worktree's _standards.md must be documented as having no authority.
    lowered = doc_text.lower()
    assert "no authority" in lowered
    assert "opt-in" in lowered


def test_gate_doc_documents_optin_regex(doc_text: str) -> None:
    assert r"^\s*sarif_output\s*:\s*true\s*$" in doc_text
