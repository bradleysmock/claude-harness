#!/usr/bin/env python3
"""Stop hook: full gate suite on any worktree in 'review-ready' state.

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


def discover_review_ready_ticket(project_root: Path) -> TicketContext | None:
    tickets_root = project_root / ".tickets"
    worktrees_root = project_root / ".worktrees"
    if not tickets_root.is_dir() or not worktrees_root.is_dir():
        return None

    for status_file in tickets_root.glob("*/status.md"):
        text = status_file.read_text(encoding="utf-8", errors="replace")
        if "status: review-ready" not in text:
            continue
        ticket_slug = status_file.parent.name
        worktree_dir = worktrees_root / ticket_slug
        if worktree_dir.is_dir():
            return TicketContext(ticket_dir=status_file.parent, worktree_dir=worktree_dir)

    return None


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
    py_files = changed_files(worktree_dir, ".py")

    if py_files:
        code, out = run_gate("ruff", ["check", "--output-format", "concise", *py_files], worktree_dir)
        if code not in (0, None) and out:
            failures.append(f"ruff:\n{out}")

        code, out = run_gate("bandit", ["-ll", "-q", "-f", "txt", *py_files], worktree_dir)
        if code not in (0, None) and "No issues identified" not in out and out:
            failures.append(f"bandit:\n{out}")

        code, out = run_gate("mypy", ["--no-error-summary", *py_files], worktree_dir)
        if code not in (0, None) and out:
            failures.append(f"mypy:\n{out}")

    code, out = run_gate("pytest", ["-q", "--no-header", "--no-summary"], worktree_dir)
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


def gates_go(worktree_dir: Path) -> list[str]:
    failures: list[str] = []
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

    ticket = discover_review_ready_ticket(project_root)
    if ticket is None:
        return 0

    failures = collect_failures(ticket.worktree_dir)
    if not failures:
        return 0

    sys.stderr.write(
        f"stop_full_gate blocked completion — gates failed on {ticket.worktree_dir.name}:\n\n"
        + "\n\n".join(failures)
        + "\n\nFix the failures before presenting Checkpoint 2.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
