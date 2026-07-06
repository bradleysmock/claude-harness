"""Deterministic core for `/build --dry-run` (ticket 0013).

`/build --dry-run XXXX` previews a build without touching the worktree: it runs
every gate phase and the critic, and prints a plan of the files a live build
*would* write — but writes no implementation files, creates no worktree, and
leaves ``status.md`` untouched.

The orchestration (spawning the critic, guarding the worktree, skipping the
status transition) lives in the markdown flows. This module holds the pieces
that must be deterministic and unit-testable:

* flag parsing and the ticket-mode-only guard (FR-1),
* the "would write" plan (FR-5),
* the spec no-persist guard (FR-6, FR-10),
* the ``DryRunReport`` assembler/renderer with the fixed limitation labels and
  proceed prompt (FR-9, FR-11),
* a sandboxed gate runner that owns and unconditionally cleans a temp dir
  (FR-2, FR-3, FR-6) plus a stale-temp reaper for interrupted runs, and
* the Step 7a auto-repair suppression predicate.

All rendered output is timestamp-free so a given ``solution.md`` yields byte
identical output across runs (NFR-2).
"""
from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from models import GateResult, Spec

DRY_RUN_FLAG = "--dry-run"
DRY_RUN_TMP_SUBDIR = ".harness/dry-run-tmp"

# Fixed labels — the renderer emits these verbatim so the dry-run output always
# states its own coverage limits (FR-9) regardless of gate/critic content.
DRY_RUN_HEADER = "=== DRY RUN — no files written ==="
GATE_COVERAGE_LABEL = (
    "Gate coverage: indicative only — cross-file integration issues not surfaced."
)
CRITIC_COVERAGE_LABEL = (
    "Critic coverage: design-phase panels only (code-phase panels require live build)."
)


class DryRunModeError(ValueError):
    """Raised when ``--dry-run`` is combined with a non-ticket (spec-mode) build."""


# ---------------------------------------------------------------------------
# FR-1 — flag parsing and the ticket-mode-only guard
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedBuildArgs:
    """The result of splitting ``--dry-run`` off a raw ``/build`` argument string."""

    dry_run: bool
    remainder: str


def parse_dry_run_flag(arguments: str) -> ParsedBuildArgs:
    """Detect and strip a ``--dry-run`` token from a raw argument string.

    The flag may appear anywhere in the whitespace-separated tokens; every
    occurrence is removed and the surviving tokens are re-joined with single
    spaces so the remainder can be handed to normal mode selection.
    """
    tokens = arguments.split()
    dry_run = DRY_RUN_FLAG in tokens
    remainder = " ".join(t for t in tokens if t != DRY_RUN_FLAG)
    return ParsedBuildArgs(dry_run=dry_run, remainder=remainder)


def is_ticket_mode(remainder: str) -> bool:
    """Ticket mode iff the first surviving token begins with four digits."""
    tokens = remainder.split()
    if not tokens:
        return False
    head = tokens[0]
    return len(head) >= 4 and head[:4].isdigit()


def validate_dry_run_mode(parsed: ParsedBuildArgs) -> None:
    """Reject ``--dry-run`` outside ticket mode (FR-1).

    Raises ``DryRunModeError`` when the dry-run flag is present but the
    remaining argument does not select ticket mode. A no-op otherwise, so it is
    safe to call unconditionally after :func:`parse_dry_run_flag`.
    """
    if parsed.dry_run and not is_ticket_mode(parsed.remainder):
        raise DryRunModeError(
            f"{DRY_RUN_FLAG} is only valid in ticket mode "
            "(the argument must begin with a four-digit ticket id)"
        )


# ---------------------------------------------------------------------------
# FR-5 — the "would write" plan
# ---------------------------------------------------------------------------


def would_write_plan(specs: Iterable[Spec]) -> list[str]:
    """One ``would write: <target_file>`` line per spec with a target file (FR-5)."""
    return [f"would write: {spec.target_file}" for spec in specs if spec.target_file]


# ---------------------------------------------------------------------------
# FR-6 / FR-10 — spec persistence guard
# ---------------------------------------------------------------------------


