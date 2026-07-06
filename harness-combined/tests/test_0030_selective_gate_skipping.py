"""Ticket 0030 — selective gate skipping via changed_files scope matching.

Covers the Test Plan in solution.md: scope-match semantics (FR-3/6/7), the
GateResult skip shape and to_dict contract (FR-4), per-language suite skipping,
fail-fast interaction (FR-9), init threading, the server changed_files parameter
+ cap + any_skipped (FR-2/7, NFR-4/1), and the /gate command documentation (FR-5/8).
"""
from __future__ import annotations

import inspect
import time
from pathlib import Path
from types import SimpleNamespace

import gates
import server
from gates import go as gomod
from gates import python as pymod
from gates import rust as rustmod
from gates import typescript as tsmod
from gates._scope import SKIP_REASON, has_scope_match
from gates.go import run_go_suite_on_dir
from gates.python import run_python_suite_on_dir
from gates.rust import run_rust_suite_on_dir
from gates.typescript import run_typescript_suite_on_dir
from models import GateResult

_ROOT = Path(__file__).resolve().parents[1]


# ── FR-3 / FR-6 / FR-7 : has_scope_match semantics ───────────────────────────

def test_no_overlap_returns_false() -> None:
    assert has_scope_match(["README.md"], ["*.py"]) is False


def test_overlap_returns_true() -> None:
    assert has_scope_match(["src/foo.py"], ["*.py"]) is True


def test_nested_path_matches_suffix_pattern() -> None:
    # PurePosixPath.match semantics: *.py matches at any directory depth.
    assert has_scope_match(["src/sub/foo.py"], ["*.py"]) is True


def test_none_changed_files_runs_gate() -> None:
    assert has_scope_match(None, ["*.py"]) is True


def test_empty_changed_files_runs_gate() -> None:
    assert has_scope_match([], ["*.py"]) is True


def test_none_scope_never_skips() -> None:
    # FR-6: a gate with no declared scope is never skipped, for any changed set.
    assert has_scope_match(["README.md"], None) is True
    assert has_scope_match(["anything.xyz"], None) is True


def test_literal_filename_patterns() -> None:
    assert has_scope_match(["go.mod"], ["*.go", "go.mod", "go.sum"]) is True
    assert has_scope_match(["vendor/go.mod"], ["go.mod"]) is True
    assert has_scope_match(["cargo.mod"], ["go.mod"]) is False


def test_markdown_only_diff_skips_all_source_scopes() -> None:
    files = ["README.md", "docs/guide.md"]
    for scope in (["*.py", "*.pyi"], ["*.ts", "*.tsx"], ["*.go", "go.mod"], ["*.rs", "Cargo.toml"]):
        assert has_scope_match(files, scope) is False


def test_perf_budget_10k_files(  # NFR-1: < 10 ms for 10k files x 5 patterns
) -> None:
    files = [f"src/pkg/module_{i}.rs" for i in range(10_000)]
    pats = ["*.py", "*.pyi", "*.ts", "*.tsx", "*.js"]  # deliberately no match
    has_scope_match(files, pats)  # warm
    best = min(
        (lambda s: (has_scope_match(files, pats), time.perf_counter() - s)[1])(time.perf_counter())
        for _ in range(10)
    )
    assert best < 0.010, f"scope match took {best * 1e3:.2f} ms (> 10 ms budget)"


# ── FR-4 : GateResult skip shape + to_dict contract ──────────────────────────

def test_skipped_result_to_dict_includes_skip_fields() -> None:
    r = GateResult(gate="lint", passed=True, errors=[], duration_ms=0,
                   skipped=True, skip_reason="no relevant changes")
    d = r.to_dict()
    assert d["skipped"] is True
    assert d["skip_reason"] == "no relevant changes"


def test_non_skipped_to_dict_omits_skip_fields() -> None:
    r = GateResult(gate="lint", passed=True, errors=[], duration_ms=5)
    d = r.to_dict()
    assert "skipped" not in d
    assert "skip_reason" not in d
    assert d == {"gate": "lint", "passed": True, "errors": [], "duration_ms": 5}


def test_gateresult_defaults_backcompat() -> None:
    # Original four-field construction still works; new fields default off.
    r = GateResult("test", True, [], 3)
    assert r.skipped is False and r.skip_reason == ""


# ── FR-1 : every dir-mode gate declares a scope (GateSpec) ────────────────────

def _dir_gate_specs(run_fn, monkeypatch, gate_mod) -> list[list[str] | None]:
    """Capture the scope_patterns a suite iterates by faking has_scope_match to
    record each spec.scope_patterns it is asked about."""
    seen: list[list[str] | None] = []
    real = has_scope_match

    def spy(changed, patterns):
        seen.append(patterns)
        return real(changed, patterns)

    # Each language module imported has_scope_match into its own namespace.
    monkeypatch.setattr(gate_mod, "has_scope_match", spy)
    run_fn(".", changed_files=["README.md"])  # all skip; no gate fn invoked
    return seen


