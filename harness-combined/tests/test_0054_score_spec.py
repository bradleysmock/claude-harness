"""Unit + integration tests for the score-spec mechanical validator (ticket 0054).

The validator ships at ``validators/score_spec.py`` (a tracked, plugin-shipped
path). It is a standalone CLI script, so the module is loaded from its file
path via importlib rather than a normal package import — mirrors
``tests/test_standards_validator.py``.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from gates.spec_remediate import RECIPE

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "validators" / "score_spec.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("score_spec", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec — score_spec.py's frozen dataclasses combined with
    # `from __future__ import annotations` need the module resolvable via
    # sys.modules during class definition (see the identical fix in
    # score_spec.py's own _load_spec_remediate()).
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ss = _load_module()

# --- fixtures ------------------------------------------------------------------

CLEAN_REQUIREMENTS = """# Requirements

## Functional Requirements

1. The system must accept a ticket directory path.
2. The system must reject a missing `solution.md` with exit code 2.
3. The CLI must print the report block in the documented order.

## Acceptance Criteria

- A clean fixture prints six PASS lines and exits 0.
- A missing file exits 2 with a stderr reason.
"""

CLEAN_SOLUTION = """# Solution

## Test Plan

| Requirement | Test Type | Scenario |
|-------------|-----------|----------|
| FR-1        | Unit      | accepts a path |
| FR-2        | Unit      | missing file |
| FR-3        | Integration | report order |

## Implementation Order

1. Write the tests.
2. Write the validator.
"""


def _fr_count_fixture(n: int) -> str:
    items = "\n".join(f"{i}. The system must do thing {i}." for i in range(1, n + 1))
    return f"# Requirements\n\n## Functional Requirements\n\n{items}\n\n## Acceptance Criteria\n\n- A.\n- B.\n"


def _result(checks: tuple, name: str):
    """The single CheckResult named ``name`` within ``checks``.

    Centralizes the repeated `next(c for c in checks if c.name == ...)`
    lookup used throughout this file's assertions.
    """
    return next(c for c in checks if c.name == name)


# --- FR-1: FR count --------------------------------------------------------------


def test_fr_count_below_minimum_blocks() -> None:
    requirements = _fr_count_fixture(2)
    report = ss.score(requirements, CLEAN_SOLUTION)
    result = _result(report.checks, "FR count")
    assert result.verdict == "BLOCK"


def test_fr_count_at_minimum_passes() -> None:
    requirements = _fr_count_fixture(3)
    solution = """# Solution

## Test Plan

| Requirement | Test Type | Scenario |
|-------------|-----------|----------|
| FR-1 | Unit | a |
| FR-2 | Unit | b |
| FR-3 | Unit | c |

## Implementation Order

1. Step one.
"""
    report = ss.score(requirements, solution)
    result = _result(report.checks, "FR count")
    assert result.verdict == "PASS"


def test_fr_count_ignores_nfr_and_nested_sublist() -> None:
    requirements = """# Requirements

## Functional Requirements

1. The system must do A.
2. The system must do B.
   1. A nested clarifying sub-point, not a separate FR.

## Non-Functional Requirements

1. The system must be fast.
2. The system must be secure.

## Acceptance Criteria

- A.
- B.
"""
    report = ss.score(requirements, CLEAN_SOLUTION)
    result = _result(report.checks, "FR count")
    # Only FR-1 and FR-2 count — the nested sub-item and the NFRs do not.
    assert result.verdict == "BLOCK"


# --- FR-2: imperative language ----------------------------------------------------


def test_nested_sublist_weak_modal_attributed_to_owning_fr_not_colliding_number() -> None:
    # The nested "1." sub-item's number collides with the real FR-1. Its weak
    # modal must be attributed to FR-2 (the item it's nested under), never to
    # FR-1, and must not be dropped as a phantom "new" FR either.
    requirements = """# Requirements

## Functional Requirements

1. The system must do A.
2. The system must do B.
   1. A nested clarifying note that should be read carefully.
3. The system must do C.

## Acceptance Criteria

- A.
- B.
"""
    report = ss.score(requirements, CLEAN_SOLUTION)
    result = _result(report.checks, "Imperative language")
    assert result.verdict == "BLOCK"
    assert any(d.startswith("FR-2:") for d in result.details)
    assert not any(d.startswith("FR-1:") for d in result.details)


def test_weak_modal_in_fr_blocks() -> None:
    requirements = """# Requirements

## Functional Requirements

1. The system must do A.
2. The system should do B.
3. The system must do C.

## Acceptance Criteria

