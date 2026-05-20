"""
Spec hardening pre-pass.

Before generation, the hardener expands a specification by enumerating the
implicit details that would otherwise be resolved by the implementer's priors:
pinned identifiers, type signatures, edge cases, and anti-requirements.

Why this matters
────────────────
From "From the Inside," Section 4.3: ambiguity in a spec gets resolved during
generation by the model's training-distribution priors, often invisibly. If
the spec says "validate input," I will generate one of several plausible
validators based on what I have seen in training. The user may not realise
I made a choice until it surfaces as a bug.

The hardener exposes this resolution step. Rather than letting it happen
invisibly during generation, the hardener performs it explicitly, with
structured output that names what was resolved and how. The result is a
spec where every degree of freedom that the implementer would otherwise
fill in is either pinned or surfaced for human review.

Two failure modes the hardener addresses directly
─────────────────────────────────────────────────
  Hidden assumptions (Section 4.3 of From the Inside)
    The implementer fills in ambiguity without notification.
    Hardener: enumerates the ambiguities and pins or surfaces each.

  Reference drift (Section 4.2)
    The implementer uses inconsistent identifiers across a long generation.
    Hardener: pins identifiers explicitly so generation has no degree of
    freedom in naming.

Important non-goal
──────────────────
The hardener is NOT a spec rewriter. It does not change the original
constraints or acceptance criteria. It produces additive material that
augments the spec for generation. The user's spec file is unchanged;
the augmented spec exists only in the orchestrator's working copy.

Conservative behaviour on ambiguity
───────────────────────────────────
When a resolution is non-obvious, the hardener surfaces it as an
"open_ambiguity" rather than guessing. Open ambiguities can be reviewed
by the user; pinned resolutions are recorded for audit. This trades some
automation for honesty about where the model is interpolating.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Spec
    from .llm.client import AnthropicLLMClient

log = logging.getLogger("harness.hardener")


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class PinnedIdentifier:
    """A name the spec referenced ambiguously, pinned to a concrete value."""
    role: str          # what role this identifier plays ("rate limiter class")
    name: str          # the concrete name selected ("RedisRateLimiter")
    rationale: str     # why this name was chosen
    source: str        # "codebase_context" | "convention" | "model_prior"


@dataclass
class OpenAmbiguity:
    """An ambiguity the hardener detected but could not confidently resolve."""
    question: str       # what is unclear
    options: list[str]  # plausible interpretations the hardener saw
    impact: str         # what changes between the options


@dataclass
class HardeningReport:
    pinned_identifiers: list[PinnedIdentifier] = field(default_factory=list)
    type_signatures: list[str] = field(default_factory=list)
    edge_cases: list[str] = field(default_factory=list)
    anti_requirements: list[str] = field(default_factory=list)
    open_ambiguities: list[OpenAmbiguity] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not any([
            self.pinned_identifiers, self.type_signatures, self.edge_cases,
            self.anti_requirements, self.open_ambiguities,
        ])

    @property
    def needs_review(self) -> bool:
        """True if there are open ambiguities the user should resolve."""
        return bool(self.open_ambiguities)

    def to_constraints(self) -> list[str]:
        """Convert hardening into additional constraint strings."""
        new = []
        for p in self.pinned_identifiers:
            new.append(f"Use {p.name} as the {p.role} (do not introduce alternate names)")
        for sig in self.type_signatures:
            new.append(f"Signature: {sig}")
        for case in self.edge_cases:
            new.append(f"Handle edge case: {case}")
        for anti in self.anti_requirements:
            new.append(f"Do NOT: {anti}")
        return new

    def formatted(self) -> str:
        lines = ["\nSpec hardening report:"]
        if self.is_empty:
            lines.append("  No hardening needed — spec is already specific.")
            return "\n".join(lines)
        if self.pinned_identifiers:
            lines.append(f"\n  Pinned identifiers ({len(self.pinned_identifiers)}):")
            for p in self.pinned_identifiers:
                lines.append(f"    • {p.role}: {p.name}  [{p.source}]")
                lines.append(f"        — {p.rationale}")
        if self.type_signatures:
            lines.append(f"\n  Type signatures ({len(self.type_signatures)}):")
            for s in self.type_signatures:
                lines.append(f"    • {s}")
        if self.edge_cases:
            lines.append(f"\n  Edge cases enumerated ({len(self.edge_cases)}):")
            for c in self.edge_cases:
                lines.append(f"    • {c}")
        if self.anti_requirements:
            lines.append(f"\n  Anti-requirements ({len(self.anti_requirements)}):")
            for a in self.anti_requirements:
                lines.append(f"    • {a}")
        if self.open_ambiguities:
            lines.append(f"\n  ⚠ Open ambiguities ({len(self.open_ambiguities)}) — needs human review:")
            for amb in self.open_ambiguities:
                lines.append(f"    ? {amb.question}")
                lines.append(f"      Options: {', '.join(amb.options[:3])}")
                lines.append(f"      Impact:  {amb.impact}")
        return "\n".join(lines)


# ── The hardener ──────────────────────────────────────────────────────────────

class SpecHardener:
    """
    Expands a spec by enumerating what would otherwise be resolved by the
    implementer's priors. Returns the original spec augmented with additional
    constraints, along with a report describing what was added and what
    remains genuinely ambiguous.

    The hardener uses the LLM but with very different framing from the
    implementer. The implementer is asked to produce code; the hardener
    is asked to find places where the spec could be misinterpreted. These
    are different tasks and produce different output distributions.
    """

    def __init__(self, llm_client: "AnthropicLLMClient"):
        self._llm = llm_client

    def harden(self, spec: "Spec") -> tuple["Spec", HardeningReport]:
        """
        Returns (hardened_spec, report).
        hardened_spec has additional constraints from the hardening; the
        original constraints and criteria are preserved unchanged.
        """
        prompt = self._build_prompt(spec)
        response = self._llm.complete_json(
            system=_HARDENER_SYSTEM_PROMPT,
            user=prompt,
        )
        report = self._parse_response(response)
        hardened = self._apply_hardening(spec, report)
        return hardened, report

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_prompt(self, spec: "Spec") -> str:
        constraints_text = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(spec.constraints))
        criteria_text = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(spec.acceptance_criteria))
        target = spec.metadata.get("target_file", "(not specified)")

        return f"""You are analysing a code generation specification for ambiguities that a code-generating LLM would resolve using its training priors, possibly invisibly.

