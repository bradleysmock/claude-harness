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
    implementation: str = Field(
        description="Complete, runnable implementation. No placeholders or TODOs."
    )
    tests: str = Field(
        description=(
            "Complete test suite. Must cover: happy path, edge cases, error conditions."
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
    """What gets sent back to the LLM when a gate fails."""
    failed_gate: str
    errors: list[GateError]
    previous_reasoning: str
    previous_code: str
    similar_past_failures: list[str]
    instruction: str


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


# ── Memory ────────────────────────────────────────────────────────────────────

@dataclass
class MemoryStats:
    total_runs: int
    total_failures: int
    resolution_rate: float
    failures_by_gate: dict[str, int]
    failures_by_error_code: dict[str, int]
    mean_attempts_to_resolve: float
