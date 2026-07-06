"""Ticket 0017 — StackName / LanguageResult domain types."""
from __future__ import annotations

from models import GateError, GateResult, LanguageResult, StackName


def _gr(gate: str = "lint", passed: bool = True) -> GateResult:
    errs = [] if passed else [GateError("boom", "f.py", 1, 2, "E1", "error")]
    return GateResult(gate=gate, passed=passed, errors=errs, duration_ms=1)


def test_stackname_is_str_enum_equal_and_hashable() -> None:
    assert StackName.PYTHON == "python"
    assert "python" in {StackName.PYTHON}
    assert StackName("python") is StackName.PYTHON


def test_stackname_canonical_order() -> None:
    assert list(StackName) == [
        StackName.PYTHON,
        StackName.TYPESCRIPT,
        StackName.GO,
        StackName.RUST,
    ]


def test_stackname_set_interop_with_plain_strings() -> None:
    detected = {StackName.PYTHON, StackName.TYPESCRIPT}
    assert {"python", "typescript"}.issubset(detected)


def test_language_result_to_dict_uses_plain_string_language() -> None:
    lr = LanguageResult(StackName.PYTHON, [_gr()])
    d = lr.to_dict()
    assert d["language"] == "python"
    assert not isinstance(d["language"], StackName) or d["language"] == "python"
    assert d["language"].__class__ is str


def test_language_result_to_dict_nests_gate_result_dicts() -> None:
    lr = LanguageResult(StackName.TYPESCRIPT, [_gr("lint"), _gr("test", passed=False)])
    d = lr.to_dict()
    assert [g["gate"] for g in d["results"]] == ["lint", "test"]
    assert d["results"][1]["passed"] is False
    assert d["results"][1]["errors"][0]["code"] == "E1"
