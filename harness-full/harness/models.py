"""
Core data models for the LLM coding harness.
All components communicate through these types — nothing else is shared.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal
from pydantic import BaseModel, Field


# ── LLM output ────────────────────────────────────────────────────────────────

class GeneratedArtifact(BaseModel):
    """Structured output produced by the LLM. Schema doubles as prompt contract."""

    reasoning: str = Field(
        description=(
            "Step-by-step analysis before writing any code. "
            "Cover: edge cases, constraints, assumptions, chosen approach and why."
        )
    )
    assumptions: list[str] = Field(
        description="Explicit list of assumptions made due to spec ambiguity."
    )

    # ── Structured confidence (Refinement 3) ──────────────────────────────────
    # These fields must appear BEFORE implementation in the schema. The forward-
    # pass nature of generation means each field is conditioned on what came
    # before. Reasoning about confidence AFTER producing code is post-hoc
    # rationalisation. Reasoning about it BEFORE constrains what code follows.
    confident_about: list[str] = Field(
        default_factory=list,
        description=(
            "Specific aspects of the implementation drawn from canonical patterns "
            "the model has seen many times. Be specific (e.g., 'dict.get(key, default) "
            "pattern for safe key access'). Vague claims are not useful."
        ),
    )
    uncertain_about: list[str] = Field(
        default_factory=list,
        description=(
            "Specific aspects where the model is extrapolating, guessing about "
            "API behaviour, or working in a domain less represented in training. "
            "Default to listing — undeclared uncertainty is a known failure mode. "
            "Empty list only when the task is truly canonical."
        ),
    )
    falsification: str = Field(
        default="",
        description=(
            "ONE specific test scenario that, if it fails, would indicate the "
            "approach is fundamentally wrong (not merely buggy). Must be specific "
            "to this implementation, not generic. Example: 'If concurrent calls "
            "with the same key produce double-counting, my lock pattern is wrong.'"
        ),
    )
    risk_assessment: Literal["low", "medium", "high"] = Field(
        default="low",
        description=(
            "low: canonical task, all patterns recognised. "
            "medium: mostly canonical with some extrapolation. "
            "high: significant novelty, unfamiliar domain, or extensive uncertainty."
        ),
    )

    implementation: str = Field(
        description="Complete, runnable implementation. No placeholders or TODOs."
    )
    tests: str = Field(
        description=(
            "Complete test suite. Must cover: happy path, edge cases, error conditions. "
            "Include at least one test that exercises the 'falsification' scenario."
        )
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Reviewer notes: caveats, follow-ups, risks."
    )


# ── Spec ──────────────────────────────────────────────────────────────────────

@dataclass
class Spec:
    """The intent coming in. Fully describes what the LLM should produce."""
    id: str
    description: str
    constraints: list[str]
    acceptance_criteria: list[str]
    examples: list[str] = field(default_factory=list)   # filled by ContextProvider
    metadata: dict = field(default_factory=dict)


# ── Gate results ──────────────────────────────────────────────────────────────

@dataclass
class GateError:
    message: str
    file: str | None
    line: int | None
    column: int | None
    code: str | None
    severity: Literal["error", "warning"]


@dataclass
class GateResult:
    gate: str
    passed: bool
    errors: list[GateError]
    duration_ms: int


# ── Run audit trail ───────────────────────────────────────────────────────────

@dataclass
class RepairContext:
    """What gets sent back to the LLM when a gate fails or verifier rejects."""
    failed_gate: str
    errors: list[GateError]
    previous_reasoning: str
    previous_code: str
    similar_past_failures: list[str]
    instruction: str
    verifier_findings: list[str] = field(default_factory=list)  # narrative per finding
    source: Literal["gates", "verifier"] = "gates"


@dataclass
class Attempt:
    number: int
    artifact: GeneratedArtifact
    gate_results: list[GateResult]
    repair_context: RepairContext | None   # None on first attempt


@dataclass
class HarnessRun:
    id: str
    spec: Spec
    attempts: list[Attempt]
    outcome: Literal["passed", "failed", "escalated"]
    total_duration_ms: int = 0
    metadata: dict = field(default_factory=dict)


# ── Memory ────────────────────────────────────────────────────────────────────

@dataclass
class MemoryStats:
    total_runs: int
    total_failures: int
    resolution_rate: float
    failures_by_gate: dict[str, int]
    failures_by_error_code: dict[str, int]
    mean_attempts_to_resolve: float
