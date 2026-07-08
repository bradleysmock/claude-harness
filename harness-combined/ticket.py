# harness-combined/ticket.py
"""Ticket state operations: number claiming, status transitions, owner.

Centralizes the git-backed ticket bookkeeping the markdown commands used to
inline by hand. Every mutation does its own scoped commit so ticket metadata
is never left uncommitted (the orphaned-update bug this module exists to kill).

Stdlib only. subprocess always called with argument lists.
"""
from __future__ import annotations

import json
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
        _push_current_branch(repo)
    return subject


def _has_remote(repo: Path) -> bool:
    return bool(git(repo, "remote", check=False).stdout.strip())


def _push_current_branch(repo: Path) -> bool:
    """Push HEAD's branch and report whether it is safe to proceed.

    Branch-only ticket states live on a worktree branch with no upstream yet —
    fall back to `push -u origin <branch>` so the first transition publishes the
    branch. Returns True when there is nothing to publish (no remote — local-only
    is expected) or the push succeeded; False only when a remote exists but the
    push was rejected, so destructive callers (delivery cleanup) can stop."""
    if not _has_remote(repo):
        return True
    proc = git(repo, "push", check=False)
    if proc.returncode == 0:
        return True
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD", check=False).stdout.strip()
    if branch and branch != "HEAD":
        return git(repo, "push", "-u", "origin", branch, check=False).returncode == 0
    return False


def _write_stub(ticket_dir: Path, number_str: str, slug: str, title: str, who: str) -> None:
    ticket_dir.mkdir(parents=True, exist_ok=True)
    (ticket_dir / "status.md").write_text(
        f"status: claimed\nticket: {number_str}\ntitle: {title}\n"
        f"branch: ticket/{number_str}-{slug}\nowner: {who}\n"
        f"source: local\nexternal_id:\nupdated: {date.today().isoformat()}\n",
        encoding="utf-8",
    )


def _create_branch_and_worktree(repo: Path, full_slug: str) -> None:
    """Create branch ticket/<full_slug> and its worktree .worktrees/<full_slug>.

    Called only AFTER the winning claim push (create-after-push), so a
    renumber-on-reject never leaves an orphaned branch or worktree behind.
    Best-effort and idempotent: skip if the branch already exists (resume)."""
    branch = f"ticket/{full_slug}"
    if git(repo, "branch", "--list", branch, check=False).stdout.strip():
        return
    worktree = repo / ".worktrees" / full_slug
    git(repo, "worktree", "add", str(worktree), "-b", branch, check=False)


def claim(repo: Path, slug: str, title: str, *, push: bool = False, max_retries: int = 5) -> str:
    tickets_root = repo / ".tickets"
    who = owner(repo)
    remote = push and _has_remote(repo)
    if remote:
        git(repo, "fetch", "origin", check=False)

    full_slug = ""
    for _attempt in range(max_retries + 1):
        number_str = format_number(next_number(tickets_root))
        full_slug = f"{number_str}-{slug}"
        ticket_dir = tickets_root / full_slug
        _write_stub(ticket_dir, number_str, slug, title, who)
        git(repo, "add", "--", str(ticket_dir.relative_to(repo)))
        git(repo, "commit", "-m", f"chore(ticket): {number_str} claim")
        if not remote:
            break
        push_proc = git(repo, "push", check=False)
        if push_proc.returncode == 0:
            break
        # Someone claimed first. Rebase, drop our number, retry with a higher one.
        # The number is dropped BEFORE any branch/worktree is created, so the
        # renumber leaves nothing orphaned.
        git(repo, "reset", "--hard", "HEAD~1", check=False)
        pull_proc = git(repo, "pull", "--rebase", check=False)
        if pull_proc.returncode != 0:
            git(repo, "rebase", "--abort", check=False)
            raise RuntimeError(
                f"claim: rebase failed while renumbering: {pull_proc.stderr.strip()}"
            )
    else:
        raise RuntimeError(f"claim exhausted {max_retries} retries (last tried {full_slug})")

    # Create-after-push: only the winning number reaches here.
    _create_branch_and_worktree(repo, full_slug)
    return full_slug


def _fold_archive(repo: Path, slug: str) -> None:
    """Fold a staged ticket dir into the pending delivery commit.

    OS-mv the (staged) `.tickets/<slug>/` into `completed/`, rewrite its status →
    `done`, then clear the staged old path and stage the archived one. Mirrors the
    archive pattern (OS mv + `git rm --cached` + `git add`) — never `git mv`, which
    is unsound against the index a `merge --squash` / `cherry-pick -n` leaves. The
    code changes already staged by the caller remain staged. Idempotent: a ticket
    already archived (dst present, src gone) is left as-is."""
    completed = repo / ".tickets" / "completed"
    completed.mkdir(parents=True, exist_ok=True)
    src = repo / ".tickets" / slug
    dst = completed / slug
    if src.is_dir() and not dst.exists():
        src.rename(dst)
    status_md = dst / "status.md"
    if status_md.exists():
        text = status_md.read_text(encoding="utf-8")
        text = _rewrite_field(text, "status", "done")
        text = _rewrite_field(text, "updated", date.today().isoformat())
        status_md.write_text(text, encoding="utf-8")
    git(repo, "rm", "-r", "--cached", "--", f".tickets/{slug}/", check=False)
    git(repo, "add", "--", f".tickets/completed/{slug}/")