def test_every_python_gate_has_scope(monkeypatch) -> None:
    patterns = _dir_gate_specs(run_python_suite_on_dir, monkeypatch, __import__("gates.python", fromlist=["x"]))
    assert len(patterns) == 4
    assert all(p == ["*.py", "*.pyi"] for p in patterns)


def test_every_typescript_gate_has_scope(monkeypatch) -> None:
    patterns = _dir_gate_specs(run_typescript_suite_on_dir, monkeypatch, tsmod)
    assert len(patterns) == 3
    assert all(p == ["*.ts", "*.tsx", "*.js", "*.jsx"] for p in patterns)


def test_every_go_gate_has_scope(monkeypatch) -> None:
    patterns = _dir_gate_specs(run_go_suite_on_dir, monkeypatch, gomod)
    assert len(patterns) == 3
    assert all(p == ["*.go", "go.mod", "go.sum"] for p in patterns)


def test_every_rust_gate_has_scope(monkeypatch) -> None:
    patterns = _dir_gate_specs(run_rust_suite_on_dir, monkeypatch, rustmod)
    assert len(patterns) == 3
    assert all(p == ["*.rs", "Cargo.toml", "Cargo.lock"] for p in patterns)


# ── Per-suite skip behaviour: no gate fn runs when scope misses ──────────────

def _fake_subprocess_success(monkeypatch) -> dict:
    called = {"n": 0}

    def fake_run(argv, **kw):
        called["n"] += 1
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(gates.subprocess, "run", fake_run)
    return called


def test_python_suite_skips_all_on_markdown_diff(monkeypatch, tmp_path: Path) -> None:
    called = _fake_subprocess_success(monkeypatch)
    results = run_python_suite_on_dir(str(tmp_path), changed_files=["README.md"])
    assert [r.gate for r in results] == ["lint", "type_check", "test", "security"]
    assert all(r.skipped and r.passed and r.skip_reason == SKIP_REASON for r in results)
    assert called["n"] == 0  # no gate subprocess ran


def test_python_suite_runs_on_py_diff(monkeypatch, tmp_path: Path) -> None:
    called = _fake_subprocess_success(monkeypatch)
    results = run_python_suite_on_dir(str(tmp_path), changed_files=["src/a.py"])
    assert all(not r.skipped and r.passed for r in results)
    assert called["n"] >= 1  # gates actually ran


def test_python_suite_no_changed_files_preserves_behaviour(monkeypatch, tmp_path: Path) -> None:
    _fake_subprocess_success(monkeypatch)
    results = run_python_suite_on_dir(str(tmp_path))
    assert all(not r.skipped for r in results)


def test_typescript_suite_skips_on_markdown(monkeypatch, tmp_path: Path) -> None:
    _fake_subprocess_success(monkeypatch)
    results = run_typescript_suite_on_dir(str(tmp_path), changed_files=["README.md"])
    assert all(r.skipped and r.passed for r in results)


def test_go_suite_skips_on_markdown(monkeypatch, tmp_path: Path) -> None:
    _fake_subprocess_success(monkeypatch)
    results = run_go_suite_on_dir(str(tmp_path), changed_files=["README.md"])
    assert all(r.skipped and r.passed for r in results)


def test_rust_suite_skips_on_markdown(monkeypatch, tmp_path: Path) -> None:
    _fake_subprocess_success(monkeypatch)
    results = run_rust_suite_on_dir(str(tmp_path), changed_files=["README.md"])
    assert all(r.skipped and r.passed for r in results)


# ── FR-9 : a skipped gate does not trip fail-fast ────────────────────────────

def test_failfast_skipped_gate_does_not_shortcircuit(monkeypatch, tmp_path: Path) -> None:
    # FR-9: a skipped gate (passed=True) must NOT trip fail-fast — the loop must
    # continue to the next gate. All four Python gates share _PY_SCOPE, so scope
    # alone can't skip one and run another; drive it by faking has_scope_match to
    # skip only the FIRST gate (lint), then make the next gate (type_check) fail.
    calls = {"n": 0}

    def fake_scope(changed, patterns):
        calls["n"] += 1
        return calls["n"] != 1  # skip gate #1 (lint); run the rest

    monkeypatch.setattr(pymod, "has_scope_match", fake_scope)

    def fake_run(argv, **kw):
        if "mypy" in argv:  # type_check fails
            return SimpleNamespace(stdout="err.py:1: error: boom [x]", stderr="", returncode=1)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(gates.subprocess, "run", fake_run)
    results = run_python_suite_on_dir(str(tmp_path), fail_fast=True, changed_files=["x.py"])
    # lint skipped (passing) did not short-circuit; type_check ran, failed, and
    # fail-fast then stopped before test/security.
    assert results[0].gate == "lint" and results[0].skipped is True and results[0].passed is True
    assert results[1].gate == "type_check" and results[1].passed is False and results[1].skipped is False
    assert [r.gate for r in results] == ["lint", "type_check"]


# ── init threading ───────────────────────────────────────────────────────────

def test_run_suite_on_dir_threads_changed_files(monkeypatch, tmp_path: Path) -> None:
    _fake_subprocess_success(monkeypatch)
    results = gates.run_suite_on_dir("python", str(tmp_path), changed_files=["README.md"])
    lang_gates = [r for r in results if r.gate in {"lint", "type_check", "test", "security"}]
    assert lang_gates and all(r.skipped for r in lang_gates)