Your goal is to surface those resolutions before generation, so they can be either pinned (made explicit) or flagged (marked for human review).

═══════════════════════════════════════════════════════════════════════════════
SPECIFICATION
═══════════════════════════════════════════════════════════════════════════════

Target file: {target}

Description:
{spec.description}

Constraints:
{constraints_text}

Acceptance criteria:
{criteria_text}

═══════════════════════════════════════════════════════════════════════════════

For this spec, identify the following four kinds of implicit content:

1. PINNED IDENTIFIERS
   For every concept the spec references by description but does not name
   (e.g., "the rate limiter," "the user store," "the validation function"),
   suggest a specific identifier name. If the spec describes a class but
   never names it, give it a name. If a function will be called but is not
   named, name it.

   Only pin when the role is clear and the naming follows obvious conventions
   (CamelCase classes, snake_case functions). Mark the source:
     - "codebase_context": derived from referenced files or conventions
     - "convention":       a standard naming pattern
     - "model_prior":      best guess from how similar concepts are usually named

2. TYPE SIGNATURES
   For every function, method, or interface implied by the spec, write its
   explicit signature with concrete types. If the spec says "returns the user
   or None," produce: `get_user_by_email(email: str) -> User | None`.

3. EDGE CASES
   Enumerate edge cases that the implementation must handle but the spec does
   not explicitly mention. Standard categories: empty input, None input, max
   length, concurrency, transient failure, boundary values. Only include cases
   that the spec's behaviour clearly implies should be handled.

4. ANTI-REQUIREMENTS
   List things the implementer might add that the spec does not authorise.
   "Do not add logging," "Do not add retry logic," "Do not introduce caching."
   These prevent scope creep during generation.

