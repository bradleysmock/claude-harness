# harness-combined/tests/test_0083_typed_helpers.py
"""Ticket 0083 — the typed test helpers that replace three type-erasing patterns.

Each helper here was previously written in a form mypy could not see through: a
``_f(**overrides: object)`` Finding builder, an ``object``-typed read of a captured
review payload, and a ``lambda d, g=g:`` dict comprehension that reads as two-arity.
These tests pin the *replacements* — their shape and their behaviour — so a later
edit cannot regress to the erasing form and quietly reintroduce the gate debt.
"""
from __future__ import annotations

import inspect
from dataclasses import fields
from pathlib import Path
from types import ModuleType

import pytest
import test_0031_pr_comments as pr_comment_tests
import test_0036_parallel_gate as parallel_gate_tests
import test_0062_finding_key as finding_key_tests
import test_0067_incremental_scope as incremental_scope_tests

from gates import pr_commenter
from gates.finding import Finding

# Read off the dataclass rather than copied from it: the builders exist to mirror
# `Finding`'s fields, so a sixth field should change what this expects, not fail it.
_FINDING_FIELDS = tuple(finding_field.name for finding_field in fields(Finding))

# The defaults, by contrast, are written out deliberately: they are the pre-fix
# `base = dict(...)` values the typed builders must keep producing, so deriving
# them from either builder would pin nothing.
_FINDING_DEFAULTS = Finding(
    file="src/module.py",
    line=12,
    severity="BLOCKER",
    code="Security / Injection",
    message="body",
)


@pytest.mark.parametrize(
    "module", [finding_key_tests, incremental_scope_tests], ids=["0062", "0067"]
)
def test_finding_builder_is_keyword_only_with_one_parameter_per_field(
    module: ModuleType,
) -> None:
    # FR-4: the point of the replacement is that each field is a declared,
    # individually-typed parameter — a `**overrides` catch-all erases them all.
    parameters = inspect.signature(module._f).parameters
    assert tuple(parameters) == _FINDING_FIELDS
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in parameters.values()
    )


@pytest.mark.parametrize(
    "module", [finding_key_tests, incremental_scope_tests], ids=["0062", "0067"]
)
def test_finding_builder_defaults_match_the_pre_fix_base_dict(module: ModuleType) -> None:
    # Behaviour preservation: the no-argument call must produce exactly what the
    # old `base = dict(...)` produced.
    assert module._f() == _FINDING_DEFAULTS


@pytest.mark.parametrize(
    "module", [finding_key_tests, incremental_scope_tests], ids=["0062", "0067"]
)
@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"line": None},
        {"code": ""},
        {"line": None, "code": ""},
        {"message": "a completely different message"},
        {"file": "src/other.py", "severity": "MINOR"},
    ],
)
def test_finding_builder_applies_overrides_field_by_field(
    module: ModuleType, overrides: dict[str, object]
) -> None:
    # Every override the existing call sites use must land on its own field and
    # leave the other four at their defaults — the `base.update(overrides)`
    # semantics, now expressed as typed parameters.
    built = module._f(**overrides)
    for field_name in _FINDING_FIELDS:
        expected = overrides.get(field_name, getattr(_FINDING_DEFAULTS, field_name))
        assert getattr(built, field_name) == expected


def test_capture_comments_returns_the_captured_review_comment_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # FR-7: one typed accessor replaces three raw `cap.review["comments"]` reads.
    # It must return the very list the review payload carried, not a copy.
    capture = pr_comment_tests._Capture(monkeypatch)
    comments = [{"path": "a.py", "line": 1, "body": "one"}]
    # `_Capture` has monkeypatched `_submit_review`, so this records the payload
    # rather than calling `gh`; the second argument is the stub's unused `cwd`.
    pr_commenter._submit_review({"comments": comments}, None)
    assert capture.comments() is capture.review["comments"]
    assert capture.comments() == comments


def test_capture_comments_on_an_unsubmitted_review_is_a_key_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The accessor is a typed read, not a defaulting one: an empty `review` means
    # nothing was submitted, and a test asserting on comments should fail loudly
    # rather than silently compare against an empty list.
    capture = pr_comment_tests._Capture(monkeypatch)
    with pytest.raises(KeyError):
        capture.comments()


def test_gate_fn_factory_binds_each_name_to_its_own_single_argument_callable(
    tmp_path: Path,
) -> None:
    # FR-9: the `g=g` default-argument trick existed to stop every closure from
    # capturing the loop's last name. The factory must preserve that per-name
    # capture while producing genuinely one-parameter callables.
    names = ("lint", "type_check", "test", "security")
    gate_fns = parallel_gate_tests._passing_gate_fns(*names)

    assert tuple(gate_fns) == names
    assert [gate_fns[name](str(tmp_path)).gate for name in names] == list(names)
    assert all(
        len(inspect.signature(gate_fn).parameters) == 1 for gate_fn in gate_fns.values()
    )