def test_run_suite_for_signature_unchanged() -> None:
    # Text mode must NOT gain changed_files (directory-mode only per solution).
    assert "changed_files" not in inspect.signature(gates.run_suite_for).parameters
    assert "changed_files" in inspect.signature(gates.run_suite_on_dir).parameters


# ── server.gate_run_on_dir : changed_files param, cap, any_skipped ───────────

def _install_fake_suite(monkeypatch, record: list[dict]):
    monkeypatch.setattr(server, "load_gate_overrides", lambda p: {})

    def fake_suite(language, directory, **kwargs):
        record.append(kwargs)
        cf = kwargs.get("changed_files")
        scope = ["*.py", "*.pyi"]
        out = []
        for name in ("lint", "type_check", "test", "security"):
            if not has_scope_match(cf, scope):
                out.append(GateResult(name, True, [], 0, skipped=True, skip_reason=SKIP_REASON))
            else:
                out.append(GateResult(name, True, [], 1))
        return out

    monkeypatch.setattr(server, "run_suite_on_dir", fake_suite)


def test_server_all_skipped_sets_any_skipped(monkeypatch, tmp_path: Path) -> None:
    import json
    record: list[dict] = []
    _install_fake_suite(monkeypatch, record)
    out = json.loads(server.gate_run_on_dir(str(tmp_path), "python", str(tmp_path),
                                            changed_files=["README.md"]))
    assert out["passed"] is True
    assert out["any_skipped"] is True
    assert record[0]["changed_files"] == ["README.md"]
    # FR-8: a single-language all-skipped run must still surface a findings body
    # /gate can write, with SKIP status + reason (not PASS/clean).
    assert "**Status**: SKIP" in out["findings_md"]
    assert "no relevant changes" in out["findings_md"]
    assert "**Status**: PASS" not in out["findings_md"]


# ── FR-8 : findings body renders skipped gates as SKIP (not PASS) ─────────────

def test_findings_md_renders_skip_status_and_reason() -> None:
    from models import LanguageResult, StackName
    lr = LanguageResult(StackName.PYTHON, [
        GateResult("lint", True, [], 0, skipped=True, skip_reason="no relevant changes"),
        GateResult("type_check", True, [], 12),  # ran + clean, for contrast
    ])
    body = server._format_polyglot_findings([lr], ".")
    assert "## lint" in body
    assert "**Status**: SKIP" in body
    assert "**Reason**: no relevant changes" in body
    # the gate that actually ran is still PASS/clean, not mislabeled
    assert "## type_check" in body
    assert body.count("**Status**: SKIP") == 1


def test_findings_md_polyglot_skip_labels_language() -> None:
    from models import LanguageResult, StackName
    results = [
        LanguageResult(StackName.PYTHON, [
            GateResult("lint", True, [], 0, skipped=True, skip_reason="no relevant changes"),
        ]),
        LanguageResult(StackName.TYPESCRIPT, [GateResult("test", True, [], 5)]),
    ]
    body = server._format_polyglot_findings(results, ".")
    assert "## python / lint" in body
    assert "**Status**: SKIP" in body
    assert "## typescript / test" in body


def test_server_no_changed_files_omits_any_skipped(monkeypatch, tmp_path: Path) -> None:
    import json
    record: list[dict] = []
    _install_fake_suite(monkeypatch, record)
    out = json.loads(server.gate_run_on_dir(str(tmp_path), "python", str(tmp_path)))
    assert out == {"passed": True, "language": "python"}  # byte-for-byte prior shape
    assert "changed_files" not in record[0]


def test_server_caps_oversize_changed_files(monkeypatch, tmp_path: Path) -> None:
    import json
    record: list[dict] = []
    _install_fake_suite(monkeypatch, record)
    huge = [f"f{i}.py" for i in range(server.MAX_CHANGED_FILES + 1)]
    out = json.loads(server.gate_run_on_dir(str(tmp_path), "python", str(tmp_path),
                                            changed_files=huge))
    # Oversize list treated as None -> all gates run, no skip, prior shape.
    assert out == {"passed": True, "language": "python"}
    assert "changed_files" not in record[0]


def test_server_signature_has_changed_files() -> None:
    assert "changed_files" in inspect.signature(server.gate_run_on_dir).parameters


# ── FR-5 / FR-8 : /gate command documentation ────────────────────────────────

def _gate_md() -> str:
    return (_ROOT / "commands" / "gate.md").read_text(encoding="utf-8")


def test_gate_md_documents_git_diff_and_fallbacks() -> None:
    text = _gate_md()
    assert "git diff --name-only HEAD" in text
    assert "git diff --name-only --cached" in text
    assert "changed_files=None" in text


def test_gate_md_documents_changed_files_argument() -> None:
    text = _gate_md()
    assert "changed_files" in text
    assert "any_skipped" in text


def test_gate_md_documents_skip_status_and_reason() -> None:
    text = _gate_md()
    assert "**Status**: PASS | FAIL | SKIP" in text
    assert "no relevant changes" in text
