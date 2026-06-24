# harness-combined/ticket.py
"""Ticket state operations: number claiming, status transitions, owner.

Centralizes the git-backed ticket bookkeeping the markdown commands used to
inline by hand. Every mutation does its own scoped commit so ticket metadata
is never left uncommitted (the orphaned-update bug this module exists to kill).

Stdlib only. subprocess always called with argument lists.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path


def find_tickets_root(start: Path) -> Path:
    cur = start.resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / ".tickets").is_dir():
            return candidate / ".tickets"
    raise FileNotFoundError(f"no .tickets/ found at or above {start}")


def _ticket_number(dir_name: str) -> int | None:
    head = dir_name[:4]
    return int(head) if head.isdigit() else None


def next_number(tickets_root: Path) -> int:
    numbers: list[int] = []
    search_dirs = [tickets_root, tickets_root / "completed"]
    for base in search_dirs:
        if not base.is_dir():
            continue
        for child in base.iterdir():
            if not child.is_dir():
                continue
            n = _ticket_number(child.name)
            if n is not None:
                numbers.append(n)
    return (max(numbers) + 1) if numbers else 1


def format_number(n: int) -> str:
    return f"{n:04d}"


def parse_status(status_md: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in status_md.read_text(encoding="utf-8").splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def owner(repo: Path) -> str:
    proc = git(repo, "config", "user.email", check=False)
    return proc.stdout.strip()


def resolve_ticket_dir(tickets_root: Path, ident: str) -> Path:
    for base in (tickets_root, tickets_root / "completed"):
        if not base.is_dir():
            continue
        matches = sorted(p for p in base.glob(f"{ident}*") if p.is_dir())
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise RuntimeError(f"ambiguous ticket id {ident!r}: {[m.name for m in matches]}")
    raise FileNotFoundError(f"no ticket directory for {ident!r}")


def _rewrite_field(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}:"):
            lines[i] = f"{key}: {value}"
            found = True
            break
    if not found:
        lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def set_status(repo: Path, ident: str, new_status: str, *, push: bool = False) -> str:
    tickets_root = repo / ".tickets"
    ticket_dir = resolve_ticket_dir(tickets_root, ident)
    status_md = ticket_dir / "status.md"
    text = status_md.read_text(encoding="utf-8")
    text = _rewrite_field(text, "status", new_status)
    text = _rewrite_field(text, "updated", date.today().isoformat())
    status_md.write_text(text, encoding="utf-8")

    number = parse_status(status_md).get("ticket", ident)
    rel = ticket_dir.relative_to(repo)
    git(repo, "add", "--", str(rel))
    subject = f"chore(ticket): {number} → {new_status}"
    git(repo, "commit", "-m", subject)
    if push:
        git(repo, "push")
    return subject


def _has_remote(repo: Path) -> bool:
    return bool(git(repo, "remote", check=False).stdout.strip())


def _write_stub(ticket_dir: Path, number_str: str, slug: str, title: str, who: str) -> None:
    ticket_dir.mkdir(parents=True, exist_ok=True)
    (ticket_dir / "status.md").write_text(
        f"status: claimed\nticket: {number_str}\ntitle: {title}\n"
        f"branch: ticket/{number_str}-{slug}\nowner: {who}\n"
        f"source: local\nexternal_id:\nupdated: {date.today().isoformat()}\n",
        encoding="utf-8",
    )


def claim(repo: Path, slug: str, title: str, *, push: bool = False, max_retries: int = 5) -> str:
    tickets_root = repo / ".tickets"
    who = owner(repo)
    remote = push and _has_remote(repo)
    if remote:
        git(repo, "fetch", "origin", check=False)

    number_str = ""
    for attempt in range(max_retries + 1):
        number_str = format_number(next_number(tickets_root))
        full_slug = f"{number_str}-{slug}"
        ticket_dir = tickets_root / full_slug
        _write_stub(ticket_dir, number_str, slug, title, who)
        git(repo, "add", "--", str(ticket_dir.relative_to(repo)))
        git(repo, "commit", "-m", f"chore(ticket): {number_str} claim")
        if not remote:
            return full_slug
        push_proc = git(repo, "push", check=False)
        if push_proc.returncode == 0:
            return full_slug
        # Someone claimed first. Rebase, drop our number, retry with a higher one.
        git(repo, "reset", "--hard", "HEAD~1", check=False)
        pull_proc = git(repo, "pull", "--rebase", check=False)
        if pull_proc.returncode != 0:
            git(repo, "rebase", "--abort", check=False)
            raise RuntimeError(
                f"claim: rebase failed while renumbering: {pull_proc.stderr.strip()}"
            )
    raise RuntimeError(f"claim exhausted {max_retries} retries (last tried {number_str})")


def _main(argv: list[str]) -> int:
    if not argv:
        print("usage: ticket <set-status|owner> ...", file=sys.stderr)
        return 2
    repo = find_tickets_root(Path.cwd()).parent
    cmd = argv[0]
    if cmd == "owner":
        print(owner(repo))
        return 0
    if cmd == "set-status":
        push = "--push" in argv
        positional = [a for a in argv[1:] if not a.startswith("--")]
        print(set_status(repo, positional[0], positional[1], push=push))
        return 0
    print(f"unknown command {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
