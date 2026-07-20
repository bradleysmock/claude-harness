"""Ticket 0036 — parallel gate execution (GateScheduler, gate graph, log writer).

The scheduler tests avoid wall-clock timing: concurrency is proven structurally
with a ``threading.Barrier`` (two gates that both reach a ``Barrier(2)`` provably
ran at the same time — a sequential runner would dead-lock), and interval overlap is
asserted from an injectable, deterministic counter clock (D-05).
"""
from __future__ import annotations

import contextvars
import itertools
import threading
from pathlib import Path
from typing import Callable

import pytest

from gates.config import ConfigError, load_gate_overrides, load_parallel_gate_limit
from gates.gate_graph import (
    GO_GATE_GRAPH,
    PYTHON_GATE_GRAPH,
    RUST_GATE_GRAPH,
    TYPESCRIPT_GATE_GRAPH,
    validate_dag,
)
from gates.log_writer import LogWriter
from gates.scheduler import GateScheduler
from models import GateError, GateResult

# ── Fixtures / helpers ────────────────────────────────────────────────────────

def _ok(name: str) -> GateResult:
    return GateResult(gate=name, passed=True, errors=[], duration_ms=1)


def _ok_fn(name: str) -> Callable[[str], GateResult]:
    """A `gate_fns` entry that ignores its directory arg and always passes as `name`."""
    def fn(directory: str) -> GateResult:
        return _ok(name)
    return fn


def _fail(name: str) -> GateResult:
    return GateResult(
        gate=name, passed=False,
        errors=[GateError(name, None, None, None, "X", "error")],
        duration_ms=1,
    )


def _counter_clock():
    """A deterministic monotonic clock: each call returns the next integer."""
    counter = itertools.count()
    return lambda: float(next(counter))


# ── gate_graph ────────────────────────────────────────────────────────────────

def test_all_language_graphs_are_valid_dags():
    for graph in (
        PYTHON_GATE_GRAPH, TYPESCRIPT_GATE_GRAPH, GO_GATE_GRAPH, RUST_GATE_GRAPH
    ):
        validate_dag(graph)  # must not raise


def test_test_gate_depends_on_type_or_build_gate():
    assert PYTHON_GATE_GRAPH["test"] == ["type_check"]
    assert TYPESCRIPT_GATE_GRAPH["test"] == ["type_check"]
    assert GO_GATE_GRAPH["test"] == ["build"]
    assert RUST_GATE_GRAPH["test"] == ["check"]
    # lint / security / vet / clippy are independent.
    assert PYTHON_GATE_GRAPH["lint"] == []
    assert PYTHON_GATE_GRAPH["security"] == []


def test_validate_dag_raises_on_cycle():
    # NFR-3: cycle detection at validate_dag() call time, not during execution.
    with pytest.raises(ValueError, match="cycle"):
        validate_dag({"a": ["b"], "b": ["a"]})


def test_validate_dag_raises_on_self_cycle():
    with pytest.raises(ValueError, match="cycle"):
        validate_dag({"a": ["a"]})


def test_validate_dag_raises_on_unknown_prerequisite():
    with pytest.raises(ValueError, match="unknown gate"):
        validate_dag({"test": ["type_check"]})  # type_check not a key


# ── log_writer ────────────────────────────────────────────────────────────────

def test_log_writer_creates_per_gate_file(tmp_path: Path):
    # FR-3: a log file is created per gate under log_dir and holds its content.
    writer = LogWriter(tmp_path / "logs")
    path = writer.write("lint", "ruff output here")
    assert path == (tmp_path / "logs" / "lint.log")
    assert path.read_text() == "ruff output here"


def test_log_writer_rejects_traversal_gate_name(tmp_path: Path):
    # FR-3 path safety (D-02): a traversal gate name raises ValueError.
    writer = LogWriter(tmp_path / "logs")
    with pytest.raises(ValueError):
        writer.write("../../etc/evil", "x")


@pytest.mark.parametrize("bad", ["a/b", "..", "", "a\\b", "with/slash"])
def test_log_writer_rejects_unsafe_names(tmp_path: Path, bad: str):
    writer = LogWriter(tmp_path / "logs")
    with pytest.raises(ValueError):
        writer.write(bad, "x")


def test_log_writer_preserves_large_output(tmp_path: Path):
    # D-15: a 1 MB gate output is written in full, not truncated.
    writer = LogWriter(tmp_path / "logs")
    content = "y" * (1024 * 1024)
    path = writer.write("test", content)
    assert path.stat().st_size == len(content.encode("utf-8"))
    assert path.read_text() == content


# ── scheduler: concurrency + intervals ────────────────────────────────────────

