"""Ticket 0077 — _standards.md [external_gates] parser (fail-closed)."""
from __future__ import annotations

from pathlib import Path

from gates.config import ConfigError, load_external_gates


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "_standards.md"
    p.write_text(body, encoding="utf-8")
    return p


def test_valid_entry_parses(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        '```gates\n[external_gates]\n'
        'snyk = { command = "snyk test --sarif", scope = "*.py,*.ts", timeout = 120 }\n'
        '```\n',
    )
    specs = load_external_gates(p)
    assert len(specs) == 1
    spec = specs[0]
    assert spec.name == "snyk"
    assert spec.command == ["snyk", "test", "--sarif"]
    assert spec.scope == "*.py,*.ts"
    assert spec.timeout_seconds == 120


def test_default_timeout_when_absent(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        '```gates\n[external_gates]\n'
        'snyk = { command = "snyk test --sarif" }\n'
        '```\n',
    )
    specs = load_external_gates(p)
    assert specs[0].timeout_seconds == 60
    assert specs[0].scope is None


def test_missing_block_returns_empty(tmp_path: Path) -> None:
    p = _write(tmp_path, '```gates\npython.lint = "ruff check ."\n```\n')
    assert load_external_gates(p) == []


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_external_gates(tmp_path / "nope.md") == []


def test_name_colliding_with_builtin_gate_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        '```gates\n[external_gates]\n'
        'test = { command = "snyk test" }\n'
        '```\n',
    )
    try:
        load_external_gates(p)
        assert False, "expected ConfigError"
    except ConfigError:
        pass


def test_name_colliding_with_cross_cutting_gate_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        '```gates\n[external_gates]\n'
        'secrets = { command = "snyk test" }\n'
        '```\n',
    )
    try:
        load_external_gates(p)
        assert False, "expected ConfigError"
    except ConfigError:
        pass


def test_duplicate_entry_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        '```gates\n[external_gates]\n'
        'snyk = { command = "a" }\n'
        'snyk = { command = "b" }\n'
        '```\n',
    )
    try:
        load_external_gates(p)
        assert False, "expected ConfigError"
    except ConfigError:
        pass


def test_missing_command_field_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        '```gates\n[external_gates]\n'
        'snyk = { scope = "*.py" }\n'
        '```\n',
    )
    try:
        load_external_gates(p)
        assert False, "expected ConfigError"
    except ConfigError:
        pass


def test_empty_scope_segment_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        '```gates\n[external_gates]\n'
        'snyk = { command = "a", scope = "*.py,,*.ts" }\n'
        '```\n',
    )
    try:
        load_external_gates(p)
        assert False, "expected ConfigError"
    except ConfigError:
        pass


def test_unbalanced_bracket_scope_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        '```gates\n[external_gates]\n'
        'snyk = { command = "a", scope = "*.[py" }\n'
        '```\n',
    )
    try:
        load_external_gates(p)
        assert False, "expected ConfigError"
    except ConfigError:
        pass


def test_reversed_character_range_scope_rejected(tmp_path: Path) -> None:
    """PurePosixPath.match accepts a reversed range like [z-a] silently (it
    just never matches) — this must be rejected at parse time instead."""
    p = _write(
        tmp_path,
        '```gates\n[external_gates]\n'
        'snyk = { command = "a", scope = "*.[z-a]" }\n'
        '```\n',
    )
    try:
        load_external_gates(p)
        assert False, "expected ConfigError"
    except ConfigError:
        pass


def test_out_of_order_brackets_scope_rejected(tmp_path: Path) -> None:
    """Balanced bracket COUNT (1 open, 1 close) but swapped order — the
    count-only check would miss this; PurePosixPath.match never raises."""
    p = _write(
        tmp_path,
        '```gates\n[external_gates]\n'
        'snyk = { command = "a", scope = "a]b[c" }\n'
        '```\n',
    )
    try:
        load_external_gates(p)
        assert False, "expected ConfigError"
    except ConfigError:
        pass


def test_valid_character_class_scope_accepted(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        '```gates\n[external_gates]\n'
        'snyk = { command = "a", scope = "*.[jt]s" }\n'
        '```\n',
    )
    specs = load_external_gates(p)
    assert specs[0].scope == "*.[jt]s"


def test_non_integer_timeout_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        '```gates\n[external_gates]\n'
        'snyk = { command = "a", timeout = "soon" }\n'
        '```\n',
    )
    try:
        load_external_gates(p)
        assert False, "expected ConfigError"
    except ConfigError:
        pass


def test_forbidden_arg0_char_rejected(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        '```gates\n[external_gates]\n'
        'snyk = { command = "../escape test" }\n'
        '```\n',
    )
    try:
        load_external_gates(p)
        assert False, "expected ConfigError"
    except ConfigError:
        pass


def test_policy_and_external_gates_do_not_bleed_into_each_other(tmp_path: Path) -> None:
    """Both sub-blocks in one fence, external_gates first — order-independent."""
    p = _write(
        tmp_path,
        '```gates\n[external_gates]\n'
        'snyk = { command = "snyk test --sarif" }\n'
        '[policy]\n'
        'python.lint.on_block = "warn"\n'
        '```\n',
    )
    specs = load_external_gates(p)
    assert len(specs) == 1
    assert specs[0].name == "snyk"

    from gates.policy import load_policy

    policy = load_policy(p.read_text(encoding="utf-8"))
    by_gate = {rule.gate: rule for rule in policy}
    assert by_gate["python.lint"].on_block == "warn"


def test_command_still_reuses_existing_hardening(tmp_path: Path) -> None:
    """`[gates]` command overrides above [external_gates] still parse fine."""
    p = _write(
        tmp_path,
        '```gates\n'
        'python.lint = "ruff check ."\n'
        '[external_gates]\n'
        'snyk = { command = "snyk test --sarif" }\n'
        '```\n',
    )
    from gates.config import load_gate_overrides

    overrides = load_gate_overrides(p)
    assert overrides == {"python": {"lint": ["ruff", "check", "."]}}
    specs = load_external_gates(p)
    assert specs[0].name == "snyk"
