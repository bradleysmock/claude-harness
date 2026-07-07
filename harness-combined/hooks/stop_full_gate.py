#!/usr/bin/env python3
"""Stop hook: full gate suite on review-ready worktrees.

Session-bound: if `.tickets/.active` exists, gates only that ticket's worktree
(avoids cross-session collisions when multiple tickets are in-flight). If no
`.active` file exists, gates ALL review-ready worktrees.

Polyglot — detects stacks present in the worktree by project-root markers and
runs the corresponding gate set. Multiple stacks per worktree are supported;
each is run independently and all failures are aggregated.

No-op outside the harness (no .tickets/ or no review-ready ticket).
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable

PER_GATE_TIMEOUT_SECONDS = 90

# Vendored / cache / generated directories excluded from recursive source probes
# (FR-3). Deliberately duplicated from server._SCAN_SKIP: the Stop hook must run
# standalone (it never imports server, to avoid dragging in the full gate suite),
# so the constant is copied and pinned identical by a consistency test rather
# than shared by import.
_SCAN_SKIP = {"node_modules", ".git", ".venv", "venv", "dist", "target", "__pycache__"}


def _has_source_file(root: Path, suffix: str) -> bool:
    """True if any file ending in ``suffix`` exists under ``root``, skipping
    vendored/generated trees (FR-3).

    Uses an ``os.walk`` that prunes every directory in ``_SCAN_SKIP`` from
    descent, so it never recurses into ``node_modules`` / ``.venv`` / etc. — a
    bounded walk rather than a full ``rglob`` of vendored trees (NFR-1).
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SCAN_SKIP]
        if any(name.endswith(suffix) for name in filenames):
            return True
    return False


