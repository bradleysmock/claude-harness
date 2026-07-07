"""Dependency-aware, thread-pooled gate scheduler (ticket 0036).

Directory-mode gate suites historically ran gates in a fixed sequential loop.
:class:`GateScheduler` runs them concurrently instead: independent gates overlap in
a :class:`~concurrent.futures.ThreadPoolExecutor`, while a gate with declared
prerequisites (e.g. ``test`` -> ``type_check``) does not start until every
prerequisite has completed **and passed**.

Design notes (see ``solution.md``):

* **Threads, not asyncio.** Gate functions are synchronous, subprocess-bound calls;
  a thread pool is sufficient and avoids the ``asyncio.run`` / running-loop
  ambiguity entirely.
* **Per-future exception catch.** Each gate runs under
  ``contextvars.copy_context().run(fn, directory)`` so run/ticket context vars
  propagate into the worker thread. A gate that raises is caught and converted to a
  ``TOOL_ERROR`` ``GateResult`` (NFR-1); siblings are unaffected. The catch
  enumerates the concrete failure types a gate can raise (the same tuple the
  dep-audit / SAST phases degrade on) so cancellation, ``KeyboardInterrupt`` and
  ``SystemExit`` are never swallowed.
* **Submission throttle.** At most ``max_workers`` gates are in flight at once
  (``None`` = unlimited). Throttling submission — not just execution — is what lets
  ``fail_fast`` withhold a not-yet-submitted gate after a failure, and what makes
  ``max_workers=1`` reproduce the old sequential early-return exactly (FR-8).
* **Declaration-order results.** ``run`` returns results ordered by the ``gates``
  list, not completion order, so downstream consumers (``gate-findings.md``) see a
  stable ordering regardless of scheduling races.
"""

from __future__ import annotations

import contextvars
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from models import GateError, GateResult

from gates.log_writer import LogWriter

#: A directory-mode gate function: takes the directory under test, returns a result.
GateFn = Callable[[str], GateResult]

#: Concrete exceptions a gate body can raise that the scheduler converts to a
#: ``TOOL_ERROR`` result rather than letting it kill sibling gates (NFR-1). Mirrors
#: the degradation tuple used by the dep-audit and SAST phases in ``gates/__init__``
#: — deliberately *not* bare ``Exception``, so ``KeyboardInterrupt`` / ``SystemExit``
#: / cancellation propagate untouched.
_GATE_CRASH_ERRORS = (
    ImportError, OSError, ValueError, RuntimeError, TypeError, AttributeError,
    KeyError, IndexError,
)


@dataclass(frozen=True)
class GateInterval:
    """Scheduling interval for one gate, stamped from the injectable clock.

    Distinct from ``GateResult.duration_ms`` (which each gate measures internally):
    these intervals are taken by the *scheduler* around dispatch, so two independent
    gates that ran concurrently have overlapping ``[start, end]`` ranges (FR-1/FR-7).
    """

    gate: str
    start: float
    end: float

    def overlaps(self, other: "GateInterval") -> bool:
        """True when this interval and ``other`` share any instant (ran concurrently)."""
        return self.start < other.end and other.start < self.end


