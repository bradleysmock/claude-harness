"""Unit tests for the pure spec-remediation fixers (gates/spec_remediate.py)."""

from __future__ import annotations

from gates.spec_remediate import (
    HARD_STOP,
    MECHANICAL,
    SEMANTIC,
    Classification,
    append_testplan_row,
    classify,
    covered_fr_numbers,
    functional_requirement_numbers,
    get_fr_text,
    nonimperative_fr_numbers,
    parse_score_report,
    phantom_fr_numbers,
    remediate_mechanical,
    remove_phantom_row,
    substitute_imperative,
    uncovered_fr_numbers,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

REQUIREMENTS = """\
# Requirements

## Functional Requirements

1. The system must enter remediation on a BLOCK verdict.
2. The system should classify each failing check by recipe.
3. Test-plan coverage must be fixed structurally only, never with
   synthesized prose.
4. A flagged FR's `should`/`may`/`could` must become `must`.

## Non-Functional Requirements

1. Every mechanical edit must be announced in one line.

## Acceptance Criteria

- A missing row is appended without lead intervention.
- Interactive build still hard-stops.
"""

SOLUTION = """\
# Solution

## Approach

Intercept the BLOCK and remediate.

## Test Plan

| Requirement | Test Type   | Scenario(s)                          |
|-------------|-------------|--------------------------------------|
| FR-1        | Integration | BLOCK enters Step S.                 |
| FR-2        | Unit        | Classifier labels each check.        |
| FR-4        | Unit        | Token substitution only.             |
| FR-7        | Integration | Phantom row — FR-7 does not exist.   |

## Implementation Order

1. Build the fixers.
"""


def _score_report(**checks: str) -> str:
    lines = ["score-spec: 0004-x", ""]
    lines += [f"[{verdict}] {name}" for name, verdict in checks.items()]
    return "\n".join(lines)


# ── Classification (FR-2, FR-6) ───────────────────────────────────────────────


def test_parse_score_report_extracts_each_check() -> None:
    report = _score_report(**{"FR count": "PASS", "Imperative language": "BLOCK"})
    parsed = parse_score_report(report)
    assert [(c.name, c.verdict) for c in parsed] == [
        ("FR count", "PASS"),
        ("Imperative language", "BLOCK"),
    ]


def test_classify_buckets_known_blocks() -> None:
    report = _score_report(
        **{
            "FR count": "BLOCK",
            "Imperative language": "BLOCK",
            "Test-plan coverage": "BLOCK",
            "No placeholders": "BLOCK",
        }
    )
    result = classify(report)
    assert set(result.mechanical) == {"Imperative language", "Test-plan coverage"}
    assert set(result.semantic) == {"FR count", "No placeholders"}
    assert result.hard_stop == []
    assert result.must_bail is False


def test_classify_ignores_pass_and_warn() -> None:
    report = _score_report(
        **{"Test-plan coverage": "PASS", "FR count": "WARN", "Imperative language": "BLOCK"}
    )
    result = classify(report)
    assert result.mechanical == ["Imperative language"]
    assert result.semantic == []
    assert result.hard_stop == []


def test_unknown_block_falls_through_to_hard_stop() -> None:
    # A fabricated / future check name in BLOCK state must fail closed (FR-6).
    report = _score_report(**{"Imperative language": "BLOCK", "Cohesion vibes": "BLOCK"})
    result = classify(report)
    assert result.hard_stop == ["Cohesion vibes"]
    assert result.must_bail is True
    assert "Imperative language" in result.mechanical


def test_classification_is_immutable_dataclass() -> None:
    assert isinstance(classify(""), Classification)


# ── FR / Test Plan parsing ────────────────────────────────────────────────────


def test_functional_requirement_numbers_scopes_to_section() -> None:
    # NFR-1 lives under Non-Functional Requirements and must not be counted.
    assert functional_requirement_numbers(REQUIREMENTS) == [1, 2, 3, 4]


def test_covered_fr_numbers_reads_requirement_column() -> None:
    assert covered_fr_numbers(SOLUTION) == [1, 2, 4, 7]


def test_get_fr_text_joins_wrapped_lines() -> None:
    text = get_fr_text(REQUIREMENTS, 3)
    assert text.startswith("Test-plan coverage must be fixed structurally only")
    assert "synthesized prose" in text  # wrapped continuation line is joined


def test_uncovered_and_phantom_detection() -> None:
    assert uncovered_fr_numbers(REQUIREMENTS, SOLUTION) == [3]  # FR-3 has no row
    assert phantom_fr_numbers(REQUIREMENTS, SOLUTION) == [7]  # FR-7 not declared


def test_nonimperative_ignores_backticked_tokens() -> None:
    # FR-2 uses a bare "should"; FR-4 only mentions `should`/`may`/`could` in
    # backticks and must not be flagged.
    assert nonimperative_fr_numbers(REQUIREMENTS) == [2]


# ── Mechanical fix: append / remove Test Plan rows (FR-3) ──────────────────────


def test_append_testplan_row_covers_missing_fr_with_crossref() -> None:
    new_solution, announcement = append_testplan_row(SOLUTION, 3, get_fr_text(REQUIREMENTS, 3))
    assert 3 in covered_fr_numbers(new_solution)
    # Cross-reference to the FR's existing text — no authored prose.
    assert "xref requirements.md FR-3" in new_solution
    assert "Test-plan coverage must be fixed structurally only" in new_solution
    assert announcement.startswith("spec-remediate: appended Test Plan row for FR-3")


def test_append_testplan_row_escapes_pipes_in_cell() -> None:
    new_solution, _ = append_testplan_row(SOLUTION, 9, "value a | value b")
    assert r"value a \| value b" in new_solution


def test_remove_phantom_row_drops_only_the_phantom() -> None:
    new_solution, announcement = remove_phantom_row(SOLUTION, 7)
    assert 7 not in covered_fr_numbers(new_solution)
    assert covered_fr_numbers(new_solution) == [1, 2, 4]  # real rows intact
    assert announcement.startswith("spec-remediate: removed phantom Test Plan row FR-7")


def test_remove_phantom_row_noop_when_absent() -> None:
    new_solution, announcement = remove_phantom_row(SOLUTION, 99)
    assert new_solution == SOLUTION
    assert announcement == ""


# ── Mechanical fix: imperative substitution (FR-4) ─────────────────────────────


def test_substitute_imperative_changes_only_target_fr() -> None:
    new_requirements, announcement = substitute_imperative(REQUIREMENTS, 2)
    fr2 = get_fr_text(new_requirements, 2)
    assert "must classify" in fr2
    assert "should" not in fr2.lower()
    # FR-4's backticked tokens are untouched.
    assert "`should`" in new_requirements
    assert "should -> must" in announcement


def test_substitute_imperative_preserves_other_frs() -> None:
    new_requirements, _ = substitute_imperative(REQUIREMENTS, 2)
    assert get_fr_text(new_requirements, 1) == get_fr_text(REQUIREMENTS, 1)
    assert get_fr_text(new_requirements, 3) == get_fr_text(REQUIREMENTS, 3)


def test_substitute_imperative_noop_when_already_imperative() -> None:
    new_requirements, announcement = substitute_imperative(REQUIREMENTS, 1)
    assert new_requirements == REQUIREMENTS
    assert announcement == ""


# ── Composition + audit (NFR-1) ───────────────────────────────────────────────


def test_remediate_mechanical_clears_all_in_one_pass() -> None:
    new_req, new_sol, announcements = remediate_mechanical(REQUIREMENTS, SOLUTION)
    # Imperative: FR-2 fixed.
    assert "should" not in get_fr_text(new_req, 2).lower()
    assert nonimperative_fr_numbers(new_req) == []
    # Coverage: FR-3 now covered, phantom FR-7 removed.
    assert uncovered_fr_numbers(new_req, new_sol) == []
    assert phantom_fr_numbers(new_req, new_sol) == []
    # One announcement per edit (substitute + append + remove == 3).
    assert len(announcements) == 3
    assert all(a.startswith("spec-remediate:") for a in announcements)


def test_remediate_mechanical_is_noop_on_clean_artifacts() -> None:
    clean_req, clean_sol, _ = remediate_mechanical(REQUIREMENTS, SOLUTION)
    again_req, again_sol, announcements = remediate_mechanical(clean_req, clean_sol)
    assert again_req == clean_req
    assert again_sol == clean_sol
    assert announcements == []


def test_constants_are_distinct() -> None:
    assert len({MECHANICAL, SEMANTIC, HARD_STOP}) == 3