def deliver_squash(repo: Path, branch: str, slug: str, title: str) -> str:
    """Deliver a ticket branch as a single squashed commit on the current branch.

    Mirrors the archive pattern (OS mv + `git rm --cached` + `git add`) — never
    `git mv`, which is unsound against the index `merge --squash` leaves. Folds the
    `→ done` transition and the `completed/` archive into the one squash commit, so
    a normally-delivered ticket adds exactly one commit at delivery."""
    # 1. Stage the whole branch diff (code + branch's .tickets/<slug>/) — no commit,
    #    and no merge commit, so commits-since-claim stays at one.
    git(repo, "merge", "--squash", branch)

    # 2-4. Fold the → done transition + completed/ archive into the pending commit.
    _fold_archive(repo, slug)

    # 5. One commit: full code diff + completed/<slug>/ at done, no .tickets/<slug>/.
    subject = f"feat: {slug} {title} (squash)"
    git(repo, "commit", "-m", subject)

    # 6. Publish FIRST. Only on a successful publish do we destroy the worktree and
    #    branch — otherwise the squashed commit would survive only locally while its
    #    source history is deleted. On a rejected push (e.g. another developer advanced
    #    main between the squash and the push), stop with everything intact so the lead
    #    can rebase and retry. `git branch -D` (not -d) because a squash leaves the
    #    branch without merge ancestry, so git never considers it "fully merged".
    if not _push_current_branch(repo):
        raise RuntimeError(
            f"deliver_squash: pushing the squashed commit to origin was rejected — "
            f"leaving the worktree and branch {branch!r} intact. Rebase onto the "
            f"updated main and retry the delivery."
        )
    git(repo, "worktree", "remove", "--force", str(repo / ".worktrees" / slug), check=False)
    git(repo, "branch", "-D", branch, check=False)
    return subject


def _batch_worktree(batch_branch: str) -> str:
    """`.worktrees/` dir name for a batch branch: `batch/<slug>` → `batch-<slug>`
    (worktree dir names cannot carry the branch's `/`)."""
    return batch_branch.replace("/", "-", 1)


def deliver_squash_batch(
    repo: Path, batch_branch: str, members: list[dict[str, str]]
) -> list[str]:
    """Deliver a batch integration branch as one squashed commit *per member*.

    `members` is an ordered list of `{"slug", "title", "head"}`, where `head` is
    the boundary rev on `batch_branch` that ends that member's commit range. The
    last member's `head` should be batch HEAD so combined-critic repairs (made
    after the last member's build) fold into that member's commit.

    Each member's cumulative delta is cherry-picked (`-n`, so its per-source
    commits collapse to one) onto the current branch and committed as a single
    `feat: <slug> <title> (squash)` commit that also folds that member's
    `completed/<slug>/` archive at `done`. The commits publish in ONE push — so a
    batch is atomic on `main` — and only on a successful publish are the batch
    branch and every member's vestigial per-ticket branch/worktree removed. A
    cherry-pick conflict or a rejected push raises with everything intact
    (fail-closed), mirroring `deliver_squash`."""
    subjects: list[str] = []
    prev = "HEAD"
    for member in members:
        slug, title, head = member["slug"], member["title"], member["head"]
        # Squash this member's range onto the delivery line. `cherry-pick -n` of a
        # rev range applies every commit in prev..head with no per-commit history.
        picked = git(repo, "cherry-pick", "--no-commit", f"{prev}..{head}", check=False)
        if picked.returncode != 0:
            git(repo, "cherry-pick", "--abort", check=False)
            raise RuntimeError(
                f"deliver_squash_batch: cherry-pick of member {slug!r} range "
                f"{prev}..{head} conflicted: {picked.stderr.strip()} — batch branch "
                f"{batch_branch!r} and all member branches left intact."
            )
        _fold_archive(repo, slug)
        subject = f"feat: {slug} {title} (squash)"
        git(repo, "commit", "-m", subject)
        subjects.append(subject)
        prev = head

    # Publish all N commits atomically. Only on a successful publish do we destroy
    # the source history — otherwise the squashed commits would survive only locally
    # while their branches are deleted. On a rejected push, stop with everything
    # intact so the lead can rebase and retry.
    if not _push_current_branch(repo):
        raise RuntimeError(
            f"deliver_squash_batch: pushing the {len(subjects)} squashed commit(s) to "
            f"origin was rejected — leaving the batch branch {batch_branch!r} and every "
            f"member branch intact. Rebase onto the updated main and retry the delivery."
        )

    git(
        repo, "worktree", "remove", "--force",
        str(repo / ".worktrees" / _batch_worktree(batch_branch)), check=False,
    )
    git(repo, "branch", "-D", batch_branch, check=False)
    for member in members:
        slug = member["slug"]
        git(repo, "worktree", "remove", "--force", str(repo / ".worktrees" / slug), check=False)
        git(repo, "branch", "-D", f"ticket/{slug}", check=False)
    return subjects


def _main(argv: list[str]) -> int:
    if not argv:
        print("usage: ticket <claim|set-status|owner> ...", file=sys.stderr)
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
    if cmd == "claim":
        push = "--push" in argv
        positional = [a for a in argv[1:] if not a.startswith("--")]
        if len(positional) < 2:
            print("usage: ticket claim <slug> <title> [--push]", file=sys.stderr)
            return 2
        print(claim(repo, positional[0], positional[1], push=push))
        return 0
    if cmd == "deliver-batch":
        positional = [a for a in argv[1:] if not a.startswith("--")]
        if len(positional) < 2:
            print(
                "usage: ticket deliver-batch <batch-branch> <members.json>",
                file=sys.stderr,
            )
            return 2
        batch_branch, members_path = positional[0], positional[1]
        members = json.loads(Path(members_path).read_text(encoding="utf-8"))
        for subject in deliver_squash_batch(repo, batch_branch, members):
            print(subject)
        return 0
    print(f"unknown command {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
