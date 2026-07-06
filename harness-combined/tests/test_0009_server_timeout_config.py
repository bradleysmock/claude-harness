"""Server-handler config detection (FR-7): gate_run loads .harness.toml from
project_root, gate_run_on_dir from the target directory, and both forward the loaded
GateTimeoutConfig (or None when absent) to the suite runner.
"""
from __future__ import annotations

import server
from gates import GateTimeoutConfig
from models import GateResult


def _passing():
    return [GateResult(gate="lint", passed=True, errors=[], duration_ms=1)]


def test_gate_run_on_dir_loads_config_from_directory(monkeypatch, tmp_path):
    (tmp_path / ".harness.toml").write_text("test_timeout_seconds = 30\n", encoding="utf-8")
    captured = {}

    def fake_suite(stack, directory, fail_fast=True, config=None, **kwargs):
        captured["config"] = config
        return _passing()

    monkeypatch.setattr(server, "run_suite_on_dir", fake_suite)
    server.gate_run_on_dir(str(tmp_path), "python", str(tmp_path))
    assert isinstance(captured["config"], GateTimeoutConfig)
    assert captured["config"].test_timeout_seconds == 30


def test_gate_run_text_loads_config_from_project_root(monkeypatch, tmp_path):
    (tmp_path / ".harness.toml").write_text("default_timeout_seconds = 45\n", encoding="utf-8")
    captured = {}

    def fake_suite(language, implementation, tests, project_root, config=None):
        captured["config"] = config
        return _passing()

    monkeypatch.setattr(server, "run_suite_for", fake_suite)
    server.gate_run("impl", "tests", "python", str(tmp_path))
    assert isinstance(captured["config"], GateTimeoutConfig)
    assert captured["config"].default_timeout_seconds == 45


def test_gate_run_text_absent_config_is_none(monkeypatch, tmp_path):
    captured = {}

    def fake_suite(language, implementation, tests, project_root, config=None):
        captured["config"] = config
        return _passing()

    monkeypatch.setattr(server, "run_suite_for", fake_suite)
    server.gate_run("impl", "tests", "python", str(tmp_path))
    assert captured["config"] is None


def test_gate_run_on_dir_absent_config_is_none(monkeypatch, tmp_path):
    captured = {}

    def fake_suite(stack, directory, fail_fast=True, config=None, **kwargs):
        captured["config"] = config
        return _passing()

    monkeypatch.setattr(server, "run_suite_on_dir", fake_suite)
    server.gate_run_on_dir(str(tmp_path), "python", str(tmp_path))
    assert captured["config"] is None