def persist_specs(
    spec_sources: Sequence[tuple[str, str]],
    project_root: str,
    *,
    dry_run: bool,
) -> list[Path]:
    """Write ``(spec_id, source)`` pairs to ``.harness/specs`` — unless dry-run.

    In dry-run mode nothing is written and ``[]`` is returned, so a dry run
    never leaves generated specs behind (FR-10) and, more broadly, never writes
    implementation state (FR-6). In a live build each source is written to
    ``.harness/specs/<spec_id>.py`` and the written paths are returned.
    """
    if dry_run:
        return []
    specs_dir = Path(project_root) / ".harness" / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for spec_id, source in spec_sources:
        path = specs_dir / f"{spec_id}.py"
        path.write_text(source, encoding="utf-8")
        written.append(path)
    return written


# ---------------------------------------------------------------------------
# Report model + assembler (kept separate from rendering — divergent change)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpecSummary:
    """The structured, code-free view of a spec shown in a dry run."""

    spec_id: str
    target_file: str
    description: str
    acceptance_criteria: list[str] = field(default_factory=list)


@dataclass
class DryRunReport:
    """Everything a dry run collected, before it is rendered for display."""

    ticket_id: str
    spec_summaries: list[SpecSummary]
    would_write: list[str]
    gate_findings: str
    critic_findings: str


def summarize_specs(specs: Iterable[Spec]) -> list[SpecSummary]:
    """Project specs down to code-free metadata for the critic and the report."""
    return [
        SpecSummary(
            spec_id=spec.id,
            target_file=spec.target_file,
            description=spec.description.strip(),
            acceptance_criteria=list(spec.acceptance_criteria),
        )
        for spec in specs
    ]


def assemble_dry_run_report(
    ticket_id: str,
    specs: Sequence[Spec],
    gate_findings: str,
    critic_findings: str,
) -> DryRunReport:
    """Collect the dry-run sections into a ``DryRunReport`` (no formatting)."""
    return DryRunReport(
        ticket_id=ticket_id,
        spec_summaries=summarize_specs(specs),
        would_write=would_write_plan(specs),
        gate_findings=gate_findings.strip(),
        critic_findings=critic_findings.strip(),
    )


# ---------------------------------------------------------------------------
# FR-9 / FR-11 — renderer
# ---------------------------------------------------------------------------


def proceed_prompt(ticket_id: str) -> str:
    """The closing prompt that asks whether to run the live build (FR-11)."""
    return (
        f"Proceed with the live build? Run `/build {ticket_id}` (without "
        f"{DRY_RUN_FLAG}) to write these changes to the worktree, or leave it "
        "as-is to keep the ticket untouched."
    )


def render_dry_run_report(report: DryRunReport) -> str:
    """Format a ``DryRunReport`` for display (FR-9 labels, FR-11 proceed prompt).

    Deterministic: no timestamps or other run-varying content, so identical
    input renders identical output (NFR-2).
    """
    lines: list[str] = [DRY_RUN_HEADER, "", f"Ticket: {report.ticket_id}", ""]

    lines.append("## Planned specs")
    if report.spec_summaries:
        for summary in report.spec_summaries:
            lines.append(f"- {summary.spec_id} → {summary.target_file}")
            lines.append(f"  {summary.description}")
            for criterion in summary.acceptance_criteria:
                lines.append(f"    - {criterion}")
    else:
        lines.append("- (no specs)")
    lines.append("")

    lines.append("## Would write")
    lines.extend(report.would_write or ["would write: (nothing)"])
    lines.append("")

    lines.append("## Gate findings")
    lines.append(GATE_COVERAGE_LABEL)
    lines.append("")
    lines.append(report.gate_findings or "(no gate findings)")
    lines.append("")

    lines.append("## Critic findings")
    lines.append(CRITIC_COVERAGE_LABEL)
    lines.append("")
    lines.append(report.critic_findings or "(no critic findings)")
    lines.append("")

    lines.append(proceed_prompt(report.ticket_id))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# FR-3 — gate-findings renderer (mirrors the `/gate` format, timestamp-free)
# ---------------------------------------------------------------------------


