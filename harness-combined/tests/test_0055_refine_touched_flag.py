# harness-combined/tests/test_0055_refine_touched_flag.py
"""Tests for ticket 0055 — persisting the refine-touched flag to disk as
`refine-touched.md`.

Two kinds of coverage, per the ticket's Test Plan:

  - Unit (git-sim, mirroring tests/test_ticket_module.py and
    tests/test_batch_delivery.py): `_fold_archive` deletes the marker on
    archive; `deliver_squash_batch` raises before any cherry-pick when any
    member carries the marker, regardless of position; no-marker paths are
    unaffected (regression guard).
  - Integration (content-verification, mirroring tests/test_ticket_archiving.py
    and tests/test_0053_llm_python_boundary.py): the marker literal and the
    branch/worktree-copy resolution wording appear in spec-remediation.md,
    autopilot-ticket.md, deliver-ticket.md, and autopilot-batch.md.
"""
import subprocess
from pathlib import Path

import ticket

ROOT = Path(__file__).parent.parent


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


# ── Unit: _fold_archive marker deletion (FR-5) ─────────────────────────────

def _init_repo_with_ticket(tmp_path: Path, marker: bool) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "config", "user.email", "d@x.c")
    _git(repo, "config", "user.name", "d")
    tdir = repo / ".tickets" / "0001-thing"
    tdir.mkdir(parents=True)
    (tdir / "status.md").write_text(
        "status: review-ready\nticket: 0001\ntitle: Thing\n"
        "branch: ticket/0001-thing\nowner: d@x.c\nupdated: 2026-06-23\n",
        encoding="utf-8",
    )
    if marker:
        (tdir / "refine-touched.md").write_text(
            "date: 2026-06-23\nchecks: FR count\n", encoding="utf-8"
        )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "seed")
    return repo


def test_fold_archive_deletes_refine_touched_marker(tmp_path: Path) -> None:
    repo = _init_repo_with_ticket(tmp_path, marker=True)
    ticket._fold_archive(repo, "0001-thing")
    dst = repo / ".tickets" / "completed" / "0001-thing"
    assert dst.is_dir()
    assert not (dst / "refine-touched.md").exists()
    assert "status: done" in (dst / "status.md").read_text(encoding="utf-8")


def test_fold_archive_without_marker_is_unaffected(tmp_path: Path) -> None:
    repo = _init_repo_with_ticket(tmp_path, marker=False)
    ticket._fold_archive(repo, "0001-thing")
    dst = repo / ".tickets" / "completed" / "0001-thing"
    assert dst.is_dir()
    assert not (dst / "refine-touched.md").exists()
    assert "status: done" in (dst / "status.md").read_text(encoding="utf-8")


# ── Unit: deliver_squash_batch refuses a marked member (FR-6) ─────────────

def _init_main_with_claims(repo: Path, members: list[tuple[str, str, str]]) -> None:
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "config", "user.email", "d@x.c")
    _git(repo, "config", "user.name", "d")
    for number, slug, title in members:
        tdir = repo / ".tickets" / f"{number}-{slug}"
        tdir.mkdir(parents=True)
        (tdir / "status.md").write_text(
            f"status: claimed\nticket: {number}\ntitle: {title}\n"
            f"branch: ticket/{number}-{slug}\nowner: d@x.c\n"
            f"source: local\nexternal_id:\nupdated: 2026-07-08\n",
            encoding="utf-8",
        )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "chore(ticket): claims")


def _build_member_range(
    repo: Path, number: str, slug: str, title: str, *, marker: bool = False
) -> str:
    tdir = repo / ".tickets" / f"{number}-{slug}"
    (tdir / "status.md").write_text(
        f"status: review-ready\nticket: {number}\ntitle: {title}\n"
        f"branch: ticket/{number}-{slug}\nowner: d@x.c\nupdated: 2026-07-08\n",
        encoding="utf-8",
    )
    (tdir / "solution.md").write_text(f"# {title}\n", encoding="utf-8")
    if marker:
        (tdir / "refine-touched.md").write_text(
            "date: 2026-07-08\nchecks: FR count\n", encoding="utf-8"
        )
    (repo / f"{slug}.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", f"feat: {number} {slug}")
    return _git(repo, "rev-parse", "HEAD")


