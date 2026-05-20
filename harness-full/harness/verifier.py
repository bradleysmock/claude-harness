"""
Adversarial verifier agent.

Closes the largest documented gap in the harness: the model cannot
reliably verify its own output. A separate LLM call, prompted with
adversarial framing and given only the spec and the generated code
(NOT the implementer's reasoning), produces a structured review.

Why this works
──────────────
Sycophancy and self-defence are products of training, but they require
investment. An LLM call that did not produce the implementation has no
investment in defending it. Adversarial framing combined with absent
reasoning context routes around the structural agreement bias.

What this is NOT
────────────────
Not a style critic. Not an improvement suggester. Not a code rewriter.
The verifier's job is bounded to finding problems against the spec.
Findings are inputs to repair; they are not themselves repairs.

Trigger
───────
The verifier runs only after all deterministic gates pass. If the type
checker, linter, and tests reject the code, the verifier's input is
already invalid — no point spending an API call. Verifier rejection
triggers the same repair loop as gate rejection.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Spec, GeneratedArtifact
    from .llm.client import AnthropicLLMClient

log = logging.getLogger("harness.verifier")


# ── Result types ──────────────────────────────────────────────────────────────

Severity = Literal["critical", "major", "minor"]
Category = Literal[
    "missing_requirement",
    "incorrect_implementation",
    "untested_edge_case",
    "spec_misinterpretation",
    "security_concern",
    "hallucinated_api",
    "other",
]


@dataclass
class VerifierFinding:
    severity: Severity
    category: Category
    description: str
    evidence: str       # specific quote from spec or code
    suggestion: str     # what should change

    def as_repair_line(self) -> str:
        sev = {"critical": "✗", "major": "▲", "minor": "•"}.get(self.severity, "?")
        return f"  {sev} [{self.severity.upper()}] {self.description}\n    Evidence: {self.evidence}\n    Suggestion: {self.suggestion}"


@dataclass
class ConstraintCheck:
    """Per-constraint and per-criterion coverage statement from the verifier."""
    text: str
    addressed: bool
    evidence: str


@dataclass
class VerifierReport:
    verdict: Literal["approved", "rejected"]
    summary: str
    constraint_coverage: list[ConstraintCheck] = field(default_factory=list)
    criteria_coverage: list[ConstraintCheck] = field(default_factory=list)
    findings: list[VerifierFinding] = field(default_factory=list)

    @property
    def critical_findings(self) -> list[VerifierFinding]:
        return [f for f in self.findings if f.severity == "critical"]

    @property
    def major_findings(self) -> list[VerifierFinding]:
        return [f for f in self.findings if f.severity == "major"]

    @property
    def blocking_findings(self) -> list[VerifierFinding]:
        """Findings that should trigger repair."""
        return self.critical_findings + self.major_findings

    def passed(self) -> bool:
        return self.verdict == "approved" and not self.blocking_findings

    def formatted(self) -> str:
        lines = [f"\nVerifier report: {self.verdict.upper()}"]
        lines.append(f"  Summary: {self.summary}")
        if self.findings:
            lines.append("\n  Findings:")
            for f in self.findings:
                lines.append(f.as_repair_line())

        unaddressed_constraints = [c for c in self.constraint_coverage if not c.addressed]
        if unaddressed_constraints:
            lines.append(f"\n  Unaddressed constraints: {len(unaddressed_constraints)}")
            for c in unaddressed_constraints[:3]:
                lines.append(f"    - {c.text}")

        unverifiable_criteria = [c for c in self.criteria_coverage if not c.addressed]
        if unverifiable_criteria:
            lines.append(f"\n  Unverifiable criteria: {len(unverifiable_criteria)}")
            for c in unverifiable_criteria[:3]:
                lines.append(f"    - {c.text}")

        return "\n".join(lines)


# ── The verifier ──────────────────────────────────────────────────────────────

class AdversarialVerifier:
    """
    Reviews a generated artifact against its spec with adversarial framing.

    Key design properties
    ─────────────────────
    1. The verifier sees only the spec and the code, NOT the implementer's
       reasoning or assumptions. This prevents the verifier from rationalising
       agreement with the implementer's chain of thought.

    2. The verifier walks through every constraint and acceptance criterion
       individually, producing a coverage statement for each. This makes
       silence (zero findings) conspicuous.

    3. The verifier produces structured findings with severity, category,
       evidence, and suggestion. These map directly into repair instructions.

    4. The verdict logic is mechanical, not LLM-determined:
       - Any critical finding → rejected
       - 2+ major findings    → rejected
       - Unaddressed constraints (>0) → rejected
       - Otherwise → approved
    """

    def __init__(self, llm_client: "AnthropicLLMClient", strict: bool = True):
        self._llm = llm_client
        self._strict = strict

    def verify(
        self,
        spec: "Spec",
        artifact: "GeneratedArtifact",
    ) -> VerifierReport:
        """
        Returns a structured verification report.
        """
        prompt = self._build_prompt(spec, artifact)
        response = self._llm.complete_json(
            system=_VERIFIER_SYSTEM_PROMPT,
            user=prompt,
        )
        report = self._parse_response(response)
        report.verdict = self._compute_verdict(report)
        return report

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_prompt(self, spec: "Spec", artifact: "GeneratedArtifact") -> str:
        constraints_text = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(spec.constraints))
        criteria_text = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(spec.acceptance_criteria))

        # ── Asymmetric exposure (Refinement 3) ────────────────────────────────
        # The verifier sees `uncertain_about` (focuses skepticism on flagged
        # areas) but NOT `confident_about` or `falsification` or `reasoning`
        # (would invite sycophantic agreement with the implementer's framing).
        uncertain_section = ""
        if getattr(artifact, "uncertain_about", None):
            uncertain_lines = "\n".join(f"  - {u}" for u in artifact.uncertain_about)
            uncertain_section = (
                f"\nThe implementer flagged the following areas as uncertain. "
                f"Verify these specifically:\n{uncertain_lines}\n"
            )

        risk_note = ""
        if getattr(artifact, "risk_assessment", None) == "high":
            risk_note = "\nThe implementer rated this as HIGH RISK. Scrutinise accordingly.\n"

        # Note: implementer's reasoning, confident_about, and falsification are
        # deliberately NOT included.
        return f"""You are reviewing an implementation against its specification.