def render_gate_findings(
    results: Sequence[GateResult],
    ticket_slug: str,
    language: str,
) -> str:
    """Render gate results as the ``gate-findings.md`` markdown the critic reads.

    Matches the ``/gate`` section layout but omits the "Run at" timestamp *and*
    the per-gate wall-clock duration so the output is deterministic (NFR-2): both
    are run-varying, and this text is embedded verbatim in the dry-run report.
    """
    lines: list[str] = [
        f"# Gate Findings — {ticket_slug}",
        "",
        f"**Language detected**: {language}",
        "",
    ]
    for result in results:
        lines.append(f"## {result.gate}")
        lines.append("")
        lines.append(f"**Status**: {'PASS' if result.passed else 'FAIL'}")
        lines.append("")
        if result.errors:
            for err in result.errors:
                location = err.file or "?"
                if err.line is not None:
                    location = f"{location}:{err.line}"
                code = f" [`{err.code}`]" if err.code else ""
                lines.append(f"- `{location}`{code}: {err.message}")
        else:
            lines.append("clean")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# FR-2 / FR-3 / FR-6 — sandboxed gate runner (temp dir owned by this flow)
# ---------------------------------------------------------------------------

GateRunner = Callable[[str, str], list[GateResult]]


def _default_gate_runner(directory: str, language: str) -> list[GateResult]:
    """Run the real gate suite over ``directory`` (all gates, no fail-fast)."""
    from gates import run_suite_on_dir

    return run_suite_on_dir(language, directory, fail_fast=False)


def clean_stale_dry_run_tmp(project_root: str) -> None:
    """Remove any temp dirs left by a prior interrupted dry run (Risks section).

    Called at the start of a dry run so a hard-killed previous run cannot leak
    disk. Never raises — a missing or already-clean root is fine.
    """
    tmp_root = Path(project_root) / DRY_RUN_TMP_SUBDIR
    shutil.rmtree(tmp_root, ignore_errors=True)


def run_dry_run_gates(
    spec_impls: Sequence[tuple[Spec, str, str]],
    project_root: str,
    language: str,
    *,
    gate_runner: GateRunner = _default_gate_runner,
) -> str:
    """Gate generated code inside a self-owned temp dir; return rendered findings.

    ``spec_impls`` is a sequence of ``(spec, implementation, tests)``. Each is
    written into a fresh temp dir under ``.harness/dry-run-tmp`` (gitignored),
    the injected ``gate_runner`` runs the suite over that dir, and the results
    are rendered to gate-findings markdown. The temp dir is removed in a
    ``finally`` so it is cleaned whether the gate run succeeds, fails, or raises
    (FR-6: nothing is ever written to the worktree).
    """
    tmp_root = Path(project_root) / DRY_RUN_TMP_SUBDIR
    tmp_root.mkdir(parents=True, exist_ok=True)
    sandbox = Path(tempfile.mkdtemp(dir=tmp_root))
    try:
        for index, (spec, implementation, tests) in enumerate(spec_impls):
            # Index-prefix every written file: ``.name`` contains traversal
            # (a spec target of ``../x`` becomes ``x``) so basenames can collide
            # across specs — an unprefixed name would let one spec silently
            # overwrite another and drop it from gate coverage.
            base = Path(spec.target_file).name or "impl.py"
            (sandbox / f"{index}_{base}").write_text(implementation, encoding="utf-8")
            (sandbox / f"test_dry_run_{index}.py").write_text(tests, encoding="utf-8")
        results = gate_runner(str(sandbox), language)
        return render_gate_findings(results, project_root_slug(project_root), language)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


def project_root_slug(project_root: str) -> str:
    """A stable label for the gate-findings header derived from the root path."""
    name = Path(project_root).resolve().name
    return name or "project"


# ---------------------------------------------------------------------------
# Step 7a suppression (build-ticket.md) — repair loop never runs in a dry run
# ---------------------------------------------------------------------------


def should_auto_repair(dry_run: bool) -> bool:
    """Guard evaluated at Step 7a entry: auto-repair is skipped under dry-run."""
    return not dry_run
