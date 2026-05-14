"""
Repair instruction escalation.

Problem solved
──────────────
The original harness sent the same repair instruction on every attempt:
"Fix only the errors listed above. Do not change anything else."

By attempt 2, the model has already failed once with that instruction.
By attempt 3, it has failed twice. A static instruction gives no new
information — the model has nothing additional to reason from.

Solution
────────
RepairInstructionEscalator analyses what happened between attempts and
selects one of three escalating strategies:

  Level 1 (attempt 1 → 2)   Targeted repair
    Standard surgical fix. Model has failed once; most likely a simple
    misunderstanding. Add the failure pattern to guide the next attempt.

  Level 2 (attempt 2 → 3)   Diagnostic repair
    The model failed twice. Force explicit root-cause reasoning before
    any code is written. Show the diff between what was tried and what
    still fails. Identify specific failure patterns (recurring errors,
    newly introduced errors, growing error count).

  Level 3 (attempt 3+)      Reset repair
    The model is stuck. Abandon incremental repair. Instruct it to
    identify the fundamental design issue and rewrite from scratch.
    The previous implementation is shown as an anti-example only.

Failure patterns detected
─────────────────────────
  RECURRING     Same error codes appear in both prev and curr attempt
  NEW_ERRORS    Curr attempt has error codes not in prev attempt
  SCOPE_TOO_WIDE  Previous fix resolved some errors but introduced others
  PARTIAL       Some errors fixed, some remain (genuine partial progress)
  REGRESSED     More errors now than before the repair
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import GateError


# ── Failure pattern analysis ──────────────────────────────────────────────────

@dataclass
class FailurePattern:
    """What happened between two consecutive repair attempts."""
    recurring_codes: set[str]      # error codes that appeared in both attempts
    new_codes: set[str]            # error codes new in the current attempt
    resolved_codes: set[str]       # error codes from prev that are now gone
    prev_count: int
    curr_count: int

    @property
    def has_recurring(self) -> bool:
        return bool(self.recurring_codes)

    @property
    def has_new_errors(self) -> bool:
        return bool(self.new_codes)

    @property
    def scope_too_wide(self) -> bool:
        """Fix resolved some errors but introduced new ones."""
        return bool(self.resolved_codes) and bool(self.new_codes)

    @property
    def regressed(self) -> bool:
        """More errors now than before."""
        return self.curr_count > self.prev_count

    @property
    def partial_progress(self) -> bool:
        """Fewer errors but not all resolved."""
        return bool(self.resolved_codes) and not self.has_new_errors

    def summary(self) -> str:
        parts = []
        if self.has_recurring:
            codes = ", ".join(sorted(self.recurring_codes)[:3])
            parts.append(f"recurring errors: [{codes}]")
        if self.scope_too_wide:
            parts.append(
                f"fix resolved {len(self.resolved_codes)} error(s) "
                f"but introduced {len(self.new_codes)} new error(s)"
            )
        elif self.has_new_errors:
            codes = ", ".join(sorted(self.new_codes)[:3])
            parts.append(f"new errors introduced: [{codes}]")
        if self.regressed:
            parts.append(
                f"error count grew from {self.prev_count} to {self.curr_count}"
            )
        elif self.partial_progress:
            parts.append(
                f"partial progress: {len(self.resolved_codes)} error(s) resolved, "
                f"{self.curr_count} remaining"
            )
        return "; ".join(parts) if parts else "no change"

    @classmethod
    def compare(
        cls,
        prev_errors: "list[GateError]",
        curr_errors: "list[GateError]",
    ) -> "FailurePattern":
        def _key(e: "GateError") -> str:
            # Use code if available, else a normalised message prefix
            return e.code if e.code else e.message[:40].lower()

        prev_keys = {_key(e) for e in prev_errors}
        curr_keys = {_key(e) for e in curr_errors}

        return cls(
            recurring_codes=prev_keys & curr_keys,
            new_codes=curr_keys - prev_keys,
            resolved_codes=prev_keys - curr_keys,
            prev_count=len(prev_errors),
            curr_count=len(curr_errors),
        )


# ── Escalator ─────────────────────────────────────────────────────────────────

class RepairInstructionEscalator:
    """
    Generates repair instructions that escalate in directiveness based on
    attempt number and failure pattern analysis.
    """

    def build(
        self,
        attempt_number: int,
        gate: str,
        current_errors: "list[GateError]",
        prev_errors: "list[GateError] | None" = None,
        prev_reasoning: str = "",
    ) -> str:
        """
        Build a repair instruction for the next attempt.

        attempt_number  the attempt that just failed (1 = first failure)
        gate            the gate that failed
        current_errors  errors from the attempt that just failed
        prev_errors     errors from the attempt before that (None on first failure)
        prev_reasoning  the model's reasoning from the attempt that just failed
        """
        pattern: FailurePattern | None = None
        if prev_errors is not None:
            pattern = FailurePattern.compare(prev_errors, current_errors)

        if attempt_number == 1:
            return self._level_1(gate, current_errors, pattern)
        elif attempt_number == 2:
            return self._level_2(gate, current_errors, pattern, prev_reasoning)
        else:
            return self._level_3(gate, current_errors, prev_reasoning)

    # ── Instruction levels ────────────────────────────────────────────────────

    def _level_1(
        self,
        gate: str,
        errors: "list[GateError]",
        pattern: FailurePattern | None,
    ) -> str:
        """
        Level 1: Targeted surgical repair.
        First failure — most likely a straightforward misapplication.
        """
        lines = [
            f"Fix only the {gate} errors listed above.",
            "Do not change anything else.",
        ]

        if pattern and pattern.has_recurring:
            codes = ", ".join(sorted(pattern.recurring_codes)[:3])
            lines.append(
                f"\nNote: the error(s) [{codes}] have appeared before. "
                "Your previous fix did not address the root cause. "
                "Read the error message carefully before making any change."
            )

        if pattern and pattern.scope_too_wide:
            lines.append(
                f"\nNote: your previous repair resolved some errors "
                f"but introduced {len(pattern.new_codes)} new one(s). "
                "Apply the minimum change — do not restructure or refactor."
            )

        return "\n".join(lines)

    def _level_2(
        self,
        gate: str,
        errors: "list[GateError]",
        pattern: FailurePattern | None,
        prev_reasoning: str,
    ) -> str:
        """
        Level 2: Diagnostic repair with forced root-cause reasoning.
        Second failure — the model needs to reason explicitly before coding.
        """
        pattern_note = (
            f"Failure pattern: {pattern.summary()}"
            if pattern else "Failure pattern: unknown (first comparison)"
        )

        lines = [
            f"You have failed to fix this {gate} error twice.",
            "",
            pattern_note,
            "",
            "Before writing any code, your reasoning field MUST cover:",
            "  1. Why your previous fix failed (be specific, not general).",
            "  2. What the root cause of this error actually is.",
            "  3. What the correct fix is and why it will work.",
            "  4. What you will NOT change (to avoid introducing new errors).",
            "",
            "Only after this reasoning should you write the corrected implementation.",
        ]

        if pattern:
            if pattern.has_recurring:
                codes = ", ".join(sorted(pattern.recurring_codes)[:3])
                lines.append(
                    f"\nCritical: error(s) [{codes}] have now appeared in "
                    "multiple consecutive attempts. You are repeating the same "
                    "mistake. Your reasoning must identify why."
                )

            if pattern.regressed:
                lines.append(
                    f"\nWarning: your last repair made things worse — "
                    f"error count grew from {pattern.prev_count} to {pattern.curr_count}. "
                    "Do not make broad changes. Identify the single smallest fix."
                )

            if pattern.scope_too_wide:
                lines.append(
                    f"\nWarning: your last repair resolved "
                    f"{len(pattern.resolved_codes)} error(s) but introduced "
                    f"{len(pattern.new_codes)} new one(s). "
                    "The change scope was too wide. Touch only the lines that cause the listed errors."
                )

        if prev_reasoning.strip():
            truncated = prev_reasoning.strip()[:400]
            lines.append(
                f"\nYour previous reasoning for reference:\n"
                f"---\n{truncated}\n---\n"
                "Identify specifically where this reasoning was wrong."
            )

        return "\n".join(lines)

    def _level_3(
        self,
        gate: str,
        errors: "list[GateError]",
        prev_reasoning: str,
    ) -> str:
        """
        Level 3: Reset — abandon incremental repair, rewrite from scratch.
        Third or later failure — the model is structurally stuck.
        """
        error_summary = "; ".join(
            f"[{e.code or e.severity}] {e.message[:60]}"
            for e in errors[:3]
        )

        lines = [
            f"You have failed to fix this {gate} error three or more times.",
            "Incremental repair has not worked. Do not attempt another incremental fix.",
            "",
            "RESET STRATEGY:",
            "  1. In your reasoning field, identify the fundamental design flaw in",
            "     your implementation that causes this class of error.",
            "     Do not describe what the error says — explain why your code produces it.",
            "",
            "  2. Rewrite the affected section from scratch.",
            "     Your previous implementation is shown for reference only.",
            "     Do not copy it. Start from the spec constraints.",
            "",
            "  3. After writing the implementation, verify explicitly in your reasoning",
            "     that each acceptance criterion is satisfied.",
            "",
            f"Current errors to eliminate: {error_summary}",
            "",
            "Do not touch any code that is unrelated to the above errors.",
            "A passing implementation is better than a refactored one.",
        ]

        if prev_reasoning.strip():
            truncated = prev_reasoning.strip()[:300]
            lines.append(
                f"\nPrevious reasoning (treat as an anti-example):\n"
                f"---\n{truncated}\n---"
            )

        return "\n".join(lines)