The implementation has already passed automated gates (type checking, linting,
unit tests). Your job is to find what those gates missed.

You are NOT being asked whether the code is good, well-structured, or could be
improved. You are being asked whether it actually satisfies the specification.
{uncertain_section}{risk_note}
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
IMPLEMENTATION
═══════════════════════════════════════════════════════════════════════════════

{artifact.implementation}

═══════════════════════════════════════════════════════════════════════════════
TESTS
═══════════════════════════════════════════════════════════════════════════════

{artifact.tests}

═══════════════════════════════════════════════════════════════════════════════

For each constraint and each acceptance criterion, state whether the
implementation addresses it. Be specific in the evidence — quote actual
identifiers, line patterns, or behaviours from the code.

For each problem you find, produce a finding with severity, category,
evidence, and suggestion.

Default to suspicion. The fact that the implementation looks reasonable
and the tests pass does NOT mean the spec is satisfied. Specifically check:
  - Does each named constraint identifier (class, method, function) actually
    appear in the code as required?
  - Are all enumerated error conditions actually handled?
  - Do the tests actually verify the acceptance criteria, or do they verify
    something adjacent?
  - Are there hallucinated API calls — functions or methods that look
    plausible but may not exist on the imported types?
  - Are there hidden assumptions in the implementation that the spec did
    not authorise?

If you find nothing wrong, you must still produce constraint_coverage and
criteria_coverage entries demonstrating each requirement was checked.

Return JSON only, matching this schema exactly:

{{
  "review_summary": "2-3 sentences describing what the implementation does and what it does not do",
  "constraint_coverage": [
    {{
      "text": "the constraint, verbatim from the spec",
      "addressed": true | false,
      "evidence": "specific reference to code that addresses it, OR why it is unaddressed"
    }}
  ],
  "criteria_coverage": [
    {{
      "text": "the acceptance criterion, verbatim from the spec",
      "addressed": true | false,
      "evidence": "specific test or code that verifies it, OR why it is unverifiable"
    }}
  ],
  "findings": [
    {{
      "severity": "critical" | "major" | "minor",
      "category": "missing_requirement" | "incorrect_implementation" | "untested_edge_case" | "spec_misinterpretation" | "security_concern" | "hallucinated_api" | "other",
      "description": "what is wrong",
      "evidence": "specific quote from the code or spec",
      "suggestion": "specific change required"
    }}
  ]
}}
"""

    def _parse_response(self, response: dict) -> VerifierReport:
        return VerifierReport(
            verdict="approved",  # placeholder, computed below
            summary=response.get("review_summary", ""),
            constraint_coverage=[
                ConstraintCheck(
                    text=c.get("text", ""),
                    addressed=bool(c.get("addressed", False)),
                    evidence=c.get("evidence", ""),
                )
                for c in response.get("constraint_coverage", [])
            ],
            criteria_coverage=[
                ConstraintCheck(
                    text=c.get("text", ""),
                    addressed=bool(c.get("addressed", False)),
                    evidence=c.get("evidence", ""),
                )
                for c in response.get("criteria_coverage", [])
            ],
            findings=[
                VerifierFinding(
                    severity=f.get("severity", "minor"),
                    category=f.get("category", "other"),
                    description=f.get("description", ""),
                    evidence=f.get("evidence", ""),
                    suggestion=f.get("suggestion", ""),
                )
                for f in response.get("findings", [])
            ],
        )

    def _compute_verdict(self, report: VerifierReport) -> Literal["approved", "rejected"]:
        if report.critical_findings:
            return "rejected"
        if len(report.major_findings) >= 2:
            return "rejected"
        unaddressed = [c for c in report.constraint_coverage if not c.addressed]
        if unaddressed:
            return "rejected"
        if self._strict:
            unverifiable = [c for c in report.criteria_coverage if not c.addressed]
            if unverifiable:
                return "rejected"
        return "approved"


# ── System prompt ─────────────────────────────────────────────────────────────

_VERIFIER_SYSTEM_PROMPT = """You are an adversarial code reviewer with a high bar.

Your role is bounded: find specification compliance failures in code that has
already passed automated gates. You do NOT suggest improvements, refactorings,
or stylistic changes. You only report what the specification requires but the
implementation does not deliver.

Critical principles:
1. The implementation has already passed automated checks. Your value is in
   finding what those checks missed — hidden assumptions, hallucinated APIs,
   spec misinterpretations, untested edge cases.
2. Default to suspicion. Plausible-looking code that compiles is not
   evidence of correctness against a specification.
3. Walk through every constraint and acceptance criterion individually.
   Silence (zero findings) requires explicit per-requirement coverage,
   not assertion.
4. Cite evidence. Every finding must reference a specific identifier,
   line pattern, or behaviour. "This could be better" is not a finding.
5. You are NOT the implementer. You have no investment in defending the
   implementation's choices. If something is wrong, name it directly.

Output JSON only. No commentary outside the JSON object."""
