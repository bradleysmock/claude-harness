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
            "confidence.declared": lambda: (
                f"  Confidence: risk={p['risk_assessment']}, "
                f"{p['confident_count']} confident, {p['uncertain_count']} uncertain"
                + ("" if p['has_falsification'] else "  ⚠ no falsification provided")
            ),
            "attempt.started":  lambda: f"  Attempt {p['attempt']} of {p['max']}",
            "gate.passed":      lambda: f"    ✓ {p['gate']} ({p['duration_ms']}ms)",
            "gate.failed":      lambda: (
                f"    ✗ {p['gate']} ({p['duration_ms']}ms) — "
                + "; ".join(e["message"][:60] for e in p["errors"][:2])
            ),
            "memory.retrieved": lambda: f"  Memory: {p['record_count']} similar failure(s)",
            "hardener.started": lambda: f"  Hardener: analysing spec for ambiguities…",
            "hardener.completed": lambda: (
                f"  Hardener: {p['pinned']} pinned, {p['signatures']} sig(s), "
                f"{p['edge_cases']} edge case(s), {p['anti_requirements']} anti-req(s)"
                + (f", ⚠ {p['open_ambiguities']} open" if p['open_ambiguities'] else "")
            ),
            "hardener.blocked": lambda: f"  ✗ Hardener BLOCKED — {p['count']} open ambiguity/ies",
            "novelty.classified": lambda: (
                f"  Novelty: {p['level']} (score={p['score']:.2f}) — "
                f"retries={p['max_retries']}"
                + (", ⚑ human review flagged" if p['human_flag'] else "")
            ),
            "novelty.upgraded": lambda: (
                f"  Novelty: upgraded {p['from_level']} → {p['to_level']} "
                f"(retries={p['new_max_retries']})"
            ),
            "run.flagged_for_review": lambda: (
                f"  ⚑ Run {p['run_id']} flagged for human review (novelty: {p['level']})"
            ),
            "verifier.started": lambda: f"  Verifier: reviewing artifact against spec…",
            "verifier.completed": lambda: (
                f"  Verifier: {p['verdict'].upper()}  "
                f"({p['finding_count']} finding(s) — "
                f"{p['critical_count']} critical, {p['major_count']} major)"
            ),
            "repair.from_verifier": lambda: (
                f"  Repair from verifier — {p['blocking_findings']} blocking finding(s)"
            ),
            "consistency.started": lambda: f"  Consistency: checking pinned identifiers…",
            "consistency.completed": lambda: (
                f"  Consistency: {'PASSED' if p['passed'] else 'FAILED'} "
                f"({p['checked']} checked, {p['violations']} violation(s))"
            ),
            "repair.from_consistency": lambda: (
                f"  Repair from consistency — {p['violations']} naming violation(s)"
            ),
            "alignment.started": lambda: f"  Alignment: checking spec vs implementation intent…",
            "alignment.completed": lambda: (
                f"  Alignment: {p['verdict'].upper()} (score: {p['score']:.2f})"
                + (f" — drift: {', '.join(p['drift_categories'][:2])}" if p['drift_categories'] else "")
            ),
            "repair.from_alignment": lambda: (
                f"  Repair from alignment — verdict: {p['verdict']}, score: {p['score']:.2f}"
            ),
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
        verifier=None,
        hardener=None,
        novelty_classifier=None,
        alignment_gate=None,
        consistency_check=None,
        block_on_open_ambiguities: bool = False,
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
        self._verifier = verifier
        self._hardener = hardener
        self._classifier = novelty_classifier
        self._alignment_gate = alignment_gate
        self._consistency_check = consistency_check
        self._block_on_open_ambiguities = block_on_open_ambiguities
        self._base_max_retries = max_retries
        self._max_retries = max_retries
        self._bus = bus or EventBus()
        self._escalator = RepairInstructionEscalator()

    def run(self, spec: Spec) -> HarnessRun:
        run_id = str(uuid.uuid4())[:8]
        self._emit("run.started", run_id=run_id, spec_id=spec.id)

        # ── Spec hardening pre-pass (Refinement 2) ────────────────────────────
        # Runs BEFORE context fetch so that retrieval queries are made against
        # the hardened spec, which has more concrete identifiers and types.
        hardening_report = None
        if self._hardener is not None:
            self._emit("hardener.started", spec_id=spec.id)
            spec, hardening_report = self._hardener.harden(spec)
            self._emit(
                "hardener.completed",
                pinned=len(hardening_report.pinned_identifiers),
                signatures=len(hardening_report.type_signatures),
                edge_cases=len(hardening_report.edge_cases),
                anti_requirements=len(hardening_report.anti_requirements),
                open_ambiguities=len(hardening_report.open_ambiguities),
            )

            if hardening_report.open_ambiguities and self._block_on_open_ambiguities:
                self._emit("hardener.blocked", count=len(hardening_report.open_ambiguities))
                run = HarnessRun(id=run_id, spec=spec, attempts=[], outcome="failed")
                run.metadata = {"blocked_by": "open_ambiguities", "report": hardening_report.formatted()}
                self._memory.record(run)
                return run

        # ── Pre-generation novelty classification (Refinement 4) ──────────────
        # Reset retry budget to base (will be adjusted by classifier if novel).
        self._max_retries = self._base_max_retries
        novelty_assessment = None
        if self._classifier is not None:
            novelty_assessment = self._classifier.classify_pre_generation(
                spec, hardening_report
            )
            self._max_retries = novelty_assessment.profile.max_retries
            self._emit(
                "novelty.classified",
                stage="pre_generation",
                level=novelty_assessment.level,
                score=novelty_assessment.score,
                max_retries=novelty_assessment.profile.max_retries,
                human_flag=novelty_assessment.profile.requires_human_flag,
            )

        examples = self._ctx.fetch(spec)
        spec.examples = examples
        self._emit("context.fetched", chunk_count=len(examples))

        artifact = self._llm.generate(spec)
        self._emit(
            "confidence.declared",
            risk_assessment=getattr(artifact, "risk_assessment", "unknown"),
            confident_count=len(getattr(artifact, "confident_about", []) or []),
            uncertain_count=len(getattr(artifact, "uncertain_about", []) or []),
            has_falsification=bool(getattr(artifact, "falsification", "")),
        )

        # ── Post-generation novelty update (Refinement 4) ─────────────────────
        # May upgrade the level if the model self-reports high risk or
        # multiple uncertainties.
        if self._classifier is not None and novelty_assessment is not None:
            novelty_assessment = self._classifier.update_with_artifact(
                novelty_assessment, artifact
            )
            if novelty_assessment.upgraded_from:
                self._max_retries = novelty_assessment.profile.max_retries
                self._emit(
                    "novelty.upgraded",
                    from_level=novelty_assessment.upgraded_from,
                    to_level=novelty_assessment.level,
                    new_max_retries=novelty_assessment.profile.max_retries,
                )

        repair_context = None
        run = HarnessRun(id=run_id, spec=spec, attempts=[], outcome="failed")
        t0 = time.monotonic()

        for n in range(1, self._max_retries + 1):
            self._emit("attempt.started", attempt=n, max=self._max_retries)

            # ── Identifier consistency (Refinement 6) ─────────────────────────
            # Runs FIRST because it is the cheapest check (no LLM, no temp env).
            # A naming violation typically means tests are wrong too, so it is
            # pointless to run the gate suite when consistency fails.
            consistency_report = None
            if (self._consistency_check is not None
                    and hardening_report is not None
                    and hardening_report.pinned_identifiers):
                self._emit("consistency.started", attempt=n)
                consistency_report = self._consistency_check.check(
                    artifact, hardening_report.pinned_identifiers,
                )
                self._emit(
                    "consistency.completed",
                    attempt=n,
                    passed=consistency_report.passed(),
                    checked=consistency_report.checked_count,
                    violations=len(consistency_report.violations),
                )

            consistency_passed = (
                consistency_report is None or consistency_report.passed()
            )

            # ── Gates (only if consistency passed) ────────────────────────────
            if consistency_passed:
                if self._sandbox and self._sandbox.enabled:
                    from .sandbox import sandboxed_gate_suite_for
                    suite_ctx = sandboxed_gate_suite_for(
                        self._language, artifact, self._project_root, self._sandbox
                    )
                else:
                    suite_ctx = gate_suite_for(self._language, artifact, self._project_root)
                with suite_ctx as gates:
                    gate_results = self._run_gates(artifact, gates)
            else:
                gate_results = []  # skipped this attempt

            attempt = Attempt(n, artifact, gate_results, repair_context)
            run.attempts.append(attempt)
            first_fail = next((g for g in gate_results if not g.passed), None)

            # ── Verifier check (gates passed + consistency passed) ────────────
            verifier_report = None
            if consistency_passed and not first_fail and self._verifier is not None:
                self._emit("verifier.started", attempt=n)
                verifier_report = self._verifier.verify(spec, artifact)
                self._emit(
                    "verifier.completed",
                    attempt=n,
                    verdict=verifier_report.verdict,
                    finding_count=len(verifier_report.findings),
                    critical_count=len(verifier_report.critical_findings),
                    major_count=len(verifier_report.major_findings),
                )

            # ── Alignment gate (Refinement 5) ─────────────────────────────────
            alignment_report = None
            verifier_passed = (verifier_report is None or verifier_report.passed())
            if (consistency_passed and not first_fail and verifier_passed
                    and self._alignment_gate is not None):
                self._emit("alignment.started", attempt=n)
                alignment_report = self._alignment_gate.check(spec, artifact)
                self._emit(
                    "alignment.completed",
                    attempt=n,
                    verdict=alignment_report.verdict,
                    score=alignment_report.alignment_score,
                    drift_categories=alignment_report.drift_categories,
                )

            alignment_passed = (
                alignment_report is None
                or alignment_report.passed(threshold=0.75)
            )

            # ── Success: consistency + gates + verifier + alignment all pass ──
            if (consistency_passed and not first_fail
                    and verifier_passed and alignment_passed):
                run.outcome = "passed"
                self._emit("run.passed", run_id=run_id, attempts=n)
                break

            if n == self._max_retries:
                run.outcome = "escalated"
                self._emit("run.escalated", run_id=run_id, attempts=n)
                self._escalation.escalate(run)
                break

            # ── Repair context selection (consistency takes precedence) ───────
            if not consistency_passed:
                repair_context = self._build_consistency_repair_context(
                    n, run, artifact, consistency_report
                )
            elif first_fail:
                repair_context = self._build_gate_repair_context(
                    n, run, artifact, first_fail
                )
            elif not verifier_passed:
                repair_context = self._build_verifier_repair_context(
                    n, run, artifact, spec, verifier_report
                )
            else:
                # gates passed and verifier approved, but alignment drifted
                repair_context = self._build_alignment_repair_context(
                    n, run, artifact, alignment_report
                )

            artifact = self._llm.repair(artifact, repair_context)

        run.total_duration_ms = int((time.monotonic() - t0) * 1000)

        # ── Record novelty in run metadata (Refinement 4) ─────────────────────
        if novelty_assessment is not None:
            run.metadata["novelty_level"] = novelty_assessment.level
            run.metadata["novelty_score"] = novelty_assessment.score
            if novelty_assessment.profile.requires_human_flag:
                run.metadata["needs_human_review"] = True
                self._emit(
                    "run.flagged_for_review",
                    run_id=run_id, level=novelty_assessment.level,
                )

        self._memory.record(run)
        return run

    # ── Repair-context builders ───────────────────────────────────────────────

    def _build_gate_repair_context(
        self, n: int, run: HarnessRun, artifact, first_fail
    ) -> RepairContext:
        similar = self._memory.retrieve_similar(first_fail.errors, first_fail.gate)
        self._emit("memory.retrieved", record_count=len(similar))

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
        self._emit("repair.escalated", attempt=n, gate=first_fail.gate, level=min(n, 3))

        return RepairContext(
            failed_gate=first_fail.gate,
            errors=first_fail.errors,
            previous_reasoning=artifact.reasoning,
            previous_code=artifact.implementation,
            similar_past_failures=similar,
            instruction=instruction,
            source="gates",
        )

    def _build_verifier_repair_context(
        self, n: int, run: HarnessRun, artifact, spec: Spec, report
    ) -> RepairContext:
        findings_text = [f.as_repair_line() for f in report.blocking_findings]

        unaddressed_constraints = [
            f"Unaddressed constraint: {c.text} — {c.evidence}"
            for c in report.constraint_coverage if not c.addressed
        ]
        unverifiable_criteria = [
            f"Unverifiable criterion: {c.text} — {c.evidence}"
            for c in report.criteria_coverage if not c.addressed
        ]
        all_findings = findings_text + unaddressed_constraints + unverifiable_criteria

        instruction = (
            f"The verifier identified {len(report.blocking_findings)} "
            f"blocking finding(s) and {len(unaddressed_constraints) + len(unverifiable_criteria)} "
            f"unaddressed requirement(s). Address each one specifically.\n\n"
            f"Verifier summary: {report.summary}"
        )

        self._emit(
            "repair.from_verifier",
            attempt=n,
            blocking_findings=len(report.blocking_findings),
        )

        return RepairContext(
            failed_gate="verifier",
            errors=[],
            previous_reasoning=artifact.reasoning,
            previous_code=artifact.implementation,
            similar_past_failures=[],
            instruction=instruction,
            verifier_findings=all_findings,
            source="verifier",
        )

    def _build_alignment_repair_context(
        self, n: int, run: HarnessRun, artifact, report
    ) -> RepairContext:
        """
        Alignment-driven repair. The implementer's code is internally
        defensible but does not match the spec's actual intent. Repair
        instruction reflects this — not "fix these bugs" but "rebuild
        around the correct interpretation."
        """
        self._emit(
            "repair.from_alignment",
            attempt=n,
            verdict=report.verdict,
            score=report.alignment_score,
            drift_categories=report.drift_categories,
        )

        return RepairContext(
            failed_gate="alignment",
            errors=[],
            previous_reasoning=artifact.reasoning,
            previous_code=artifact.implementation,
            similar_past_failures=[],
            instruction=report.repair_instruction(),
            verifier_findings=[report.drift_analysis],
            source="verifier",  # use verifier repair prompt template
        )

    def _build_consistency_repair_context(
        self, n: int, run: HarnessRun, artifact, report
    ) -> RepairContext:
        """
        Consistency-driven repair. The implementation passes everything else
        but the pinned identifiers from hardening do not appear. This is
        purely a renaming task — the repair instruction reflects that.
        """
        self._emit(
            "repair.from_consistency",
            attempt=n,
            violations=len(report.violations),
        )

        finding_lines = [v.as_repair_line() for v in report.violations]
        instruction = (
            f"The identifier consistency check found {len(report.violations)} "
            f"pinned identifier(s) missing from your implementation. "
            f"These identifiers were pinned by the spec hardening pass and "
            f"are explicit naming requirements.\n\n"
            f"This is a renaming task. The structure of your implementation may "
            f"be correct; the identifiers must match the pinned names exactly. "
            f"Update both implementation and tests to use the pinned names."
        )

        return RepairContext(
            failed_gate="consistency",
            errors=[],
            previous_reasoning=artifact.reasoning,
            previous_code=artifact.implementation,
            similar_past_failures=[],
            instruction=instruction,
            verifier_findings=finding_lines,
            source="verifier",  # reuse verifier repair template
        )

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
