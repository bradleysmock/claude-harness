"""Harness health dashboard — read-only aggregator over gate-findings.md + memory.db.

Reads gate-findings.md files from active and completed tickets and queries the
failure-memory SQLite database (``.harness/memory.db``) to produce a cross-ticket
view of build quality: gate pass rates, average repair cycles, recurring failure
modes, top failing tickets, and per-gate trend indicators.

Strictly read-only — no file or database is ever written. ``project_root`` is
validated (resolved to an absolute path, must be an existing directory) before any
filesystem or database access, so the module fails closed on invalid paths.

The report text is the CLI deliverable and is emitted to stdout by the ``__main__``
entry point; warnings (e.g. a skipped malformed file) go to stderr.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Number of most-recent builds (gate-findings.md files) considered. Files are
# mtime-sorted and only the top ``WINDOW`` are read (FR-8).
WINDOW = 10

# Trend threshold: a last-5-minus-prior-5 pass-rate delta must exceed this
# magnitude to count as improving/declining; within +/- it is stable (FR-6).
TREND_THRESHOLD = 0.10

# Error-code shapes B102 / E501 / F401 / W291 / TS2345: 1-3 uppercase letters
# followed by 3+ digits. Error codes are conventionally uppercase, so anchoring on
# uppercase avoids matching lowercase identifiers such as ``sha256`` (FR-4).
_ERROR_CODE = re.compile(r"\b([A-Z]{1,3}\d{3,})\b")

# A Results-table data row: ``| gate | ✓ | notes |``. The pass cell is a check or
# cross mark (with optional surrounding whitespace).
_RESULT_ROW = re.compile(r"^\|\s*([A-Za-z_][\w-]*)\s*\|\s*([✓✗xX×])\s*\|")
_RUN_DATE = re.compile(r"^##\s*Run date:\s*(.+?)\s*$")
_TITLE_TICKET = re.compile(r"^#\s*Gate Findings\s*[—–-]\s*(.+?)\s*$")


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ParsedFindings:
    """One successfully parsed gate-findings.md file."""

    ticket: str
    date: str | None
    gates: dict[str, bool]  # gate name -> passed?
    mtime: float


@dataclass(frozen=True)
class GatePassRate:
    """Aggregated pass rate and trend for a single gate type."""

    gate: str
    passed: int
    total: int
    trend: str  # "improving" | "declining" | "stable"

    @property
    def rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


@dataclass(frozen=True)
class HealthReport:
    """The full computed health report — the contract between computation and
    formatting. ``format_report`` consumes exactly these fields."""

    pass_rates: list[GatePassRate]
    builds_analyzed: int  # N — files successfully parsed
    builds_window: int  # M — the requested window (WINDOW)
    top_failing_tickets: list[tuple[str, int]]
    memory_db_present: bool
    avg_repair_cycles: dict[str, float] | None
    top_failure_modes: list[tuple[str, int]] | None
    notes: list[str] = field(default_factory=list)


# ── project_root validation (trust boundary) ─────────────────────────────────


def _validate_project_root(project_root: str) -> Path:
    """Resolve ``project_root`` to an absolute path and require it be an existing
    directory. Raises ``ValueError`` otherwise — enforced *before* any filesystem
    or database access so the module fails closed on invalid input (FR-11)."""
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise ValueError(f"project_root is not an existing directory: {project_root}")
    return root


# ── gate-findings.md discovery + parsing ─────────────────────────────────────


def discover_gate_findings(root: Path) -> list[Path]:
    """Return up to ``WINDOW`` gate-findings.md paths under ``<root>/.tickets``,
    most-recent-first by mtime. Files are mtime-sorted before slicing so only the
    top-``WINDOW`` are ever read (FR-8). Returns ``[]`` when ``.tickets`` is absent."""
    tickets = root / ".tickets"
    if not tickets.is_dir():
        return []
    files = list(tickets.rglob("gate-findings.md"))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:WINDOW]


def parse_gate_findings(path: Path) -> ParsedFindings | None:
    """Parse one gate-findings.md into a :class:`ParsedFindings`, or ``None`` when
    the file is missing/malformed (no readable Results table). Defensive by design:
    structural problems yield ``None`` rather than raising, and a warning is emitted
    to stderr so the file is skipped and processing continues (FR-9)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"health: skipping unreadable {path}: {exc}", file=sys.stderr)
        return None

    gates: dict[str, bool] = {}
    date: str | None = None
    ticket: str | None = None
    for line in text.splitlines():
        date_match = _RUN_DATE.match(line)
        if date_match:
            date = date_match.group(1)
            continue
        title_match = _TITLE_TICKET.match(line)
        if title_match:
            ticket = title_match.group(1)
            continue
        row = _RESULT_ROW.match(line)
        if row:
            name = row.group(1).lower()
            # Skip the table header/separator masquerading as a row.
            if name in ("gate", "gates"):
                continue
            gates[name] = row.group(2) == "✓"

    if not gates:
        print(f"health: skipping malformed gate-findings (no gate rows): {path}", file=sys.stderr)
        return None

    if not ticket:
        # Fall back to the containing ticket directory name.
        ticket = path.parent.name

    return ParsedFindings(ticket=ticket, date=date, gates=gates, mtime=path.stat().st_mtime)