class GateScheduler:
    """Run named gate functions in dependency order across a thread pool.

    Parameters
    ----------
    gates:
        Gate names in the order results should be returned (topological declaration
        order — typically the language's historical sequential order).
    gate_graph:
        Gate name -> prerequisite gate names. A gate absent from the mapping (or
        mapped to ``[]``) has no prerequisites.
    gate_fns:
        Gate name -> callable ``fn(directory) -> GateResult``. Supplies the actual
        work; ``gates`` supplies only names/order. Every name in ``gates`` must have
        an entry here.
    max_workers:
        Max gates in flight at once; ``None`` = unlimited (all independent gates run
        concurrently — the FR-5 default).
    log_dir:
        When set, a per-gate log file is written on completion via :class:`LogWriter`.
        ``None`` disables log writing.
    fail_fast:
        When True, no *new* gate is submitted once any gate has failed; already
        in-flight gates still run to completion and their results are captured.
    _clock:
        Injectable monotonic clock seam for deterministic interval tests.
    """

    def __init__(
        self,
        gates: list[str],
        gate_graph: dict[str, list[str]],
        gate_fns: dict[str, GateFn],
        max_workers: int | None = None,
        log_dir: Path | None = None,
        *,
        fail_fast: bool = False,
        _clock: Callable[[], float] = time.monotonic,
    ) -> None:
        missing = [g for g in gates if g not in gate_fns]
        if missing:
            raise ValueError(f"no gate function supplied for: {missing}")
        self.gates = list(gates)
        self.gate_graph = gate_graph
        self.gate_fns = gate_fns
        self.max_workers = max_workers
        self.log_dir = log_dir
        self.fail_fast = fail_fast
        self._clock = _clock
        self._writer = LogWriter(log_dir) if log_dir is not None else None
        self._lock = threading.Lock()
        #: Populated during :meth:`run`; one entry per gate that was dispatched.
        self.intervals: list[GateInterval] = []

    def _can_submit(self, in_flight: int) -> bool:
        return self.max_workers is None or in_flight < self.max_workers

    def _skip_result(self, gate: str, failed_prereqs: list[str]) -> GateResult:
        """A skip-status result for a gate whose prerequisite failed (FR-6)."""
        joined = ", ".join(failed_prereqs)
        return GateResult(
            gate=gate,
            passed=False,
            errors=[GateError(
                message=f"skipped: prerequisite gate(s) did not pass ({joined})",
                file=None, line=None, column=None,
                code="SKIPPED", severity="error",
            )],
            duration_ms=0,
        )

    def _log_content(self, result: GateResult) -> str:
        """Render a gate's result into log text.

        The gate functions parse their subprocess ``stdout``/``stderr`` into the
        structured ``GateResult`` before the scheduler sees them, so this renders the
        captured findings (the derived output) into a per-gate log file. Written in
        full — never truncated (D-15).
        """
        lines = [
            f"gate: {result.gate}",
            f"passed: {result.passed}",
            f"duration_ms: {result.duration_ms}",
            "",
        ]
        for err in result.errors:
            loc = f"{err.file or '?'}:{err.line if err.line is not None else '?'}"
            code = f"[{err.code}] " if err.code else ""
            lines.append(f"{err.severity} {code}{loc} {err.message}")
        return "\n".join(lines) + "\n"

    def _execute(
        self, gate: str, directory: str, ctx: contextvars.Context,
    ) -> GateResult:
        """Run one gate, stamping its interval and writing its log on completion.

        ``ctx`` is the caller's context, snapshotted in the *submitting* thread (see
        :meth:`_dispatch_ready`) and run here so run/ticket context vars propagate
        into the worker thread — ``copy_context()`` must be called on the thread
        whose context is being copied, not on the fresh worker thread (D-10).

        A gate that raises one of :data:`_GATE_CRASH_ERRORS` is converted to a
        ``TOOL_ERROR`` result (NFR-1). The interval is recorded and the log is
        written in *both* the success and the crash path, so a crashing gate still
        leaves a log behind and appears in the overlap record.
        """
        start = self._clock()
        try:
            result = ctx.run(self.gate_fns[gate], directory)
        except _GATE_CRASH_ERRORS as exc:  # surface; do not let it kill siblings
            result = GateResult(
                gate=gate,
                passed=False,
                errors=[GateError(
                    message=f"gate {gate!r} crashed: {exc}",
                    file=None, line=None, column=None,
                    code="TOOL_ERROR", severity="error",
                )],
                duration_ms=0,
            )
        end = self._clock()
        with self._lock:
            self.intervals.append(GateInterval(gate=gate, start=start, end=end))
        if self._writer is not None:
            try:
                self._writer.write(gate, self._log_content(result))
            except OSError:
                # Per-gate logs are advisory (FR-3): a filesystem fault writing one
                # (read-only worktree, full disk, a `.harness` path already a file)
                # must never abort the gate run or discard sibling results. Degrade
                # silently, mirroring the coverage / dep-audit / SAST phases.
                pass
        return result

    def run(self, directory: str) -> list[GateResult]:
        """Execute the gates against ``directory``; return results in declaration order.

        Only gates that were dispatched (submitted-and-completed, or skipped because a
        prerequisite failed) appear in the returned list. Under ``fail_fast`` a gate
        that was never submitted because an earlier failure latched the scheduler is
        simply absent — matching the sequential loop's early return.
        """
        results: dict[str, GateResult] = {}
        passed: set[str] = set()
        failed: set[str] = set()  # failed or skipped — either blocks dependents
        remaining = list(self.gates)
        in_flight: dict[Future[GateResult], str] = {}
        stopped = False  # fail_fast latch

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            while True:
                if not stopped:
                    self._dispatch_ready(
                        pool, directory, remaining, results, passed, failed, in_flight
                    )
                if not in_flight:
                    break
                done, _ = wait(set(in_flight), return_when=FIRST_COMPLETED)
                for fut in done:
                    gate = in_flight.pop(fut)
                    result = fut.result()  # _execute never raises
                    results[gate] = result
                    if result.passed:
                        passed.add(gate)
                    else:
                        failed.add(gate)
                        if self.fail_fast:
                            stopped = True

        return [results[g] for g in self.gates if g in results]

    def _dispatch_ready(
        self,
        pool: ThreadPoolExecutor,
        directory: str,
        remaining: list[str],
        results: dict[str, GateResult],
        passed: set[str],
        failed: set[str],
        in_flight: dict[Future[GateResult], str],
    ) -> None:
        """Skip dependents of failed prereqs and submit every ready gate, up to cap.

        Loops until a full pass makes no further progress: resolving one skip can
        unblock the next (a chain of dependents collapses in one call), and freeing a
        worker slot is handled by the caller re-invoking after each completion.
        """
        progressed = True
        while progressed:
            progressed = False
            for gate in list(remaining):
                prereqs = self.gate_graph.get(gate, [])
                blocked = [p for p in prereqs if p in failed]
                if blocked:
                    results[gate] = self._skip_result(gate, blocked)
                    failed.add(gate)
                    remaining.remove(gate)
                    progressed = True
                    continue
                if all(p in passed for p in prereqs):
                    if not self._can_submit(len(in_flight)):
                        continue
                    # Snapshot the context HERE, on the submitting thread, so the
                    # worker runs the gate under the caller's context vars (D-10).
                    ctx = contextvars.copy_context()
                    future = pool.submit(self._execute, gate, directory, ctx)
                    in_flight[future] = gate
                    remaining.remove(gate)
                    progressed = True