def test_independent_gates_overlap(tmp_path: Path):
    # FR-1 / FR-7: two independent gates record overlapping (start, end) intervals.
    barrier = threading.Barrier(2, timeout=5)

    def make(name):
        def fn(directory):
            barrier.wait()  # both gates must be in-flight before either returns
            return _ok(name)
        return fn

    sched = GateScheduler(
        ["lint", "security"], {}, {"lint": make("lint"), "security": make("security")},
        max_workers=None, _clock=_counter_clock(),
    )
    results = sched.run(str(tmp_path))
    assert all(r.passed for r in results)
    by_name = {i.gate: i for i in sched.intervals}
    assert by_name["lint"].overlaps(by_name["security"])


def test_contextvars_propagate_into_worker(tmp_path: Path):
    # D-10: a context var set on the calling thread must be visible inside the gate
    # running on a worker thread (the context is snapshotted at submit time).
    var: contextvars.ContextVar[str] = contextvars.ContextVar("ticket", default="none")
    var.set("0036")
    seen: dict[str, str] = {}

    def fn(directory):
        seen["ticket"] = var.get()
        return _ok("g")

    GateScheduler(["g"], {}, {"g": fn}, max_workers=None).run(str(tmp_path))
    assert seen["ticket"] == "0036"


def test_gate_crash_surfaces_tool_error_siblings_complete(tmp_path: Path):
    # NFR-1: an unhandled gate exception becomes TOOL_ERROR; siblings still run.
    def boom(directory):
        raise ValueError("kaboom")

    sched = GateScheduler(
        ["boom", "ok"], {}, {"boom": boom, "ok": lambda d: _ok("ok")},
        max_workers=None,
    )
    results = sched.run(str(tmp_path))
    by_name = {r.gate: r for r in results}
    assert by_name["boom"].passed is False
    assert by_name["boom"].errors[0].code == "TOOL_ERROR"
    assert by_name["ok"].passed is True


# ── scheduler: dependency ordering + skip propagation ─────────────────────────

def test_prerequisite_failure_skips_dependent(tmp_path: Path):
    # FR-2 / FR-6: when type_check fails, test is skipped with a skip-status result.
    sched = GateScheduler(
        ["type_check", "test"], {"test": ["type_check"]},
        {"type_check": lambda d: _fail("type_check"), "test": lambda d: _ok("test")},
        max_workers=None, fail_fast=False,
    )
    results = sched.run(str(tmp_path))
    by_name = {r.gate: r for r in results}
    assert by_name["type_check"].passed is False
    assert by_name["test"].passed is False
    assert by_name["test"].errors[0].code == "SKIPPED"


def test_serial_dispatch_respects_dependency(tmp_path: Path):
    # FR-5: max_workers=1 dispatches strictly serially in dependency order.
    order: list[str] = []
    lock = threading.Lock()

    def make(name):
        def fn(directory):
            with lock:
                order.append(name)
            return _ok(name)
        return fn

    graph = {"test": ["type_check"]}
    fns = {g: make(g) for g in ("lint", "type_check", "test", "security")}
    sched = GateScheduler(
        ["lint", "type_check", "test", "security"], graph, fns,
        max_workers=1, _clock=_counter_clock(),
    )
    results = sched.run(str(tmp_path))
    assert [r.gate for r in results] == ["lint", "type_check", "test", "security"]
    # type_check must run before test; with 1 worker no intervals overlap.
    assert order.index("type_check") < order.index("test")
    ints = sorted(sched.intervals, key=lambda i: i.start)
    for a, b in zip(ints, ints[1:]):
        assert not a.overlaps(b)


# ── scheduler: fail_fast ──────────────────────────────────────────────────────

def test_fail_fast_serial_stops_at_first_failure(tmp_path: Path):
    # FR-8: max_workers=1 + fail_fast=True returns only up to the first failure,
    # matching the old sequential early-return.
    calls: list[str] = []

    def make(name, passed):
        def fn(directory):
            calls.append(name)
            return _ok(name) if passed else _fail(name)
        return fn

    fns = {
        "a": make("a", True), "b": make("b", False),
        "c": make("c", True), "d": make("d", True),
    }
    sched = GateScheduler(
        ["a", "b", "c", "d"], {}, fns, max_workers=1, fail_fast=True,
    )
    results = sched.run(str(tmp_path))
    assert [r.gate for r in results] == ["a", "b"]
    assert "c" not in calls and "d" not in calls  # never submitted after failure


