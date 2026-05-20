"""
Spec-implementation alignment gate.

The final check in the verification pipeline. Runs after gates pass and
the adversarial verifier approves. Asks the holistic question: does this
implementation, end-to-end, accomplish what the spec was actually trying
to do?

Why this exists as a separate check
───────────────────────────────────
The adversarial verifier (Refinement 1) finds specific defects: missing
requirements, hallucinated APIs, untested criteria, security concerns.
Its attention is on finding-by-finding compliance.

The alignment gate addresses a different failure mode: implementations
where every individual compliance check passes but the overall purpose
has drifted. A function correctly named, correctly typed, with all
required identifiers, well-tested — but doing X when the spec was asking
for Y. Each verifier finding would defend the implementation; the spec
was nonetheless misunderstood.

Three structural differences from the verifier
──────────────────────────────────────────────
1. CAN see the implementer's reasoning. The verifier is shielded from it
   (to prevent sycophantic agreement with the implementer's framing); the
   alignment gate specifically needs it. Its job is to compare what the
   implementer thought they were building against what the spec asked for.

2. Framing is "second pair of eyes," not adversarial. The verifier has
   already done the adversarial work. This check is a sanity test on the
   overall target.

3. Output is a characterization, not findings. Spec intent + implementation
   intent + drift analysis + verdict. When alignment fails, repair gets a
   structured description of where the drift is, not a list of defects.

Position in the pipeline
────────────────────────
gates → verifier → ALIGNMENT GATE → accept or repair

The alignment gate runs only if gates and verifier both pass. If it
rejects, repair triggers with alignment-specific instructions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Spec, GeneratedArtifact
    from .llm.client import AnthropicLLMClient

log = logging.getLogger("harness.alignment")


# ── Output types ──────────────────────────────────────────────────────────────

Verdict = Literal["aligned", "drifted", "misaligned"]
DriftCategory = Literal[
    "wrong_abstraction",       # implementation uses different concepts than spec
    "wrong_scope",             # implementation does more or less than asked
    "missing_intent",          # implementation fails to capture core purpose
    "extra_intent",            # implementation does things not requested
    "right_code_wrong_purpose",# code correct in isolation but solves wrong problem
    "shallow_implementation",  # technically right but doesn't engage with the problem
]


@dataclass
class AlignmentReport:
    verdict: Verdict
    alignment_score: float       # 0.0–1.0, higher = better aligned
    spec_intent: str             # 1-2 sentences: what the spec asks for
    implementation_intent: str   # 1-2 sentences: what the impl appears to do
    drift_analysis: str          # where the divergence is, if any
    drift_categories: list[DriftCategory] = field(default_factory=list)

    def passed(self, threshold: float = 0.75) -> bool:
        if self.verdict == "misaligned":
            return False
        if self.verdict == "drifted" and self.alignment_score < threshold:
            return False
        return self.alignment_score >= threshold

    def repair_instruction(self) -> str:
        """Format the alignment report as a repair instruction for the LLM."""
        lines = [
            "The alignment gate determined that your implementation has drifted "
            "from the specification's intent.",
            "",
            f"What the specification asks for: {self.spec_intent}",
            "",
            f"What your implementation appears to do: {self.implementation_intent}",
            "",
            f"Drift analysis: {self.drift_analysis}",
        ]
        if self.drift_categories:
            categories = ", ".join(self.drift_categories)
            lines.append(f"\nDrift categories: {categories}")
        lines.append(
            "\nThis is not a bug-fix request. Your implementation may be internally "
            "correct, but it is not solving the problem the specification described. "
            "Re-read the specification carefully and rebuild around its actual intent."
        )
        return "\n".join(lines)

    def formatted(self) -> str:
        lines = [
            f"\nAlignment report: {self.verdict.upper()} "
            f"(score: {self.alignment_score:.2f})"
        ]
        lines.append(f"  Spec intent:     {self.spec_intent}")
        lines.append(f"  Impl intent:     {self.implementation_intent}")
        if self.drift_analysis and self.verdict != "aligned":
            lines.append(f"  Drift analysis:  {self.drift_analysis}")
        if self.drift_categories:
            lines.append(f"  Drift categories: {', '.join(self.drift_categories)}")
        return "\n".join(lines)


# ── The gate ──────────────────────────────────────────────────────────────────

class AlignmentGate:
    """
    Compares specification intent against implementation intent.
    Returns an AlignmentReport with a verdict, an alignment score, and
    a structured analysis of any drift.
    """

    def __init__(
        self,
        llm_client: "AnthropicLLMClient",
        threshold: float = 0.75,
    ):
        self._llm = llm_client
        self._threshold = threshold

    def check(self, spec: "Spec", artifact: "GeneratedArtifact") -> AlignmentReport:
        prompt = self._build_prompt(spec, artifact)
        response = self._llm.complete_json(
            system=_ALIGNMENT_SYSTEM_PROMPT,
            user=prompt,
        )
        return self._parse_response(response)

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_prompt(self, spec: "Spec", artifact: "GeneratedArtifact") -> str:
        constraints_text = "\n".join(f"  - {c}" for c in spec.constraints)
        criteria_text = "\n".join(f"  - {c}" for c in spec.acceptance_criteria)
        reasoning = getattr(artifact, "reasoning", "") or "(no reasoning recorded)"

        return f"""You are performing a final alignment check between a specification and its implementation.

