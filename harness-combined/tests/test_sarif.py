"""Ticket 0037 — SARIF 2.1.0 emission (unit) and gate_run_on_dir wiring (integration)."""
from __future__ import annotations

import errno
import json
from pathlib import Path

import pytest

from models import GateError, GateResult
from sarif_output import build_sarif, sarif_optin_enabled, write_sarif


def _err(
    message: str = "boom",
    file: str | None = "pkg/mod.py",
    line: int | None = 12,
    column: int | None = 3,
    code: str | None = "E501",
    severity: str = "error",
) -> GateError:
    return GateError(message=message, file=file, line=line, column=column, code=code, severity=severity)


# ── build_sarif: document shape ──────────────────────────────────────────────


def test_build_sarif_top_level_shape() -> None:
    # FR-1/FR-6: version 2.1.0, one run per gate, driver name == gate.
    results = [
        GateResult("ruff", False, [_err(code="E501")], 5),
        GateResult("mypy", False, [_err(code="arg-type", severity="error")], 7),
    ]
    doc = build_sarif(results, "/repo")
    assert doc["version"] == "2.1.0"
    assert "$schema" in doc
    names = [run["tool"]["driver"]["name"] for run in doc["runs"]]
    assert names == ["ruff", "mypy"]


def test_clean_gate_contributes_no_run() -> None:
    # AC: one run per gate tool *that produced findings* — a clean gate emits none.
    doc = build_sarif([GateResult("ruff", True, [], 1)], "/repo")
    assert doc["runs"] == []


def test_multiple_gateresults_same_gate_merge_into_one_run() -> None:
    # FR-7: all findings from a tool live in a single runs entry per gate tool.
    results = [
        GateResult("bandit", False, [_err(severity="high")], 2),
        GateResult("bandit", False, [_err(severity="low")], 2),
    ]
    doc = build_sarif(results, "/repo")
    assert len(doc["runs"]) == 1
    assert len(doc["runs"][0]["results"]) == 2


# ── build_sarif: per-result mapping ──────────────────────────────────────────


