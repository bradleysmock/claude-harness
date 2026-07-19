# harness-combined/tests/test_harness_tickets_branch.py
"""Verification suite for the `.harness-tickets` coordination branch (the design
doc 2026-07-19-harness-tickets-branch-design.md).

Ticket-number allocation and the coarse lifecycle log move OFF `main` onto a
dedicated orphan branch (`harness-tickets` — the design's ".harness-tickets",
with the leading dot dropped because a git ref component may not begin with a
dot). After this: `main` receives exactly ONE commit per delivered ticket and
NOTHING before delivery; the claim/deliver/cancel arbiter is an append-only
`ledger.jsonl` on the coordination branch, published first-push-wins to origin.

Fixtures use a real bare `origin` remote so first-push-wins is genuinely
exercised, mirroring tests/test_ticket_module.py.
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

import ticket

GUARD_PATH = Path(__file__).parent.parent / "hooks" / "ticket_commit_guard.py"
_spec = importlib.util.spec_from_file_location("ticket_commit_guard", GUARD_PATH)
assert _spec and _spec.loader
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

BRANCH = ticket.TICKETS_BRANCH  # "harness-tickets"


# ── fixtures ────────────────────────────────────────────────────────────────

def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _bare(tmp_path: Path) -> Path:
    bare = tmp_path / "origin.git"
    if not bare.exists():
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    return bare


def _clone(tmp_path: Path, name: str, *, seed: bool = False) -> Path:
    bare = _bare(tmp_path)
    clone = tmp_path / name
    subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True)
    subprocess.run(["git", "config", "user.email", f"{name}@x.c"], cwd=clone, check=True)
    subprocess.run(["git", "config", "user.name", name], cwd=clone, check=True)
    if seed:
        (clone / ".tickets").mkdir()
        (clone / ".tickets" / ".keep").write_text("", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=clone, check=True)
        subprocess.run(["git", "commit", "-qm", "seed"], cwd=clone, check=True)
        subprocess.run(["git", "push", "-q", "origin", "HEAD"], cwd=clone, check=True)
        # Point the bare's HEAD at the seeded branch so later clones auto-checkout.
        branch = _git(clone, "rev-parse", "--abbrev-ref", "HEAD")
        subprocess.run(
            ["git", "-C", str(bare), "symbolic-ref", "HEAD", f"refs/heads/{branch}"],
            check=True,
        )
    return clone


def _main_count(repo: Path) -> int:
    return int(_git(repo, "rev-list", "--count", "HEAD"))


def _events(repo: Path) -> list[tuple]:
    return [(r.get("event"), r.get("number")) for r in ticket.ledger_read(repo)]


def _branch_exists(repo: Path, branch: str) -> bool:
    return bool(_git(repo, "branch", "--list", branch))


# ── 1. Number race → distinct numbers + loser renumbers + create-after-push ──

def test_number_race_distinct_numbers_and_loser_renumbers(tmp_path: Path) -> None:
    alice = _clone(tmp_path, "alice", seed=True)
    bob = _clone(tmp_path, "bob")

    # Both start from the same (empty) ledger HEAD, then push in sequence.
    alice_slug = ticket.claim(alice, "alpha", "Alpha", push=True)  # wins 0001
    bob_slug = ticket.claim(bob, "beta", "Beta", push=True)        # loses → renumbers 0002

    assert alice_slug == "0001-alpha"
    assert bob_slug == "0002-beta"
    # distinct claim numbers recorded in the shared ledger
    numbers = sorted(r["number"] for r in ticket.ledger_read(bob) if r["event"] == "claim")
    assert numbers == [1, 2]
    # create-after-push: each winning number got a branch + worktree, and only it
    assert _branch_exists(alice, "ticket/0001-alpha")
    assert (alice / ".worktrees" / "0001-alpha").is_dir()
    assert _branch_exists(bob, "ticket/0002-beta")
    assert (bob / ".worktrees" / "0002-beta").is_dir()
    # the number bob first tried (0001) left NO orphan branch/worktree in bob's repo
    assert not _branch_exists(bob, "ticket/0001-beta")
    assert not (bob / ".worktrees" / "0001-beta").exists()


def test_claim_makes_no_main_commit(tmp_path: Path) -> None:
    alice = _clone(tmp_path, "alice", seed=True)
    before = _main_count(alice)
    ticket.claim(alice, "widget", "Widget", push=True)
    assert _main_count(alice) == before  # arbiter is the ledger line, not a main commit
    assert _events(alice) == [("claim", 1)]


# ── 2. `main` stays clean through claim → design → build → review-ready ──────

def test_main_stays_clean_until_delivery(tmp_path: Path) -> None:
    dev = _clone(tmp_path, "dev", seed=True)
    main_at_claim = _git(dev, "rev-parse", "HEAD")
    slug = ticket.claim(dev, "feature", "Feature", push=True)
    wt = dev / ".worktrees" / slug

    # design → build → review-ready: all branch-only edits + a code change
    (wt / ".tickets" / slug / "solution.md").write_text("# design\n", encoding="utf-8")
    (wt / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
    ticket.set_status(wt, slug, "implementing", push=True)
    ticket.set_status(wt, slug, "review-ready", push=True)
    _git(wt, "add", "-A")
    _git(wt, "commit", "-qm", "feat: feature")

    # main has NO new commit for the ticket…
    assert _git(dev, "rev-parse", "HEAD") == main_at_claim
    assert not (dev / ".tickets" / slug).exists()
    # …the ledger shows the claim…
    assert ("claim", 1) in _events(dev)
    # …and the branch carries the full ticket dir.
    assert (wt / ".tickets" / slug / "solution.md").exists()
    assert (wt / ".tickets" / slug / "status.md").exists()


# ── 3. Delivery is exactly one main commit + one `delivered` ledger line ─────

def test_delivery_is_one_main_commit_and_one_delivered_event(tmp_path: Path) -> None:
    dev = _clone(tmp_path, "dev", seed=True)
    slug = ticket.claim(dev, "thing", "Thing", push=True)
    wt = dev / ".worktrees" / slug
    (wt / "thing.py").write_text("VALUE = 1\n", encoding="utf-8")
    ticket.set_status(wt, slug, "review-ready", push=True)
    _git(wt, "add", "-A")
    _git(wt, "commit", "-qm", "feat: thing")
    _git(wt, "push", "-q", "-u", "origin", f"ticket/{slug}")

    main_before = _main_count(dev)
    subject = ticket.deliver_squash(dev, f"ticket/{slug}", slug, "Thing")

    assert "(squash)" in subject
    assert _main_count(dev) - main_before == 1  # exactly one main commit
    assert _git(dev, "rev-list", "--merges", "--count", "HEAD~1..HEAD") == "0"
    tree = _git(dev, "ls-tree", "-r", "--name-only", "HEAD")
    assert "thing.py" in tree
    assert f".tickets/completed/{slug}/status.md" in tree
    assert f".tickets/{slug}/status.md" not in tree
    # exactly one delivered ledger line, carrying the squash SHA
    delivered = [r for r in ticket.ledger_read(dev) if r["event"] == "delivered"]
    assert len(delivered) == 1
    assert delivered[0]["number"] == 1
    assert delivered[0]["sha"] == _git(dev, "rev-parse", "HEAD")
    assert not _branch_exists(dev, f"ticket/{slug}")


# ── 4. Cancel is `main`-free ────────────────────────────────────────────────

def test_cancel_is_main_free_and_docs_recoverable(tmp_path: Path) -> None:
    dev = _clone(tmp_path, "dev", seed=True)
    slug = ticket.claim(dev, "scrap", "Scrap", push=True)
    wt = dev / ".worktrees" / slug
    (wt / ".tickets" / slug / "solution.md").write_text("# scrap design\n", encoding="utf-8")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-qm", "wip")
    _git(wt, "push", "-q", "-u", "origin", f"ticket/{slug}")

    main_before = _main_count(dev)
    number = ticket.cancel(dev, slug, push=True)

    assert number == 1
    assert _main_count(dev) == main_before  # no main commit
    assert ("cancelled", 1) in _events(dev)
    assert not _branch_exists(dev, f"ticket/{slug}")
    assert not (dev / ".worktrees" / slug).exists()
    # docs archived onto the coordination branch, recoverable for /reopen
    archived = _git(dev, "ls-tree", "-r", "--name-only", f"origin/{BRANCH}")
    assert f"cancelled/{slug}/solution.md" in archived


def test_reopen_restores_cancelled_docs_on_fresh_branch(tmp_path: Path) -> None:
    dev = _clone(tmp_path, "dev", seed=True)
    slug = ticket.claim(dev, "scrap", "Scrap", push=True)
    wt = dev / ".worktrees" / slug
    (wt / ".tickets" / slug / "solution.md").write_text("# scrap design\n", encoding="utf-8")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-qm", "wip")
    _git(wt, "push", "-q", "-u", "origin", f"ticket/{slug}")
    ticket.cancel(dev, slug, push=True)

    reopened = ticket.reopen(dev, slug, push=True)
    assert reopened == slug
    restored = dev / ".worktrees" / slug / ".tickets" / slug
    assert (restored / "solution.md").read_text(encoding="utf-8") == "# scrap design\n"
    assert ticket.parse_status(restored / "status.md")["status"] == "solution"
    assert ("reopened", 1) in _events(dev)


# ── 5. Bootstrap + migration seeds the ledger and continues numbering ────────

def test_ensure_tickets_branch_bootstraps_orphan(tmp_path: Path) -> None:
    dev = _clone(tmp_path, "dev", seed=True)
    # no coordination branch yet
    assert (
        subprocess.run(
            ["git", "-C", str(dev), "rev-parse", "--verify", "--quiet", f"origin/{BRANCH}"],
            capture_output=True, text=True,
        ).returncode != 0
    )
    ticket.ensure_tickets_branch(dev, push=True)
    # orphan created on origin with an (empty) ledger.jsonl
    assert _git(dev, "ls-tree", "-r", "--name-only", f"origin/{BRANCH}") == ticket.LEDGER_FILE
    assert ticket.ledger_read(dev) == []
    assert ticket.next_number(dev) == 1


def test_migrate_seeds_from_filesystem_and_continues_numbering(tmp_path: Path) -> None:
    dev = _clone(tmp_path, "dev", seed=True)
    # simulate the pre-existing state: in-flight + completed ticket dirs on main
    for name, status in [("0053-alpha", "solution"), ("0054-beta", "implementing")]:
        d = dev / ".tickets" / name
        d.mkdir(parents=True)
        (d / "status.md").write_text(
            f"status: {status}\nticket: {name[:4]}\ntitle: {name}\n"
            f"branch: ticket/{name}\nowner: dev@x.c\n",
            encoding="utf-8",
        )
    for name, status in [("0051-old", "done"), ("0052-dropped", "cancelled")]:
        d = dev / ".tickets" / "completed" / name
        d.mkdir(parents=True)
        (d / "status.md").write_text(
            f"status: {status}\nticket: {name[:4]}\ntitle: {name}\n"
            f"branch: ticket/{name}\nowner: dev@x.c\n",
            encoding="utf-8",
        )
    _git(dev, "add", "-A")
    _git(dev, "commit", "-qm", "pre-existing tickets")

    count = ticket.migrate(dev, push=True)
    assert count > 0
    events = _events(dev)
    # a claim per ticket (4) + terminal events for the two completed ones
    assert ("claim", 51) in events and ("claim", 52) in events
    assert ("claim", 53) in events and ("claim", 54) in events
    assert ("delivered", 51) in events   # completed + done
    assert ("cancelled", 52) in events   # completed + cancelled
    # numbering continues from the migrated max, no collision
    assert ticket.next_number(dev) == 55

    # migration is idempotent — a second run appends nothing
    assert ticket.migrate(dev, push=True) == 0


# ── 6. Guards ───────────────────────────────────────────────────────────────

def test_guard_blocks_tickets_branch_merge_source() -> None:
    assert guard.is_tickets_branch_merge(BRANCH) is True
    assert guard.is_tickets_branch_merge(f"refs/heads/{BRANCH}") is True
    assert guard.is_tickets_branch_merge("main") is False
    assert guard.is_tickets_branch_merge("ticket/0001-x") is False


def test_deliver_refuses_to_merge_coordination_branch(tmp_path: Path) -> None:
    dev = _clone(tmp_path, "dev", seed=True)
    with pytest.raises(RuntimeError, match="never merged"):
        ticket.deliver_squash(dev, BRANCH, "0001-x", "X")


def test_guard_blocks_inflight_ticket_dir_staged_on_main(tmp_path: Path) -> None:
    dev = _clone(tmp_path, "dev", seed=True)
    # stage an in-flight ticket dir directly onto main (the forbidden pattern)
    d = dev / ".tickets" / "0001-x"
    d.mkdir(parents=True)
    (d / "status.md").write_text("status: claimed\n", encoding="utf-8")
    _git(dev, "add", "--", ".tickets/0001-x/")
    flagged = guard.staged_inflight_ticket_dirs(dev)
    assert any("0001-x" in f for f in flagged)

    # a staged completed/ archive is allowed (delivered docs may reach main)
    _git(dev, "reset", "-q")
    c = dev / ".tickets" / "completed" / "0002-y"
    c.mkdir(parents=True)
    (c / "status.md").write_text("status: done\n", encoding="utf-8")
    _git(dev, "add", "--", ".tickets/completed/0002-y/")
    assert guard.staged_inflight_ticket_dirs(dev) == []


def test_guard_blocks_unpushed_ledger_mutation(tmp_path: Path) -> None:
    dev = _clone(tmp_path, "dev", seed=True)
    ticket.ensure_tickets_branch(dev, push=True)
    # forge a LOCAL harness-tickets branch that is ahead of origin (unpushed)
    _git(dev, "branch", BRANCH, f"origin/{BRANCH}")
    wt = tmp_path / "ledger-wt"
    _git(dev, "worktree", "add", "-q", str(wt), BRANCH)
    (wt / ticket.LEDGER_FILE).write_text(
        '{"event":"claim","number":1,"slug":"x","ts":"t"}\n', encoding="utf-8"
    )
    _git(wt, "add", "-A")
    _git(wt, "commit", "-qm", "local-only ledger mutation")

    unpushed = guard.unpushed_ledger_commits(dev)
    assert len(unpushed) == 1  # the local-only commit is detected

    # after publishing, the guard is clear
    _git(dev, "push", "-q", "origin", BRANCH)
    assert guard.unpushed_ledger_commits(dev) == []


def test_guard_noop_when_no_local_coordination_branch(tmp_path: Path) -> None:
    dev = _clone(tmp_path, "dev", seed=True)
    ticket.ensure_tickets_branch(dev, push=True)
    # normal remote flow keeps no local harness-tickets branch → nothing unpushed
    assert guard.unpushed_ledger_commits(dev) == []


# ── Cross-cutting query surface: ledger-based enumeration ───────────────────

def test_list_tickets_enumerates_from_ledger_not_main(tmp_path: Path) -> None:
    dev = _clone(tmp_path, "dev", seed=True)
    # in-flight ticket: claim + branch-only fine status/effort in the worktree
    slug = ticket.claim(dev, "inflight", "In Flight", push=True)
    wt = dev / ".worktrees" / slug
    status_md = wt / ".tickets" / slug / "status.md"
    text = status_md.read_text(encoding="utf-8")
    text = text.replace("status: claimed", "status: implementing") + "effort: medium\n"
    status_md.write_text(text, encoding="utf-8")

    rows = ticket.list_tickets(dev)
    assert len(rows) == 1
    row = rows[0]
    # in-flight enumeration comes from the ledger + the worktree fine status —
    # NOT from `main`, which has no `.tickets/0001-inflight/` at all
    assert not (dev / ".tickets" / slug).exists()
    assert row["number"] == "0001"
    assert row["status"] == "implementing"  # joined from the worktree, not "claimed"
    assert row["effort"] == "medium"
    assert row["completed"] is False


def test_list_tickets_includes_delivered_from_completed(tmp_path: Path) -> None:
    dev = _clone(tmp_path, "dev", seed=True)
    slug = ticket.claim(dev, "ship", "Ship", push=True)
    wt = dev / ".worktrees" / slug
    (wt / "ship.py").write_text("V=1\n", encoding="utf-8")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-qm", "feat: ship")
    _git(wt, "push", "-q", "-u", "origin", f"ticket/{slug}")
    ticket.deliver_squash(dev, f"ticket/{slug}", slug, "Ship")

    rows = ticket.list_tickets(dev)
    delivered = [r for r in rows if r["number"] == "0001"]
    assert len(delivered) == 1  # surfaced once, from main's completed/
    assert delivered[0]["completed"] is True
    assert delivered[0]["status"] == "done"
