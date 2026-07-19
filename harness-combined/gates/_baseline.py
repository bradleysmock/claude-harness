"""Language-neutral baseline-delta machinery for the directory-mode test gate.

Ticket 0041 built full-suite + merge-base baseline-delta for the TypeScript test
gate: run the whole suite, subtract the set of tests already failing at the merge
base (cached per merge-base SHA under ``.harness/test-baselines/``, computed once in a
throwaway detached worktree), and fail only on the remainder. This module extracts
that mechanism so Python, Go, Rust, and TypeScript all share one implementation; the
*only* language-specific input is a callback that runs a suite and reports its test
IDs (``failing_test_ids`` in the design — generalized here to a :class:`SuiteCollection`
so removed-test detection can also see the passing set).

Nothing here launches a language toolchain directly: callers inject the run/parse
step, which keeps the delta math, the SHA cache, and the worktree lifecycle unit
testable without any compiler installed.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar

from models import GateError, GateResult

#: Where per-SHA baseline caches live, relative to the gate's config root.
BASELINE_SUBDIR = Path(".harness") / "test-baselines"

T = TypeVar("T")


@dataclass(frozen=True)
class SuiteCollection:
    """The outcome of one suite run as two stable test-ID sets.

    ``failing`` is the set of test IDs that failed; ``present`` is every test ID that
    ran to a pass/fail conclusion (so ``present - failing`` is the passing set). Both
    are frozen so a collection can be a dict value / cached safely. IDs must be
    run-independent (path/pkg/crate-relative) so they match between the HEAD run and
    the merge-base baseline run, which happen in different directories.
    """

    failing: frozenset[str]
    present: frozenset[str]

    @classmethod
    def of(cls, failing: Iterable[str], present: Iterable[str]) -> "SuiteCollection":
        return cls(frozenset(failing), frozenset(present))


@dataclass(frozen=True)
class Delta:
    """The baseline-delta decision for one test run.

    ``new_failures`` and ``removed`` gate the ticket; ``baseline_excluded`` is
    report-only (pre-existing merge-base failures that this ticket did not cause).
    """

    new_failures: list[str]      # failing now, not at baseline → gate
    baseline_excluded: list[str]  # failing now AND at baseline → report only
    removed: list[str]           # passing at baseline, absent now → gate

    @property
    def gating(self) -> list[str]:
        """All IDs that fail the gate (new failures plus removed passing tests)."""
        return sorted(set(self.new_failures) | set(self.removed))

    @property
    def ok(self) -> bool:
        return not self.new_failures and not self.removed


def compute_delta(
    current_failing: Iterable[str],
    baseline_failing: Iterable[str],
    *,
    current_present: Iterable[str] | None = None,
    baseline_present: Iterable[str] | None = None,
) -> Delta:
    """Diff a run's failures against the merge-base baseline.

    ``new_failures`` are failures absent at the baseline (regressions to gate).
    ``baseline_excluded`` are failures already present at the baseline (report only —
    an unrelated already-red test must not block this ticket). A failure that existed
    at the baseline but is *not* failing now is neither — it is silently ignored.

    When both present sets are supplied, ``removed`` also flags pass→removed
    regressions: a test that was present-and-passing at the baseline but is absent
    from the current run (a deleted previously-green test the failure-set diff alone
    would miss). Without present sets, removed-detection is disabled (the TS path).
    """
    cf = set(current_failing)
    bf = set(baseline_failing)
    new_failures = sorted(cf - bf)
    baseline_excluded = sorted(cf & bf)
    removed: list[str] = []
    if current_present is not None and baseline_present is not None:
        baseline_passing = set(baseline_present) - bf
        removed = sorted(baseline_passing - set(current_present))
    return Delta(new_failures, baseline_excluded, removed)


# ── Merge base + SHA-keyed cache ───────────────────────────────────────────────

def merge_base_sha(root: Path, base: str) -> str | None:
    """Merge-base SHA between HEAD and ``base``, or None when it cannot be resolved."""
    try:
        mb = subprocess.run(
            ["git", "-C", str(root), "merge-base", "HEAD", base],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    sha = mb.stdout.strip()
    return sha if mb.returncode == 0 and sha else None


def baseline_cache_path(root: Path, sha: str) -> Path:
    return Path(root) / BASELINE_SUBDIR / f"{sha}.json"


def _write_cache(path: Path, payload: dict[str, object]) -> None:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass  # a cache we cannot persist just recomputes next run — never fatal


def read_failing_cache(path: Path) -> set[str] | None:
    """Load a failing-only baseline cache. None on any unreadable/corrupt file."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return set(data["failing"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None


def write_failing_cache(path: Path, sha: str, failing: Iterable[str]) -> None:
    _write_cache(path, {"sha": sha, "failing": sorted(failing)})