def test_file_and_line_map_to_relative_uri_and_startline() -> None:
    # FR-4: physicalLocation with POSIX-relative uri (not absolute) and startLine.
    root = "/repo/project"
    doc = build_sarif([GateResult("ruff", False, [_err(file="src/a.py", line=42)], 1)], root)
    loc = doc["runs"][0]["results"][0]["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "src/a.py"
    assert not loc["artifactLocation"]["uri"].startswith("/")
    assert loc["region"]["startLine"] == 42


def test_code_none_omits_ruleid() -> None:
    # FR-4: GateError.code is None -> no ruleId key at all.
    doc = build_sarif([GateResult("ruff", False, [_err(code=None)], 1)], "/repo")
    assert "ruleId" not in doc["runs"][0]["results"][0]


def test_code_present_sets_ruleid() -> None:
    doc = build_sarif([GateResult("ruff", False, [_err(code="E501")], 1)], "/repo")
    assert doc["runs"][0]["results"][0]["ruleId"] == "E501"


def test_relative_file_resolves_against_worktree_root_not_cwd(tmp_path: Path) -> None:
    # FR-4 rel: a relative file anchors to worktree_root, never the process cwd.
    root = tmp_path / "wt"
    (root / "sub").mkdir(parents=True)
    doc = build_sarif([GateResult("ruff", False, [_err(file="sub/x.py", line=1)], 1)], str(root))
    uri = doc["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert uri == "sub/x.py"


def test_null_file_yields_result_without_physicallocation() -> None:
    # FR-5: a null-file finding (e.g. TOOL_ERROR) is still a result, no location.
    doc = build_sarif([GateResult("mypy", False, [_err(file=None, line=None)], 1)], "/repo")
    result = doc["runs"][0]["results"][0]
    assert "locations" not in result
    assert result["message"]["text"] == "boom"


def test_file_outside_worktree_omits_location_no_absolute_leak(tmp_path: Path) -> None:
    # FR-5 oob: an out-of-bounds file drops the location and leaks no absolute path.
    root = tmp_path / "wt"
    root.mkdir()
    outside = tmp_path / "elsewhere" / "secret.py"
    doc = build_sarif([GateResult("ruff", False, [_err(file=str(outside), line=9)], 1)], str(root))
    result = doc["runs"][0]["results"][0]
    assert "locations" not in result
    assert str(tmp_path) not in json.dumps(doc)


def test_line_none_keeps_artifact_without_region(tmp_path: Path) -> None:
    root = tmp_path / "wt"
    (root / "a.py").parent.mkdir(parents=True, exist_ok=True)
    doc = build_sarif([GateResult("ruff", False, [_err(file="a.py", line=None)], 1)], str(root))
    phys = doc["runs"][0]["results"][0]["locations"][0]["physicalLocation"]
    assert phys["artifactLocation"]["uri"] == "a.py"
    assert "region" not in phys


# ── severity mapping ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "severity,expected",
    [
        ("error", "error"),
        ("ERROR", "error"),
        ("warning", "warning"),
        ("warn", "warning"),
        ("note", "note"),
        ("info", "note"),
        ("information", "note"),
        ("low", "note"),
        ("medium", "warning"),
        ("high", "error"),
        ("something-unknown", "warning"),
    ],
)
def test_severity_mapping(severity: str, expected: str) -> None:
    doc = build_sarif([GateResult("g", False, [_err(severity=severity)], 1)], "/repo")
    assert doc["runs"][0]["results"][0]["level"] == expected


# ── write_sarif: atomic write ────────────────────────────────────────────────


def test_write_sarif_atomic_via_tempfile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # FR-9 ok: temp file lives in out_path.parent and the file lands atomically.
    out = tmp_path / ".harness" / "results.sarif"
    seen: dict[str, str] = {}
    real_mkstemp = __import__("tempfile").mkstemp

    def spy(*args: object, **kwargs: object) -> tuple[int, str]:
        seen["dir"] = str(kwargs.get("dir"))
        return real_mkstemp(*args, **kwargs)

    monkeypatch.setattr("sarif_output.tempfile.mkstemp", spy)
    doc = build_sarif([GateResult("ruff", False, [_err()], 1)], "/repo")
    assert write_sarif(doc, out) is True
    assert seen["dir"] == str(out.parent)
    assert json.loads(out.read_text())["version"] == "2.1.0"


def test_write_sarif_returns_false_on_exdev(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # FR-9 xdev: os.replace raising EXDEV -> return False, no raise, no partial file.
    out = tmp_path / ".harness" / "results.sarif"

    def boom(src: object, dst: object) -> None:
        raise OSError(errno.EXDEV, "cross-device")

    monkeypatch.setattr("sarif_output.os.replace", boom)
    doc = build_sarif([GateResult("ruff", False, [_err()], 1)], "/repo")
    assert write_sarif(doc, out) is False
    assert not out.exists()
    # the temp file was cleaned up
    assert list(out.parent.glob(".results-*")) == []


def test_write_sarif_creates_missing_parent(tmp_path: Path) -> None:
    # FR-9 mkdir: parent directory is created before the temp file.
    out = tmp_path / "deep" / "nested" / ".harness" / "results.sarif"
    doc = build_sarif([GateResult("ruff", False, [_err()], 1)], "/repo")
    assert write_sarif(doc, out) is True
    assert out.exists()


# ── integration: gate_run_on_dir emit_sarif wiring ───────────────────────────

pytest.importorskip("mcp")
import server  # noqa: E402 - after importorskip guard


def _fake_suite_with_findings(stack: object, directory: str, **kwargs: object) -> list[GateResult]:
    return [GateResult("ruff", False, [GateError("bad", "m.py", 3, 1, "E1", "error")], 2)]


def test_emit_sarif_false_writes_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # FR-3: without opt-in, no .sarif file and the response shape is unchanged.
    monkeypatch.setattr(server, "run_suite_on_dir", _fake_suite_with_findings)
    out = json.loads(
        server.gate_run_on_dir(str(tmp_path), "python", str(tmp_path), fail_fast=False)
    )
    assert "sarif_write_failed" not in out
    assert not (tmp_path / ".harness" / "results.sarif").exists()


def test_emit_sarif_true_writes_valid_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # FR-10: emit_sarif=True writes .harness/results.sarif with valid content.
    monkeypatch.setattr(server, "run_suite_on_dir", _fake_suite_with_findings)
    server.gate_run_on_dir(str(tmp_path), "python", str(tmp_path), fail_fast=False, emit_sarif=True)
    sarif_path = tmp_path / ".harness" / "results.sarif"
    assert sarif_path.exists()
    doc = json.loads(sarif_path.read_text())
    assert doc["version"] == "2.1.0"
    assert doc["runs"][0]["tool"]["driver"]["name"] == "ruff"


def test_emit_sarif_write_failure_is_non_fatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # FR-10 fail: a write failure surfaces sarif_write_failed and never crashes.
    monkeypatch.setattr(server, "run_suite_on_dir", _fake_suite_with_findings)
    monkeypatch.setattr("sarif_output.write_sarif", lambda doc, path: False)
    out = json.loads(
        server.gate_run_on_dir(str(tmp_path), "python", str(tmp_path), fail_fast=False, emit_sarif=True)
    )
    assert out["sarif_write_failed"] is True
    assert out["passed"] is False  # the gate verdict is otherwise unchanged


def test_emit_sarif_true_with_clean_gate_writes_empty_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        server, "run_suite_on_dir",
        lambda stack, directory, **kw: [GateResult("ruff", True, [], 1)],
    )
    server.gate_run_on_dir(str(tmp_path), "python", str(tmp_path), fail_fast=False, emit_sarif=True)
    doc = json.loads((tmp_path / ".harness" / "results.sarif").read_text())
    assert doc["runs"] == []


# ── FR-2: _standards.md opt-in and its trust-boundary scope ──────────────────


def _write_standards(root: Path, body: str) -> None:
    tickets = root / ".tickets"
    tickets.mkdir(parents=True, exist_ok=True)
    (tickets / "_standards.md").write_text(body, encoding="utf-8")


def test_optin_enabled_for_exact_lowercase_true(tmp_path: Path) -> None:
    # FR-2: `sarif_output: true` in the harness-root _standards.md enables emission.
    _write_standards(tmp_path, "# standards\n\nsarif_output: true\n")
    assert sarif_optin_enabled(str(tmp_path)) is True


@pytest.mark.parametrize(
    "value",
    ["True", "TRUE", "yes", "on", "1", "false", "  # sarif_output: true (commented)"],
)
def test_optin_rejects_non_lowercase_true(tmp_path: Path, value: str) -> None:
    # FR-2: Python-capitalized True / yes / on are intentionally NOT matched.
    body = value if value.lstrip().startswith("#") else f"sarif_output: {value}"
    _write_standards(tmp_path, f"# standards\n\n{body}\n")
    assert sarif_optin_enabled(str(tmp_path)) is False


def test_optin_fails_closed_when_standards_absent(tmp_path: Path) -> None:
    # No _standards.md at all -> fail closed (False), never raise.
    assert sarif_optin_enabled(str(tmp_path)) is False


def test_optin_scope_worktree_standards_has_no_authority(tmp_path: Path) -> None:
    # FR-2 scope: only <project_root>/.tickets/_standards.md is authoritative.
    project_root = tmp_path / "harness"
    worktree = tmp_path / "worktree"
    project_root.mkdir()
    worktree.mkdir()
    # The opt-in lives ONLY in the scanned worktree — it must be ignored.
    _write_standards(worktree, "sarif_output: true\n")
    assert sarif_optin_enabled(str(project_root)) is False
    # And it IS honored when it lives in the harness root.
    _write_standards(project_root, "sarif_output: true\n")
    assert sarif_optin_enabled(str(project_root)) is True


def test_standards_optin_emits_sarif_without_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # FR-2 wiring: a harness-root opt-in emits SARIF even with emit_sarif=False.
    monkeypatch.setattr(server, "run_suite_on_dir", _fake_suite_with_findings)
    project_root = tmp_path / "harness"
    worktree = tmp_path / "worktree"
    project_root.mkdir()
    worktree.mkdir()
    _write_standards(project_root, "sarif_output: true\n")
    server.gate_run_on_dir(str(worktree), "python", str(project_root), fail_fast=False)
    assert (worktree / ".harness" / "results.sarif").exists()


def test_worktree_optin_does_not_emit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # FR-2 scope wiring: an opt-in inside the scanned worktree does NOT emit.
    monkeypatch.setattr(server, "run_suite_on_dir", _fake_suite_with_findings)
    project_root = tmp_path / "harness"
    worktree = tmp_path / "worktree"
    project_root.mkdir()
    worktree.mkdir()
    _write_standards(worktree, "sarif_output: true\n")  # no authority
    server.gate_run_on_dir(str(worktree), "python", str(project_root), fail_fast=False)
    assert not (worktree / ".harness" / "results.sarif").exists()


def test_ac5_sarif_tools_can_ingest_output(tmp_path: Path) -> None:
    # AC-5 / NFR-2: the emitted SARIF is schema-conformant enough for the real
    # sarif-tools ecosystem loader to parse every record back out. `import sarif`
    # here binds to the third-party sarif-tools package (our module is
    # `sarif_output`), so there is no shadowing — the rename (MAJOR-1) is what
    # makes this cross-check possible.
    pytest.importorskip("sarif", reason="sarif-tools dev/test dep not installed")
    from sarif import loader  # third-party sarif-tools, NOT our sarif_output module

    doc = build_sarif(
        [GateResult("ruff", False, [GateError("boom", "a.py", 7, 1, "E501", "error")], 1)],
        str(tmp_path),
    )
    out = tmp_path / ".harness" / "results.sarif"
    assert write_sarif(doc, out) is True

    records = loader.load_sarif_file(str(out)).get_records()
    assert len(records) == 1
    record = records[0]
    assert record["Tool"] == "ruff"
    assert "E501" in str(record["Code"])
    assert record["Severity"] == "error"
    assert str(record["Line"]) == "7"
