"""Tests for gates.critic_reconciler (ticket 0062)."""

from __future__ import annotations

from gates.critic_reconciler import (
    harvest_keys,
    latest_section,
    marker_for_key,
    reconcile,
)
from gates.finding import Finding, finding_key


def _f(file: str, line: int | None, severity: str, code: str, message: str = "body") -> Finding:
    return Finding(file=file, line=line, severity=severity, code=code, message=message)


def test_round_1_has_no_prior_round_all_new() -> None:
    curr = [_f("a.py", 1, "BLOCKER", "Security / X"), _f("b.py", 2, "MAJOR", "Perf / Y")]
    result = reconcile([], curr)
    assert result.fixed == []
    assert result.persisted == []
    assert result.new == curr


def test_final_round_has_no_curr_all_fixed() -> None:
    prev = [_f("a.py", 1, "BLOCKER", "Security / X"), _f("b.py", 2, "MAJOR", "Perf / Y")]
    result = reconcile(prev, [])
    assert result.fixed == [finding_key(f) for f in prev]
    assert result.persisted == []
    assert result.new == []


def test_one_fixed_one_new_rest_persisted() -> None:
    stays = _f("c.py", 3, "BLOCKER", "Correctness / Z")
    fixed_finding = _f("a.py", 1, "BLOCKER", "Security / X")
    new_finding = _f("d.py", 4, "MAJOR", "API / W")
    prev = [stays, fixed_finding]
    curr = [stays, new_finding]
    result = reconcile(prev, curr)
    assert result.fixed == [finding_key(fixed_finding)]
    assert result.persisted == [stays]
    assert result.new == [new_finding]


def test_order_independence_of_the_multisets() -> None:
    a = _f("a.py", 1, "BLOCKER", "Security / X")
    b = _f("b.py", 2, "MAJOR", "Perf / Y")
    c = _f("c.py", 3, "BLOCKER", "Correctness / Z")
    forward = reconcile([a, b], [b, c])
    shuffled = reconcile([b, a], [c, b])
    assert set(forward.fixed) == set(shuffled.fixed)
    assert {finding_key(f) for f in forward.persisted} == {finding_key(f) for f in shuffled.persisted}
    assert {finding_key(f) for f in forward.new} == {finding_key(f) for f in shuffled.new}


def test_duplicate_key_multiset_counting() -> None:
    dup = _f("a.py", 1, "BLOCKER", "Security / X")
    prev = [dup, dup]
    curr = [dup, dup, dup]
    result = reconcile(prev, curr)
    assert result.fixed == []
    assert len(result.persisted) == 2
    assert len(result.new) == 1


def test_minor_and_obs_are_excluded_from_every_bucket() -> None:
    minor = _f("a.py", 1, "MINOR", "Style / X")
    obs = _f("b.py", 2, "OBS", "Note / Y")
    blocker = _f("c.py", 3, "BLOCKER", "Security / Z")
    prev = [minor, obs]
    curr = [minor, obs, blocker]
    result = reconcile(prev, curr)
    assert result.fixed == []
    assert result.persisted == []
    assert result.new == [blocker]


def test_marker_for_key_format_with_int_and_none_line() -> None:
    key_int = ("a.py", 1, "BLOCKER", "Security / X")
    key_none = ("", None, "BLOCKER", "")
    assert marker_for_key(key_int) == "<!-- harness-finding-key a.py:1:BLOCKER:Security / X -->"
    assert marker_for_key(key_none) == "<!-- harness-finding-key :None:BLOCKER: -->"


def test_harvest_keys_round_trip() -> None:
    key_int = ("a.py", 1, "BLOCKER", "Security / X")
    key_none = ("", None, "MAJOR", "Perf")
    text = f"prose\n{marker_for_key(key_int)}\nmore prose\n{marker_for_key(key_none)}\nend"
    assert harvest_keys(text) == [key_int, key_none]


def test_harvest_keys_no_markers_returns_empty() -> None:
    assert harvest_keys("no markers here") == []


def test_harvest_keys_multiple_markers_in_document_order() -> None:
    keys = [("a.py", 1, "BLOCKER", "A"), ("b.py", 2, "MAJOR", "B"), ("c.py", 3, "BLOCKER", "C")]
    text = "\n".join(marker_for_key(k) for k in keys)
    assert harvest_keys(text) == keys


def test_latest_section_returns_text_after_last_heading() -> None:
    text = "## Round 1 — 2026-07-20\n\nfirst\n\n## Round 2 — 2026-07-20\n\nsecond\n"
    assert latest_section(text) == "## Round 2 — 2026-07-20\n\nsecond\n"


def test_latest_section_no_heading_returns_text_unchanged() -> None:
    text = "no headings here at all"
    assert latest_section(text) == text


def test_latest_section_is_not_shadowed_by_an_escalation_diagnosis_subsection() -> None:
    """A `### Escalation diagnosis` sub-section carries no markers and must not become
    the "latest section" in place of the `## Round` it's nested under (round-3 regression:
    repair-escalation.md persists the diagnosis, as a `### ` sub-heading, before its
    reconcile call — a `## `-level diagnosis heading would shadow the real prior round)."""
    key = ("a.py", 1, "BLOCKER", "X")
    text = (
        f"## Round 2 — d\n\n{marker_for_key(key)}\n\n"
        "### Escalation diagnosis — d\n\n"
        "**Root cause**: …\n**Fix strategy**: …\n**Target locations**: …\n"
    )
    assert harvest_keys(latest_section(text)) == [key]


def test_latest_section_scopes_harvest_to_the_most_recent_round_only() -> None:
    """A key re-embedded in every round it persists must not be double-counted (FR-3/FR-7)."""
    dup = ("a.py", 1, "BLOCKER", "X")
    full_text = (
        f"## Round 1 — d\n\n{marker_for_key(dup)}\n\n"
        f"## Round 2 — d\n\n{marker_for_key(dup)}\n"
    )
    assert harvest_keys(full_text) == [dup, dup]
    assert harvest_keys(latest_section(full_text)) == [dup]
