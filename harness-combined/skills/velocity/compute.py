#!/usr/bin/env python3
"""Deterministic date-arithmetic helper for the ``/velocity`` cycle-time report.

CLI contract: read a JSON array of ``{"id", "start", "end"}`` objects from
**stdin** and write a JSON report object to **stdout**. Passing ticket data over
stdin (never a shell argument) keeps attacker-influenceable dates and slugs off
the command line. All date math uses :class:`datetime.date` + ``isocalendar()``
so the same input always yields the same output — no LLM inference is involved.

The module also exposes importable pure helpers — extraction regexes, path
containment, cycle-day / ISO-week computation, weekly aggregation, and
:func:`scan_completed` — that the ``commands/velocity.md`` skill mirrors and the
test suite exercises directly.

Output schema (stdout)::

    {
      "tickets": [{"id", "start", "end", "days", "iso_year", "iso_week"}],
      "weekly":  [{"iso_year", "iso_week", "count", "avg_days", "min_days", "max_days"}],
      "overall_avg": float,
      "skipped": int
    }

Exit code 0 on success (partial results if some entries were skipped); exit code
1 on a fatal input error (stdin is not a JSON array), with a structured error
object on stderr and nothing on stdout.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

# Strict YYYY-MM-DD only; any other shape is treated as malformed.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_START_RE = re.compile(r"\*\*Date\*\*:\s*(\d{4}-\d{2}-\d{2})")
_END_RE = re.compile(r"updated:\s*(\d{4}-\d{2}-\d{2})")
_TITLE_RE = re.compile(r"title:\s*(.+)")


def parse_date(value: object) -> date | None:
    """Return a :class:`date` for a strict ``YYYY-MM-DD`` string, else ``None``."""
    if not isinstance(value, str) or not _DATE_RE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def cycle_days(start: object, end: object) -> int:
    """Integer day difference ``(end - start)``.

    ``start`` / ``end`` may be a :class:`date` or a ``YYYY-MM-DD`` string. Raises
    :class:`ValueError` if either is not a valid date — callers pre-filter, so a
    raise here signals a programming error, not user data.
    """
    start_d = start if isinstance(start, date) else parse_date(start)
    end_d = end if isinstance(end, date) else parse_date(end)
    if start_d is None or end_d is None:
        raise ValueError("cycle_days requires valid YYYY-MM-DD dates")
    return (end_d - start_d).days


def iso_week(value: object) -> tuple[int, int]:
    """``(iso_year, iso_week)`` for a date, via :meth:`date.isocalendar`.

    ISO 8601 semantics: ``2021-01-01`` is week 53 of 2020; ``2021-01-04`` is week
    1 of 2021.
    """
    value_d = value if isinstance(value, date) else parse_date(value)
    if value_d is None:
        raise ValueError("iso_week requires a valid YYYY-MM-DD date")
    cal = value_d.isocalendar()
    return (cal[0], cal[1])


def extract_start(problem_text: str | None) -> str | None:
    """The ``**Date**`` creation date from a ``problem.md`` body, or ``None``."""
    match = _START_RE.search(problem_text or "")
    return match.group(1) if match else None


def extract_end(status_text: str | None) -> str | None:
    """The LAST ``updated:`` date from a ``status.md`` body, or ``None``.

    A re-delivered ticket carries several ``updated`` lines; the latest is the
    true completion date.
    """
    matches = _END_RE.findall(status_text or "")
    return matches[-1] if matches else None


def extract_title(status_text: str | None) -> str | None:
    """The ``title:`` value from a ``status.md`` body, or ``None``."""
    match = _TITLE_RE.search(status_text or "")
    return match.group(1).strip() if match else None


def is_contained(candidate: object, root: object) -> bool:
    """True only when ``candidate`` resolves to ``root`` or a descendant of it.

    Both paths are resolved via :meth:`Path.resolve` before comparison, so a
    ``../../etc`` slug or a symlink that escapes the harness root is rejected.
    """
    try:
        root_resolved = Path(str(root)).resolve()
        candidate_resolved = Path(str(candidate)).resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    return candidate_resolved == root_resolved or root_resolved in candidate_resolved.parents


def scan_completed(root: object) -> tuple[list[dict[str, str]], list[tuple[str, str]]]:
    """Scan ``<root>/.tickets/completed/*/`` into ticket entries + skip notes.

    Returns ``(entries, skipped)`` where each entry is
    ``{"id", "title", "start", "end"}`` and each skip note is
    ``(ticket_name, reason)``. Paths that escape ``root`` (via a symlink or a
    crafted slug) are skipped; tickets missing a parseable ``**Date**`` or
    ``updated`` field are skipped and noted. This mirrors, in tested Python, the
    scan the ``/velocity`` skill documents.
    """
    root_path = Path(str(root)).resolve()
    completed = root_path / ".tickets" / "completed"
    entries: list[dict[str, str]] = []
    skipped: list[tuple[str, str]] = []
    if not completed.is_dir():
        return entries, skipped
    for ticket_dir in sorted(completed.glob("*")):
        if not ticket_dir.is_dir():
            continue
        if not is_contained(ticket_dir, root_path):
            skipped.append((ticket_dir.name, "path escapes harness root"))
            continue
        problem = ticket_dir / "problem.md"
        status = ticket_dir / "status.md"
        problem_text = problem.read_text() if problem.is_file() else ""
        status_text = status.read_text() if status.is_file() else ""
        start = extract_start(problem_text)
        end = extract_end(status_text)
        if start is None or end is None:
            skipped.append((ticket_dir.name, "missing or malformed date field"))
            continue
        entries.append(
            {
                "id": ticket_dir.name.split("-", 1)[0],
                "title": extract_title(status_text) or ticket_dir.name,
                "start": start,
                "end": end,
            }
        )
    return entries, skipped


def _aggregate_weekly(tickets: list[dict[str, object]]) -> list[dict[str, object]]:
    """Group per-ticket rows by ``(iso_year, iso_week)`` into summary rows."""
    groups: dict[tuple[int, int], list[int]] = {}
    for ticket in tickets:
        key = (int(ticket["iso_year"]), int(ticket["iso_week"]))  # type: ignore[call-overload]  # ints set by compute(); cast narrows dict[str, object]
        groups.setdefault(key, []).append(int(ticket["days"]))  # type: ignore[call-overload]  # int set by compute(); cast narrows dict[str, object]
    rows: list[dict[str, object]] = []
    for (iso_year, iso_wk), days_list in sorted(groups.items()):
        rows.append(
            {
                "iso_year": iso_year,
                "iso_week": iso_wk,
                "count": len(days_list),
                "avg_days": round(sum(days_list) / len(days_list), 2),
                "min_days": min(days_list),
                "max_days": max(days_list),
            }
        )
    return rows


def compute(raw_entries: object) -> dict[str, object]:
    """Turn a list of ``{"id","start","end"}`` entries into the report object.

    Entries that are not dicts, carry a non-``YYYY-MM-DD`` date, or have a
    negative cycle time (``end < start``) are skipped and counted in
    ``skipped`` — a partial report is still returned. Never raises on user data
    and never divides by zero.
    """
    tickets: list[dict[str, object]] = []
    skipped = 0
    for entry in raw_entries if isinstance(raw_entries, list) else []:
        if not isinstance(entry, dict):
            skipped += 1
            continue
        start = parse_date(entry.get("start"))
        end = parse_date(entry.get("end"))
        if start is None or end is None:
            skipped += 1
            continue
        days = (end - start).days
        if days < 0:
            skipped += 1
            continue
        iso_year, iso_wk = iso_week(end)
        tickets.append(
            {
                "id": entry.get("id"),
                "start": entry.get("start"),
                "end": entry.get("end"),
                "days": days,
                "iso_year": iso_year,
                "iso_week": iso_wk,
            }
        )
    overall_avg = (
        round(sum(int(t["days"]) for t in tickets) / len(tickets), 2) if tickets else 0.0  # type: ignore[call-overload]  # days set by compute(); cast narrows dict[str, object]
    )
    return {
        "tickets": tickets,
        "weekly": _aggregate_weekly(tickets),
        "overall_avg": overall_avg,
        "skipped": skipped,
    }


def _main(stdin_text: str) -> int:
    if sys.version_info < (3, 7):  # date.fromisoformat('YYYY-MM-DD') needs 3.7+
        sys.stderr.write(json.dumps({"error": "Python 3.7+ required"}) + "\n")
        return 1
    try:
        data = json.loads(stdin_text)
    except json.JSONDecodeError as exc:
        sys.stderr.write(
            json.dumps({"error": "invalid JSON input", "detail": str(exc)}) + "\n"
        )
        return 1
    if not isinstance(data, list):
        sys.stderr.write(json.dumps({"error": "input must be a JSON array"}) + "\n")
        return 1
    sys.stdout.write(json.dumps(compute(data)))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.stdin.read()))
