"""Tests for audit.py — identity-stamped audit log (ticket 0075)."""
from __future__ import annotations

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import audit


def test_record_writes_one_well_formed_line(tmp_path: Path) -> None:
    audit.record("deliver", "0001", "merged to main", root=tmp_path)
    lines = (tmp_path / ".harness" / "audit.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["action"] == "deliver"
    assert entry["ticket"] == "0001"
    assert entry["detail"] == "merged to main"
    assert "who" in entry and "ts" in entry


def test_record_creates_harness_dir_if_absent(tmp_path: Path) -> None:
    assert not (tmp_path / ".harness").exists()
    audit.record("deliver", "0001", "x", root=tmp_path)
    assert (tmp_path / ".harness" / "audit.log").exists()


def test_identity_falls_back_to_user_env_when_git_config_unset(
    tmp_path: Path, monkeypatch
) -> None:
    def _fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="")

    monkeypatch.setattr(audit.subprocess, "run", _fake_run)
    monkeypatch.setenv("USER", "envuser")
    audit.record("deliver", "0001", "x", root=tmp_path)
    entry = json.loads(
        (tmp_path / ".harness" / "audit.log").read_text(encoding="utf-8").splitlines()[0]
    )
    assert entry["who"] == "envuser"


def test_identity_falls_back_to_getpass_when_git_and_env_absent(
    tmp_path: Path, monkeypatch
) -> None:
    def _fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="")

    monkeypatch.setattr(audit.subprocess, "run", _fake_run)
    monkeypatch.delenv("USER", raising=False)
    monkeypatch.setattr(audit.getpass, "getuser", lambda: "getpassuser")
    audit.record("deliver", "0001", "x", root=tmp_path)
    entry = json.loads(
        (tmp_path / ".harness" / "audit.log").read_text(encoding="utf-8").splitlines()[0]
    )
    assert entry["who"] == "getpassuser"


def test_identity_all_fail_writes_unknown(tmp_path: Path, monkeypatch) -> None:
    def _fake_run(cmd, **kwargs):
        raise OSError("no git")

    def _fake_getuser():
        raise OSError("no passwd entry")

    monkeypatch.setattr(audit.subprocess, "run", _fake_run)
    monkeypatch.delenv("USER", raising=False)
    monkeypatch.setattr(audit.getpass, "getuser", _fake_getuser)
    audit.record("deliver", "0001", "x", root=tmp_path)
    entry = json.loads(
        (tmp_path / ".harness" / "audit.log").read_text(encoding="utf-8").splitlines()[0]
    )
    assert entry["who"] == "unknown"


def test_read_filters_by_ticket(tmp_path: Path) -> None:
    audit.record("deliver", "0001", "a", root=tmp_path)
    audit.record("deliver", "0002", "b", root=tmp_path)
    entries = audit.read("0001", root=tmp_path)
    assert len(entries) == 1
    assert entries[0]["ticket"] == "0001"


def test_read_none_returns_all(tmp_path: Path) -> None:
    audit.record("deliver", "0001", "a", root=tmp_path)
    audit.record("rollback", "0002", "b", root=tmp_path)
    assert len(audit.read(None, root=tmp_path)) == 2


def test_read_missing_file_returns_empty(tmp_path: Path) -> None:
    assert audit.read(None, root=tmp_path) == []


def test_read_skips_one_bad_line_among_good_ones(tmp_path: Path) -> None:
    log_path = tmp_path / ".harness" / "audit.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        '{"ts": "t", "who": "a", "action": "deliver", "ticket": "0001", "detail": "x"}\n'
        "not json at all\n"
        '{"ts": "t", "who": "a", "action": "deliver", "ticket": "0002", "detail": "y"}\n',
        encoding="utf-8",
    )
    entries = audit.read(None, root=tmp_path)
    assert len(entries) == 2
    assert entries[0]["ticket"] == "0001"
    assert entries[1]["ticket"] == "0002"


def test_concurrent_writers_produce_non_interleaved_lines(tmp_path: Path) -> None:
    def _write(i: int) -> None:
        audit.record("deliver", f"{i:04d}", "x" * 200, root=tmp_path)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_write, range(20)))

    lines = (tmp_path / ".harness" / "audit.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 20
    for line in lines:
        json.loads(line)  # every line parses cleanly — no interleaving


def test_record_uses_single_os_write_call(tmp_path: Path, monkeypatch) -> None:
    calls: list[bytes] = []
    real_write = os.write

    def _tracking_write(fd, data):
        calls.append(data)
        return real_write(fd, data)

    monkeypatch.setattr(audit.os, "write", _tracking_write)
    audit.record("deliver", "0001", "x", root=tmp_path)
    assert len(calls) == 1
