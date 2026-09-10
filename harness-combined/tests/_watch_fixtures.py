"""Shared repo/ticket-seeding helpers for the ticket 0078 test suite.

Not a `test_*` module — not collected by pytest — so both
`test_0078_autopilot_watch_core.py` and `test_0078_autopilot_watch_cli.py`
import these directly instead of duplicating them or reaching into each
other's module.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import ticket


def init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=repo, check=True)
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)
    return repo


def seed_claim(repo: Path, number: int, slug: str) -> None:
    ticket.ledger_append(
        repo,
        lambda recs, number=number, slug=slug: (
            [{
                "event": "claim", "number": number, "slug": slug,
                "title": slug, "owner": "dev@example.com",
                "branch": f"ticket/{number:04d}-{slug}", "ts": "t",
            }],
            None,
        ),
        push=False,
    )


def seed_ticket_branch_and_worktree(
    repo: Path, number: int, slug: str, status_fields: dict[str, str]
) -> tuple[Path, Path]:
    full = f"{number:04d}-{slug}"
    branch = f"ticket/{full}"
    subprocess.run(["git", "branch", branch], cwd=repo, check=True)
    worktree = repo / ".worktrees" / full
    subprocess.run(["git", "worktree", "add", "-q", str(worktree), branch], cwd=repo, check=True)
    ticket_dir = worktree / ".tickets" / full
    ticket_dir.mkdir(parents=True)
    for name in ("problem.md", "requirements.md", "solution.md"):
        (ticket_dir / name).write_text(f"{name} v1\n", encoding="utf-8")
    lines = "\n".join(f"{key}: {value}" for key, value in status_fields.items())
    (ticket_dir / "status.md").write_text(lines + "\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=worktree, check=True)
    subprocess.run(["git", "commit", "-qm", "design"], cwd=worktree, check=True)
    return worktree, ticket_dir


def head(worktree: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def approve(worktree: Path, ticket_dir: Path, approved_commit: str) -> None:
    text = (ticket_dir / "status.md").read_text(encoding="utf-8")
    text = text.rstrip("\n") + f"\napproved-at: 2026-09-10\napproved-commit: {approved_commit}\n"
    (ticket_dir / "status.md").write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(worktree), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(worktree), "commit", "-qm", "chore: approve"], check=True)


def base_fields(number: int, slug: str) -> dict[str, str]:
    full = f"{number:04d}-{slug}"
    return {
        "status": "solution", "ticket": f"{number:04d}", "title": slug,
        "branch": f"ticket/{full}", "owner": "dev@example.com",
        "source": "local", "external_id": "", "updated": "2026-09-10",
        "approved-at": "", "approved-commit": "",
    }