- A.
- B.
"""
    report = ss.score(requirements, CLEAN_SOLUTION)
    result = _result(report.checks, "Imperative language")
    assert result.verdict == "BLOCK"
    assert any("FR-2" in d for d in result.details)


def test_weak_modal_inside_inline_code_passes() -> None:
    requirements = """# Requirements

## Functional Requirements

1. The system must document the `should`/`may`/`could` remediation words.
2. The system must do B.
3. The system must do C.

## Acceptance Criteria

- A.
- B.
"""
    report = ss.score(requirements, CLEAN_SOLUTION)
    result = _result(report.checks, "Imperative language")
    assert result.verdict == "PASS"


def test_fr_with_no_modal_passes() -> None:
    requirements = """# Requirements

## Functional Requirements

1. The validator emits six mechanical check lines.
2. The system must do B.
3. The system must do C.

## Acceptance Criteria

- A.
- B.
"""
    report = ss.score(requirements, CLEAN_SOLUTION)
    result = _result(report.checks, "Imperative language")
    assert result.verdict == "PASS"


# --- FR-3: test-plan coverage ------------------------------------------------------


def test_fr_missing_from_test_plan_blocks() -> None:
    requirements = _fr_count_fixture(3)
    solution = """# Solution

## Test Plan

| Requirement | Test Type | Scenario |
|-------------|-----------|----------|
| FR-1 | Unit | a |
| FR-2 | Unit | b |

## Implementation Order

1. Step one.
"""
    report = ss.score(requirements, solution)
    result = _result(report.checks, "Test-plan coverage")
    assert result.verdict == "BLOCK"
    assert any("FR-3" in d for d in result.details)


def test_phantom_test_plan_fr_blocks() -> None:
    requirements = _fr_count_fixture(3)
    solution = """# Solution

## Test Plan

| Requirement | Test Type | Scenario |
|-------------|-----------|----------|
| FR-1 | Unit | a |
| FR-2 | Unit | b |
| FR-3 | Unit | c |
| FR-9 | Unit | phantom |

## Implementation Order

1. Step one.
"""
    report = ss.score(requirements, solution)
    result = _result(report.checks, "Test-plan coverage")
    assert result.verdict == "BLOCK"
    assert any("FR-9" in d for d in result.details)


def test_nested_sublist_does_not_break_testplan_coverage() -> None:
    requirements = """# Requirements

## Functional Requirements

1. The system must do A.
2. The system must do B.
   1. A nested clarifying note, not a separate FR.
3. The system must do C.

## Acceptance Criteria

- A.
- B.
"""
    solution = """# Solution

## Test Plan

| Requirement | Test Type | Scenario |
|-------------|-----------|----------|
| FR-1 | Unit | a |
| FR-2 | Unit | b |
| FR-3 | Unit | c |

## Implementation Order

1. Step one.
"""
    report = ss.score(requirements, solution)
    result = _result(report.checks, "Test-plan coverage")
    assert result.verdict == "PASS"


def test_combined_testplan_cell_parses_both_frs() -> None:
    requirements = _fr_count_fixture(9)
    rows = "\n".join(f"| FR-{i} | Unit | s{i} |" for i in range(1, 9))
    solution = f"""# Solution

## Test Plan

| Requirement | Test Type | Scenario |
|-------------|-----------|----------|
{rows}
| FR-5/9 | Unit | combined |

## Implementation Order

