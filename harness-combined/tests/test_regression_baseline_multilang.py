"""Regression baseline-delta generalized to Python, Go, and Rust (follow-up to 0041).

The TypeScript test gate (ticket 0041) runs the full suite and subtracts a cached
merge-base failure set. This follow-up extracts that machinery into
``gates/_baseline.py`` and routes Python / Go / Rust through it. Two tiers of tests:

* **Toolchain-independent unit tests** — ``compute_delta`` math, the SHA-keyed cache
  read/write, ``load_baseline`` orchestration and the shared ``build_delta_result``
  finisher. These never launch a real compiler/test-runner and MUST always pass.
* **Integration tests** — each guarded with ``skipif`` on the language toolchain.
  They run the *real* suite (pytest / go / cargo) with the baseline injected, so the
  language-specific ``failing_test_ids`` parsers are exercised against genuine output.

TS integration is already covered by ``test_0041_ts_baseline_delta.py``; a TS run here
would need jest (not installed), so it is intentionally omitted (see module docstring
of 0041 for the jest-injection pattern).
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

pytest.importorskip("mcp")

import gates._baseline as bl  # noqa: E402
import gates.go as gomod  # noqa: E402
import gates.python as pymod  # noqa: E402
import gates.rust as rustmod  # noqa: E402
from models import GateError, GateResult  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════
# Toolchain-independent unit tests — MUST always pass
# ══════════════════════════════════════════════════════════════════════════════

# ── compute_delta math ─────────────────────────────────────────────────────────

def test_compute_delta_pass_to_fail_detected() -> None:
    """A test failing now but not at baseline is a new failure (gates)."""
    d = bl.compute_delta({"a.py::t_new"}, set())
    assert d.new_failures == ["a.py::t_new"]
    assert d.baseline_excluded == []
    assert d.removed == []
    assert d.ok is False
    assert d.gating == ["a.py::t_new"]


def test_compute_delta_baseline_excluded_not_gating() -> None:
    """A failure already present at the merge base is reported, not gated."""
    d = bl.compute_delta({"a.py::t_old"}, {"a.py::t_old"})
    assert d.new_failures == []
    assert d.baseline_excluded == ["a.py::t_old"]
    assert d.ok is True


def test_compute_delta_new_failing_isolated_from_preexisting() -> None:
    """Mixed set: only the genuinely new failure gates; the pre-existing one is
    excluded and a baseline-only failure (now gone) is ignored entirely."""
    d = bl.compute_delta(
        current_failing={"a.py::t_old", "b.py::t_new"},
        baseline_failing={"a.py::t_old", "c.py::t_vanished"},
    )
    assert d.new_failures == ["b.py::t_new"]
    assert d.baseline_excluded == ["a.py::t_old"]
    # c.py::t_vanished was failing at baseline and is not failing now — not a
    # regression, must never appear anywhere.
    assert "c.py::t_vanished" not in d.new_failures
    assert "c.py::t_vanished" not in d.removed


def test_compute_delta_preexisting_failure_ignored_when_present_supplied() -> None:
    """Present sets do not turn a still-failing baseline failure into a regression."""
    d = bl.compute_delta(
        current_failing={"a.py::t_old"},
        baseline_failing={"a.py::t_old"},
        current_present={"a.py::t_old", "a.py::t_ok"},
        baseline_present={"a.py::t_old", "a.py::t_ok"},
    )
    assert d.new_failures == []
    assert d.removed == []
    assert d.baseline_excluded == ["a.py::t_old"]


def test_compute_delta_pass_to_removed_detected() -> None:
    """A test present-and-passing at baseline but absent now is a regression."""
    d = bl.compute_delta(
        current_failing=set(),
        baseline_failing=set(),
        current_present={"a.py::t_ok"},
        baseline_present={"a.py::t_ok", "a.py::t_gone"},
    )
    assert d.removed == ["a.py::t_gone"]
    assert d.new_failures == []
    assert d.ok is False
    assert d.gating == ["a.py::t_gone"]


def test_compute_delta_removed_ignores_baseline_failing_now_absent() -> None:
    """A test that was FAILING at baseline and is now absent is not a removed-pass
    regression (it never passed)."""
    d = bl.compute_delta(
        current_failing=set(),
        baseline_failing={"a.py::t_bad"},
        current_present={"a.py::t_ok"},
        baseline_present={"a.py::t_ok", "a.py::t_bad"},
    )
    assert d.removed == []
    assert d.ok is True


def test_compute_delta_no_removed_without_present_sets() -> None:
    """Without present sets, removed-detection is disabled (TS's failing-only path)."""
    d = bl.compute_delta({"a.py::t_new"}, {"a.py::t_old"})
    assert d.removed == []


# ── SHA-keyed cache read/write ─────────────────────────────────────────────────

def test_cache_path_keyed_by_sha(tmp_path: Path) -> None:
    p1 = bl.baseline_cache_path(tmp_path, "sha1")
    p2 = bl.baseline_cache_path(tmp_path, "sha2")
    assert p1 != p2
    assert p1.name == "sha1.json"
    assert p1.parent == tmp_path / ".harness" / "test-baselines"


def test_failing_cache_roundtrip(tmp_path: Path) -> None:
    p = bl.baseline_cache_path(tmp_path, "abc")
    bl.write_failing_cache(p, "abc", {"a.py::t", "b.py::u"})
    assert p.exists()
    assert bl.read_failing_cache(p) == {"a.py::t", "b.py::u"}
    # persisted content is SHA-tagged and sorted
    data = json.loads(p.read_text())
    assert data["sha"] == "abc"
    assert data["failing"] == ["a.py::t", "b.py::u"]
    assert "present" not in data  # failing-only cache stays minimal (TS parity)


def test_collection_cache_roundtrip(tmp_path: Path) -> None:
    p = bl.baseline_cache_path(tmp_path, "def")
    coll = bl.SuiteCollection.of({"a::bad"}, {"a::bad", "a::ok"})
    bl.write_collection_cache(p, "def", coll)
    got = bl.read_collection_cache(p)
    assert got is not None
    assert got.failing == frozenset({"a::bad"})
    assert got.present == frozenset({"a::bad", "a::ok"})


def test_failing_cache_dirty_returns_none(tmp_path: Path) -> None:
    p = bl.baseline_cache_path(tmp_path, "bad")
    p.parent.mkdir(parents=True)
    p.write_text("{not valid json")
    assert bl.read_failing_cache(p) is None


def test_collection_cache_dirty_returns_none(tmp_path: Path) -> None:
    p = bl.baseline_cache_path(tmp_path, "bad")
    p.parent.mkdir(parents=True)
    p.write_text("{not valid json")
    assert bl.read_collection_cache(p) is None


def test_collection_cache_missing_present_key_returns_none(tmp_path: Path) -> None:
    """A failing-only payload cannot satisfy a collection read (no present set)."""
    p = bl.baseline_cache_path(tmp_path, "old")
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"sha": "old", "failing": ["a::b"]}))
    assert bl.read_collection_cache(p) is None


