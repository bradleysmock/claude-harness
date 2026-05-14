"""
Spec quality scorer.

Runs before any API call. Scores a Spec across five dimensions and
produces a structured report with actionable suggestions.

No network calls. No LLM. Completes in <10ms.

Dimensions
──────────
constraint_specificity   Do constraints name real identifiers, not vague intentions?
criteria_testability     Are acceptance criteria specific, falsifiable assertions?
reference_validity       Do referenced and target files exist on disk?
description_precision    Is the description specific enough to constrain generation?
coverage_balance         Are error paths covered alongside the happy path?

Thresholds
──────────
>= 0.80   PASS    — submit immediately
0.60–0.79 WARN    — submit with printed warnings
< 0.60    BLOCK   — refuse to submit unless --force is passed
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .models import Spec


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class DimensionScore:
    name: str
    score: float                  # 0.0–1.0
    weight: float                 # contribution to overall score
    issues: list[str]             # specific problems found
    suggestions: list[str]        # how to fix them


@dataclass
class SpecScore:
    spec_id: str
    dimensions: list[DimensionScore]
    overall: float                # weighted average
    verdict: Literal["pass", "warn", "block"]
    blocking_issues: list[str]    # issues that forced a block regardless of score

    PASS_THRESHOLD  = 0.80
    WARN_THRESHOLD  = 0.60

    def passed(self) -> bool:
        return self.verdict == "pass"

    def formatted_report(self) -> str:
        lines = [
            f"\nSpec quality: {self.spec_id}",
            f"{'─' * 52}",
            f"Overall score: {self.overall:.0%}  [{self.verdict.upper()}]",
            "",
        ]
        for dim in self.dimensions:
            bar = _bar(dim.score)
            lines.append(f"  {dim.name:<28} {bar}  {dim.score:.0%}")
            for issue in dim.issues:
                lines.append(f"    ✗ {issue}")
            for sug in dim.suggestions:
                lines.append(f"    → {sug}")
        if self.blocking_issues:
            lines += ["", "  Blocking issues:"]
            for b in self.blocking_issues:
                lines.append(f"    ✗ {b}")
        lines.append("")
        return "\n".join(lines)


# ── Scorer ────────────────────────────────────────────────────────────────────

class SpecScorer:
    """
    Scores a Spec across five dimensions using heuristic analysis.
    All checks are local — no filesystem access beyond reference file validation.
    """

    # Words that indicate a constraint is vague, not specific
    _VAGUE_WORDS = frozenset({
        "correctly", "properly", "appropriately", "efficiently", "well",
        "handle", "handles", "ensure", "ensures", "process", "processes",
        "manage", "manages", "support", "supports", "implement", "implements",
        "work", "works", "function", "functions", "behave", "behaves",
    })

    # Patterns that signal specificity in constraints
    _SPECIFIC_PATTERNS = [
        re.compile(r'\b[A-Z][a-zA-Z]+[A-Z][a-zA-Z]*\b'),  # CamelCase identifier
        re.compile(r'\b[a-z][a-z_]+\([^)]*\)'),             # method_call()
        re.compile(r'from\s+\S+\s+import'),                  # import statement
        re.compile(r'["\'][a-z/_]+\.py["\']'),               # file path string
        re.compile(r'\b\d{3}\b'),                             # HTTP status code
        re.compile(r'\b\d+\s*(ms|seconds?|minutes?|hours?)'), # time bound
        re.compile(r'[A-Z][A-Z_]{3,}'),                       # CONSTANT_NAME
        re.compile(r'->|:\s*(?:str|int|bool|float|list|dict|None|Optional)'), # type annotation
    ]

    # Patterns that signal a testable acceptance criterion
    _TESTABLE_PATTERNS = [
        re.compile(r'\breturns?\b.+\bwhen\b', re.IGNORECASE),
        re.compile(r'\breturns?\b.+\b(None|True|False|\d+)\b', re.IGNORECASE),
        re.compile(r'\braises?\b.+\b(Error|Exception|ValueError)\b', re.IGNORECASE),
        re.compile(r'\bdoes not raise\b', re.IGNORECASE),
        re.compile(r'\b(4\d{2}|5\d{2}|2\d{2})\b'),           # HTTP status in criteria
        re.compile(r'\b(assert|expect|verify|confirm)\b', re.IGNORECASE),
        re.compile(r'\b(is|are|contains?|equals?|matches?)\b.+\b', re.IGNORECASE),
        re.compile(r'\bstill pass\b', re.IGNORECASE),         # regression criterion
    ]

    # Words that indicate a criterion is not testable
    _UNTESTABLE_WORDS = frozenset({
        "correctly", "properly", "appropriately", "efficiently",
        "gracefully", "seamlessly", "robustly", "reliably",
    })

    # Error-path indicators in acceptance criteria
    _ERROR_INDICATORS = re.compile(
        r'\b(error|fail|invalid|missing|empty|none|null|exception|'
        r'not found|timeout|refused|denied|unauthori[sz]ed|forbidden|'
        r'4\d{2}|5\d{2})\b',
        re.IGNORECASE,
    )

    def score(self, spec: Spec, project_root: str = ".") -> SpecScore:
        blocking: list[str] = []

        # Hard blocks — no score needed
        if not spec.constraints:
            blocking.append("No constraints defined")
        if not spec.acceptance_criteria:
            blocking.append("No acceptance criteria defined")
        if not spec.description or len(spec.description.strip()) < 30:
            blocking.append("Description is too short to constrain generation")

        dimensions = [
            self._score_constraint_specificity(spec),
            self._score_criteria_testability(spec),
            self._score_reference_validity(spec, project_root),
            self._score_description_precision(spec),
            self._score_coverage_balance(spec),
        ]

        overall = (
            sum(d.score * d.weight for d in dimensions)
            / sum(d.weight for d in dimensions)
            if not blocking else 0.0
        )

        if blocking:
            verdict = "block"
        elif overall >= SpecScore.PASS_THRESHOLD:
            verdict = "pass"
        elif overall >= SpecScore.WARN_THRESHOLD:
            verdict = "warn"
        else:
            verdict = "block"

        return SpecScore(
            spec_id=spec.id,
            dimensions=dimensions,
            overall=round(overall, 3),
            verdict=verdict,
            blocking_issues=blocking,
        )

    # ── Dimensions ────────────────────────────────────────────────────────────

    def _score_constraint_specificity(self, spec: Spec) -> DimensionScore:
        if not spec.constraints:
            return _dim("constraint_specificity", 0.0, 0.30,
                        ["No constraints"], ["Add at least 3 specific constraints"])

        scores, issues, suggestions = [], [], []

        for i, c in enumerate(spec.constraints, 1):
            words = c.lower().split()
            vague_count = sum(1 for w in words if w in self._VAGUE_WORDS)
            specific_hits = sum(
                1 for p in self._SPECIFIC_PATTERNS if p.search(c)
            )
            length_ok = len(c) >= 25

            # Per-constraint score
            s = 0.5
            s += min(specific_hits * 0.15, 0.45)
            s -= min(vague_count * 0.15, 0.45)
            s = s if length_ok else s * 0.7
            s = max(0.0, min(1.0, s))
            scores.append(s)

            if s < 0.5:
                if vague_count > 0:
                    vague = [w for w in words if w in self._VAGUE_WORDS]
                    issues.append(
                        f"Constraint {i} is vague: '{c[:60]}…' "
                        f"(vague words: {', '.join(vague[:3])})"
                    )
                    suggestions.append(
                        f"Constraint {i}: name the specific class, method, or "
                        f"file path instead of describing intent"
                    )
                if specific_hits == 0:
                    issues.append(
                        f"Constraint {i} contains no specific identifiers: '{c[:60]}'"
                    )

        if len(spec.constraints) < 3:
            issues.append(f"Only {len(spec.constraints)} constraint(s) — most specs need 4+")
            suggestions.append("Add constraints for: imports, error handling, config source, conventions")

        score = sum(scores) / len(scores) if scores else 0.0
        return _dim("constraint_specificity", score, 0.30, issues, suggestions)

    def _score_criteria_testability(self, spec: Spec) -> DimensionScore:
        if not spec.acceptance_criteria:
            return _dim("criteria_testability", 0.0, 0.25,
                        ["No acceptance criteria"],
                        ["Add testable assertions: 'Returns X when Y'"])

        scores, issues, suggestions = [], [], []

        for i, c in enumerate(spec.acceptance_criteria, 1):
            words_lower = c.lower().split()
            testable_hits = sum(1 for p in self._TESTABLE_PATTERNS if p.search(c))
            untestable = [w for w in words_lower if w in self._UNTESTABLE_WORDS]

            s = min(testable_hits * 0.4, 1.0)
            s -= min(len(untestable) * 0.2, 0.4)
            s = max(0.0, min(1.0, s))
            scores.append(s)

            if s < 0.4:
                issues.append(f"Criterion {i} is not clearly testable: '{c[:70]}'")
                suggestions.append(
                    f"Criterion {i}: rewrite as 'Returns/Raises/Contains X when Y' "
                    f"or 'Does not raise when Z'"
                )

        if len(spec.acceptance_criteria) < 3:
            issues.append(
                f"Only {len(spec.acceptance_criteria)} criterion — "
                "most specs need 4+ to cover happy path and error paths"
            )

        score = sum(scores) / len(scores) if scores else 0.0
        return _dim("criteria_testability", score, 0.25, issues, suggestions)

    def _score_reference_validity(self, spec: Spec, project_root: str) -> DimensionScore:
        issues, suggestions = [], []
        root = Path(project_root)
        scores = [1.0]  # default to full score if nothing to check

        target = spec.metadata.get("target_file")
        refs = spec.metadata.get("reference_files", [])

        if not target:
            issues.append("No target_file in metadata")
            suggestions.append("Add metadata={'target_file': 'src/path/to/file.py'}")
            scores = [0.0]
        else:
            # Target shouldn't exist yet — but its parent directory should
            target_path = root / target
            if not target_path.parent.exists():
                issues.append(
                    f"Parent directory of target_file does not exist: "
                    f"{target_path.parent}"
                )
                suggestions.append(
                    f"Check target_file path — expected parent: {target_path.parent}"
                )
                scores = [0.3]

        for ref in refs:
            ref_path = root / ref
            if not ref_path.exists():
                issues.append(f"reference_file not found: {ref}")
                suggestions.append(
                    f"Check path '{ref}' — use paths relative to project root"
                )
                scores.append(0.0)
            else:
                scores.append(1.0)

        if not refs and target:
            issues.append("No reference_files — LLM has no codebase patterns to follow")
            suggestions.append(
                "Add reference_files with similar implementations from your codebase"
            )
            scores.append(0.5)  # penalise but don't block

        score = sum(scores) / len(scores)
        return _dim("reference_validity", score, 0.25, issues, suggestions)

    def _score_description_precision(self, spec: Spec) -> DimensionScore:
        issues, suggestions = [], []
        desc = spec.description.strip()

        score = 1.0

        if len(desc) < 60:
            issues.append("Description is too short — aim for 60+ characters")
            suggestions.append(
                "Expand to: what the unit does, what it returns, what it integrates with"
            )
            score -= 0.4

        # Check for specificity signals
        has_what = any(kw in desc.lower() for kw in ["function", "class", "method", "endpoint", "middleware", "service"])
        has_where = re.search(r'[A-Z][a-z]+[A-Z]|\bfrom\s+\w+\b|/api/', desc)
        has_return = re.search(r'\breturns?\b|\bproduces?\b|\byields?\b', desc, re.IGNORECASE)

        if not has_what:
            issues.append("Description doesn't state what type of unit this is")
            suggestions.append("Begin with: 'A function/class/endpoint/middleware that…'")
            score -= 0.2

        if not has_where:
            issues.append("Description doesn't reference where this fits in the system")
            suggestions.append("Name the service, router, or module this belongs to")
            score -= 0.2

        if not has_return:
            issues.append("Description doesn't state what this produces or returns")
            suggestions.append("Add: '…returning X' or '…that produces Y'")
            score -= 0.1

        # Penalise vague description words
        vague_in_desc = [w for w in self._VAGUE_WORDS if w in desc.lower().split()]
        if vague_in_desc:
            issues.append(f"Description contains vague words: {', '.join(vague_in_desc[:4])}")
            suggestions.append("Replace intent words with observable behaviour")
            score -= min(len(vague_in_desc) * 0.05, 0.2)

        score = max(0.0, min(1.0, score))
        return _dim("description_precision", score, 0.10, issues, suggestions)

    def _score_coverage_balance(self, spec: Spec) -> DimensionScore:
        issues, suggestions = [], []

        all_text = " ".join(spec.acceptance_criteria + spec.constraints)
        has_error_coverage = bool(self._ERROR_INDICATORS.search(all_text))

        criteria_count = len(spec.acceptance_criteria)
        error_criteria = sum(
            1 for c in spec.acceptance_criteria
            if self._ERROR_INDICATORS.search(c)
        )

        if not has_error_coverage:
            issues.append("No error paths covered in criteria or constraints")
            suggestions.append(
                "Add criteria for: invalid input, missing data, "
                "dependency failure, edge cases (empty, None, zero)"
            )
            score = 0.3
        elif error_criteria == 0 and criteria_count >= 3:
            issues.append(
                "Constraints mention errors but acceptance criteria only cover happy path"
            )
            suggestions.append(
                "Add at least one criterion per error condition in constraints"
            )
            score = 0.6
        else:
            # Score based on ratio — at least 25% error coverage is healthy
            ratio = error_criteria / criteria_count if criteria_count > 0 else 0
            score = min(1.0, 0.5 + ratio * 2)

        return _dim("coverage_balance", score, 0.10, issues, suggestions)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dim(name, score, weight, issues, suggestions) -> DimensionScore:
    return DimensionScore(
        name=name,
        score=round(score, 3),
        weight=weight,
        issues=issues,
        suggestions=suggestions,
    )

def _bar(score: float, width: int = 12) -> str:
    filled = round(score * width)
    colour = (
        "\033[32m" if score >= 0.8
        else "\033[33m" if score >= 0.6
        else "\033[31m"
    )
    reset = "\033[0m"
    return f"{colour}{'█' * filled}{'░' * (width - filled)}{reset}"