def read_collection_cache(path: Path) -> SuiteCollection | None:
    """Load a present+failing baseline cache. None on any unreadable/corrupt file.

    A failing-only payload (no ``present`` key) reads as None so a stale TS-shaped
    cache never silently disables removed-detection for a language that expects it.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return SuiteCollection.of(set(data["failing"]), set(data["present"]))
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None


def write_collection_cache(path: Path, sha: str, collection: SuiteCollection) -> None:
    _write_cache(path, {
        "sha": sha,
        "failing": sorted(collection.failing),
        "present": sorted(collection.present),
    })


def load_baseline(
    root: Path,
    base: str,
    timeout: int,
    *,
    merge_base_fn: Callable[[Path, str], str | None],
    compute_fn: Callable[[Path, str, int], T | None],
    read_cache: Callable[[Path], T | None],
    write_cache: Callable[[Path, str, T], None],
) -> T | None:
    """Resolve the merge-base baseline, computing on cache miss.

    Returns None — the "fall back to full-suite strictness" signal — when git is
    absent, the merge base is unknown, the SHA's cache is dirty (present but corrupt),
    or the baseline computation itself fails. Otherwise returns the cached-or-computed
    baseline (a ``set[str]`` for the failing-only variant, a :class:`SuiteCollection`
    for the collection variant), computing at most once per SHA across a repair loop.

    ``merge_base_fn`` and ``compute_fn`` are injected (not module globals) so a caller
    can route them through its own monkeypatchable seams.
    """
    if shutil.which("git") is None:
        return None
    sha = merge_base_fn(root, base)
    if not sha:
        return None
    cache = baseline_cache_path(root, sha)
    if cache.exists():
        # A present-but-corrupt cache is a dirty cache → strict fallback (None).
        return read_cache(cache)
    computed = compute_fn(root, sha, timeout)
    if computed is None:
        return None
    write_cache(cache, sha, computed)
    return computed


# ── Detached baseline worktree ─────────────────────────────────────────────────

def repo_prefix(root: Path) -> str:
    """Path of ``root`` relative to its git top-level ('' when at the root)."""
    try:
        p = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-prefix"],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return p.stdout.strip() if p.returncode == 0 else ""


def run_in_detached_baseline_worktree(
    root: Path,
    sha: str,
    run_suite: Callable[[Path], T | None],
    *,
    prepare: Callable[[Path, Path], None] | None = None,
    tmp_prefix: str = "harness_baseline_",
) -> T | None:
    """Run ``run_suite`` against ``sha`` in a throwaway detached worktree.

    Never touches the ticket worktree: a temporary ``git worktree`` is added at the
    baseline commit, ``run_suite`` runs there (with the sub-package prefix applied so
    a monorepo gate lands in the right directory), and the worktree is always removed.
    ``prepare(src_root, base_root)`` runs before the suite for any per-language
    provisioning (e.g. symlinking installed dependencies). Returns whatever
    ``run_suite`` returns, or None when the worktree cannot be established or the suite
    times out — the caller then falls back to full-suite strictness.
    """
    prefix = repo_prefix(root)
    tmp = Path(tempfile.mkdtemp(prefix=tmp_prefix))
    wt = tmp / "wt"
    try:
        add = subprocess.run(
            ["git", "-C", str(root), "worktree", "add", "--detach", str(wt), sha],
            capture_output=True, text=True, timeout=60,
        )
        if add.returncode != 0:
            return None
        base_root = (wt / prefix) if prefix else wt
        if prepare is not None:
            prepare(Path(root), base_root)
        try:
            return run_suite(base_root)
        except subprocess.TimeoutExpired:
            return None
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        subprocess.run(
            ["git", "-C", str(root), "worktree", "remove", "--force", str(wt)],
            capture_output=True, text=True, timeout=60,
        )
        shutil.rmtree(tmp, ignore_errors=True)


# ── Result finishers shared by every language dir gate ─────────────────────────

def build_delta_result(
    gate: str,
    start: float,
    present: Iterable[str],
    failing_errors: dict[str, GateError],
    baseline: SuiteCollection | None,
    *,
    removed_error: Callable[[str], GateError],
) -> GateResult:
    """Turn a parsed run + resolved baseline into the gate's ``GateResult``.

    ``failing_errors`` maps each currently-failing test ID to its rendered
    ``GateError``. When ``baseline`` is None the gate runs strict full-suite (every
    failure gates, no removed-detection, ``mode="full"``). Otherwise it subtracts the
    baseline: new failures and pass→removed regressions gate; pre-existing baseline
    failures are reported as ``baseline_excluded`` (``mode="baseline-delta"``).
    """
    failing = set(failing_errors)
    if baseline is None:
        errors = [failing_errors[t] for t in sorted(failing)]
        return _finish(gate, start, not errors, errors, "full", [])
    delta = compute_delta(
        failing, baseline.failing,
        current_present=present, baseline_present=baseline.present,
    )
    errors = [failing_errors[t] for t in delta.new_failures]
    errors += [removed_error(rid) for rid in delta.removed]
    return _finish(gate, start, not errors, errors, "baseline-delta", delta.baseline_excluded)


def strict_exit_result(
    gate: str, start: float, returncode: int, output: str, *, fallback_msg: str,
) -> GateResult:
    """Strict exit-code fallback when the suite produced no parseable test report.

    A crash / build failure / config error with no machine-readable output: exit 0 is
    a pass, non-zero fails with the raw output (or ``fallback_msg`` when it is empty).
    Always ``mode="full"`` — no baseline was consulted.
    """
    dur = int((time.monotonic() - start) * 1000)
    if returncode == 0:
        return GateResult(gate=gate, passed=True, errors=[], duration_ms=dur, mode="full")
    err = GateError(
        message=(output[:600] or fallback_msg),
        file=None, line=None, column=None, code="TEST_FAILURE", severity="error",
    )
    return GateResult(gate=gate, passed=False, errors=[err], duration_ms=dur, mode="full")


def _finish(
    gate: str, start: float, passed: bool, errors: list[GateError],
    mode: str, excluded: list[str],
) -> GateResult:
    return GateResult(
        gate=gate, passed=passed, errors=errors,
        duration_ms=int((time.monotonic() - start) * 1000),
        mode=mode, baseline_excluded=excluded,
    )
