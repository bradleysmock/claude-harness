"""Ticket 0041 — TypeScript test gate: full-suite run + baseline-delta comparison.

The directory-mode Jest gate must run the *entire* suite (no changed-file scoping)
and fail only on failures absent from a cached merge-base baseline. When the baseline
cannot be determined it falls back to full-suite strictness (every failure fails).
Covers FR-1..FR-4 and NFR-1 from requirements.md.

All Jest/git subprocess work is exercised through monkeypatched seams
(``_run_jest_json_dir``, ``_baseline``, ``_merge_base_sha``, ``_compute_baseline_at``)
so the tests are deterministic and need neither node nor a live git checkout.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("mcp")

import gates.typescript as ts  # noqa: E402
from gates import ProcessResult  # noqa: E402
from models import GateResult  # noqa: E402

# ── jest --json fixture builder ────────────────────────────────────────────────

def _jest_json(entries: list[tuple[str, str, str]]) -> str:
    """Build a jest --json stdout blob.

    ``entries`` is a list of ``(relative_file, fullName, status)`` where status is
    ``"passed"`` or ``"failed"``. Groups assertions by file into ``testResults``.
    """
    by_file: dict[str, list[dict]] = {}
    for rel, full, status in entries:
        by_file.setdefault(rel, []).append({
            "fullName": full,
            "title": full.split(" ")[-1],
            "ancestorTitles": full.split(" ")[:-1],
            "status": status,
            "failureMessages": ["Error: boom\n    at x"] if status == "failed" else [],
        })
    num_failed = sum(1 for _, _, s in entries if s == "failed")
    return json.dumps({
        "numFailedTests": num_failed,
        "success": num_failed == 0,
        "testResults": [
            {"name": rel, "assertionResults": ars} for rel, ars in by_file.items()
        ],
    })


def _fake_jest_runner(entries: list[tuple[str, str, str]]):
    rc = 0 if all(s == "passed" for _, _, s in entries) else 1
    blob = _jest_json(entries)

    def _run(root, timeout):  # signature of _run_jest_json_dir
        return ProcessResult(blob, "", rc)

    return _run


# ── _parse_jest_json ───────────────────────────────────────────────────────────

def test_parse_jest_json_collects_failing_ids() -> None:
    blob = _jest_json([
        ("a.test.ts", "Suite adds", "passed"),
        ("a.test.ts", "Suite subtracts", "failed"),
        ("b.test.ts", "Other divides", "failed"),
    ])
    ok, failures = ts._parse_jest_json(blob, Path("/root"))
    assert ok is True
    assert set(failures) == {"a.test.ts::Suite subtracts", "b.test.ts::Other divides"}
    err = failures["a.test.ts::Suite subtracts"]
    assert err.code == "TEST_FAILURE"
    assert err.severity == "error"
    assert "Suite subtracts" in err.message


def test_parse_jest_json_all_passing_is_empty() -> None:
    blob = _jest_json([("a.test.ts", "Suite adds", "passed")])
    ok, failures = ts._parse_jest_json(blob, Path("/root"))
    assert ok is True
    assert failures == {}


def test_parse_jest_json_rejects_non_json() -> None:
    ok, failures = ts._parse_jest_json("not json at all", Path("/root"))
    assert ok is False
    assert failures == {}


def test_parse_jest_json_rejects_json_without_test_results() -> None:
    ok, failures = ts._parse_jest_json(json.dumps({"unexpected": 1}), Path("/root"))
    assert ok is False


# ── _test_gate_dir: full run + delta ───────────────────────────────────────────

def test_broken_untouched_test_fails_gate(monkeypatch, tmp_path: Path) -> None:
    """FR-1 / AC-1: an implementation change that breaks an untouched test fails.

    The failing test is *not* on the baseline, so it gates even though the old
    changed-file scoping would never have run it.
    """
    monkeypatch.setattr(ts, "_run_jest_json_dir", _fake_jest_runner([
        ("untouched.test.ts", "legacy behaves", "failed"),
    ]))
    monkeypatch.setattr(ts, "_baseline", lambda root, timeout=180: set())
    res = ts._test_gate_dir(str(tmp_path))
    assert isinstance(res, GateResult)
    assert res.passed is False
    assert res.mode == "baseline-delta"
    assert res.baseline_excluded == []
    assert any("legacy behaves" in e.message for e in res.errors)


def test_preexisting_baseline_failure_is_excluded(monkeypatch, tmp_path: Path) -> None:
    """FR-2 / AC-2: a failure already present at the merge base does not fail."""
    fid = "flaky.test.ts::already broken"
    monkeypatch.setattr(ts, "_run_jest_json_dir", _fake_jest_runner([
        ("flaky.test.ts", "already broken", "failed"),
    ]))
    monkeypatch.setattr(ts, "_baseline", lambda root, timeout=180: {fid})
    res = ts._test_gate_dir(str(tmp_path))
    assert res.passed is True
    assert res.mode == "baseline-delta"
    assert res.baseline_excluded == [fid]
    assert res.errors == []


def test_new_failure_gates_while_baseline_failure_excluded(monkeypatch, tmp_path: Path) -> None:
    """Mixed set: a new regression fails; a pre-existing failure is only informational."""
    old = "flaky.test.ts::already broken"
    monkeypatch.setattr(ts, "_run_jest_json_dir", _fake_jest_runner([
        ("flaky.test.ts", "already broken", "failed"),
        ("new.test.ts", "regressed", "failed"),
    ]))
    monkeypatch.setattr(ts, "_baseline", lambda root, timeout=180: {old})
    res = ts._test_gate_dir(str(tmp_path))
    assert res.passed is False
    assert res.baseline_excluded == [old]
    assert [e.file for e in res.errors] == ["new.test.ts"]
    assert all("already broken" not in e.message for e in res.errors)


def test_fallback_to_strict_when_baseline_unavailable(monkeypatch, tmp_path: Path) -> None:
    """FR-3: no baseline → every failure fails the gate, mode reported as full."""
    monkeypatch.setattr(ts, "_run_jest_json_dir", _fake_jest_runner([
        ("a.test.ts", "one fails", "failed"),
    ]))
    monkeypatch.setattr(ts, "_baseline", lambda root, timeout=180: None)
    res = ts._test_gate_dir(str(tmp_path))
    assert res.passed is False
    assert res.mode == "full"
    assert res.baseline_excluded == []


def test_green_suite_passes_without_consulting_baseline(monkeypatch, tmp_path: Path) -> None:
    """A fully green run passes and must not pay the baseline-computation cost."""
    called = {"n": 0}

    def _baseline_spy(root, timeout=180):
        called["n"] += 1
        return set()

    monkeypatch.setattr(ts, "_run_jest_json_dir", _fake_jest_runner([
        ("a.test.ts", "all good", "passed"),
    ]))
    monkeypatch.setattr(ts, "_baseline", _baseline_spy)
    res = ts._test_gate_dir(str(tmp_path))
    assert res.passed is True
    assert res.mode == "full"
    assert called["n"] == 0


def test_unparseable_jest_output_falls_back_to_exit_code(monkeypatch, tmp_path: Path) -> None:
    """A jest crash (no JSON) must fall back to strict exit-code semantics."""
    def _run(root, timeout):
        return ProcessResult("segfault, no json", "boom", 1)

    monkeypatch.setattr(ts, "_run_jest_json_dir", _run)
    res = ts._test_gate_dir(str(tmp_path))
    assert res.passed is False
    assert res.errors and res.errors[0].code == "TEST_FAILURE"


def test_scoping_helper_no_longer_gates(monkeypatch, tmp_path: Path) -> None:
    """AC-3: _changed_test_files must not influence pass/fail.

    If it were still consulted it would raise here (patched to blow up); the gate
    must ignore it entirely.
    """
    def _boom(*a, **k):
        raise AssertionError("_changed_test_files must not gate pass/fail")

    monkeypatch.setattr(ts, "_changed_test_files", _boom)
    monkeypatch.setattr(ts, "_run_jest_json_dir", _fake_jest_runner([
        ("a.test.ts", "ok", "passed"),
    ]))
    monkeypatch.setattr(ts, "_baseline", lambda root, timeout=180: set())
    res = ts._test_gate_dir(str(tmp_path))
    assert res.passed is True


# ── _baseline: cache keying + fallback ─────────────────────────────────────────

def test_baseline_none_when_git_absent(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ts.shutil, "which", lambda _: None)
    assert ts._baseline(tmp_path) is None


def test_baseline_none_when_no_merge_base(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ts.shutil, "which", lambda _: "/usr/bin/git")
    monkeypatch.setattr(ts, "_merge_base_sha", lambda root, base: None)
    assert ts._baseline(tmp_path) is None


def test_baseline_cache_miss_computes_then_caches(monkeypatch, tmp_path: Path) -> None:
    """NFR-1: compute at most once per SHA; the second call reads the cache."""
    calls = {"n": 0}

    def _compute(root, sha, timeout):
        calls["n"] += 1
        return {"x.test.ts::a", "y.test.ts::b"}

    monkeypatch.setattr(ts.shutil, "which", lambda _: "/usr/bin/git")
    monkeypatch.setattr(ts, "_merge_base_sha", lambda root, base: "deadbeef")
    monkeypatch.setattr(ts, "_compute_baseline_at", _compute)

    first = ts._baseline(tmp_path)
    second = ts._baseline(tmp_path)
    assert first == {"x.test.ts::a", "y.test.ts::b"}
    assert second == first
    assert calls["n"] == 1  # cached on the second call
    cache = tmp_path / ".harness" / "test-baselines" / "deadbeef.json"
    assert cache.exists()


def test_baseline_cache_hit_does_not_recompute(monkeypatch, tmp_path: Path) -> None:
    cache = tmp_path / ".harness" / "test-baselines" / "cafe.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({"sha": "cafe", "failing": ["a.test.ts::z"]}))

    def _boom(root, sha, timeout):
        raise AssertionError("cache hit must not recompute")

    monkeypatch.setattr(ts.shutil, "which", lambda _: "/usr/bin/git")
    monkeypatch.setattr(ts, "_merge_base_sha", lambda root, base: "cafe")
    monkeypatch.setattr(ts, "_compute_baseline_at", _boom)
    assert ts._baseline(tmp_path) == {"a.test.ts::z"}


def test_baseline_dirty_cache_falls_back_to_strict(monkeypatch, tmp_path: Path) -> None:
    """FR-3: a corrupt cache file for the SHA yields strict fallback (None)."""
    cache = tmp_path / ".harness" / "test-baselines" / "beef.json"
    cache.parent.mkdir(parents=True)
    cache.write_text("{not valid json")

    monkeypatch.setattr(ts.shutil, "which", lambda _: "/usr/bin/git")
    monkeypatch.setattr(ts, "_merge_base_sha", lambda root, base: "beef")
    monkeypatch.setattr(ts, "_compute_baseline_at",
                        lambda root, sha, timeout: (_ for _ in ()).throw(AssertionError("no compute")))
    assert ts._baseline(tmp_path) is None


def test_baseline_none_when_compute_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ts.shutil, "which", lambda _: "/usr/bin/git")
    monkeypatch.setattr(ts, "_merge_base_sha", lambda root, base: "1234")
    monkeypatch.setattr(ts, "_compute_baseline_at", lambda root, sha, timeout: None)
    assert ts._baseline(tmp_path) is None
    # a failed computation must not leave a poisoned cache entry
    assert not (tmp_path / ".harness" / "test-baselines" / "1234.json").exists()


# ── GateResult model fields ────────────────────────────────────────────────────

def test_gate_result_defaults_have_no_mode() -> None:
    r = GateResult(gate="lint", passed=True, errors=[], duration_ms=1)
    assert r.mode is None
    assert r.baseline_excluded == []
    d = r.to_dict()
    assert "mode" not in d
    assert "baseline_excluded" not in d


# ── _compute_baseline_at: real git worktree integration (only jest injected) ───

def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True,
                   capture_output=True, text=True)


def _init_repo(root: Path) -> str:
    """Init a git repo with one commit; return its SHA."""
    subprocess.run(["git", "init", "-q", str(root)], check=True,
                   capture_output=True, text=True)
    _git(root, "config", "user.email", "t@t.t")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    (root / "impl.ts").write_text("export const x = 1;\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                         check=True, capture_output=True, text=True)
    return out.stdout.strip()


@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
def test_compute_baseline_at_runs_in_worktree_and_cleans_up(monkeypatch, tmp_path: Path) -> None:
    """M-1: exercise the real worktree add/parse/cleanup + B-1 node_modules symlink.

    Only ``_run_jest_json_dir`` is injected; ``git worktree add/remove`` and
    ``_repo_prefix`` run for real. The injected runner asserts the baseline worktree
    exists and has a ``node_modules`` symlink at call time (proving B-1's fix), then
    returns a canned failing report.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    sha = _init_repo(repo)
    (repo / "node_modules").mkdir()  # HEAD checkout's installed deps

    seen: dict[str, object] = {}

    def _fake_run(root, timeout):
        seen["root"] = Path(root)
        seen["has_node_modules"] = (Path(root) / "node_modules").exists()
        seen["nm_is_symlink"] = (Path(root) / "node_modules").is_symlink()
        blob = _jest_json([("impl.test.ts", "Suite fails", "failed")])
        return ProcessResult(blob, "", 1)

    monkeypatch.setattr(ts, "_run_jest_json_dir", _fake_run)

    result = ts._compute_baseline_at(repo, sha, 60)

    assert result == {"impl.test.ts::Suite fails"}
    # Ran inside a detached worktree (not the repo itself), with deps provisioned.
    assert seen["root"] != repo
    assert seen["has_node_modules"] is True
    assert seen["nm_is_symlink"] is True
    # The throwaway worktree was removed — the repo has no lingering worktrees.
    wt = subprocess.run(["git", "-C", str(repo), "worktree", "list", "--porcelain"],
                        capture_output=True, text=True).stdout
    assert str(seen["root"]) not in wt


@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
def test_compute_baseline_at_returns_none_on_unparseable_jest(monkeypatch, tmp_path: Path) -> None:
    """A baseline run that yields no JSON returns None (→ caller runs strict)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    sha = _init_repo(repo)
    monkeypatch.setattr(ts, "_run_jest_json_dir",
                        lambda root, timeout: ProcessResult("jest exploded", "err", 1))
    assert ts._compute_baseline_at(repo, sha, 60) is None


def test_gate_result_to_dict_carries_mode_and_excluded() -> None:
    r = GateResult(gate="test", passed=True, errors=[], duration_ms=2,
                   mode="baseline-delta", baseline_excluded=["a.test.ts::x"])
    d = r.to_dict()
    assert d["mode"] == "baseline-delta"
    assert d["baseline_excluded"] == ["a.test.ts::x"]


# ── gate-findings.md rendering (FR-4) ──────────────────────────────────────────

def test_findings_render_mode_and_baseline_excluded() -> None:
    from models import LanguageResult, StackName
    from server import _format_polyglot_findings

    gr = GateResult(
        gate="test", passed=True, errors=[], duration_ms=9,
        mode="baseline-delta", baseline_excluded=["legacy.test.ts::flaky one"],
    )
    out = _format_polyglot_findings(
        [LanguageResult(StackName.TYPESCRIPT, [gr])], "/wt"
    )
    assert "**Mode**: baseline-delta" in out
    assert "legacy.test.ts::flaky one" in out
    # baseline exclusions are informational, not failures
    assert "**Status**: PASS" in out


def test_findings_render_omits_mode_for_non_test_gates() -> None:
    from models import LanguageResult, StackName
    from server import _format_polyglot_findings

    gr = GateResult(gate="lint", passed=True, errors=[], duration_ms=3)
    out = _format_polyglot_findings(
        [LanguageResult(StackName.PYTHON, [gr])], "/wt"
    )
    assert "**Mode**" not in out
