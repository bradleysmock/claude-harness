"""
Novelty-calibrated verification.

Classifies task novelty from signals available in the pipeline (hardener
output, spec specificity, self-reported risk) and uses the classification
to scale verification rigor.

Design principle
────────────────
Never decrease baseline verification rigor based on novelty classification.
The cost of running verification on a canonical task is small; the cost of
missing a bug on a novel task can be substantial. Classification only
INCREASES rigor — additional retry budget, stricter verifier mode, human
review flag — when signals indicate the task is at or beyond the model's
typical training distribution.

This is a deterministic classifier. No LLM call. The signals are already
present in the pipeline (hardener report, spec structure, artifact's
structured confidence fields from Refinement 3). Classification is free
and reproducible: same inputs always produce the same level.

Levels
──────
canonical  Standard task with high spec specificity, low ambiguity, no
           self-reported risk. Baseline verification applies.
adapted    Mostly canonical with some extrapolation or ambiguity.
           Baseline verification + strictness held at maximum.
novel      Significant novelty: many open ambiguities, model-prior pins,
           or high self-reported risk. Extended retry budget, mandatory
           human review flag, every-attempt verifier.

Two-stage classification
────────────────────────
Stage 1 (pre-generation): from spec + hardening output
Stage 2 (post-generation): may upgrade based on artifact's risk_assessment
                           and uncertain_about. Never downgrades.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .models import Spec, GeneratedArtifact
    from .hardener import HardeningReport

log = logging.getLogger("harness.novelty")

NoveltyLevel = Literal["canonical", "adapted", "novel"]


# ── Verification profile ──────────────────────────────────────────────────────

@dataclass
class VerificationProfile:
    """
    Verification rigor configuration for a given novelty level.
    Higher novelty → more rigor; never less than baseline.
    """
    level: NoveltyLevel
    max_retries: int
    verifier_strict: bool
    requires_human_flag: bool
    verifier_every_attempt: bool

    @classmethod
    def for_level(cls, level: NoveltyLevel, base_retries: int = 3) -> "VerificationProfile":
        if level == "canonical":
            return cls(
                level="canonical",
                max_retries=base_retries,
                verifier_strict=True,
                requires_human_flag=False,
                verifier_every_attempt=False,  # only on first passing attempt
            )
        if level == "adapted":
            return cls(
                level="adapted",
                max_retries=base_retries,
                verifier_strict=True,
                requires_human_flag=False,
                verifier_every_attempt=True,
            )
        # novel
        return cls(
            level="novel",
            max_retries=base_retries + 2,
            verifier_strict=True,
            requires_human_flag=True,
            verifier_every_attempt=True,
        )


# ── Assessment ────────────────────────────────────────────────────────────────

@dataclass
class NoveltyAssessment:
    level: NoveltyLevel
    score: float                      # 0.0–1.0
    stage: Literal["pre_generation", "post_generation"]
    signals: dict[str, float] = field(default_factory=dict)
    profile: VerificationProfile = field(default=None)  # type: ignore
    upgraded_from: NoveltyLevel | None = None

    def formatted(self) -> str:
        lines = [
            f"\nNovelty: {self.level.upper()} "
            f"(score: {self.score:.2f}, stage: {self.stage})"
        ]
        if self.upgraded_from:
            lines.append(f"  ↑ Upgraded from {self.upgraded_from} "
                          "(self-reported risk above threshold)")
        for signal, value in self.signals.items():
            sign = "+" if value > 0 else ""
            lines.append(f"  {signal:<32} {sign}{value:.2f}")
        if self.profile:
            lines.append(
                f"  → Profile: retries={self.profile.max_retries}, "
                f"verifier_every_attempt={self.profile.verifier_every_attempt}, "
                f"human_flag={self.profile.requires_human_flag}"
            )
        return "\n".join(lines)


# ── Classifier ────────────────────────────────────────────────────────────────

class NoveltyClassifier:
    """
    Deterministic two-stage novelty classifier.

    Pre-generation: uses hardening output and spec structure.
    Post-generation: incorporates artifact's structured confidence fields.

    Thresholds
    ──────────
    score < 0.30  → canonical
    0.30 ≤ score < 0.60  → adapted
    score ≥ 0.60  → novel
    """

    CANONICAL_MAX = 0.30
    ADAPTED_MAX   = 0.60

    def __init__(self, base_retries: int = 3):
        self._base_retries = base_retries

    # ── Stage 1: pre-generation ───────────────────────────────────────────────

    def classify_pre_generation(
        self,
        spec: "Spec",
        hardening: "HardeningReport | None" = None,
    ) -> NoveltyAssessment:
        signals: dict[str, float] = {}

        # Signal: spec specificity (more constraints → more canonical)
        constraint_count = len(spec.constraints)
        criteria_count = len(spec.acceptance_criteria)
        if constraint_count < 3:
            signals["sparse_constraints"] = 0.15
        if criteria_count < 3:
            signals["sparse_criteria"] = 0.10

        # Signal: hardening output
        if hardening is not None:
            n_open = len(hardening.open_ambiguities)
            if n_open > 0:
                signals["open_ambiguities"] = min(n_open * 0.15, 0.30)

            model_prior_pins = sum(
                1 for p in hardening.pinned_identifiers
                if p.source == "model_prior"
            )
            if model_prior_pins > 0:
                # Pins from model priors (not codebase/convention) indicate
                # the spec is filling blanks the model is guessing about.
                signals["model_prior_pins"] = min(model_prior_pins * 0.05, 0.20)

        score = min(sum(signals.values()), 1.0)
        level = self._level_for_score(score)
        profile = VerificationProfile.for_level(level, self._base_retries)

        return NoveltyAssessment(
            level=level,
            score=round(score, 3),
            stage="pre_generation",
            signals=signals,
            profile=profile,
        )

    # ── Stage 2: post-generation upgrade ──────────────────────────────────────

    def update_with_artifact(
        self,
        prior: NoveltyAssessment,
        artifact: "GeneratedArtifact",
    ) -> NoveltyAssessment:
        """
        Incorporates the artifact's structured confidence fields.
        May upgrade the novelty level. Never downgrades.
        """
        signals = dict(prior.signals)

        risk = getattr(artifact, "risk_assessment", "low")
        if risk == "high":
            signals["self_reported_risk_high"] = 0.30
        elif risk == "medium":
            signals["self_reported_risk_medium"] = 0.15

        uncertain = getattr(artifact, "uncertain_about", []) or []
        if len(uncertain) >= 3:
            signals["multiple_uncertainties"] = 0.20
        elif len(uncertain) >= 1:
            signals["some_uncertainty"] = 0.10

        if not getattr(artifact, "falsification", "").strip():
            signals["no_falsification"] = 0.15

        score = min(sum(signals.values()), 1.0)
        new_level = self._level_for_score(score)
        final_level = _max_level(prior.level, new_level)  # never downgrade

        upgraded_from = prior.level if final_level != prior.level else None
        profile = VerificationProfile.for_level(final_level, self._base_retries)

        return NoveltyAssessment(
            level=final_level,
            score=round(score, 3),
            stage="post_generation",
            signals=signals,
            profile=profile,
            upgraded_from=upgraded_from,
        )

    # ── Private ───────────────────────────────────────────────────────────────

    def _level_for_score(self, score: float) -> NoveltyLevel:
        if score < self.CANONICAL_MAX:
            return "canonical"
        if score < self.ADAPTED_MAX:
            return "adapted"
        return "novel"


# ── Helpers ───────────────────────────────────────────────────────────────────

_LEVEL_ORDER = {"canonical": 0, "adapted": 1, "novel": 2}


def _max_level(a: NoveltyLevel, b: NoveltyLevel) -> NoveltyLevel:
    return a if _LEVEL_ORDER[a] >= _LEVEL_ORDER[b] else b
