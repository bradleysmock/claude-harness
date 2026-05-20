"""
Identifier consistency check.

Verifies that identifiers pinned by the hardener (Refinement 2) actually
appear in the generated implementation. Catches the reference drift
failure mode from "From the Inside" Section 4.2: each local naming
choice looks reasonable, but the global naming diverges from the spec.

Why this exists as a separate check
───────────────────────────────────
  - Gates pass because the code compiles, types check, and tests run.
  - The verifier may not catch it: a class named differently from the spec
    can satisfy each finding-by-finding compliance check ("a rate limiter
    class exists," "it implements the required methods") while violating
    the explicit pinning.
  - The alignment gate may not catch it: the implementation does the right
    thing, just with the wrong name. Intent is aligned even if names drift.

This check fires only when the hardener actually pinned identifiers.
If no pinning was done, no-op.

Multi-language strategy
───────────────────────
Python: AST walk extracts identifiers from ClassDef, FunctionDef, Import,
        ImportFrom, Name, and Attribute nodes.
Other:  Regex-based identifier scan with token patterns appropriate to
        the language. Less precise but works for any language with
        identifier-style naming conventions.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import GeneratedArtifact
    from .hardener import PinnedIdentifier

log = logging.getLogger("harness.consistency")


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class ConsistencyViolation:
    pinned_role: str            # "rate limiter class"
    pinned_name: str            # "RedisRateLimiter"
    found_alternatives: list[str] = field(default_factory=list)
    location_hint: str = ""     # context: "implementation" | "tests" | "both"

    def as_repair_line(self) -> str:
        line = f"  ✗ Pinned '{self.pinned_name}' (role: {self.pinned_role}) not found in {self.location_hint}"
        if self.found_alternatives:
            alts = ", ".join(self.found_alternatives[:3])
            line += f"\n    Similar names found: {alts}"
            line += f"\n    Suggestion: rename '{self.found_alternatives[0]}' to '{self.pinned_name}'"
        return line


@dataclass
class ConsistencyReport:
    violations: list[ConsistencyViolation] = field(default_factory=list)
    checked_count: int = 0

    def passed(self) -> bool:
        return not self.violations

    def formatted(self) -> str:
        if self.passed():
            return f"\nConsistency: PASSED — {self.checked_count} pinned identifier(s) all present"
        lines = [
            f"\nConsistency: FAILED — {len(self.violations)} violation(s) of {self.checked_count} checked"
        ]
        for v in self.violations:
            lines.append(v.as_repair_line())
        return "\n".join(lines)


# ── Identifier extractors ─────────────────────────────────────────────────────

class _PythonIdentifierExtractor:
    """Walks Python AST to extract every identifier that appears in the source."""

    @staticmethod
    def extract(source: str) -> set[str]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            # Fall back to regex if AST parse fails — code may be syntactically
            # invalid mid-generation. Regex still gets us most names.
            return _RegexIdentifierExtractor.extract(source)

        names: set[str] = set()

        for node in ast.walk(tree):
            # Class and function definitions
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(node.name)

            # Imports: from X import Y as Z  → Y, Z
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    names.add(alias.name)
                    if alias.asname:
                        names.add(alias.asname)

            # Imports: import X.Y as Z  → X, Y, Z
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for part in alias.name.split("."):
                        names.add(part)
                    if alias.asname:
                        names.add(alias.asname)

            # Name references
            elif isinstance(node, ast.Name):
                names.add(node.id)

            # Attribute access: obj.attr  → attr
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)

        return names


class _RegexIdentifierExtractor:
    """Language-agnostic fallback. Extracts identifier-shaped tokens."""

    # Matches typical identifier patterns: CamelCase, snake_case, camelCase
    _PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")

    # Tokens that aren't really identifiers
    _STOPWORDS = frozenset({
        "if", "else", "for", "while", "return", "import", "from", "as",
        "def", "class", "fn", "func", "var", "let", "const", "function",
        "true", "false", "True", "False", "null", "None", "nil",
        "self", "this", "and", "or", "not", "in", "is", "with",
        "try", "except", "catch", "throw", "raise", "finally",
        "public", "private", "protected", "static", "void",
        "int", "str", "bool", "float", "list", "dict", "tuple",
        "string", "number", "boolean", "any", "object",
    })

    @classmethod
    def extract(cls, source: str) -> set[str]:
        return {
            tok for tok in cls._PATTERN.findall(source)
            if tok not in cls._STOPWORDS
        }


def _extract_identifiers(source: str, language: str) -> set[str]:
    if language == "python":
        return _PythonIdentifierExtractor.extract(source)
    return _RegexIdentifierExtractor.extract(source)


# ── The check ────────────────────────────────────────────────────────────────

class IdentifierConsistencyCheck:
    """
    Verifies that every pinned identifier from the hardener appears in the
    generated artifact. Returns a structured report of any violations.

    Cheap: pure AST walk + set membership tests. No LLM call.
    """

    def __init__(self, language: str = "python"):
        self._language = language

    def check(
        self,
        artifact: "GeneratedArtifact",
        pinned_identifiers: "list[PinnedIdentifier]",
    ) -> ConsistencyReport:
        if not pinned_identifiers:
            return ConsistencyReport(checked_count=0)

        impl_names = _extract_identifiers(artifact.implementation, self._language)
        test_names = _extract_identifiers(artifact.tests, self._language)
        all_names = impl_names | test_names

        violations: list[ConsistencyViolation] = []

        for pin in pinned_identifiers:
            if pin.name in all_names:
                continue  # found, no violation

            # Find similar names — substring matches, case-insensitive
            pin_lower = pin.name.lower()
            alternatives = sorted(
                [n for n in all_names if self._is_similar(pin_lower, n.lower())],
                key=lambda x: -self._similarity(pin_lower, x.lower()),
            )

            location = "implementation"
            if pin.name in test_names and pin.name not in impl_names:
                location = "implementation (present in tests only)"
            elif not impl_names and not test_names:
                location = "implementation (no identifiers extracted)"

            violations.append(ConsistencyViolation(
                pinned_role=pin.role,
                pinned_name=pin.name,
                found_alternatives=alternatives[:5],
                location_hint=location,
            ))

        return ConsistencyReport(
            violations=violations,
            checked_count=len(pinned_identifiers),
        )

    # ── Private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _is_similar(a: str, b: str) -> bool:
        """Two identifiers are similar if one contains the other, or they
        share a 3+ character substring root."""
        if len(a) < 3 or len(b) < 3:
            return False
        # Direct substring containment
        if a in b or b in a:
            return True
        # Shared root (first 4 chars or stripped underscores match)
        a_clean = a.replace("_", "")
        b_clean = b.replace("_", "")
        if len(a_clean) >= 4 and len(b_clean) >= 4:
            if a_clean[:4] == b_clean[:4]:
                return True
        return False

    @staticmethod
    def _similarity(a: str, b: str) -> int:
        """Cheap similarity score for ranking alternatives."""
        score = 0
        if a in b or b in a:
            score += 10
        # Count shared character bigrams
        a_grams = {a[i:i+2] for i in range(len(a) - 1)}
        b_grams = {b[i:i+2] for i in range(len(b) - 1)}
        score += len(a_grams & b_grams)
        return score
