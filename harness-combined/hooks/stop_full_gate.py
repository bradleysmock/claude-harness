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

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

PER_GATE_TIMEOUT_SECONDS = 90


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
    elif any(worktree_dir.glob("**/*.py")):
        stacks.append("python")

    if (worktree_dir / "package.json").is_file():
        if (worktree_dir / "tsconfig.json").is_file() or any(worktree_dir.glob("**/*.ts")):
            stacks.append("typescript")
        else:
            stacks.append("javascript")

    if (worktree_dir / "go.mod").is_file():
        stacks.append("go")

    if (worktree_dir / "Cargo.toml").is_file():
        stacks.append("rust")

    return stacks


def run_gate(executable: str, args: list[str], cwd: Path) -> tuple[int, str]:
    if shutil.which(executable) is None:
        return 0, ""
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

def gates_python(worktree_dir: Path) -> list[str]:
    failures: list[str] = []
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
        code, out = run_gate("ruff", ["check", "--output-format", "concise", *py_files], python_root)
        if code not in (0, None) and out:
            failures.append(f"ruff:\n{out}")

        code, out = run_gate("bandit", ["-ll", "-q", "-f", "txt", *py_files], python_root)
        if code not in (0, None) and "No issues identified" not in out and out:
            failures.append(f"bandit:\n{out}")

        code, out = run_gate("mypy", ["--no-error-summary", *py_files], python_root)
        if code not in (0, None) and out:
            failures.append(f"mypy:\n{out}")

    code, out = run_gate("pytest", ["-q", "--no-header", "--no-summary"], python_root)
    if code not in (0, None) and out:
        tail = "\n".join(out.splitlines()[-40:])
        failures.append(f"pytest (last 40 lines):\n{tail}")

    return failures


def gates_javascript_typescript(worktree_dir: Path) -> list[str]:
    failures: list[str] = []
    if (worktree_dir / "node_modules" / ".bin" / "eslint").exists() or shutil.which("eslint") is not None:
        code, out = run_gate("npx", ["--no-install", "eslint", "--no-color", "."], worktree_dir)
        if code not in (0, None) and out:
            tail = "\n".join(out.splitlines()[-60:])
            failures.append(f"eslint:\n{tail}")

    if (worktree_dir / "tsconfig.json").is_file():
        code, out = run_gate("npx", ["--no-install", "tsc", "--noEmit"], worktree_dir)
        if code not in (0, None) and out:
            tail = "\n".join(out.splitlines()[-60:])
            failures.append(f"tsc:\n{tail}")

    if (worktree_dir / "package.json").is_file():
        code, out = run_gate("npm", ["test", "--silent"], worktree_dir)
        if code not in (0, None) and out:
            tail = "\n".join(out.splitlines()[-40:])
            failures.append(f"npm test (last 40 lines):\n{tail}")

    return failures


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


def gates_go(worktree_dir: Path) -> list[str]:
    failures: list[str] = []

    # Fast pre-check: migration conflicts break the migrator at test startup,
    # so skip the compiler gates if any are found.
    migration_failures = check_migration_conflicts(worktree_dir)
    if migration_failures:
        return migration_failures

    code, out = run_gate("gofmt", ["-l", "."], worktree_dir)
    if out.strip():
        failures.append(f"gofmt (unformatted files):\n{out.strip()}")

    code, out = run_gate("go", ["vet", "./..."], worktree_dir)
    if code not in (0, None) and out:
        failures.append(f"go vet:\n{out}")

    code, out = run_gate("go", ["test", "./..."], worktree_dir)
    if code not in (0, None) and out:
        tail = "\n".join(out.splitlines()[-40:])
        failures.append(f"go test (last 40 lines):\n{tail}")

    return failures


def gates_rust(worktree_dir: Path) -> list[str]:
    failures: list[str] = []
    code, out = run_gate("cargo", ["fmt", "--check"], worktree_dir)
    if code not in (0, None) and out:
        failures.append(f"cargo fmt --check:\n{out[:600]}")

    code, out = run_gate("cargo", ["clippy", "--", "-D", "warnings"], worktree_dir)
    if code not in (0, None) and out:
        tail = "\n".join(out.splitlines()[-40:])
        failures.append(f"cargo clippy:\n{tail}")

    code, out = run_gate("cargo", ["test", "--quiet"], worktree_dir)
    if code not in (0, None) and out:
        tail = "\n".join(out.splitlines()[-40:])
        failures.append(f"cargo test (last 40 lines):\n{tail}")

    return failures


STACK_GATES: dict[str, Callable[[Path], list[str]]] = {
    "python": gates_python,
    "javascript": gates_javascript_typescript,
    "typescript": gates_javascript_typescript,
    "go": gates_go,
    "rust": gates_rust,
}


def collect_failures(worktree_dir: Path) -> list[str]:
    stacks = detect_stacks(worktree_dir)
    failures: list[str] = []
    seen_dispatchers: set[Callable[[Path], list[str]]] = set()
    for stack in stacks:
        gate_runner = STACK_GATES.get(stack)
        if gate_runner is None or gate_runner in seen_dispatchers:
            continue
        seen_dispatchers.add(gate_runner)
        section = gate_runner(worktree_dir)
        if section:
            failures.append(f"=== {stack} ===\n" + "\n\n".join(section))
    return failures


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
    for ticket in tickets:
        failures = collect_failures(ticket.worktree_dir)
        if failures:
            all_failures.append((ticket.worktree_dir.name, failures))

    if not all_failures:
        return 0

    sections: list[str] = []
    for worktree_name, failures in all_failures:
        sections.append(f"--- {worktree_name} ---\n\n" + "\n\n".join(failures))

    sys.stderr.write(
        "stop_full_gate blocked completion — gate failures detected:\n\n"
        + "\n\n".join(sections)
        + "\n\nFix the failures before presenting Checkpoint 2.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