5. OPEN AMBIGUITIES
   For ambiguities that have multiple plausible interpretations and no clear
   way to choose, do NOT guess. Surface the ambiguity with the options you
   considered and the impact of each choice. The user will resolve these
   before the spec proceeds to generation.

Be conservative. When in doubt between pinning and surfacing, surface.
The cost of an unresolved ambiguity is one prompt iteration; the cost of
a wrong pin is silent miscompliance with the spec.

Return JSON only:

{{
  "pinned_identifiers": [
    {{
      "role": "the concept the identifier represents",
      "name": "the concrete identifier name",
      "rationale": "why this name (one sentence)",
      "source": "codebase_context" | "convention" | "model_prior"
    }}
  ],
  "type_signatures": [
    "function_name(param: Type) -> ReturnType"
  ],
  "edge_cases": [
    "specific edge case to handle (one per line)"
  ],
  "anti_requirements": [
    "specific thing the implementer should not do"
  ],
  "open_ambiguities": [
    {{
      "question": "what is unclear",
      "options": ["interpretation 1", "interpretation 2"],
      "impact": "what changes between the options"
    }}
  ]
}}

If the spec is already fully specified and no hardening is needed, return
all arrays empty. This is a valid and correct output for specs that are
already precise.
"""

    def _parse_response(self, response: dict) -> HardeningReport:
        return HardeningReport(
            pinned_identifiers=[
                PinnedIdentifier(
                    role=p.get("role", ""),
                    name=p.get("name", ""),
                    rationale=p.get("rationale", ""),
                    source=p.get("source", "model_prior"),
                )
                for p in response.get("pinned_identifiers", [])
            ],
            type_signatures=response.get("type_signatures", []),
            edge_cases=response.get("edge_cases", []),
            anti_requirements=response.get("anti_requirements", []),
            open_ambiguities=[
                OpenAmbiguity(
                    question=a.get("question", ""),
                    options=a.get("options", []),
                    impact=a.get("impact", ""),
                )
                for a in response.get("open_ambiguities", [])
            ],
        )

    def _apply_hardening(self, spec: "Spec", report: HardeningReport) -> "Spec":
        """
        Return a new Spec with hardening applied as additional constraints.
        Original constraints and criteria are preserved verbatim.
        """
        from .models import Spec
        from dataclasses import replace

        new_constraints = list(spec.constraints) + report.to_constraints()
        # Carry hardening in metadata for audit
        new_metadata = dict(spec.metadata)
        new_metadata["hardening_applied"] = True
        new_metadata["pinned_count"] = len(report.pinned_identifiers)
        new_metadata["open_ambiguities"] = len(report.open_ambiguities)

        try:
            # If Spec is a pydantic BaseModel
            return spec.model_copy(update={
                "constraints": new_constraints,
                "metadata": new_metadata,
            })
        except AttributeError:
            # Dataclass fallback
            return replace(spec, constraints=new_constraints, metadata=new_metadata)


# ── System prompt ─────────────────────────────────────────────────────────────

_HARDENER_SYSTEM_PROMPT = """You analyse code generation specifications for hidden ambiguities.

Your role is to make explicit what would otherwise be resolved silently during code generation. You are NOT the implementer; you do not produce code. You produce structured output that names what a code generator would have to decide, so those decisions can be reviewed before generation begins.

Key principles:
1. Pin what is obvious; surface what is not. If a concept clearly maps to a single
   conventional name, pin it. If there are multiple plausible interpretations,
   surface the ambiguity with its options.
2. Do not invent requirements. Only pin and enumerate things the spec already
   implies. Adding new functional requirements is out of scope.
3. Anti-requirements matter. Enumerating what the implementation should NOT do
   prevents scope creep during generation.
4. Edge cases must follow from the spec. Enumerate only the cases that the
   spec's stated behaviour requires handling, not every conceivable case.
5. Be conservative on pinning. A surfaced ambiguity costs one human review
   moment. A wrongly pinned identifier costs a silent spec violation.

Output JSON only. No commentary outside the JSON object."""