def _load_repair_integrity() -> ModuleType | None:
    """Load gates/repair_integrity.py by file path (FR-4).

    Loading by path deliberately bypasses ``gates/__init__.py`` (which imports
    the ``models`` package) so the Stop hook never drags in the full gate suite.
    Returns None if the module cannot be found — the suppression section is then
    simply omitted rather than crashing the hook.
    """
    module_path = Path(__file__).resolve().parent.parent / "gates" / "repair_integrity.py"
    if not module_path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("repair_integrity", module_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    # Register before exec: @dataclass resolves cls.__module__ via sys.modules
    # during class creation (py3.12+), which fails if the module is absent.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def worktree_diff_against_main(worktree_dir: Path) -> str:
    """Unified diff of the worktree against main (empty string on any failure)."""
    if shutil.which("git") is None:
        return ""
    try:
        completed = subprocess.run(
            ["git", "-C", str(worktree_dir), "diff", "main"],
            capture_output=True, text=True, timeout=PER_GATE_TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        return ""
    return completed.stdout if completed.returncode == 0 else ""


def unexplained_suppressions(worktree_dir: Path) -> list[str]:
    """Net-new UNEXPLAINED suppression pragmas in the worktree diff (FR-4).

    Reuses gates/repair_integrity's marker detection (single source of the marker
    list). Returns a one-item report section when any are present, else []. Fails
    safe: any error (module missing, git failure) yields no section.
    """
    repair_integrity = _load_repair_integrity()
    if repair_integrity is None:
        return []
    diff = worktree_diff_against_main(worktree_dir)
    if not diff:
        return []
    bare = [s for s in repair_integrity.added_suppressions(diff) if not s.explained]
    if not bare:
        return []
    lines = [f"net-new unexplained suppression pragma(s): {len(bare)}"]
    for s in bare:
        lines.append(f"  {s.file}: [{s.marker}] {s.excerpt}")
    lines.append("Add a reason suffix (e.g. '# nosec: <why>') or fix the underlying issue.")
    return ["\n".join(lines)]


@dataclass(frozen=True)
class TicketContext:
    ticket_dir: Path
    worktree_dir: Path


def read_active_slug(tickets_root: Path) -> str | None:
    active_file = tickets_root / ".active"
    if not active_file.is_file():
        return None
    slug = active_file.read_text(encoding="utf-8", errors="replace").strip()
    return slug if slug else None


def discover_tickets_to_gate(project_root: Path) -> list[TicketContext]:
    """Return the ticket(s) to gate this turn.

    If .tickets/.active names a slug, return only that ticket (if review-ready).
    Otherwise return every review-ready ticket that has a matching worktree.
    """
    tickets_root = project_root / ".tickets"
    worktrees_root = project_root / ".worktrees"
    if not tickets_root.is_dir() or not worktrees_root.is_dir():
        return []

    active_slug = read_active_slug(tickets_root)

    if active_slug is not None:
        ticket_dir = tickets_root / active_slug
        if not ticket_dir.is_dir():
            return []
        status_file = ticket_dir / "status.md"
        if not status_file.is_file():
            return []
        text = status_file.read_text(encoding="utf-8", errors="replace")
        if "status: review-ready" not in text:
            return []
        worktree_dir = worktrees_root / active_slug
        if not worktree_dir.is_dir():
            return []
        return [TicketContext(ticket_dir=ticket_dir, worktree_dir=worktree_dir)]

    # No active session file: gate all review-ready worktrees.
    results: list[TicketContext] = []
    for status_file in sorted(tickets_root.glob("*/status.md")):
        text = status_file.read_text(encoding="utf-8", errors="replace")
        if "status: review-ready" not in text:
            continue
        ticket_slug = status_file.parent.name
        worktree_dir = worktrees_root / ticket_slug
        if worktree_dir.is_dir():
            results.append(TicketContext(ticket_dir=status_file.parent, worktree_dir=worktree_dir))
    return results


def _python_project_root(worktree_dir: Path) -> Path:
    """Find the Python project root within the worktree.

    Returns worktree_dir if Python markers (pyproject.toml, etc.) exist there.
    Otherwise returns the first non-hidden subdirectory that has Python markers.
    Handles monorepo structures where the Python project lives one level deep.
    """
    markers = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")
    if any((worktree_dir / m).exists() for m in markers):
        return worktree_dir
    for child in sorted(worktree_dir.iterdir()):
        if child.is_dir() and not child.name.startswith(".") and any((child / m).exists() for m in markers):
            return child
    return worktree_dir


def detect_stacks(worktree_dir: Path) -> list[str]:
    stacks: list[str] = []
    if any((worktree_dir / marker).exists() for marker in ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")):
        stacks.append("python")
    elif _has_source_file(worktree_dir, ".py"):
        stacks.append("python")

    if (worktree_dir / "package.json").is_file():
        if (worktree_dir / "tsconfig.json").is_file() or _has_source_file(worktree_dir, ".ts"):
            stacks.append("typescript")
        else:
            stacks.append("javascript")

    if (worktree_dir / "go.mod").is_file():
        stacks.append("go")

    if (worktree_dir / "Cargo.toml").is_file():
        stacks.append("rust")

    return stacks


def run_gate(
    executable: str, args: list[str], cwd: Path,
    skipped: list[str] | None = None,
) -> tuple[int | None, str]:
    """Run one gate tool; record (never swallow) a missing executable (ticket 0043).

    When ``executable`` is not on PATH, append its name (deduped) to ``skipped`` if a
    collector was supplied and return the non-run sentinel code ``None`` — distinct
    from ``0`` (ran and passed) so a caller can tell "did not run" from "ran clean".
    The existing ``code not in (0, None)`` failure checks already treat ``None`` as
    not-a-failure, so a skip is informational and never blocks completion.
    """
    if shutil.which(executable) is None:
        if skipped is not None and executable not in skipped:
            skipped.append(executable)
        return None, ""
    try:
        completed = subprocess.run(
            [executable, *args],
            capture_output=True,
            text=True,
            timeout=PER_GATE_TIMEOUT_SECONDS,
            cwd=str(cwd),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return -1, f"{executable} timed out after {PER_GATE_TIMEOUT_SECONDS}s"
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode, output.strip()


def changed_files(worktree_dir: Path, suffix: str) -> list[str]:
    if shutil.which("git") is None:
        return []
    try:
        completed = subprocess.run(
            ["git", "-C", str(worktree_dir), "diff", "--name-only", "main"],
            capture_output=True, text=True, timeout=PER_GATE_TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        return []
    if completed.returncode != 0:
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip().endswith(suffix)]


# --- Per-stack gate sets ---------------------------------------------------


@dataclass
class StackReport:
    """One stack's Stop-hook outcome: blocking failures plus skipped tools.

    ``failures`` are the human-readable blocking sections (unchanged shape).
    ``skipped`` names the optional tools that were not installed this run — visible
    but non-blocking (ticket 0043). Kept as a small struct so a stack can report a
    skip *and* a pass in the same run.
    """

    failures: list[str]
    skipped: list[str]


def gates_python(worktree_dir: Path) -> StackReport:
    failures: list[str] = []
    skipped: list[str] = []
    python_root = _python_project_root(worktree_dir)
    all_py_files = changed_files(worktree_dir, ".py")

    # Remap paths to be relative to python_root; skip files outside it.
    # changed_files() returns paths relative to worktree_dir (git root), e.g.
    # "harness-combined/server.py". When python_root is a subdirectory we strip
    # the prefix so tools run correctly from python_root.
    if python_root != worktree_dir:
        rel_prefix = python_root.relative_to(worktree_dir)
        py_files: list[str] = []
        for f in all_py_files:
            try:
                py_files.append(str(Path(f).relative_to(rel_prefix)))
            except ValueError:
                pass  # Outside python_root — skip
    else:
        py_files = all_py_files

    if py_files:
        code, out = run_gate("ruff", ["check", "--output-format", "concise", *py_files], python_root, skipped=skipped)
        if code not in (0, None) and out:
            failures.append(f"ruff:\n{out}")

        code, out = run_gate("bandit", ["-ll", "-q", "-f", "txt", *py_files], python_root, skipped=skipped)
        if code not in (0, None) and "No issues identified" not in out and out:
            failures.append(f"bandit:\n{out}")

        code, out = run_gate("mypy", ["--no-error-summary", *py_files], python_root, skipped=skipped)
        if code not in (0, None) and out:
            failures.append(f"mypy:\n{out}")

    code, out = run_gate("pytest", ["-q", "--no-header", "--no-summary"], python_root, skipped=skipped)
    if code not in (0, None) and out:
        tail = "\n".join(out.splitlines()[-40:])
        failures.append(f"pytest (last 40 lines):\n{tail}")

    return StackReport(failures=failures, skipped=skipped)


def gates_javascript_typescript(worktree_dir: Path) -> StackReport:
    failures: list[str] = []
    skipped: list[str] = []
    if (worktree_dir / "node_modules" / ".bin" / "eslint").exists() or shutil.which("eslint") is not None:
        code, out = run_gate("npx", ["--no-install", "eslint", "--no-color", "."], worktree_dir, skipped=skipped)
        if code not in (0, None) and out:
            tail = "\n".join(out.splitlines()[-60:])
            failures.append(f"eslint:\n{tail}")

    if (worktree_dir / "tsconfig.json").is_file():
        code, out = run_gate("npx", ["--no-install", "tsc", "--noEmit"], worktree_dir, skipped=skipped)
        if code not in (0, None) and out:
            tail = "\n".join(out.splitlines()[-60:])
            failures.append(f"tsc:\n{tail}")

    if (worktree_dir / "package.json").is_file():
        code, out = run_gate("npm", ["test", "--silent"], worktree_dir, skipped=skipped)
        if code not in (0, None) and out:
            tail = "\n".join(out.splitlines()[-40:])
            failures.append(f"npm test (last 40 lines):\n{tail}")

    return StackReport(failures=failures, skipped=skipped)


def check_migration_conflicts(worktree_dir: Path) -> list[str]:
    """Detect duplicate numeric prefixes in migrations/. Fast, no compiler needed.

    .up.sql and .down.sql are two halves of the same migration — strip the
    direction suffix before comparing so they don't false-positive against each
    other. A real conflict is two different slugs sharing the same number.
    """
    migrations_dir = worktree_dir / "migrations"
    if not migrations_dir.is_dir():
        return []
    seen: dict[str, str] = {}  # prefix → canonical name (no direction suffix)
    conflicts: list[str] = []
    for f in sorted(migrations_dir.glob("*.sql")):
        name = f.name
        for suffix in (".up.sql", ".down.sql"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        parts = name.split("_", 1)
        if len(parts) < 2:
            continue
        prefix = parts[0]
        if prefix in seen:
            if seen[prefix] != name:
                entry = f"  {seen[prefix]}  ←→  {name}"
                if entry not in conflicts:
                    conflicts.append(entry)
        else:
            seen[prefix] = name
    if not conflicts:
        return []
    return ["migration number conflicts (renumber before merging):\n" + "\n".join(conflicts)]


def gates_go(worktree_dir: Path) -> StackReport:
    failures: list[str] = []
    skipped: list[str] = []

    # Fast pre-check: migration conflicts break the migrator at test startup,
    # so skip the compiler gates if any are found.
    migration_failures = check_migration_conflicts(worktree_dir)
    if migration_failures:
        return StackReport(failures=migration_failures, skipped=skipped)

    code, out = run_gate("gofmt", ["-l", "."], worktree_dir, skipped=skipped)
    if out.strip():
        failures.append(f"gofmt (unformatted files):\n{out.strip()}")

    code, out = run_gate("go", ["vet", "./..."], worktree_dir, skipped=skipped)
    if code not in (0, None) and out:
        failures.append(f"go vet:\n{out}")

    # -race matches the MCP Go gate (gates/go.py runs `go test -race -v ./...`),
    # so a data race cannot pass the turn-end hook and then fail the MCP gate.
    code, out = run_gate("go", ["test", "-race", "./..."], worktree_dir, skipped=skipped)
    if code not in (0, None) and out:
        tail = "\n".join(out.splitlines()[-40:])
        failures.append(f"go test (last 40 lines):\n{tail}")

    return StackReport(failures=failures, skipped=skipped)


def gates_rust(worktree_dir: Path) -> StackReport:
    failures: list[str] = []
    skipped: list[str] = []
    code, out = run_gate("cargo", ["fmt", "--check"], worktree_dir, skipped=skipped)
    if code not in (0, None) and out:
        failures.append(f"cargo fmt --check:\n{out[:600]}")

    code, out = run_gate("cargo", ["clippy", "--", "-D", "warnings"], worktree_dir, skipped=skipped)
    if code not in (0, None) and out:
        tail = "\n".join(out.splitlines()[-40:])
        failures.append(f"cargo clippy:\n{tail}")

    code, out = run_gate("cargo", ["test", "--quiet"], worktree_dir, skipped=skipped)
    if code not in (0, None) and out:
        tail = "\n".join(out.splitlines()[-40:])
        failures.append(f"cargo test (last 40 lines):\n{tail}")

    return StackReport(failures=failures, skipped=skipped)


STACK_GATES: dict[str, Callable[[Path], StackReport]] = {
    "python": gates_python,
    "javascript": gates_javascript_typescript,
    "typescript": gates_javascript_typescript,
    "go": gates_go,
    "rust": gates_rust,
}


def collect_report(
    worktree_dir: Path, stacks: list[str] | None = None
) -> tuple[list[str], list[str]]:
    """Return ``(failure sections, skip lines)`` for every detected stack.

    Failure sections are the blocking ``=== stack ===`` bodies (unchanged). Skip
    lines name each optional tool that was not installed, one line per stack, so a
    missing gate tool is *visible* instead of a silent pass (ticket 0043, FR-2). A
    skip line never contributes to the blocking decision — it is informational.
    ``stacks`` may be pre-supplied by the caller (ticket 0047 honest-stack
    handling); when ``None`` it is detected here.
    """
    if stacks is None:
        stacks = detect_stacks(worktree_dir)
    failures: list[str] = []
    skip_lines: list[str] = []
    seen_dispatchers: set[Callable[[Path], StackReport]] = set()
    for stack in stacks:
        gate_runner = STACK_GATES.get(stack)
        if gate_runner is None or gate_runner in seen_dispatchers:
            continue
        seen_dispatchers.add(gate_runner)
        report = gate_runner(worktree_dir)
        if report.failures:
            failures.append(f"=== {stack} ===\n" + "\n\n".join(report.failures))
        if report.skipped:
            skip_lines.append(
                f"{stack}: skipped (not installed) — " + ", ".join(report.skipped)
            )

    suppression_section = unexplained_suppressions(worktree_dir)
    if suppression_section:
        failures.append("=== repair-integrity ===\n" + "\n\n".join(suppression_section))
    return failures, skip_lines


def collect_failures(worktree_dir: Path, stacks: list[str] | None = None) -> list[str]:
    """Blocking failure sections only. Skip lines are surfaced via ``collect_report``."""
    return collect_report(worktree_dir, stacks)[0]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}

    project_root_str = payload.get("cwd") or ""
    project_root = Path(project_root_str) if project_root_str else Path.cwd()

    tickets = discover_tickets_to_gate(project_root)
    if not tickets:
        return 0

    all_failures: list[tuple[str, list[str]]] = []
    all_skips: list[tuple[str, list[str]]] = []
    for ticket in tickets:
        stacks = detect_stacks(ticket.worktree_dir)
        # A review-ready worktree with no supported stack yields zero *language*
        # gate coverage. Print a single honest warning naming it instead of
        # passing in silence (FR-4), but do NOT skip the ticket: the
        # stack-independent repair-integrity check inside collect_report still
        # runs, so a net-new unexplained suppression in an unsupported worktree
        # still blocks. The warning alone never changes the exit code.
        if not stacks:
            sys.stderr.write(
                f"stop_full_gate: no supported stack detected in worktree "
                f"'{ticket.worktree_dir.name}' — no gate coverage for this ticket.\n"
            )
        failures, skips = collect_report(ticket.worktree_dir, stacks=stacks)
        if failures:
            all_failures.append((ticket.worktree_dir.name, failures))
        if skips:
            all_skips.append((ticket.worktree_dir.name, skips))

    # Build the informational skip note once (non-blocking — ticket 0043, FR-2).
    skip_note = ""
    if all_skips:
        skip_sections = [
            f"--- {name} ---\n" + "\n".join(skips) for name, skips in all_skips
        ]
        skip_note = (
            "stop_full_gate: gate tools skipped (not installed — provision via "
            "the ticket 0022 doctor):\n\n" + "\n\n".join(skip_sections)
        )

    if not all_failures:
        # Skips only (or nothing): surface any skip note but never block the turn.
        if skip_note:
            sys.stderr.write(skip_note + "\n")
        return 0

    sections: list[str] = []
    for worktree_name, failures in all_failures:
        sections.append(f"--- {worktree_name} ---\n\n" + "\n\n".join(failures))

    if skip_note:
        sections.append(skip_note)

    sys.stderr.write(
        "stop_full_gate blocked completion — gate failures detected:\n\n"
        + "\n\n".join(sections)
        + "\n\nFix the failures before presenting Checkpoint 2.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
