"""Tests for wiring the dependency-audit gate into ``run_suite_on_dir`` (0012).

The language suite and the dep-audit gate are both mocked so these tests only
exercise the wiring in ``gates/__init__.py`` — ordering, the local->models
adapter, fail-fast short-circuit, and fault degradation.
"""

from __future__ import annotations

from unittest import mock

import pytest

from gates import run_suite_on_dir
from gates.dep_audit import GateError as DepError
from gates.dep_audit import GateResult as DepResult
from models import GateResult as ModelResult


def _lang_ok() -> list[ModelResult]:
    return [ModelResult(gate="lint", passed=True, errors=[], duration_ms=1)]


def test_dep_audit_is_appended_last_as_model_result():
    with mock.patch("gates._language_suite_on_dir", return_value=_lang_ok()), \
         mock.patch("gates.dep_audit.run_dep_audit_gate",
                    return_value=DepResult(True, [DepError("WARNING", "x", "p", "m")])):
        results = run_suite_on_dir("python", "/proj", fail_fast=False)
    assert isinstance(results[-1], ModelResult)
    assert results[-1].gate == "dep-audit"
    assert results[-1].passed is True
    assert results[-1].errors[0].severity == "warning"


def test_blocker_maps_to_failed_error_result():
    with mock.patch("gates._language_suite_on_dir", return_value=_lang_ok()), \
         mock.patch("gates.dep_audit.run_dep_audit_gate",
                    return_value=DepResult(False, [DepError("BLOCKER", "1065", "lodash", "pp")])):
        results = run_suite_on_dir("python", "/proj", fail_fast=False)
    dep = results[-1]
    assert dep.passed is False
    assert any(e.severity == "error" and e.code == "1065" for e in dep.errors)


def test_warning_only_passes():
    with mock.patch("gates._language_suite_on_dir", return_value=_lang_ok()), \
         mock.patch("gates.dep_audit.run_dep_audit_gate",
                    return_value=DepResult(True, [DepError("WARNING", "freshness", "", "stale")])):
        results = run_suite_on_dir("python", "/proj", fail_fast=False)
    assert results[-1].passed is True


def test_fail_fast_short_circuits_before_dep_audit():
    failing = [ModelResult(gate="lint", passed=False, errors=[], duration_ms=1)]
    with mock.patch("gates._language_suite_on_dir", return_value=failing), \
         mock.patch("gates.dep_audit.run_dep_audit_gate") as run:
        results = run_suite_on_dir("python", "/proj", fail_fast=True)
    assert all(r.gate != "dep-audit" for r in results)
    run.assert_not_called()


def test_unsupported_language_still_raises():
    with pytest.raises(ValueError):
        run_suite_on_dir("cobol", "/proj", fail_fast=False)


def test_dep_audit_skipped_when_gate_config_disables_it():
    # FR-10 — selective skip: when config disables dep-audit, the phase is omitted
    # and the gate is never invoked.
    with mock.patch("gates._language_suite_on_dir", return_value=_lang_ok()), \
         mock.patch("gates.dep_audit.dep_audit_enabled", return_value=False), \
         mock.patch("gates.dep_audit.run_dep_audit_gate") as run:
        results = run_suite_on_dir("python", "/proj", fail_fast=False)
    assert all(r.gate != "dep-audit" for r in results)
    run.assert_not_called()


def test_dep_audit_fault_degrades_to_passing_warning():
    with mock.patch("gates._language_suite_on_dir", return_value=_lang_ok()), \
         mock.patch("gates.dep_audit.run_dep_audit_gate", side_effect=RuntimeError("boom")):
        results = run_suite_on_dir("python", "/proj", fail_fast=False)
    dep = results[-1]
    assert dep.gate == "dep-audit"
    assert dep.passed is True
    assert dep.errors[0].severity == "warning"