# ── load_baseline orchestration (fake merge-base + compute) ────────────────────

def _git_present(monkeypatch) -> None:
    monkeypatch.setattr(bl.shutil, "which", lambda _: "/usr/bin/git")


def test_load_baseline_none_when_git_absent(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(bl.shutil, "which", lambda _: None)
    out = bl.load_baseline(
        tmp_path, "main", 180,
        merge_base_fn=lambda r, b: "sha",
        compute_fn=lambda r, s, t: {"x"},
        read_cache=bl.read_failing_cache, write_cache=bl.write_failing_cache,
    )
    assert out is None


def test_load_baseline_none_when_no_merge_base(monkeypatch, tmp_path: Path) -> None:
    _git_present(monkeypatch)
    out = bl.load_baseline(
        tmp_path, "main", 180,
        merge_base_fn=lambda r, b: None,
        compute_fn=lambda r, s, t: {"x"},
        read_cache=bl.read_failing_cache, write_cache=bl.write_failing_cache,
    )
    assert out is None


def test_load_baseline_cache_miss_computes_then_reads(monkeypatch, tmp_path: Path) -> None:
    _git_present(monkeypatch)
    calls = {"n": 0}

    def compute(root, sha, timeout):
        calls["n"] += 1
        return {"x.py::a", "y.py::b"}

    kw = dict(
        merge_base_fn=lambda r, b: "deadbeef", compute_fn=compute,
        read_cache=bl.read_failing_cache, write_cache=bl.write_failing_cache,
    )
    first = bl.load_baseline(tmp_path, "main", 180, **kw)
    second = bl.load_baseline(tmp_path, "main", 180, **kw)
    assert first == {"x.py::a", "y.py::b"}
    assert second == first
    assert calls["n"] == 1  # second call hit the cache
    assert (tmp_path / ".harness" / "test-baselines" / "deadbeef.json").exists()


def test_load_baseline_dirty_cache_falls_back(monkeypatch, tmp_path: Path) -> None:
    _git_present(monkeypatch)
    cache = tmp_path / ".harness" / "test-baselines" / "beef.json"
    cache.parent.mkdir(parents=True)
    cache.write_text("{not valid json")

    def boom(root, sha, timeout):
        raise AssertionError("dirty cache must not recompute")

    out = bl.load_baseline(
        tmp_path, "main", 180,
        merge_base_fn=lambda r, b: "beef", compute_fn=boom,
        read_cache=bl.read_failing_cache, write_cache=bl.write_failing_cache,
    )
    assert out is None


def test_load_baseline_compute_failure_no_poison_cache(monkeypatch, tmp_path: Path) -> None:
    _git_present(monkeypatch)
    out = bl.load_baseline(
        tmp_path, "main", 180,
        merge_base_fn=lambda r, b: "1234", compute_fn=lambda r, s, t: None,
        read_cache=bl.read_failing_cache, write_cache=bl.write_failing_cache,
    )
    assert out is None
    assert not (tmp_path / ".harness" / "test-baselines" / "1234.json").exists()


def test_load_baseline_collection_variant(monkeypatch, tmp_path: Path) -> None:
    _git_present(monkeypatch)
    coll = bl.SuiteCollection.of({"a::bad"}, {"a::bad", "a::ok"})
    out = bl.load_baseline(
        tmp_path, "main", 180,
        merge_base_fn=lambda r, b: "cafe", compute_fn=lambda r, s, t: coll,
        read_cache=bl.read_collection_cache, write_cache=bl.write_collection_cache,
    )
    assert out == coll
    # cached copy is a faithful round trip
    again = bl.load_baseline(
        tmp_path, "main", 180,
        merge_base_fn=lambda r, b: "cafe",
        compute_fn=lambda r, s, t: (_ for _ in ()).throw(AssertionError("cached")),
        read_cache=bl.read_collection_cache, write_cache=bl.write_collection_cache,
    )
    assert again == coll


# ── build_delta_result finisher (shared by every language dir gate) ────────────

def _err(tid: str) -> GateError:
    return GateError(message=f"{tid}: boom", file=None, line=None, column=None,
                     code="TEST_FAILURE", severity="error")


def _removed_err(tid: str) -> GateError:
    return GateError(message=f"{tid}: previously-passing test removed", file=None,
                     line=None, column=None, code="TEST_REMOVED", severity="error")


def test_build_delta_result_strict_full_when_no_baseline() -> None:
    r = bl.build_delta_result(
        "test", time.monotonic(), present={"a::bad"},
        failing_errors={"a::bad": _err("a::bad")}, baseline=None,
        removed_error=_removed_err,
    )
    assert isinstance(r, GateResult)
    assert r.mode == "full"
    assert r.passed is False
    assert [e.message for e in r.errors] == ["a::bad: boom"]
    assert r.baseline_excluded == []


def test_build_delta_result_excludes_baseline_failure() -> None:
    coll = bl.SuiteCollection.of({"a::bad"}, {"a::bad", "a::ok"})
    r = bl.build_delta_result(
        "test", time.monotonic(), present={"a::bad", "a::ok"},
        failing_errors={"a::bad": _err("a::bad")}, baseline=coll,
        removed_error=_removed_err,
    )
    assert r.mode == "baseline-delta"
    assert r.passed is True
    assert r.baseline_excluded == ["a::bad"]
    assert r.errors == []


def test_build_delta_result_gates_new_failure() -> None:
    coll = bl.SuiteCollection.of(set(), {"a::ok"})
    r = bl.build_delta_result(
        "test", time.monotonic(), present={"a::ok", "a::new"},
        failing_errors={"a::new": _err("a::new")}, baseline=coll,
        removed_error=_removed_err,
    )
    assert r.passed is False
    assert any("a::new" in e.message for e in r.errors)


def test_build_delta_result_flags_removed_test() -> None:
    coll = bl.SuiteCollection.of(set(), {"a::ok", "a::gone"})
    r = bl.build_delta_result(
        "test", time.monotonic(), present={"a::ok"}, failing_errors={},
        baseline=coll, removed_error=_removed_err,
    )
    assert r.passed is False
    assert any("a::gone" in e.message and e.code == "TEST_REMOVED" for e in r.errors)


def test_strict_exit_result_pass_and_fail() -> None:
    ok = bl.strict_exit_result("test", time.monotonic(), 0, "", fallback_msg="none")
    assert ok.passed is True and ok.mode == "full"
    bad = bl.strict_exit_result("test", time.monotonic(), 1, "kaboom", fallback_msg="none")
    assert bad.passed is False and bad.errors[0].code == "TEST_FAILURE"
    assert "kaboom" in bad.errors[0].message


# ── language parsers (pure, canned output — toolchain-independent) ─────────────

def test_parse_pytest_report_ids() -> None:
    out = (
        "PASSED test_mod.py::test_ok\n"
        "FAILED test_mod.py::test_bad - assert False\n"
        "ERROR test_broken.py::test_err - ImportError\n"
        "SKIPPED test_mod.py::test_skip\n"
    )
    ok, present, failing = pymod._parse_pytest_report(out, 0)
    assert ok is True
    assert "test_mod.py::test_ok" in present
    assert "test_mod.py::test_bad" in present
    assert set(failing) == {"test_mod.py::test_bad", "test_broken.py::test_err"}
    assert "test_mod.py::test_skip" not in present


def test_parse_go_json_ids() -> None:
    out = "\n".join([
        json.dumps({"Action": "pass", "Package": "demo", "Test": "TestOK"}),
        json.dumps({"Action": "fail", "Package": "demo", "Test": "TestBad"}),
        json.dumps({"Action": "fail", "Package": "demo"}),  # package-level, ignored
        json.dumps({"Action": "output", "Package": "demo", "Test": "TestBad",
                    "Output": "boom\n"}),
    ])
    ok, present, failing = gomod._parse_go_test_json(out, 1)
    assert ok is True
    assert present == {"demo.TestOK", "demo.TestBad"}
    assert set(failing) == {"demo.TestBad"}


def test_parse_cargo_tests_ids() -> None:
    out = (
        "running 2 tests\n"
        "test tests::ok_case ... ok\n"
        "test tests::bad_case ... FAILED\n"
        "test result: FAILED. 1 passed; 1 failed\n"
    )
    ok, present, failing = rustmod._parse_cargo_test_output(out, 1)
    assert ok is True
    assert present == {"tests::ok_case", "tests::bad_case"}
    assert set(failing) == {"tests::bad_case"}


def test_parse_unparseable_nonzero_is_not_ok() -> None:
    ok, present, failing = pymod._parse_pytest_report("Traceback: boom", 2)
    assert ok is False
    assert present == set()


# ══════════════════════════════════════════════════════════════════════════════
# Integration tests — guarded on each language's toolchain
# ══════════════════════════════════════════════════════════════════════════════

_PY_TESTS = (
    "def test_ok():\n    assert True\n\n\ndef test_bad():\n    assert False\n"
)


@pytest.mark.skipif(importlib.util.find_spec("pytest") is None, reason="pytest required")
class TestPythonIntegration:
    def _write(self, proj: Path, body: str) -> None:
        (proj / "test_mod.py").write_text(body)

    def test_baseline_excludes_preexisting(self, monkeypatch, tmp_path: Path) -> None:
        self._write(tmp_path, _PY_TESTS)
        monkeypatch.setattr(pymod, "_baseline", lambda *a, **k: bl.SuiteCollection.of(
            {"test_mod.py::test_bad"},
            {"test_mod.py::test_bad", "test_mod.py::test_ok"},
        ))
        res = pymod._test_gate_dir(str(tmp_path))
        assert res.mode == "baseline-delta"
        assert res.passed is True
        assert res.baseline_excluded == ["test_mod.py::test_bad"]

    def test_new_failure_gates(self, monkeypatch, tmp_path: Path) -> None:
        self._write(tmp_path, _PY_TESTS)
        monkeypatch.setattr(pymod, "_baseline", lambda *a, **k: bl.SuiteCollection.of(
            set(), {"test_mod.py::test_bad", "test_mod.py::test_ok"},
        ))
        res = pymod._test_gate_dir(str(tmp_path))
        assert res.passed is False
        assert any("test_bad" in e.message for e in res.errors)

    def test_removed_test_detected(self, monkeypatch, tmp_path: Path) -> None:
        self._write(tmp_path, "def test_ok():\n    assert True\n")  # test_gone deleted
        monkeypatch.setattr(pymod, "_baseline", lambda *a, **k: bl.SuiteCollection.of(
            set(), {"test_mod.py::test_ok", "test_mod.py::test_gone"},
        ))
        res = pymod._test_gate_dir(str(tmp_path))
        assert res.passed is False
        assert any("test_gone" in e.message for e in res.errors)

    def test_strict_fallback_when_no_baseline(self, monkeypatch, tmp_path: Path) -> None:
        self._write(tmp_path, "def test_bad():\n    assert False\n")
        monkeypatch.setattr(pymod, "_baseline", lambda *a, **k: None)
        res = pymod._test_gate_dir(str(tmp_path))
        assert res.mode == "full"
        assert res.passed is False


def _write_go_project(proj: Path) -> None:
    (proj / "go.mod").write_text("module demo\n\ngo 1.23\n")
    (proj / "m.go").write_text("package demo\n\nfunc Add(a, b int) int { return a + b }\n")
    (proj / "m_test.go").write_text(
        "package demo\n\nimport \"testing\"\n\n"
        "func TestOK(t *testing.T) { if Add(1, 2) != 3 { t.Fatal(\"bad\") } }\n"
        "func TestBad(t *testing.T) { if Add(1, 2) != 4 { t.Fatal(\"boom\") } }\n"
    )


@pytest.mark.skipif(shutil.which("go") is None, reason="go toolchain required")
class TestGoIntegration:
    def test_baseline_excludes_preexisting(self, monkeypatch, tmp_path: Path) -> None:
        _write_go_project(tmp_path)
        monkeypatch.setattr(gomod, "_baseline", lambda *a, **k: bl.SuiteCollection.of(
            {"demo.TestBad"}, {"demo.TestBad", "demo.TestOK"},
        ))
        res = gomod._test_gate_dir(str(tmp_path))
        assert res.mode == "baseline-delta"
        assert res.passed is True
        assert res.baseline_excluded == ["demo.TestBad"]

    def test_new_failure_gates(self, monkeypatch, tmp_path: Path) -> None:
        _write_go_project(tmp_path)
        monkeypatch.setattr(gomod, "_baseline", lambda *a, **k: bl.SuiteCollection.of(
            set(), {"demo.TestBad", "demo.TestOK"},
        ))
        res = gomod._test_gate_dir(str(tmp_path))
        assert res.passed is False
        assert any("TestBad" in e.message for e in res.errors)

    def test_removed_test_detected(self, monkeypatch, tmp_path: Path) -> None:
        # Only TestOK exists now; baseline had a passing TestGone.
        (tmp_path / "go.mod").write_text("module demo\n\ngo 1.23\n")
        (tmp_path / "m.go").write_text("package demo\n\nfunc Add(a, b int) int { return a + b }\n")
        (tmp_path / "m_test.go").write_text(
            "package demo\n\nimport \"testing\"\n\n"
            "func TestOK(t *testing.T) { if Add(1, 2) != 3 { t.Fatal(\"bad\") } }\n"
        )
        monkeypatch.setattr(gomod, "_baseline", lambda *a, **k: bl.SuiteCollection.of(
            set(), {"demo.TestOK", "demo.TestGone"},
        ))
        res = gomod._test_gate_dir(str(tmp_path))
        assert res.passed is False
        assert any("TestGone" in e.message for e in res.errors)


def _write_rust_project(proj: Path) -> None:
    (proj / "Cargo.toml").write_text(
        "[package]\nname = \"demo\"\nversion = \"0.1.0\"\nedition = \"2021\"\n\n"
        "[lib]\nname = \"demo\"\npath = \"src/lib.rs\"\n"
    )
    src = proj / "src"
    src.mkdir(exist_ok=True)
    (src / "lib.rs").write_text(
        "pub fn add(a: i32, b: i32) -> i32 { a + b }\n\n"
        "#[cfg(test)]\nmod tests {\n    use super::*;\n"
        "    #[test] fn ok_case() { assert_eq!(add(1, 2), 3); }\n"
        "    #[test] fn bad_case() { assert_eq!(add(1, 2), 4); }\n}\n"
    )


@pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo toolchain required")
class TestRustIntegration:
    def test_baseline_excludes_preexisting(self, monkeypatch, tmp_path: Path) -> None:
        _write_rust_project(tmp_path)
        monkeypatch.setattr(rustmod, "_baseline", lambda *a, **k: bl.SuiteCollection.of(
            {"tests::bad_case"}, {"tests::bad_case", "tests::ok_case"},
        ))
        res = rustmod._test_gate_dir(str(tmp_path))
        assert res.mode == "baseline-delta"
        assert res.passed is True
        assert res.baseline_excluded == ["tests::bad_case"]

    def test_new_failure_gates(self, monkeypatch, tmp_path: Path) -> None:
        _write_rust_project(tmp_path)
        monkeypatch.setattr(rustmod, "_baseline", lambda *a, **k: bl.SuiteCollection.of(
            set(), {"tests::bad_case", "tests::ok_case"},
        ))
        res = rustmod._test_gate_dir(str(tmp_path))
        assert res.passed is False
        assert any("bad_case" in e.message for e in res.errors)


# ── shared detached-worktree runner (real git, fake suite) ─────────────────────

def _init_repo(root: Path) -> str:
    subprocess.run(["git", "init", "-q", str(root)], check=True,
                   capture_output=True, text=True)
    for k, v in (("user.email", "t@t.t"), ("user.name", "t"),
                 ("commit.gpgsign", "false")):
        subprocess.run(["git", "-C", str(root), "config", k, v], check=True,
                       capture_output=True, text=True)
    (root / "f.txt").write_text("hi\n")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True,
                   capture_output=True, text=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "base"], check=True,
                   capture_output=True, text=True)
    out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                         check=True, capture_output=True, text=True)
    return out.stdout.strip()


@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
def test_run_in_detached_worktree_runs_and_cleans_up(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    sha = _init_repo(repo)
    seen: dict[str, object] = {}

    def run_suite(base_root):
        seen["root"] = Path(base_root)
        seen["exists"] = Path(base_root).exists()
        return bl.SuiteCollection.of(set(), {"f::t"})

    out = bl.run_in_detached_baseline_worktree(repo, sha, run_suite)
    assert out == bl.SuiteCollection.of(set(), {"f::t"})
    assert seen["root"] != repo
    assert seen["exists"] is True
    # the throwaway worktree is gone afterwards
    listing = subprocess.run(
        ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
        capture_output=True, text=True).stdout
    assert str(seen["root"]) not in listing


@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
def test_run_in_detached_worktree_bad_sha_returns_none(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    def run_suite(base_root):  # pragma: no cover - must not be reached
        raise AssertionError("suite must not run when worktree add fails")

    assert bl.run_in_detached_baseline_worktree(
        repo, "0" * 40, run_suite) is None
