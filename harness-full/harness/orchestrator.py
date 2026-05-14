"""
Event bus + instrumented orchestrator.
The orchestrator is the main loop — it depends on all other components via protocols.
"""

from __future__ import annotations
import logging
import uuid
import time
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Callable, Any

from .models import (
    Spec, GeneratedArtifact, HarnessRun, Attempt, RepairContext, GateResult,
)
from .gates import gate_suite_for
from .escalator import RepairInstructionEscalator


# ── Event bus ─────────────────────────────────────────────────────────────────

@dataclass
class HarnessEvent:
    kind: str
    timestamp: datetime
    payload: dict[str, Any]

EventListener = Callable[[HarnessEvent], None]


class EventBus:
    def __init__(self):
        self._listeners: list[EventListener] = []

    def subscribe(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    def emit(self, kind: str, **payload) -> None:
        event = HarnessEvent(kind=kind, timestamp=datetime.now(UTC), payload=payload)
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                pass


class LoggingListener:
    def __init__(self, level: str = "INFO"):
        self._log = logging.getLogger("harness")
        self._log.setLevel(level)
        if not self._log.handlers:
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] harness — %(message)s"
            ))
            self._log.addHandler(h)

    def __call__(self, event: HarnessEvent) -> None:
        p = event.payload
        _LEVEL_LABELS = {1: "targeted", 2: "diagnostic", 3: "reset"}
        messages = {
            "run.started":      lambda: f"Run {p['run_id']} started — {p['spec_id']}",
            "context.fetched":  lambda: f"  Context: {p['chunk_count']} chunk(s) retrieved",
            "attempt.started":  lambda: f"  Attempt {p['attempt']} of {p['max']}",
            "gate.passed":      lambda: f"    ✓ {p['gate']} ({p['duration_ms']}ms)",
            "gate.failed":      lambda: (
                f"    ✗ {p['gate']} ({p['duration_ms']}ms) — "
                + "; ".join(e["message"][:60] for e in p["errors"][:2])
            ),
            "memory.retrieved": lambda: f"  Memory: {p['record_count']} similar failure(s)",
            "repair.escalated": lambda: (
                f"  Repair level {p['level']} "
                f"({_LEVEL_LABELS.get(p['level'], 'unknown')}) — "
                f"gate: {p['gate']}"
            ),
            "run.passed":       lambda: f"Run {p['run_id']} ✓ passed in {p['attempts']} attempt(s)",
            "run.escalated":    lambda: f"Run {p['run_id']} ⚠ ESCALATED after {p['attempts']} attempt(s)",
        }
        if event.kind in messages:
            lvl = logging.WARNING if "escalated" in event.kind or "failed" in event.kind \
                  else logging.INFO
            self._log.log(lvl, messages[event.kind]())


# ── Escalation ────────────────────────────────────────────────────────────────

class LoggingEscalationHandler:
    def escalate(self, run: HarnessRun) -> None:
        log = logging.getLogger("harness.escalation")
        log.warning(
            "ESCALATED run=%s spec=%s attempts=%d",
            run.id, run.spec.id, len(run.attempts),
        )
        # Extend: open GitHub issue, post Slack message, page on-call, etc.


# ── Orchestrator ──────────────────────────────────────────────────────────────

class InstrumentedOrchestrator:
    """
    The main loop. Depends on all other components via protocols.
    No stack-specific knowledge here.
    """

    def __init__(
        self,
        context_provider,
        llm,
        memory,
        escalation,
        project_root: str,
        language: str = "python",
        sandbox=None,
        max_retries: int = 3,
        bus: EventBus | None = None,
    ):
        self._ctx = context_provider
        self._llm = llm
        self._memory = memory
        self._escalation = escalation
        self._project_root = project_root
        self._language = language
        self._sandbox = sandbox
        self._max_retries = max_retries
        self._bus = bus or EventBus()
        self._escalator = RepairInstructionEscalator()

    def run(self, spec: Spec) -> HarnessRun:
        run_id = str(uuid.uuid4())[:8]
        self._emit("run.started", run_id=run_id, spec_id=spec.id)

        examples = self._ctx.fetch(spec)
        spec.examples = examples
        self._emit("context.fetched", chunk_count=len(examples))

        artifact = self._llm.generate(spec)
        repair_context = None
        run = HarnessRun(id=run_id, spec=spec, attempts=[], outcome="failed")
        t0 = time.monotonic()

        for n in range(1, self._max_retries + 1):
            self._emit("attempt.started", attempt=n, max=self._max_retries)

            if self._sandbox and self._sandbox.enabled:
                from .sandbox import sandboxed_gate_suite_for
                suite_ctx = sandboxed_gate_suite_for(
                    self._language, artifact, self._project_root, self._sandbox
                )
            else:
                suite_ctx = gate_suite_for(self._language, artifact, self._project_root)
            with suite_ctx as gates:
                gate_results = self._run_gates(artifact, gates)

            attempt = Attempt(n, artifact, gate_results, repair_context)
            run.attempts.append(attempt)
            first_fail = next((g for g in gate_results if not g.passed), None)

            if not first_fail:
                run.outcome = "passed"
                self._emit("run.passed", run_id=run_id, attempts=n)
                break

            if n == self._max_retries:
                run.outcome = "escalated"
                self._emit("run.escalated", run_id=run_id, attempts=n)
                self._escalation.escalate(run)
                break

            similar = self._memory.retrieve_similar(first_fail.errors, first_fail.gate)
            self._emit("memory.retrieved", record_count=len(similar))

            # Build escalating repair instruction based on attempt history
            prev_errors = (
                next(
                    (g.errors for g in run.attempts[-2].gate_results if not g.passed),
                    None,
                )
                if len(run.attempts) >= 2 else None
            )
            instruction = self._escalator.build(
                attempt_number=n,
                gate=first_fail.gate,
                current_errors=first_fail.errors,
                prev_errors=prev_errors,
                prev_reasoning=artifact.reasoning,
            )
            self._emit(
                "repair.escalated",
                attempt=n, gate=first_fail.gate,
                level=min(n, 3),
            )

            repair_context = RepairContext(
                failed_gate=first_fail.gate,
                errors=first_fail.errors,
                previous_reasoning=artifact.reasoning,
                previous_code=artifact.implementation,
                similar_past_failures=similar,
                instruction=instruction,
            )
            artifact = self._llm.repair(artifact, repair_context)

        run.total_duration_ms = int((time.monotonic() - t0) * 1000)
        self._memory.record(run)
        return run

    def _run_gates(self, artifact, gates) -> list[GateResult]:
        results = []
        for gate in gates:
            result = gate.run(artifact)
            results.append(result)
            key = "gate.passed" if result.passed else "gate.failed"
            self._emit(key, gate=result.gate, duration_ms=result.duration_ms,
                       errors=[{"message": e.message, "code": e.code}
                               for e in result.errors])
            if not result.passed:
                break
        return results

    def _emit(self, kind: str, **payload) -> None:
        self._bus.emit(kind, **payload)