This is a holistic question, not a defect search. The implementation has
already passed deterministic gates (type check, lint, tests) and an
adversarial verifier (spec compliance review). Your role is different: to
verify that the implementation, taken as a whole, accomplishes what the
specification was actually asking for.

═══════════════════════════════════════════════════════════════════════════════
SPECIFICATION
═══════════════════════════════════════════════════════════════════════════════

Description:
{spec.description}

Constraints:
{constraints_text}

Acceptance criteria:
{criteria_text}

═══════════════════════════════════════════════════════════════════════════════
IMPLEMENTER'S REASONING
═══════════════════════════════════════════════════════════════════════════════

This is what the implementing model wrote about its own approach.
Use this to understand what the implementer THOUGHT it was building.
If the reasoning shows a misinterpretation of the spec, alignment may
be poor regardless of code correctness.

{reasoning}

═══════════════════════════════════════════════════════════════════════════════
IMPLEMENTATION
═══════════════════════════════════════════════════════════════════════════════

{artifact.implementation}

═══════════════════════════════════════════════════════════════════════════════

Your task:

1. Read the specification and form your own understanding of what it asks for.
   State this as `spec_intent` — one or two sentences capturing the
   fundamental purpose of the requested code.

2. Read the implementation and the implementer's reasoning. Form your
   understanding of what the implementation actually does (independent of
   whether it does it correctly). State this as `implementation_intent`.

3. Compare. Does the implementation accomplish the spec's intent? Or has
   the implementation drifted toward solving a different problem that
   happens to look similar?

4. Assign an `alignment_score` between 0.0 and 1.0:
     1.0      = implementation directly accomplishes spec intent
     0.75–0.9 = aligned with minor drift; still fundamentally correct
     0.5–0.74 = drifted; partially correct but misses important aspects
     0.0–0.49 = misaligned; solves a different problem

5. Choose a `verdict`:
     "aligned"     — alignment_score >= 0.85
     "drifted"     — 0.5 <= alignment_score < 0.85
     "misaligned"  — alignment_score < 0.5

6. If `verdict` is "drifted" or "misaligned", provide:
   - `drift_analysis`: a specific description of where the divergence is
   - `drift_categories`: zero or more from this list:
       - "wrong_abstraction"        (different concepts than spec)
       - "wrong_scope"              (does more or less than asked)
       - "missing_intent"           (fails to capture core purpose)
       - "extra_intent"             (does things not requested)
       - "right_code_wrong_purpose" (correct in isolation, wrong problem)
       - "shallow_implementation"   (technically right but unengaged)

Be honest about alignment. Minor cosmetic differences are not drift.
Significant interpretive differences are. A perfectly written
implementation of the wrong thing is misaligned, not aligned.

Return JSON only:

{{
  "spec_intent": "...",
  "implementation_intent": "...",
  "alignment_score": 0.0,
  "verdict": "aligned" | "drifted" | "misaligned",
  "drift_analysis": "...",
  "drift_categories": []
}}
"""

    def _parse_response(self, response: dict) -> AlignmentReport:
        return AlignmentReport(
            verdict=response.get("verdict", "aligned"),
            alignment_score=float(response.get("alignment_score", 1.0)),
            spec_intent=response.get("spec_intent", ""),
            implementation_intent=response.get("implementation_intent", ""),
            drift_analysis=response.get("drift_analysis", ""),
            drift_categories=response.get("drift_categories", []),
        )


# ── System prompt ─────────────────────────────────────────────────────────────

_ALIGNMENT_SYSTEM_PROMPT = """You evaluate whether an implementation accomplishes the intent of a specification.

This is a holistic alignment check, not a defect search. You are reading
both the spec and the implementation as a senior reviewer would, asking:
"Is this code solving the problem the spec describes?"

Key principles:
1. Distinguish alignment from correctness. A correctly written implementation
   of the wrong thing is misaligned. A roughly written implementation of
   the right thing is aligned.
2. The implementer's reasoning is your window into their interpretation.
   If their reasoning shows a misreading of the spec, alignment is suspect
   even if the code looks reasonable.
3. Be specific about drift. Vague concerns are not useful. If there is
   drift, describe exactly what the implementation does that the spec did
   not ask for, or what the spec asked for that the implementation does not do.
4. Cosmetic differences are not drift. Different variable names, different
   internal structure, different test organisation — none of these are
   alignment issues. Interpretive differences are.
5. Score honestly. Most well-engineered implementations align with their
   specs and should score high. Drift is the exception, not the default.
   But when drift is present, name it clearly.

Output JSON only. No commentary outside the JSON object."""
