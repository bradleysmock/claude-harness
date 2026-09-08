"""Tests for gates/policy.py — the data-driven promotion policy (ticket 0074)."""
from __future__ import annotations

import pytest

from gates.policy import (
    PolicyConfigError,
    PolicyRule,
    PromotionVerdict,
    evaluate_promotion,
    load_policy,
)
from models import GateError, GateResult, LanguageResult, StackName


def _result(gate: str, passed: bool, skipped: bool = False) -> GateResult:
    errors = [] if passed else [GateError(
        message="boom", file=None, line=None, column=None, code="X", severity="error",
    )]
    return GateResult(gate=gate, passed=passed, errors=errors, duration_ms=1, skipped=skipped)


def _lang(language: StackName, results: list[GateResult]) -> LanguageResult:
    return LanguageResult(language=language, results=results)


# ---------------------------------------------------------------------------
# FR-1/2/3 — dataclasses construct; evaluate_promotion is deterministic
# ---------------------------------------------------------------------------

def test_policy_rule_and_verdict_construct():
    rule = PolicyRule(gate="python.lint", required=True, on_block="fail")
    assert rule.gate == "python.lint"
    assert rule.depends_on == ()
    verdict = PromotionVerdict(outcome="promote", blocking_gates=(), reasons=())
    assert verdict.outcome == "promote"


def test_evaluate_promotion_is_deterministic():
    policy = load_policy("")
    lang_results = [_lang(StackName.PYTHON, [_result("lint", True)])]
    v1 = evaluate_promotion(lang_results, [], policy)
    v2 = evaluate_promotion(lang_results, [], policy)
    assert v1 == v2


# ---------------------------------------------------------------------------
# FR-5/7/9 — no [policy] block reproduces today's behavior; warn never blocks
# ---------------------------------------------------------------------------

def test_default_policy_all_pass_promotes():
    policy = load_policy("")
    lang_results = [_lang(StackName.PYTHON, [
        _result("lint", True), _result("test", True), _result("secrets", True),
        _result("coverage", True), _result("dep-audit", True), _result("sast", True),
        _result("type_check", True), _result("security", True),
    ])]
    verdict = evaluate_promotion(lang_results, [_result("commit_lint", True)], policy)
    assert verdict.outcome == "promote"
    assert verdict.blocking_gates == ()


def test_default_policy_any_failure_blocks():
    policy = load_policy("")
    lang_results = [_lang(StackName.PYTHON, [_result("lint", False), _result("test", True)])]
    verdict = evaluate_promotion(lang_results, [], policy)
    assert verdict.outcome == "block"
    assert "python.lint" in verdict.blocking_gates


def test_default_policy_covers_cross_cutting_gates():
    policy = load_policy("")
    lang_results = [_lang(StackName.PYTHON, [_result("secrets", False)])]
    verdict = evaluate_promotion(lang_results, [], policy)
    assert verdict.outcome == "block"
    assert "python.secrets" in verdict.blocking_gates


def test_warn_never_blocks_but_appears_in_reasons():
    text = '```gates\n[policy]\npython.lint.on_block = "warn"\n```'
    policy = load_policy(text)
    lang_results = [_lang(StackName.PYTHON, [_result("lint", False)])]
    verdict = evaluate_promotion(lang_results, [], policy)
    assert verdict.outcome == "promote"
    assert verdict.blocking_gates == ()
    assert any(r.startswith("python.lint: warn (failed)") for r in verdict.reasons)


# ---------------------------------------------------------------------------
# FR-8 — required=false never blocks, regardless of on_block or result
# ---------------------------------------------------------------------------

def test_required_false_never_blocks():
    text = '```gates\n[policy]\npython.lint.required = false\n```'
    policy = load_policy(text)
    lang_results = [_lang(StackName.PYTHON, [_result("lint", False)])]
    verdict = evaluate_promotion(lang_results, [], policy)
    assert verdict.outcome == "promote"
    assert verdict.blocking_gates == ()