def test_fail_fast_captures_in_flight_siblings(tmp_path: Path):
    # FR-6 fail_fast (D-13): two independent gates both submitted; first fails; the
    # already-in-flight sibling still completes and both results are captured.
    barrier = threading.Barrier(2, timeout=5)

    def make(name, passed):
        def fn(directory):
            barrier.wait()  # both provably in-flight before either returns
            return _ok(name) if passed else _fail(name)
        return fn

    fns = {"a": make("a", False), "b": make("b", True)}
    sched = GateScheduler(
        ["a", "b"], {}, fns, max_workers=None, fail_fast=True,
    )
    results = sched.run(str(tmp_path))
    by_name = {r.gate: r for r in results}
    assert set(by_name) == {"a", "b"}
    assert by_name["a"].passed is False
    assert by_name["b"].passed is True


# ── scheduler: per-gate logs + declaration-order equivalence ──────────────────

def test_scheduler_writes_per_gate_logs(tmp_path: Path):
    # FR-3: with a log_dir, each dispatched gate leaves a log file.
    log_dir = tmp_path / "gate-logs"
    fns = {"lint": lambda d: _ok("lint"), "type_check": lambda d: _fail("type_check")}
    sched = GateScheduler(
        ["lint", "type_check"], {}, fns, max_workers=None, log_dir=log_dir,
    )
    sched.run(str(tmp_path))
    assert (log_dir / "lint.log").exists()
    tc_log = (log_dir / "type_check.log").read_text()
    assert "type_check" in tc_log


def test_log_write_failure_does_not_abort_run(tmp_path: Path):
    # N1: an OSError writing an advisory log must NOT abort the run or drop siblings.
    # log_dir sits under a regular file, so mkdir() raises NotADirectoryError.
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a dir")
    fns = {"a": lambda d: _ok("a"), "b": lambda d: _ok("b")}
    sched = GateScheduler(
        ["a", "b"], {}, fns, max_workers=None, log_dir=blocker / "logs",
    )
    results = sched.run(str(tmp_path))
    assert {r.gate for r in results} == {"a", "b"}
    assert all(r.passed for r in results)


def test_results_ordered_by_declaration_not_completion(tmp_path: Path):
    # Solution invariant: results follow the gates list, not completion order.
    fns = {g: _ok_fn(g) for g in ("lint", "type_check", "test", "security")}
    sched = GateScheduler(
        ["lint", "type_check", "test", "security"], {"test": ["type_check"]}, fns,
        max_workers=None,
    )
    results = sched.run(str(tmp_path))
    assert [r.gate for r in results] == ["lint", "type_check", "test", "security"]


def test_parallel_and_serial_agree_on_all_pass(tmp_path: Path):
    # FR-4 (structural equivalence): same gates, same directory, unlimited vs
    # serial produce identical result ordering and pass/fail.
    def build(max_workers):
        fns = {g: _ok_fn(g) for g in ("lint", "type_check", "test", "security")}
        return GateScheduler(
            ["lint", "type_check", "test", "security"], {"test": ["type_check"]}, fns,
            max_workers=max_workers,
        ).run(str(tmp_path))

    par = [(r.gate, r.passed) for r in build(None)]
    seq = [(r.gate, r.passed) for r in build(1)]
    assert par == seq


# ── config: parallel_gate_limit ───────────────────────────────────────────────

def _standards(tmp_path: Path, body: str) -> str:
    p = tmp_path / "_standards.md"
    p.write_text(body, encoding="utf-8")
    return str(p)


def test_parallel_limit_absent_is_none(tmp_path: Path):
    assert load_parallel_gate_limit(_standards(tmp_path, "# nothing here\n")) is None


def test_parallel_limit_missing_file_is_none(tmp_path: Path):
    assert load_parallel_gate_limit(str(tmp_path / "nope.md")) is None


def test_parallel_limit_parsed_from_gates_block(tmp_path: Path):
    body = "```gates\nparallel_gate_limit = 4\npython.lint = \"ruff check .\"\n```\n"
    path = _standards(tmp_path, body)
    assert load_parallel_gate_limit(path) == 4
    # The limit line must not be mistaken for a command override.
    assert load_gate_overrides(path) == {"python": {"lint": ["ruff", "check", "."]}}


def test_parallel_limit_accepts_quoted_value(tmp_path: Path):
    body = "```gates\nparallel_gate_limit = \"2\"\n```\n"
    assert load_parallel_gate_limit(_standards(tmp_path, body)) == 2


@pytest.mark.parametrize("bad", ["0", "-1", "abc", "1.5"])
def test_parallel_limit_rejects_invalid(tmp_path: Path, bad: str):
    body = f"```gates\nparallel_gate_limit = {bad}\n```\n"
    with pytest.raises(ConfigError):
        load_parallel_gate_limit(_standards(tmp_path, body))