# ── Metrics over parsed gate-findings ────────────────────────────────────────


def _window_pass_rate(builds: list[ParsedFindings], gate: str) -> float | None:
    """Pass rate for ``gate`` across ``builds`` that recorded it, or ``None`` when
    none did (so an absent gate in a window is distinguishable from a 0% rate)."""
    present = [b for b in builds if gate in b.gates]
    if not present:
        return None
    passed = sum(1 for b in present if b.gates[gate])
    return passed / len(present)


def trend_indicator(last_rate: float, prior_rate: float) -> str:
    """Classify a pass-rate trend from the last-5 and prior-5 window rates:
    improving if ``last - prior > 0.10``; declining if ``< -0.10``; stable otherwise
    (including an exact +/-0.10 delta or equal rates) (FR-6)."""
    delta = last_rate - prior_rate
    if delta > TREND_THRESHOLD:
        return "improving"
    if delta < -TREND_THRESHOLD:
        return "declining"
    return "stable"


def pass_rate_by_gate(builds: list[ParsedFindings]) -> list[GatePassRate]:
    """Aggregate pass rate + trend per gate across ``builds`` (mtime-sorted,
    most-recent-first). Trend compares the last-5 vs prior-5 windows; when the prior
    window has no data for a gate the trend is ``stable`` (FR-2, FR-6)."""
    last5, prior5 = builds[:5], builds[5:10]
    totals: dict[str, int] = {}
    passed: dict[str, int] = {}
    for build in builds:
        for gate, ok in build.gates.items():
            totals[gate] = totals.get(gate, 0) + 1
            passed[gate] = passed.get(gate, 0) + (1 if ok else 0)

    results: list[GatePassRate] = []
    for gate in sorted(totals):
        last_rate = _window_pass_rate(last5, gate)
        prior_rate = _window_pass_rate(prior5, gate)
        if last_rate is None or prior_rate is None:
            trend = "stable"
        else:
            trend = trend_indicator(last_rate, prior_rate)
        results.append(GatePassRate(gate=gate, passed=passed[gate], total=totals[gate], trend=trend))
    return results


