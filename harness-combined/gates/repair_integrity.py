"""Pure diff classifier that detects repair-gaming shapes (ticket 0040).

The build/repair loop tells the model to "fix the specific ``file:line``
locations". Nothing in the loop prevents a *degenerate* repair that turns a red
gate green by weakening the safety net instead of fixing the defect: deleting or
skipping failing tests, or adding an unexplained suppression pragma. This module
classifies a unified diff and reports those shapes so a repair round carrying any
of them can be failed and re-entered with a corrective instruction (FR-2).

Design mirrors :mod:`gates.spec_remediate`: pure functions, stdlib only
(``re``, ``dataclasses``), no filesystem or network I/O (NFR-1), regex-over-diff
rather than per-language AST (adequate for pragma/test-signature shapes, and
fast — well under 1s on a 5000-line diff, NFR-2). Reasons are free text; the
classifier never judges their adequacy (NFR-3) — presence of any trailing
explanatory text after a marker exempts it.

Three violation classes:

* **removed_tests** — a *net* removal of test-function definitions per file
  (removed defs minus added defs). Measuring the net delta means a *same-file*
  rename or move of a test (equal add and remove) is not flagged (solution
  Risks). A test relocated across files still nets a removal in the source file;
  the repair brief tells the model how to annotate a genuine cross-file move.

  Known limitation (the flip side of the rename tolerance above): a *swap* that
  deletes a real test and adds a trivial one in the same file — e.g. removing
  ``def test_important()`` (with its assertions) and adding ``def test_dummy():
  pass`` — nets to zero and is NOT flagged here. A name-set approach (removed def
  names not re-added) would catch the swap but would then flag every legitimate
  rename, which the approved design deliberately rejected. The swap is therefore
  left to the acknowledged backstops: the critic-brief Step 2.5 weakened-tests
  check (which compares the diff against solution.md's Test Plan) and the
  ``stop_full_gate`` turn-end suite. This count catches the *unbalanced* removal;
  the reviewer catches the *balanced* swap.
* **added_skips** — a skip / xfail / ignore marker introduced on an added line.
* **bare_suppressions** — a suppression pragma on an added line with no reason
  suffix. :data:`SUPPRESSION_MARKERS` is the single named marker source, reused
  by ``hooks/stop_full_gate.py`` (FR-4) so the list lives in exactly one place.

Deliberate tradeoff on the reason suffix (NFR-3 — "reasons are free-text; the
guard never judges adequacy"): a marker followed by *any* trailing text counts as
reasoned, so a targeted ``# noqa: E501`` / ``# type: ignore[assignment]`` passes
while the *blanket* forms ``# noqa`` / ``# type: ignore`` (which silence every
lint / type error on the line — the higher-risk gaming shape) are flagged. Judging
whether the trailing text is a "real" justification vs a mere rule code would be an
adequacy judgement NFR-3 explicitly forbids; that call stays with review (the
critic-brief Step 2.5 weakened-tests check and the human reviewer).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ── Marker / pattern tables ───────────────────────────────────────────────────

@dataclass(frozen=True)
class _Marker:
    """One suppression-marker rule.

    ``langs`` is ``None`` for language-agnostic markers, or a set of language
    names the marker is valid in (e.g. ``as any`` is TypeScript syntax, so
    scanning it in Go/Python prose would false-positive). ``needs_comment``
    requires the marker to sit at or after a comment introducer on the line, so
    a bare token appearing in a string or identifier is not treated as a pragma.
    """

    name: str
    pattern: re.Pattern[str]
    langs: frozenset[str] | None
    needs_comment: bool


#: The single source of the suppression-marker list (FR-1, reused by
#: stop_full_gate for FR-4). The regex matches only the marker token — the text
#: *after* ``match.end()`` is inspected for a reason suffix. Add a new suppression
#: syntax by extending this tuple. Markers are language-scoped and/or
#: comment-anchored to avoid flagging ordinary prose/string content that merely
#: contains the substring (e.g. "…as any…" in English, "nanosec" as an identifier).
SUPPRESSION_MARKERS: tuple[_Marker, ...] = (
    _Marker("noqa", re.compile(r"#\s*noqa"), None, False),
    _Marker("type-ignore", re.compile(r"#\s*type:\s*ignore"), None, False),
    _Marker("nosec", re.compile(r"\bnosec\b"), None, True),
    _Marker("nolint", re.compile(r"\bnolint\b"), None, True),
    _Marker(
        "eslint-disable",
        re.compile(r"eslint-disable(?:-next-line|-line)?"),
        frozenset({"javascript", "typescript"}),
        True,
    ),
    _Marker("ts-expect-error", re.compile(r"@ts-expect-error"), frozenset({"typescript"}), False),
    _Marker("ts-ignore", re.compile(r"@ts-ignore"), frozenset({"typescript", "javascript"}), False),
    _Marker("as-any", re.compile(r"\bas\s+any\b"), frozenset({"typescript"}), False),
    _Marker("allow", re.compile(r"#\[allow"), frozenset({"rust"}), False),
)

#: Comment introducers used to anchor ``needs_comment`` markers.
_COMMENT_INTRO = re.compile(r"#|//|/\*")

#: Leading separators between a marker and its reason: colon, em/en dash, hyphen,
#: opening bracket/paren, whitespace. Stripped before checking for reason text.
_REASON_LEAD = re.compile(r"^[\s:：—–\-\[(]+")
_WORD = re.compile(r"\w")

_EXT_TO_LANG: dict[str, str] = {
    "py": "python",
    "pyi": "python",
    "ts": "typescript",
    "tsx": "typescript",
    "js": "javascript",
    "jsx": "javascript",
    "mjs": "javascript",
    "cjs": "javascript",
    "go": "go",
    "rs": "rust",
}

#: Test-function *definition* signatures, per language. Matched on both added and
#: removed lines to compute the net per-file delta.
_TEST_DEF: dict[str, re.Pattern[str]] = {
    "python": re.compile(r"\bdef\s+test\w*\s*\("),
    "javascript": re.compile(r"^\s*(?:it|test)\s*\("),
    "typescript": re.compile(r"^\s*(?:it|test)\s*\("),
    "go": re.compile(r"\bfunc\s+Test\w*\s*\("),
    "rust": re.compile(r"#\[test\]"),
}

#: Skip / xfail / ignore markers, per language. Matched on added lines only.
_SKIP: dict[str, re.Pattern[str]] = {
    "python": re.compile(
        r"@(?:pytest\.mark|mark)\.(?:skip|xfail)\b"
        r"|pytest\.skip\s*\("
        r"|@unittest\.skip"
        r"|\.skipTest\s*\("
    ),
    "javascript": re.compile(r"\b(?:it|test|describe)\.(?:skip|todo)\b|\bx(?:it|describe)\s*\("),
    "typescript": re.compile(r"\b(?:it|test|describe)\.(?:skip|todo)\b|\bx(?:it|describe)\s*\("),
    "go": re.compile(r"\bt\.Skip(?:Now)?\s*\("),
    "rust": re.compile(r"#\[ignore\]"),
}


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Suppression:
    """A suppression marker found on an added diff line."""

    file: str
    marker: str
    excerpt: str
    explained: bool


@dataclass(frozen=True)
class RemovedTest:
    """A net removal of test-function definitions in one file."""

    file: str
    net_removed: int


@dataclass(frozen=True)
class AddedSkip:
    """A skip/xfail/ignore marker introduced on an added line."""

    file: str
    excerpt: str


@dataclass(frozen=True)
class DiffViolations:
    """Result of :func:`classify_diff`."""

    removed_tests: list[RemovedTest]
    added_skips: list[AddedSkip]
    bare_suppressions: list[Suppression]

    @property
    def has_violations(self) -> bool:
        return bool(self.removed_tests or self.added_skips or self.bare_suppressions)

    def corrective_brief(self) -> str:
        """A repair-round instruction naming what to restore (FR-2).

        Empty when there are no violations.
        """
        if not self.has_violations:
            return ""
        lines = ["Repair-integrity violation — this round weakened the safety net:"]
        for rt in self.removed_tests:
            lines.append(
                f"  - {rt.file}: {rt.net_removed} test function(s) removed net. "
                "Restore the test and fix the implementation instead. If this is a "
                "genuine rename/move, keep the add and remove balanced."
            )
        for sk in self.added_skips:
            lines.append(
                f"  - {sk.file}: added skip/xfail marker `{sk.excerpt}`. "
                "Un-skip the test and make it pass."
            )
        for su in self.bare_suppressions:
            lines.append(
                f"  - {su.file}: added bare `{su.marker}` suppression `{su.excerpt}`. "
                "Fix the underlying issue, or add a reason suffix if the suppression "
                "is genuinely justified."
            )
        return "\n".join(lines)


# ── Diff parsing ──────────────────────────────────────────────────────────────


def _strip_ab(path: str) -> str:
    path = path.strip()
    # Drop a trailing tab-separated timestamp some diff formats append.
    path = path.split("\t", 1)[0]
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path


def _lang_of(path: str, hints: dict[str, str] | None) -> str:
    if hints and path in hints:
        return hints[path]
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return _EXT_TO_LANG.get(ext, "")


def _iter_diff_lines(diff_text: str) -> list[tuple[str, str, str]]:
    """Return ``(file, kind, content)`` for every added/removed diff line.

    ``kind`` is ``"add"`` or ``"del"``; ``content`` is the line with its leading
    ``+``/``-`` stripped. The active file is taken from the ``+++ b/…`` header,
    falling back to ``--- a/…`` when the new side is ``/dev/null`` (a deletion).
    """
    rows: list[tuple[str, str, str]] = []
    old_path = ""
    current = ""
    for line in diff_text.splitlines():
        if line.startswith("--- "):
            old_path = _strip_ab(line[4:])
            continue
        if line.startswith("+++ "):
            new_path = _strip_ab(line[4:])
            current = old_path if new_path in ("", "/dev/null") else new_path
            continue
        if line.startswith(("diff --git", "@@", "index ", "new file", "deleted file", "rename ", "similarity ")):
            continue
        if line.startswith("+"):
            rows.append((current, "add", line[1:]))
        elif line.startswith("-"):
            rows.append((current, "del", line[1:]))
    return rows


# ── Detection helpers ─────────────────────────────────────────────────────────


def _reason_after(rest: str) -> bool:
    """True when text following a marker carries any explanatory content."""
    return bool(_WORD.search(_REASON_LEAD.sub("", rest)))


def _in_comment(content: str, pos: int) -> bool:
    """True when a comment introducer appears at or before ``pos`` on the line."""
    intro = _COMMENT_INTRO.search(content)
    return intro is not None and intro.start() <= pos


def scan_suppressions(content: str, lang: str = "") -> list[tuple[str, bool]]:
    """Every suppression marker in ``content`` as ``(name, explained)``.

    ``lang`` scopes language-specific markers (``as any`` etc.); the empty string
    scans only the language-agnostic markers. ``needs_comment`` markers must sit
    at/after a comment introducer so a bare substring in a string or identifier
    is not treated as a pragma. Multiple distinct markers on one line are all
    reported (a line's first occurrence of each marker name).
    """
    found: list[tuple[str, bool]] = []
    for marker in SUPPRESSION_MARKERS:
        if marker.langs is not None and lang not in marker.langs:
            continue
        match = marker.pattern.search(content)
        if match is None:
            continue
        if marker.needs_comment and not _in_comment(content, match.start()):
            continue
        found.append((marker.name, _reason_after(content[match.end() :])))
    return found


def added_suppressions(diff_text: str, language_hints: dict[str, str] | None = None) -> list[Suppression]:
    """All suppression markers introduced on added lines (net-new), with the
    ``explained`` flag set. Reused by ``stop_full_gate`` (FR-4)."""
    out: list[Suppression] = []
    for file, kind, content in _iter_diff_lines(diff_text):
        if kind != "add":
            continue
        for name, explained in scan_suppressions(content, _lang_of(file, language_hints)):
            out.append(
                Suppression(file=file, marker=name, excerpt=content.strip()[:120], explained=explained)
            )
    return out


def unexplained_suppression_count(diff_text: str) -> int:
    """Count of net-new suppression markers on added lines with no reason (FR-4)."""
    return sum(1 for s in added_suppressions(diff_text) if not s.explained)


# ── Public entry point ────────────────────────────────────────────────────────


def classify_diff(diff_text: str, language_hints: dict[str, str] | None = None) -> DiffViolations:
    """Classify a unified diff into repair-integrity violations (FR-1).

    ``language_hints`` optionally maps a file path to a language name, overriding
    extension inference (useful for extension-less test files).
    """
    added_defs: dict[str, int] = {}
    removed_defs: dict[str, int] = {}
    added_skips: list[AddedSkip] = []
    bare_suppressions: list[Suppression] = []

    for file, kind, content in _iter_diff_lines(diff_text):
        lang = _lang_of(file, language_hints)

        test_def = _TEST_DEF.get(lang)
        if test_def is not None and test_def.search(content):
            bucket = added_defs if kind == "add" else removed_defs
            bucket[file] = bucket.get(file, 0) + 1

        if kind != "add":
            continue

        skip = _SKIP.get(lang)
        if skip is not None and skip.search(content):
            added_skips.append(AddedSkip(file=file, excerpt=content.strip()[:120]))

        for name, explained in scan_suppressions(content, lang):
            if not explained:
                bare_suppressions.append(
                    Suppression(file=file, marker=name, excerpt=content.strip()[:120], explained=False)
                )

    removed_tests: list[RemovedTest] = []
    for file in sorted(set(added_defs) | set(removed_defs)):
        net = removed_defs.get(file, 0) - added_defs.get(file, 0)
        if net > 0:
            removed_tests.append(RemovedTest(file=file, net_removed=net))

    return DiffViolations(
        removed_tests=removed_tests,
        added_skips=added_skips,
        bare_suppressions=bare_suppressions,
    )