# ── runner integration ────────────────────────────────────────────────────────

def test_python_runner_concurrent_by_default_when_not_fail_fast(monkeypatch, tmp_path: Path):
    # M2 / FR-5: with NO explicit parallel limit and fail_fast=False (the /gate
    # path), the three independent python gates run concurrently — proven by a
    # Barrier(3) that only releases if all three are in flight at once. A sequential
    # runner would dead-lock (BrokenBarrierError -> failure via the 5s timeout).
    from gates import python as pymod

    barrier = threading.Barrier(3, timeout=5)

    def make_indep(name):
        def fn(directory, config):
            barrier.wait()
            return _ok(name)
        return fn

    monkeypatch.setattr(pymod, "_lint_gate_dir", make_indep("lint"))
    monkeypatch.setattr(pymod, "_type_check_gate_dir", make_indep("type_check"))
    monkeypatch.setattr(pymod, "_security_gate_dir", make_indep("security"))
    monkeypatch.setattr(pymod, "_test_gate_dir", lambda d, c: _ok("test"))

    # No max_workers passed -> auto default -> concurrent because fail_fast=False.
    results = pymod.run_python_suite_on_dir(str(tmp_path), fail_fast=False)
    assert [r.gate for r in results] == ["lint", "type_check", "test", "security"]
    assert all(r.passed for r in results)


def test_python_runner_writes_per_gate_logs_by_default(monkeypatch, tmp_path: Path):
    # M1 / FR-3: a directory-mode run writes a per-gate log under
    # <dir>/.harness/gate-logs/<language>/ without the caller supplying a log_dir.
    from gates import python as pymod

    for attr, name in [
        ("_lint_gate_dir", "lint"), ("_type_check_gate_dir", "type_check"),
        ("_test_gate_dir", "test"), ("_security_gate_dir", "security"),
    ]:
        monkeypatch.setattr(pymod, attr, lambda d, c, name=name: _ok(name))

    pymod.run_python_suite_on_dir(str(tmp_path), fail_fast=False)
    log_dir = tmp_path / ".harness" / "gate-logs" / "python"
    assert (log_dir / "lint.log").exists()
    assert (log_dir / "type_check.log").exists()
    assert (log_dir / "security.log").exists()


def test_python_runner_default_is_sequential_fail_fast(monkeypatch, tmp_path: Path):
    # Back-compat: the runner default (max_workers=None -> auto -> 1 under
    # fail_fast) preserves the sequential early-return — lint fails, nothing
    # downstream runs.
    from gates import python as pymod

    calls: list[str] = []

    def make(name, passed):
        def fn(directory, config):
            calls.append(name)
            return _ok(name) if passed else _fail(name)
        return fn

    monkeypatch.setattr(pymod, "_lint_gate_dir", make("lint", False))
    monkeypatch.setattr(pymod, "_type_check_gate_dir", make("type_check", True))
    monkeypatch.setattr(pymod, "_test_gate_dir", make("test", True))
    monkeypatch.setattr(pymod, "_security_gate_dir", make("security", True))

    results = pymod.run_python_suite_on_dir(str(tmp_path), fail_fast=True)
    assert [r.gate for r in results] == ["lint"]
    assert calls == ["lint"]


# ── server wiring ─────────────────────────────────────────────────────────────

def test_server_forwards_parallel_limit_when_set(monkeypatch, tmp_path: Path):
    import server

    tickets = tmp_path / ".tickets"
    tickets.mkdir()
    (tickets / "_standards.md").write_text("```gates\nparallel_gate_limit = 3\n```\n")

    captured: dict = {}

    def fake_suite(language, directory, **kwargs):
        captured.update(kwargs)
        return [_ok("lint")]

    monkeypatch.setattr(server, "run_suite_on_dir", fake_suite)
    server.gate_run_on_dir(str(tmp_path), "python", str(tmp_path), fail_fast=False)
    assert captured.get("max_workers") == 3


def test_server_omits_parallel_limit_when_absent(monkeypatch, tmp_path: Path):
    import server

    (tmp_path / ".tickets").mkdir()
    # No _standards.md -> no parallel_gate_limit -> max_workers must NOT be passed
    # (keeps sequential default and existing fakes working).
    captured: dict = {}

    def fake_suite(language, directory, **kwargs):
        captured.update(kwargs)
        return [_ok("lint")]

    monkeypatch.setattr(server, "run_suite_on_dir", fake_suite)
    server.gate_run_on_dir(str(tmp_path), "python", str(tmp_path), fail_fast=False)
    assert "max_workers" not in captured