1. Step one.
"""
    report = ss.score(requirements, solution)
    result = _result(report.checks, "Test-plan coverage")
    assert result.verdict == "PASS"


# --- FR-4: no placeholders -----------------------------------------------------------


def test_bare_keyword_outside_fence_blocks_with_location() -> None:
    requirements = _fr_count_fixture(3) + "\nTODO: fill this in.\n"
    report = ss.score(requirements, CLEAN_SOLUTION)
    result = _result(report.checks, "No placeholders")
    assert result.verdict == "BLOCK"
    assert any("requirements.md" in d and "TODO" in d for d in result.details)


def test_bare_keyword_inside_backtick_fence_passes() -> None:
    requirements = _fr_count_fixture(3) + "\n```\nTODO inside a fence is not a placeholder.\n```\n"
    report = ss.score(requirements, CLEAN_SOLUTION)
    result = _result(report.checks, "No placeholders")
    assert result.verdict == "PASS"


def test_bare_keyword_inside_tilde_fence_with_info_string_passes() -> None:
    requirements = _fr_count_fixture(3) + "\n~~~python\nTODO\n~~~\n"
    report = ss.score(requirements, CLEAN_SOLUTION)
    result = _result(report.checks, "No placeholders")
    assert result.verdict == "PASS"


def test_bare_keyword_inside_inline_span_passes() -> None:
    requirements = _fr_count_fixture(3) + "\nUse `TODO` as a literal marker name.\n"
    report = ss.score(requirements, CLEAN_SOLUTION)
    result = _result(report.checks, "No placeholders")
    assert result.verdict == "PASS"


def test_content_after_unclosed_fence_is_scanned_as_unfenced() -> None:
    requirements = _fr_count_fixture(3) + "\n```\nunclosed fence\n\nTODO after unclosed fence.\n"
    report = ss.score(requirements, CLEAN_SOLUTION)
    result = _result(report.checks, "No placeholders")
    assert result.verdict == "BLOCK"


def test_bracketed_prose_placeholder_blocks() -> None:
    requirements = _fr_count_fixture(3) + "\n<Bullet list: what must be true.>\n"
    report = ss.score(requirements, CLEAN_SOLUTION)
    result = _result(report.checks, "No placeholders")
    assert result.verdict == "BLOCK"


def test_single_token_bracket_span_not_flagged() -> None:
    requirements = _fr_count_fixture(3) + "\nSee `.tickets/XXXX-<slug>/status.md` for the format.\n"
    report = ss.score(requirements, CLEAN_SOLUTION)
    result = _result(report.checks, "No placeholders")
    assert result.verdict == "PASS"


def test_all_ellipsis_table_row_flagged() -> None:
    solution = CLEAN_SOLUTION + "\n| ... | ... | ... |\n"
    report = ss.score(_fr_count_fixture(3), solution)
    result = _result(report.checks, "No placeholders")
    assert result.verdict == "BLOCK"
    assert any("solution.md" in d for d in result.details)


# --- FR-5: Implementation Order / Acceptance criteria (WARN-only) ----------------------


def test_missing_implementation_order_warns_not_blocks() -> None:
    solution = """# Solution

## Test Plan

| Requirement | Test Type | Scenario |
|-------------|-----------|----------|
| FR-1 | Unit | a |
| FR-2 | Unit | b |
| FR-3 | Unit | c |
"""
    report = ss.score(_fr_count_fixture(3), solution)
    result = _result(report.checks, "Implementation Order present")
    assert result.verdict == "WARN"
    assert report.verdict != "BLOCK"


def test_single_acceptance_bullet_warns() -> None:
    requirements = """# Requirements

## Functional Requirements

1. The system must do A.
2. The system must do B.
3. The system must do C.

## Acceptance Criteria

- Only one bullet here.
"""
    report = ss.score(requirements, CLEAN_SOLUTION)
    result = _result(report.checks, "Acceptance criteria")
    assert result.verdict == "WARN"


def test_bullets_outside_acceptance_section_not_counted() -> None:
    requirements = """# Requirements

## Functional Requirements

1. The system must do A.
2. The system must do B.
3. The system must do C.

- A stray bullet before any Acceptance Criteria heading.
- Another stray bullet.

## Acceptance Criteria

- Only one real bullet.
"""
    report = ss.score(requirements, CLEAN_SOLUTION)
    result = _result(report.checks, "Acceptance criteria")
    assert result.verdict == "WARN"


def test_both_present_passes() -> None:
    report = ss.score(_fr_count_fixture(3), CLEAN_SOLUTION)
    order = _result(report.checks, "Implementation Order present")
    acceptance_source = """# Requirements

## Functional Requirements

1. A.
2. B.
3. C.

## Acceptance Criteria

- One.
- Two.
"""
    acceptance = _result(
        ss.score(acceptance_source, CLEAN_SOLUTION).checks, "Acceptance criteria"
    )
    assert order.verdict == "PASS"
    assert acceptance.verdict == "PASS"


# --- FR-6 / FR-8: report format + pure seam -----------------------------------------


def test_score_is_pure_no_temp_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.iterdir())
    ss.score(_fr_count_fixture(3), CLEAN_SOLUTION)
    after = set(tmp_path.iterdir())
    assert before == after


def test_cli_clean_fixture_byte_exact_report_exit_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ticket_dir = tmp_path / "0001-fixture"
    ticket_dir.mkdir()
    (ticket_dir / "requirements.md").write_text(_fr_count_fixture(3), encoding="utf-8")
    (ticket_dir / "solution.md").write_text(CLEAN_SOLUTION, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    exit_code = ss.main(["0001-fixture"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert out == (
        "score-spec: 0001-fixture\n"
        "\n"
        "[PASS] FR count\n"
        "[PASS] Imperative language\n"
        "[PASS] Test-plan coverage\n"
        "[PASS] Implementation Order present\n"
        "[PASS] No placeholders\n"
        "[PASS] Acceptance criteria\n"
        "\n"
        "Verdict: PASS\n"
    )


def test_cli_warn_fixture_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ticket_dir = tmp_path / "0002-fixture"
    ticket_dir.mkdir()
    (ticket_dir / "requirements.md").write_text(_fr_count_fixture(3), encoding="utf-8")
    solution_no_order = """# Solution

