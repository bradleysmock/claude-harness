"""Unit tests for GateTimeoutConfig loading/resolution and the shared _timeout_error.

Ticket 0009 — gate timeout configuration. Covers FR-1..FR-5, C-04, C-08 and the
_timeout_error message contract (FR-4).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from gates import GateTimeoutConfig, _timeout_error


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / ".harness.toml"
    path.write_text(body, encoding="utf-8")
    return path


# ── from_directory / load (FR-1) ──────────────────────────────────────────────

def test_from_directory_absent_returns_none(tmp_path):
    assert GateTimeoutConfig.from_directory(tmp_path) is None


def test_from_directory_present_returns_config(tmp_path):
    _write(tmp_path, "test_timeout_seconds = 30\n")
    cfg = GateTimeoutConfig.from_directory(tmp_path)
    assert isinstance(cfg, GateTimeoutConfig)
    assert cfg.test_timeout_seconds == 30


def test_malformed_toml_raises_valueerror_with_filename(tmp_path):
    path = _write(tmp_path, "test_timeout_seconds = = 5\n")
    with pytest.raises(ValueError) as exc:
        GateTimeoutConfig.load(path)
    assert str(path) in str(exc.value)


def test_unknown_key_is_ignored(tmp_path):
    cfg = GateTimeoutConfig.load(_write(tmp_path, "typo_timeout_seconds = 10\ntest_timeout_seconds = 5\n"))
    assert cfg.test_timeout_seconds == 5
    assert not hasattr(cfg, "typo_timeout_seconds")


# ── timeout_for precedence (FR-2, FR-3, C-08) ─────────────────────────────────

def test_per_gate_override(tmp_path):
    cfg = GateTimeoutConfig.load(_write(tmp_path, "test_timeout_seconds = 30\n"))
    assert cfg.timeout_for("test", 120) == 30


def test_global_default_applies_to_unset_gates(tmp_path):
    cfg = GateTimeoutConfig.load(_write(tmp_path, "default_timeout_seconds = 45\n"))
    assert cfg.timeout_for("lint", 60) == 45
    assert cfg.timeout_for("typecheck", 60) == 45


def test_precedence_override_beats_global_beats_hardcoded(tmp_path):
    cfg = GateTimeoutConfig.load(
        _write(tmp_path, "default_timeout_seconds = 45\ntest_timeout_seconds = 30\n")
    )
    assert cfg.timeout_for("test", 120) == 30  # per-gate override wins
    assert cfg.timeout_for("lint", 99) == 45   # falls to global default
    assert cfg.timeout_for("security", 77) == 45


def test_no_timeout_keys_returns_hardcoded_default(tmp_path):
    cfg = GateTimeoutConfig.load(_write(tmp_path, "# present but unconfigured\nunrelated = 1\n"))
    for gate, hardcoded in (("lint", 60), ("typecheck", 61), ("test", 120), ("security", 62)):
        assert cfg.timeout_for(gate, hardcoded) == hardcoded


def test_none_config_would_defer_to_caller_default():
    # A bare config (no keys) resolves to the caller's default for every gate.
    cfg = GateTimeoutConfig()
    assert cfg.timeout_for("test", 180) == 180


# ── value validation (C-04, float truncation) ────────────────────────────────

def test_zero_value_raises(tmp_path):
    with pytest.raises(ValueError):
        GateTimeoutConfig.load(_write(tmp_path, "test_timeout_seconds = 0\n"))


def test_negative_value_raises(tmp_path):
    with pytest.raises(ValueError):
        GateTimeoutConfig.load(_write(tmp_path, "default_timeout_seconds = -1\n"))


def test_float_value_truncated_to_int(tmp_path):
    cfg = GateTimeoutConfig.load(_write(tmp_path, "test_timeout_seconds = 30.5\n"))
    assert cfg.test_timeout_seconds == 30
    assert cfg.timeout_for("test", 120) == 30


def test_float_truncating_to_zero_raises(tmp_path):
    with pytest.raises(ValueError):
        GateTimeoutConfig.load(_write(tmp_path, "test_timeout_seconds = 0.4\n"))


def test_bool_value_rejected(tmp_path):
    with pytest.raises(ValueError):
        GateTimeoutConfig.load(_write(tmp_path, "test_timeout_seconds = true\n"))


def test_string_value_rejected(tmp_path):
    with pytest.raises(ValueError):
        GateTimeoutConfig.load(_write(tmp_path, 'test_timeout_seconds = "30"\n'))


# ── _timeout_error contract (FR-4) ────────────────────────────────────────────

def test_timeout_error_contract():
    res = _timeout_error("test", 5)
    assert res.gate == "test"
    assert res.passed is False
    assert len(res.errors) == 1
    err = res.errors[0]
    assert err.code == "TIMEOUT"
    assert err.severity == "error"
    assert err.message == "test gate timed out after 5 s"
    assert res.duration_ms == 5000


def test_timeout_error_message_interpolates_gate_and_value():
    assert _timeout_error("lint", 30).errors[0].message == "lint gate timed out after 30 s"
    assert _timeout_error("type_check", 45).errors[0].message == "type_check gate timed out after 45 s"
