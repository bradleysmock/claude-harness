#!/usr/bin/env python3
"""Fail-closed schema validator for ``.tickets/_standards.md``.

This is a **CLI module**: ``main()`` writes its validation report to ``stderr``
(that report is the tool's contract, not application logging), and the pipeline
command prose invokes it before any generative phase:

    python3 "${CLAUDE_PLUGIN_ROOT}/validators/standards_validator.py" \
        .tickets/_standards.md

On failure it exits ``1`` with a per-section error list on ``stderr``; on success
it exits ``0`` with no output, so stub engineering standards can never silently
flow into a ``/problem`` or ``/build`` run.

The pure ``validate(path, config)`` seam is the unit-test entry point — it raises
``StandardsValidationError`` (carrying structured fields) instead of exiting, so
tests can assert on the failure shape directly.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Required sections when no config file is present. Substring-matched,
# case-insensitively, against Markdown headings at any level.
DEFAULT_REQUIRED_SECTIONS: list[str] = ["language", "test strategy"]

# Default location of the operator-owned override, relative to the project root.
CONFIG_PATH = Path(".harness/validators/standards_config.toml")

# Exact stub tokens. A body line is a stub line if its lowercase form contains
# any of these. Plain substring matching (no regex) keeps this ReDoS-free.
# Update when the /init `_standards.md` stub changes.
STUB_STRINGS: frozenset[str] = frozenset(
    {"todo", "<fill in>", "placeholder", "tbd", "fixme"}
)

# Per-line stub patterns. A list for future extensibility; today it holds the
# single `/init` example-bullet format ("- (e.g.) ..."). Applied per line, so
# there is no full-body backtracking and no ReDoS exposure.
# Update when the /init `_standards.md` stub changes.
STUB_LINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*-\s+\(e\.g\.\)"),
)

# ATX heading at any level h1–h6 (up to three leading spaces per CommonMark).
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(?P<text>.*\S)\s*$")

# Timing safeguard: cap each section body before running any pattern check.
MAX_SECTION_BYTES = 64 * 1024


class StandardsValidationError(Exception):
    """Raised by :func:`validate` when ``_standards.md`` fails the schema check.

    Structured fields let callers react without parsing the message:

    * ``file_error`` — set when the file is missing/unreadable (then no section
      fields are populated); ``None`` on a section-level failure.
    * ``missing_sections`` — required section names with no matching heading.
    * ``stub_sections`` — ``[{"section": name, "reason": "stub"}, ...]`` for
      headings present but populated only with stub/placeholder content.
    """

    def __init__(
        self,
        *,
        file_error: str | None = None,
        missing_sections: list[str] | None = None,
        stub_sections: list[dict[str, str]] | None = None,
    ) -> None:
        self.file_error = file_error
        self.missing_sections = missing_sections or []
        self.stub_sections = stub_sections or []
        super().__init__(self._summary())

    def _summary(self) -> str:
        if self.file_error is not None:
            return f"_standards.md: {self.file_error}"
        parts: list[str] = []
        if self.missing_sections:
            parts.append("missing: " + ", ".join(self.missing_sections))
        if self.stub_sections:
            parts.append(
                "stubbed: " + ", ".join(s["section"] for s in self.stub_sections)
            )
        return "_standards.md failed validation (" + "; ".join(parts) + ")"


def load_required_sections(config_path: str | Path | None = None) -> list[str]:
    """Return the required-section list from the operator config, or the default.

    A missing config file is not an error — the built-in
    :data:`DEFAULT_REQUIRED_SECTIONS` is returned. An unreadable or
    syntactically invalid config file, or a malformed/empty
    ``required_sections`` value, also falls back to the default.
    """
    # Imported lazily inside the function: tomllib is stdlib (3.11+), but the
    # gate's ruff isort config resolves an older target and misgroups it at the
    # module top. It is only needed when a config file is actually present.
    import tomllib

    path = Path(config_path) if config_path is not None else CONFIG_PATH
    if not path.exists():
        return list(DEFAULT_REQUIRED_SECTIONS)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError):
        # A malformed (bad TOML or non-UTF-8) or unreadable operator config falls
        # back to the default rather than crashing the pipeline guard.
        return list(DEFAULT_REQUIRED_SECTIONS)
    sections = data.get("required_sections")
    if (
        isinstance(sections, list)
        and sections
        and all(isinstance(s, str) and s.strip() for s in sections)
    ):
        return [s.strip() for s in sections]
    return list(DEFAULT_REQUIRED_SECTIONS)


def _resolve_contained(path: str | Path, root: Path) -> Path:
    """Resolve ``path`` and verify it stays within ``root`` (McGraw containment)."""
    candidate = Path(path)
    resolved = (
        candidate.resolve()
        if candidate.is_absolute()
        else (root / candidate).resolve()
    )
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(f"path escapes project root: {path!r}") from None
    return resolved


def _parse_sections(text: str) -> list[tuple[str, list[str]]]:
    """Split Markdown into (heading_text, body_lines) pairs.

    Content before the first heading (preamble) is discarded. A section's body
    runs from just after its heading to the next heading of any level.
    """
    sections: list[tuple[str, list[str]]] = []
    heading: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            if heading is not None:
                sections.append((heading, body))
            heading = match.group("text")
            body = []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections.append((heading, body))
    return sections


def _find_section_body(
    sections: list[tuple[str, list[str]]], name: str
) -> list[str] | None:
    """Return the body of the first heading containing ``name`` (case-insensitive)."""
    key = name.lower()
    for heading, body in sections:
        if key in heading.lower():
            return body
    return None


def _is_stub_line(line: str) -> bool:
    lowered = line.lower()
    if any(token in lowered for token in STUB_STRINGS):
        return True
    return any(pattern.search(line) for pattern in STUB_LINE_PATTERNS)


def _is_stub_body(body: list[str]) -> bool:
    """A body is a stub iff it has no non-blank line, or every one is a stub line."""
    capped = "\n".join(body)[:MAX_SECTION_BYTES].split("\n")
    non_blank = [line for line in capped if line.strip()]
    if not non_blank:
        return True
    return all(_is_stub_line(line) for line in non_blank)


def validate(
    path: str | Path,
    config: list[str],
    *,
    root: Path | None = None,
) -> None:
    """Validate ``_standards.md`` at ``path`` against required sections ``config``.

    Returns ``None`` on success. Raises :class:`StandardsValidationError` when the
    file is missing, a required section heading is absent, or a required section
    contains only stub/placeholder content. ``root`` defaults to the current
    working directory and bounds path containment; tests pass a temp root.
    """
    base = (root or Path.cwd()).resolve()
    target = _resolve_contained(path, base)

    if not target.is_file():
        raise StandardsValidationError(file_error=f"not found: {path}")

    sections = _parse_sections(target.read_text(encoding="utf-8"))
    missing: list[str] = []
    stubbed: list[dict[str, str]] = []
    for name in config:
        body = _find_section_body(sections, name)
        if body is None:
            missing.append(name)
        elif _is_stub_body(body):
            stubbed.append({"section": name, "reason": "stub"})

    if missing or stubbed:
        raise StandardsValidationError(missing_sections=missing, stub_sections=stubbed)
    return None


def _format_report(exc: StandardsValidationError) -> str:
    """Render a StandardsValidationError as a per-section stderr report."""
    lines = ["_standards.md validation failed:"]
    if exc.file_error is not None:
        lines.append(f"  - file: {exc.file_error}")
    for name in exc.missing_sections:
        lines.append(f"  - section '{name}': missing")
    for entry in exc.stub_sections:
        lines.append(f"  - section '{entry['section']}': stub content")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 on pass, 1 on validation failure, 2 on misuse."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        sys.stderr.write(
            "usage: standards_validator.py <path-to-_standards.md>\n"
        )
        return 2
    config = load_required_sections()
    try:
        validate(args[0], config)
    except StandardsValidationError as exc:
        sys.stderr.write(_format_report(exc))
        return 1
    except (OSError, ValueError) as exc:
        # Unreadable file or a path that escaped the project root: halt cleanly
        # with a one-line diagnostic instead of leaking a traceback.
        sys.stderr.write(f"_standards.md validation could not run: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