## Test Plan

| Requirement | Test Type | Scenario |
|-------------|-----------|----------|
| FR-1 | Unit | a |
| FR-2 | Unit | b |
| FR-3 | Unit | c |
"""
    (ticket_dir / "solution.md").write_text(solution_no_order, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert ss.main(["0002-fixture"]) == 1


def test_cli_phantom_fr_fixture_exits_2_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ticket_dir = tmp_path / "0003-fixture"
    ticket_dir.mkdir()
    (ticket_dir / "requirements.md").write_text(_fr_count_fixture(3), encoding="utf-8")
    solution_phantom = CLEAN_SOLUTION.replace(
        "| FR-3        | Integration | report order |\n",
        "| FR-3        | Integration | report order |\n| FR-9 | Unit | phantom |\n",
    )
    (ticket_dir / "solution.md").write_text(solution_phantom, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    exit_code = ss.main(["0003-fixture"])

    assert exit_code == 2
    out = capsys.readouterr().out
    assert "[BLOCK] Test-plan coverage" in out
    assert "Verdict: BLOCK" in out


# --- FR-7: fail-closed error paths ----------------------------------------------------


def test_cli_missing_solution_exits_2_stderr_no_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ticket_dir = tmp_path / "0004-fixture"
    ticket_dir.mkdir()
    (ticket_dir / "requirements.md").write_text(_fr_count_fixture(3), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    exit_code = ss.main(["0004-fixture"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "score-spec could not run" in captured.err
    assert "Traceback" not in captured.err


def test_cli_unreadable_file_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ticket_dir = tmp_path / "0005-fixture"
    ticket_dir.mkdir()
    (ticket_dir / "requirements.md").write_text(_fr_count_fixture(3), encoding="utf-8")
    (ticket_dir / "solution.md").write_text(CLEAN_SOLUTION, encoding="utf-8")

    original_read_text = Path.read_text

    def _boom(self: Path, *args: str | None, **kwargs: str | None) -> str:
        if self.name == "solution.md":
            raise OSError("permission denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _boom)
    monkeypatch.chdir(tmp_path)

    exit_code = ss.main(["0005-fixture"])

    assert exit_code == 2
    assert "score-spec could not run" in capsys.readouterr().err


def test_cli_spec_remediate_load_failure_exits_2_not_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The spec_remediate loader is lazy (triggered on first score() call, from
    # inside main()'s try) so a load failure must still exit 2 with a reason
    # on stderr, never an uncaught traceback at import time.
    ticket_dir = tmp_path / "0006-fixture"
    ticket_dir.mkdir()
    (ticket_dir / "requirements.md").write_text(_fr_count_fixture(3), encoding="utf-8")
    (ticket_dir / "solution.md").write_text(CLEAN_SOLUTION, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(ss, "_spec_remediate", None)

    def _boom() -> ModuleType:
        raise ImportError("cannot load spec_remediate module")

    monkeypatch.setattr(ss, "_load_spec_remediate", _boom)

    exit_code = ss.main(["0006-fixture"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "score-spec could not run" in captured.err
    assert "Traceback" not in captured.err


def test_cli_no_args_usage_error_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        ss.main([])
    assert excinfo.value.code == 2


# --- NFR-2: RECIPE label regression ---------------------------------------------------


def test_block_check_labels_pin_to_spec_remediate_recipe() -> None:
    block_labels = {"FR count", "Imperative language", "Test-plan coverage", "No placeholders"}
    assert block_labels == set(RECIPE.keys())
    assert {ss.CHECK_FR_COUNT, ss.CHECK_IMPERATIVE, ss.CHECK_TESTPLAN, ss.CHECK_PLACEHOLDERS} == block_labels


# --- FR-9: context/score-spec.md wiring (content verification) -----------------------


SCORE_SPEC_DOC = (ROOT / "context" / "score-spec.md").read_text(encoding="utf-8")


def test_doc_names_validator_invocation() -> None:
    assert "score_spec.py" in SCORE_SPEC_DOC


def test_doc_scopes_model_to_check_7_only() -> None:
    lowered = SCORE_SPEC_DOC.lower()
    assert "check 7" in lowered
    before, after = lowered.split("check 7", 1)
    assert "only" in after[:400] or "only" in before[-400:]


def test_doc_states_insert_above_verdict_and_recompute_rule() -> None:
    lowered = SCORE_SPEC_DOC.lower()
    assert "verdict" in lowered
    assert "recompute" in lowered or "recomputing" in lowered