def top_failing_tickets(builds: list[ParsedFindings], limit: int = 5) -> list[tuple[str, int]]:
    """Tickets ranked by total failing gates summed across their parsed builds,
    descending (ties broken by ticket name). Only tickets with >=1 failure appear
    (FR-5)."""
    failures: dict[str, int] = {}
    for build in builds:
        fails = sum(1 for ok in build.gates.values() if not ok)
        if fails:
            failures[build.ticket] = failures.get(build.ticket, 0) + fails
    ranked = sorted(failures.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[:limit]


# ── Metrics over memory.db ───────────────────────────────────────────────────


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    """Open ``db_path`` read-only via a file: URI so a query can never create or
    mutate the database (NFR-1)."""
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def avg_repair_cycles(db_path: Path) -> dict[str, float] | None:
    """Average repair cycles per gate: for each ``(spec_id, gate)`` that eventually
    passed, take ``MAX(attempt)`` as its cycle count, then average per gate (FR-3).
    Returns ``None`` when the database is absent or has no such table."""
    if not db_path.is_file():
        return None
    try:
        with _connect_readonly(db_path) as conn:
            rows = conn.execute(
                "SELECT gate, AVG(max_attempt) FROM ("
                "  SELECT spec_id, gate, MAX(attempt) AS max_attempt"
                "  FROM failure_records WHERE outcome = 'passed'"
                "  GROUP BY spec_id, gate"
                ") GROUP BY gate"
            ).fetchall()
    except sqlite3.DatabaseError as exc:
        print(f"health: memory.db unreadable, skipping repair-cycle section: {exc}", file=sys.stderr)
        return None
    return {gate: float(avg) for gate, avg in rows if avg is not None}


def top_failure_modes(db_path: Path, limit: int = 5) -> list[tuple[str, int]] | None:
    """Top recurring failure-mode error codes across non-passing records, clustered
    by code (B102 / E501 / TS2345 …), most-frequent-first (ties broken by code).
    Returns ``None`` when the database is absent/unreadable (FR-4)."""
    if not db_path.is_file():
        return None
    try:
        with _connect_readonly(db_path) as conn:
            rows = conn.execute(
                "SELECT errors_text FROM failure_records WHERE outcome != 'passed'"
            ).fetchall()
    except sqlite3.DatabaseError as exc:
        print(f"health: memory.db unreadable, skipping failure-mode section: {exc}", file=sys.stderr)
        return None
    counts: dict[str, int] = {}
    for (errors_text,) in rows:
        for code in _ERROR_CODE.findall(errors_text or ""):
            counts[code] = counts.get(code, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[:limit]


# ── Top-level report ─────────────────────────────────────────────────────────


def health_report(project_root: str) -> HealthReport:
    """Collect and compute the full :class:`HealthReport` for ``project_root``.

    Validates ``project_root`` (raising ``ValueError`` before any I/O — FR-11),
    discovers up to ``WINDOW`` gate-findings.md files, parses them defensively, and
    computes every metric. Absent/empty memory.db yields ``None`` repair-cycle and
    failure-mode sections with an explanatory note (FR-10)."""
    root = _validate_project_root(project_root)

    gate_files = discover_gate_findings(root)
    parsed = [p for f in gate_files if (p := parse_gate_findings(f)) is not None]

    pass_rates = pass_rate_by_gate(parsed)
    failing_tickets = top_failing_tickets(parsed)

    db_path = root / ".harness" / "memory.db"
    memory_present = db_path.is_file()
    cycles = avg_repair_cycles(db_path)
    failure_modes = top_failure_modes(db_path)

    notes: list[str] = []
    if not memory_present:
        notes.append(
            "memory.db not found — repair-cycle and recurring-failure sections omitted."
        )
    skipped = len(gate_files) - len(parsed)
    if skipped:
        notes.append(f"{skipped} gate-findings file(s) skipped (missing or malformed).")
    if not gate_files:
        notes.append("No gate-findings.md files found under .tickets/.")

    return HealthReport(
        pass_rates=pass_rates,
        builds_analyzed=len(parsed),
        builds_window=WINDOW,
        top_failing_tickets=failing_tickets,
        memory_db_present=memory_present,
        avg_repair_cycles=cycles,
        top_failure_modes=failure_modes,
        notes=notes,
    )


# ── Formatting ───────────────────────────────────────────────────────────────


def _percent(rate: float) -> str:
    return f"{rate * 100:.0f}%"


def format_report(report: HealthReport) -> str:
    """Render a :class:`HealthReport` as a CLI-readable text report with section
    headers and simple tables (FR-7). Pure string builder — no I/O."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("Harness Health Dashboard")
    lines.append("=" * 60)

    # ── Gate Pass Rates ──
    lines.append("")
    lines.append(
        f"Gate Pass Rates ({report.builds_analyzed} of {report.builds_window} builds analyzed)"
    )
    if report.pass_rates:
        lines.append(f"  {'Gate':<14} {'Pass Rate':<14} {'Trend':<10}")
        lines.append(f"  {'-' * 14} {'-' * 14} {'-' * 10}")
        for pr in report.pass_rates:
            rate_cell = f"{pr.passed} of {pr.total} ({_percent(pr.rate)})"
            lines.append(f"  {pr.gate:<14} {rate_cell:<14} {pr.trend:<10}")
    else:
        lines.append("  (no gate-findings data)")

    # ── Average Repair Cycles ──
    lines.append("")
    lines.append("Average Repair Cycles")
    if report.avg_repair_cycles is None:
        lines.append("  (memory.db unavailable — section omitted)")
    elif not report.avg_repair_cycles:
        lines.append("  (no passing repair records)")
    else:
        lines.append(f"  {'Gate':<14} {'Avg Cycles':<12}")
        lines.append(f"  {'-' * 14} {'-' * 12}")
        for gate in sorted(report.avg_repair_cycles):
            lines.append(f"  {gate:<14} {report.avg_repair_cycles[gate]:<12.2f}")

    # ── Top Recurring Failure Modes ──
    lines.append("")
    lines.append("Top Recurring Failure Modes")
    if report.top_failure_modes is None:
        lines.append("  (memory.db unavailable — section omitted)")
    elif not report.top_failure_modes:
        lines.append("  (no recurring error codes)")
    else:
        for code, count in report.top_failure_modes:
            lines.append(f"  {code:<10} {count} occurrence(s)")

    # ── Tickets With Most Gate Failures ──
    lines.append("")
    lines.append("Tickets With Most Gate Failures")
    if report.top_failing_tickets:
        for ticket, count in report.top_failing_tickets:
            lines.append(f"  {ticket:<28} {count} failing gate(s)")
    else:
        lines.append("  (no gate failures recorded)")

    # ── Notes ──
    if report.notes:
        lines.append("")
        lines.append("Notes")
        for note in report.notes:
            lines.append(f"  - {note}")

    return "\n".join(lines)


# ── CLI entry point ──────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """CLI entry: print the report to stdout (exit 0). Exit 2 on an invalid
    project_root or an unreadable ``.tickets/`` directory."""
    args = list(sys.argv[1:] if argv is None else argv)
    project_root = args[0] if args else "."
    try:
        root = _validate_project_root(project_root)
    except ValueError as exc:
        print(f"health: {exc}", file=sys.stderr)
        return 2
    if not (root / ".tickets").is_dir():
        print(f"health: .tickets/ directory not found under {root}", file=sys.stderr)
        return 2
    report = health_report(str(root))
    print(format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