def _three_member_batch(tmp_path: Path, marked_slug: str) -> tuple[Path, list[dict], str]:
    """A 3-member batch where exactly `marked_slug` carries the marker.

    Returns (repo, members, claim_base_rev)."""
    repo = tmp_path / "repo"
    _init_main_with_claims(
        repo,
        [("0001", "alpha", "Alpha"), ("0002", "beta", "Beta"), ("0003", "gamma", "Gamma")],
    )
    claim_base = _git(repo, "rev-parse", "HEAD")
    main = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    _git(repo, "checkout", "-qb", "batch/0001-alpha")
    heads = {}
    for number, slug, title in [("0001", "alpha", "Alpha"), ("0002", "beta", "Beta"), ("0003", "gamma", "Gamma")]:
        full = f"{number}-{slug}"
        heads[full] = _build_member_range(repo, number, slug, title, marker=(full == marked_slug))
    _git(repo, "checkout", "-q", main)
    members = [
        {"slug": "0001-alpha", "title": "Alpha", "head": heads["0001-alpha"]},
        {"slug": "0002-beta", "title": "Beta", "head": heads["0002-beta"]},
        {"slug": "0003-gamma", "title": "Gamma", "head": heads["0003-gamma"]},
    ]
    return repo, members, claim_base


def _assert_no_batch_side_effects(repo: Path) -> None:
    porcelain = _git(repo, "status", "--porcelain")
    assert porcelain == ""
    # only the pre-existing claim commit is on main — no delivery commit landed.
    assert _git(repo, "rev-list", "--count", "HEAD") == "1"


def test_deliver_squash_batch_raises_for_marker_first(tmp_path: Path) -> None:
    repo, members, _ = _three_member_batch(tmp_path, marked_slug="0001-alpha")
    try:
        ticket.deliver_squash_batch(repo, "batch/0001-alpha", members)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "0001-alpha" in str(exc)
    _assert_no_batch_side_effects(repo)
    assert _git(repo, "branch", "--list", "batch/0001-alpha") != ""


def test_deliver_squash_batch_raises_for_marker_middle(tmp_path: Path) -> None:
    repo, members, _ = _three_member_batch(tmp_path, marked_slug="0002-beta")
    try:
        ticket.deliver_squash_batch(repo, "batch/0001-alpha", members)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "0002-beta" in str(exc)
    _assert_no_batch_side_effects(repo)


def test_deliver_squash_batch_raises_for_marker_last(tmp_path: Path) -> None:
    repo, members, _ = _three_member_batch(tmp_path, marked_slug="0003-gamma")
    try:
        ticket.deliver_squash_batch(repo, "batch/0001-alpha", members)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "0003-gamma" in str(exc)
    _assert_no_batch_side_effects(repo)


def test_deliver_squash_batch_no_marker_unaffected(tmp_path: Path) -> None:
    repo, members, claim_base = _three_member_batch(tmp_path, marked_slug="")
    subjects = ticket.deliver_squash_batch(repo, "batch/0001-alpha", members)
    assert subjects == [
        "feat: 0001-alpha Alpha (squash)",
        "feat: 0002-beta Beta (squash)",
        "feat: 0003-gamma Gamma (squash)",
    ]
    assert _git(repo, "rev-list", "--count", f"{claim_base}..HEAD") == "3"


# ── Content verification: the four flow docs (FR-1..4, FR-7, FR-8) ────────

def test_marker_literal_in_all_four_docs() -> None:
    for rel in (
        "context/spec-remediation.md",
        "context/flows/autopilot-ticket.md",
        "context/flows/deliver-ticket.md",
        "context/flows/autopilot-batch.md",
    ):
        assert "refine-touched.md" in read(rel), f"missing marker literal in {rel}"


def test_spec_remediation_s2_writes_marker_before_refine() -> None:
    content = read("context/spec-remediation.md")
    s2 = content.split("### S2", 1)[1].split("### Hard-stop", 1)[0]
    assert "refine-touched.md" in s2
    assert "before" in s2 and "/refine" in s2
    assert "bail" in s2.lower()


def test_autopilot_ticket_step_b_checks_disk_not_session_memory() -> None:
    content = read("context/flows/autopilot-ticket.md")
    step_b = content.split("## Step B", 1)[1]
    assert "refine-touched.md" in step_b
    assert "session memory" in step_b
    assert "audit trail" in step_b


def test_autopilot_ticket_step_s_describes_persisted_marker() -> None:
    content = read("context/flows/autopilot-ticket.md")
    step_s = content.split("## Step S", 1)[1].split("## Step A", 1)[0]
    assert "refine-touched.md" in step_s
    assert "in-session note" in step_s


def test_deliver_ticket_resolves_marker_from_branch_copy() -> None:
    content = read("context/flows/deliver-ticket.md")
    assert "refine-touched.md" in content
    assert "never" in content and "root" in content and ".tickets/" in content
    assert "skip-Step-3" in content or "skipped" in content
    assert "_fold_archive" in content


def test_autopilot_batch_step0_excludes_marked_members() -> None:
    content = read("context/flows/autopilot-batch.md")
    step0 = content.split("## Step 0", 1)[1].split("## Step 1", 1)[0]
    assert "refine-touched.md" in step0
    assert "ticket/XXXX-<slug>" in step0
    assert "1 member remains" in step0
    assert "0 members remain" in step0
