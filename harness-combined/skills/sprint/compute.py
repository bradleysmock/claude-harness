#!/usr/bin/env python3
"""Deterministic sprint-planning core for the ``/sprint`` command.

CLI contract: read a JSON array of ticket records from **stdin** and write a
JSON plan object to **stdout**. Passing ticket data over stdin (never a shell
argument) keeps attacker-influenceable titles and slugs off the command line —
the same posture as ``skills/velocity/compute.py``. All ordering and date math
is pure Python (Kahn's topological sort, greedy earliest-fit bin-packing,
:class:`datetime.date` arithmetic) so the same input always yields the same
plan — no LLM inference is involved.

Input schema (stdin) — a JSON array of::

    {
      "number": "0035",            # 4-digit ticket id (string)
      "title":  "Sprint Planning", # display title
      "effort": "medium",          # small|medium|large|null (null -> medium + warning)
      "status": "solution",        # display status
      "depends_on": ["0013"],      # list OR "0013, 0014" string of ticket ids
      "completed": false           # true for .tickets/completed/* (pre-satisfied dep)
    }

Output schema (stdout)::

    {
      "sprints": [{"n", "label", "tickets": [{"number","title","effort",
                   "effort_pts","status"}], "capacity_used", "capacity_total"}],
      "overflow": [{"number", "title", "reason"}],
      "warnings": [str]
    }

Exit code 0 on success. Exit code 1 on a fatal input error (stdin is not a JSON
array) **or** a circular ``depends_on`` chain — in the cycle case a structured
error naming the cycle members is written to stderr and nothing to stdout (no
partial plan). Errors never leak a stack trace or internal path.

CLI flags::

    --sprint-capacity N   effort points per sprint      (default 6)
    --max-sprints N       hard cap on planned sprints    (default 8)
    --as-of YYYY-MM-DD    anchor date for labels         (default: required)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta

# Strict formats — anything else is treated as malformed.
_TICKET_RE = re.compile(r"^\d{4}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

EFFORT_POINTS = {"small": 1, "medium": 2, "large": 3}
DEFAULT_EFFORT = "medium"
DEFAULT_EFFORT_PTS = EFFORT_POINTS[DEFAULT_EFFORT]

DEFAULT_CAPACITY = 6
DEFAULT_MAX_SPRINTS = 8


class CycleError(Exception):
    """Raised when the open-ticket ``depends_on`` graph contains a cycle."""

    def __init__(self, members: list[str]) -> None:
        self.members = members
        super().__init__("circular dependency among tickets: " + ", ".join(members))


def parse_date(value: object) -> date | None:
    """Return a :class:`date` for a strict ``YYYY-MM-DD`` string, else ``None``."""
    if not isinstance(value, str) or not _DATE_RE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def sprint1_monday(as_of: date) -> date:
    """Monday of the calendar week **following** ``as_of``.

    ``as_of.weekday()`` is 0 for Monday … 6 for Sunday, so
    ``as_of - weekday`` is the Monday of ``as_of``'s own week and ``+ 7`` steps
    to the next week's Monday. Sprint 1 always starts on a Monday strictly after
    ``as_of``.
    """
    monday_this_week = as_of - timedelta(days=as_of.weekday())
    return monday_this_week + timedelta(days=7)


def sprint_start(as_of: date, n: int) -> date:
    """Start date (a Monday) of sprint ``n`` (1-based). Sprint N is N-1 weeks
    after sprint 1."""
    return sprint1_monday(as_of) + timedelta(days=7 * (n - 1))


def sprint_label(as_of: date, n: int) -> str:
    """``Sprint N — Week of YYYY-MM-DD`` (em-dash, matching harness output)."""
    return f"Sprint {n} — Week of {sprint_start(as_of, n).isoformat()}"


def effort_points(effort: object) -> tuple[int, bool]:
    """``(points, defaulted)`` for an effort label.

    An empty/absent effort, or an unrecognised label, maps to
    ``medium`` (:data:`DEFAULT_EFFORT_PTS`) and flags ``defaulted=True`` so the
    caller can surface a visible warning.
    """
    if effort is None:
        return DEFAULT_EFFORT_PTS, True
    key = str(effort).strip().lower()
    if key in EFFORT_POINTS:
        return EFFORT_POINTS[key], False
    return DEFAULT_EFFORT_PTS, True


def normalize_deps(value: object) -> list[str]:
    """Flatten a ``depends_on`` value into a list of stripped, non-empty tokens.

    Accepts either a list (``["0001","0002"]``) or a comma-separated string
    (``"0001, 0002"``); every element is additionally comma-split so a list
    element like ``"0001, 0002"`` is handled too. Leading/trailing whitespace is
    stripped from each token, so ``"0001, 0002"`` yields ``["0001", "0002"]``
    (never ``" 0002"``).
    """
    if value is None:
        return []
    if isinstance(value, str):
        raw_parts = value.split(",")
    elif isinstance(value, list):
        raw_parts = []
        for item in value:
            raw_parts.extend(str(item).split(","))
    else:
        return []
    return [part.strip() for part in raw_parts if part.strip()]


def sanitize_title(value: object) -> str:
    """Neutralise a ticket title before it crosses into a Markdown table cell.

    ``title`` is free text lifted from ``status.md``; a literal ``|`` would break
    the table row and a newline would split the cell. Pipes are backslash-escaped
    (rendered as a literal ``|``) and every run of whitespace — including embedded
    newlines/tabs — is collapsed to a single space. Symmetric with the
    ``^[0-9]{4}$`` validation the solution applies to ``depends-on`` tokens to
    prevent Markdown injection.
    """
    text = " ".join(str(value).split())
    return text.replace("|", "\\|")


def _topological_order(
    plannable: dict[str, dict[str, object]],
    edges: dict[str, set[str]],
) -> list[str]:
    """Kahn's algorithm over ``plannable`` ticket numbers.

    ``edges[a]`` is the set of tickets that depend on ``a`` (i.e. ``a`` must be
    scheduled first). Ready nodes are drained in ascending ticket-number order
    for a deterministic result. Raises :class:`CycleError` naming the members
    still carrying dependencies if the graph does not fully drain.
    """
    indegree = {num: 0 for num in plannable}
    for dependents in edges.values():
        for dependent in dependents:
            indegree[dependent] += 1
    ready = sorted(num for num, deg in indegree.items() if deg == 0)
    order: list[str] = []
    while ready:
        num = ready.pop(0)
        order.append(num)
        for dependent in sorted(edges.get(num, ())):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
        ready.sort()
    if len(order) != len(plannable):
        cycle_members = sorted(num for num, deg in indegree.items() if deg > 0)
        raise CycleError(cycle_members)
    return order


def plan(
    raw_entries: object,
    *,
    capacity: int = DEFAULT_CAPACITY,
    max_sprints: int = DEFAULT_MAX_SPRINTS,
    as_of: date,
) -> dict[str, object]:
    """Turn ticket records into a sprint plan object (see module docstring).

    Never raises on user data except :class:`CycleError` for a genuine circular
    dependency (FR-6, which must abort rather than emit a partial plan).
    """
    entries = raw_entries if isinstance(raw_entries, list) else []
    warnings: list[str] = []

    if capacity < 1:
        warnings.append(
            f"--sprint-capacity {capacity} is invalid; using default {DEFAULT_CAPACITY}"
        )
        capacity = DEFAULT_CAPACITY
    if max_sprints < 1:
        warnings.append(
            f"--max-sprints {max_sprints} is invalid; using default {DEFAULT_MAX_SPRINTS}"
        )
        max_sprints = DEFAULT_MAX_SPRINTS

    # ── Pass 1: partition open vs completed, normalise fields ────────────────
    completed_numbers: set[str] = set()
    open_tickets: dict[str, dict[str, object]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        number = str(entry.get("number", "")).strip()
        if not _TICKET_RE.match(number):
            continue  # a ticket without a valid 4-digit id cannot be planned
        if entry.get("completed"):
            completed_numbers.add(number)
            continue
        pts, defaulted = effort_points(entry.get("effort"))
        if defaulted:
            warnings.append(
                f"{number}: missing/unknown effort, defaulted to medium"
            )
        open_tickets[number] = {
            "number": number,
            "title": sanitize_title(entry.get("title", "") or number),
            "effort": DEFAULT_EFFORT
            if defaulted
            else str(entry.get("effort")).strip().lower(),
            "effort_pts": pts,
            "status": str(entry.get("status", "") or ""),
            "raw_deps": normalize_deps(entry.get("depends_on")),
        }

    open_numbers = set(open_tickets)

    # ── Pass 2: resolve dependencies per open ticket ─────────────────────────
    overflow: dict[str, dict[str, str]] = {}
    deps_of: dict[str, set[str]] = {}
    for number in sorted(open_tickets):
        ticket = open_tickets[number]
        real_deps: set[str] = set()
        unresolved: list[str] = []
        raw_deps = ticket["raw_deps"]
        for token in raw_deps if isinstance(raw_deps, list) else []:
            if not _TICKET_RE.match(token):
                warnings.append(
                    f"{number}: invalid depends-on token '{token}' (excluded)"
                )
                continue
            if token == number:
                warnings.append(f"{number}: depends on itself (excluded)")
                continue
            if token in completed_numbers:
                continue  # pre-satisfied by a completed ticket
            if token in open_numbers:
                real_deps.add(token)
            else:
                unresolved.append(token)
        if unresolved:
            reason = "unresolvable dependency: " + ", ".join(sorted(unresolved))
            overflow[number] = {
                "number": number,
                "title": str(ticket["title"]),
                "reason": reason,
            }
            warnings.append(f"{number}: {reason} (moved to overflow)")
        deps_of[number] = real_deps

    # ── Pass 3: cascade overflow to dependents of unplanned tickets ──────────
    changed = True
    while changed:
        changed = False
        for number in sorted(open_tickets):
            if number in overflow:
                continue
            blocked_on = sorted(d for d in deps_of[number] if d in overflow)
            if blocked_on:
                overflow[number] = {
                    "number": number,
                    "title": str(open_tickets[number]["title"]),
                    "reason": "depends on unplanned ticket(s): "
                    + ", ".join(blocked_on),
                }
                changed = True

    # ── Pass 4: topological sort of the plannable sub-graph ──────────────────
    plannable = {n: t for n, t in open_tickets.items() if n not in overflow}
    edges: dict[str, set[str]] = {n: set() for n in plannable}
    for number in plannable:
        for dep in deps_of[number]:
            if dep in plannable:  # overflow deps already cascaded out
                edges[dep].add(number)
    order = _topological_order(plannable, edges)  # raises CycleError on a cycle

    # ── Pass 5: greedy earliest-fit bin-packing ──────────────────────────────
    # ``order`` is topological, so every dependency is visited before its
    # dependents. That lets pack-time overflow cascade forward: a ticket whose
    # dependency landed in overflow here (effort > capacity, or does-not-fit) is
    # itself overflowed rather than scheduled ahead of an unplanned dependency
    # (fail-closed on FR-5's ordering guarantee).
    used: list[int] = []  # capacity consumed per sprint index (0-based)
    assigned: dict[str, int] = {}
    for number in order:
        ticket = plannable[number]
        blocked_on = sorted(dep for dep in deps_of[number] if dep in overflow)
        if blocked_on:
            overflow[number] = {
                "number": number,
                "title": str(ticket["title"]),
                "reason": "depends on unplanned ticket(s): " + ", ".join(blocked_on),
            }
            continue
        pts = int(ticket["effort_pts"])  # type: ignore[call-overload]  # effort_pts is an int set by effort_points(); cast narrows dict[str, object]
        if pts > capacity:
            overflow[number] = {
                "number": number,
                "title": str(ticket["title"]),
                "reason": f"effort {pts} exceeds sprint capacity {capacity}",
            }
            continue
        earliest = 0
        for dep in deps_of[number]:
            # Every remaining dep is assigned (overflow deps were caught above).
            earliest = max(earliest, assigned[dep] + 1)
        slot = None
        idx = earliest
        while idx < max_sprints:
            if idx >= len(used):
                used.extend([0] * (idx - len(used) + 1))
            if used[idx] + pts <= capacity:
                slot = idx
                break
            idx += 1
        if slot is None:
            overflow[number] = {
                "number": number,
                "title": str(ticket["title"]),
                "reason": f"does not fit within max {max_sprints} sprint(s)",
            }
            continue
        used[slot] += pts
        assigned[number] = slot

    # ── Pass 6: assemble output ──────────────────────────────────────────────
    sprint_tickets: dict[int, list[dict[str, object]]] = {}
    for number, slot in assigned.items():
        ticket = plannable[number]
        sprint_tickets.setdefault(slot, []).append(
            {
                "number": number,
                "title": ticket["title"],
                "effort": ticket["effort"],
                "effort_pts": ticket["effort_pts"],
                "status": ticket["status"],
            }
        )
    sprints: list[dict[str, object]] = []
    for slot in sorted(sprint_tickets):
        tickets_in = sorted(sprint_tickets[slot], key=lambda t: str(t["number"]))
        n = slot + 1
        sprints.append(
            {
                "n": n,
                "label": sprint_label(as_of, n),
                "tickets": tickets_in,
                "capacity_used": used[slot],
                "capacity_total": capacity,
            }
        )

    overflow_list = [overflow[num] for num in sorted(overflow)]
    return {"sprints": sprints, "overflow": overflow_list, "warnings": warnings}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic sprint-planning core for /sprint.",
    )
    parser.add_argument("--sprint-capacity", type=int, default=DEFAULT_CAPACITY)
    parser.add_argument("--max-sprints", type=int, default=DEFAULT_MAX_SPRINTS)
    parser.add_argument("--as-of", default=None)
    return parser


def _main(argv: list[str], stdin_text: str) -> int:
    args = _build_parser().parse_args(argv)
    as_of = parse_date(args.as_of)
    if as_of is None:
        sys.stderr.write(
            json.dumps({"error": "--as-of must be a YYYY-MM-DD date"}) + "\n"
        )
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
    try:
        result = plan(
            data,
            capacity=args.sprint_capacity,
            max_sprints=args.max_sprints,
            as_of=as_of,
        )
    except CycleError as exc:
        sys.stderr.write(
            json.dumps(
                {"error": "circular dependency detected", "cycle": exc.members}
            )
            + "\n"
        )
        return 1
    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:], sys.stdin.read()))