# ---------------------------------------------------------------------------
# FR-4/6/11 — bad key form, unresolvable depends_on, bad on_block -> CONFIG_ERROR
# ---------------------------------------------------------------------------

def test_bare_key_without_namespace_is_config_error():
    text = '```gates\n[policy]\nlint.required = false\n```'
    with pytest.raises(PolicyConfigError):
        load_policy(text)


def test_unknown_gate_for_language_is_config_error():
    text = '```gates\n[policy]\npython.nonexistent.required = false\n```'
    with pytest.raises(PolicyConfigError):
        load_policy(text)


def test_invalid_on_block_value_is_config_error():
    text = '```gates\n[policy]\npython.lint.on_block = "sometimes"\n```'
    with pytest.raises(PolicyConfigError):
        load_policy(text)


def test_unresolvable_depends_on_is_config_error():
    text = '```gates\n[policy]\npython.test.depends_on = "python.nonexistent"\n```'
    with pytest.raises(PolicyConfigError):
        load_policy(text)


# ---------------------------------------------------------------------------
# FR-4 — global.commit_lint and python.secrets both resolve correctly
# ---------------------------------------------------------------------------

def test_global_and_language_namespaces_both_resolve():
    text = (
        '```gates\n[policy]\n'
        'global.commit_lint.on_block = "warn"\n'
        'python.secrets.on_block = "pause_for_human"\n'
        '```'
    )
    policy = load_policy(text)
    by_gate = {rule.gate: rule for rule in policy}
    assert by_gate["global.commit_lint"].on_block == "warn"
    assert by_gate["python.secrets"].on_block == "pause_for_human"

    lang_results = [_lang(StackName.PYTHON, [_result("secrets", False)])]
    verdict = evaluate_promotion(lang_results, [_result("commit_lint", False)], policy)
    assert verdict.outcome == "pause_for_human"
    assert any(r.startswith("global.commit_lint: warn (failed)") for r in verdict.reasons)


# ---------------------------------------------------------------------------
# FR-10 — reasons format
# ---------------------------------------------------------------------------

def test_reasons_format_matches_spec():
    policy = load_policy("")
    lang_results = [_lang(StackName.PYTHON, [
        _result("lint", True), _result("test", False), _result("secrets", True, skipped=True),
    ])]
    verdict = evaluate_promotion(lang_results, [], policy)
    reasons_by_gate = {r.split(":")[0]: r for r in verdict.reasons}
    assert reasons_by_gate["python.lint"] == "python.lint: fail (passed)"
    assert reasons_by_gate["python.test"] == "python.test: fail (failed)"
    assert reasons_by_gate["python.secrets"] == "python.secrets: fail (skipped)"


# ---------------------------------------------------------------------------
# FR-11 — blocking_gates suppression via depends_on; reasons stay full
# ---------------------------------------------------------------------------

def test_depends_on_suppresses_downstream_from_blocking_gates_not_reasons():
    text = '```gates\n[policy]\npython.test.depends_on = "python.lint"\n```'
    policy = load_policy(text)
    lang_results = [_lang(StackName.PYTHON, [_result("lint", False), _result("test", False)])]
    verdict = evaluate_promotion(lang_results, [], policy)
    assert verdict.outcome == "block"
    assert "python.lint" in verdict.blocking_gates
    assert "python.test" not in verdict.blocking_gates
    assert any(r.startswith("python.test:") for r in verdict.reasons)


def test_depends_on_does_not_suppress_when_dependency_passed():
    text = '```gates\n[policy]\npython.test.depends_on = "python.lint"\n```'
    policy = load_policy(text)
    lang_results = [_lang(StackName.PYTHON, [_result("lint", True), _result("test", False)])]
    verdict = evaluate_promotion(lang_results, [], policy)
    assert "python.test" in verdict.blocking_gates
