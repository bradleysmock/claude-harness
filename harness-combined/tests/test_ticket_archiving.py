"""Content-verification tests for the ticket archiving feature (ticket 0001).

This ticket modifies markdown instruction files, not Python code. These tests
verify that the key structural changes are present in each modified file.
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ── FR-1 / FR-7: deliver archives ticket to completed/ ────────────────────

def test_deliver_ticket_step3_shows_archive_in_confirm() -> None:
    content = read("context/flows/deliver-ticket.md")
    assert "mv .tickets/XXXX-<slug>/ .tickets/completed/XXXX-<slug>/" in content
    assert "(archive)" in content


def test_deliver_ticket_step6_uses_os_mv() -> None:
    """Ticket 0068 moved the raw git rm/add pair behind `ticket.py deliver-commit`
    (`deliver_commit()`); the doc now documents the call, mirroring the archive
    pattern in prose rather than inlining every git command."""
    content = read("context/flows/deliver-ticket.md")
    assert "mv .tickets/XXXX-<slug>/ .tickets/completed/XXXX-<slug>/" in content
    assert "deliver-commit" in content
    assert "git rm -r --cached" in content


def test_deliver_ticket_step6_idempotency_guard() -> None:
    content = read("context/flows/deliver-ticket.md")
    assert "Idempotency" in content
    assert "already archived" in content or "already exists" in content


def test_deliver_ticket_step6_partial_move_guard() -> None:
    content = read("context/flows/deliver-ticket.md")
    assert "Partial-move guard" in content


# ── FR-2: cancel is MAIN-FREE — archives docs onto harness-tickets ─────────
# NEW CONTRACT: a cancelled ticket never merged, so it must not land on `main`.
# Old contract archived `.tickets/XXXX/` → `.tickets/completed/XXXX/` in a
# terminal commit on `main`; the new contract appends a `cancelled` ledger event
# and archives the docs onto the `harness-tickets` branch, with NO `main` commit.

def test_cancel_confirm_shows_main_free_archive() -> None:
    content = read("commands/cancel.md")
    assert "main-free" in content
    assert "cancelled/XXXX-<slug>/" in content  # docs archived onto harness-tickets


def test_cancel_delegates_to_main_free_helper() -> None:
    content = read("commands/cancel.md")
    assert 'ticket.py" cancel XXXX --push' in content
    # the old main-side archive commit must be gone
    assert "chore(ticket): XXXX archive → completed/" not in content
    assert "no `main` commit" in content


def test_cancel_is_idempotent_by_event_number() -> None:
    content = read("commands/cancel.md")
    assert "idempotent" in content.lower()


def test_cancel_step9_no_longer_says_preserved() -> None:
    content = read("commands/cancel.md")
    assert "preserved for reference — delete it manually" not in content


# ── FR-3: only in-flight (non-terminal) tickets can be cancelled ──────────

def test_cancel_step1_rejects_done_or_cancelled() -> None:
    content = read("commands/cancel.md")
    assert "must not be `done` or `cancelled`" in content


# ── FR-4: /reopen moves ticket back to root ──────────────────────────────

def test_reopen_command_exists() -> None:
    assert (ROOT / "commands/reopen.md").exists()


def test_reopen_sets_status_to_solution() -> None:
    content = read("commands/reopen.md")
    assert "status: solution" in content or "status → solution" in content


def test_reopen_forks_fresh_branch_from_main() -> None:
    # NEW CONTRACT: reopen forks a fresh branch from main HEAD and restores the
    # dir from its archive (main's completed/ for delivered, harness-tickets for
    # cancelled) via the helper — no bare OS mv on main. Old assertion pinned
    # "mv .tickets/completed/XXXX-<slug>/ .tickets/XXXX-<slug>/".
    content = read("commands/reopen.md")
    assert "git worktree add .worktrees/XXXX-<slug> -b ticket/XXXX-<slug> main" in content
    assert 'ticket.py" reopen XXXX --push' in content


def test_reopen_handles_partial_reopen_state() -> None:
    content = read("commands/reopen.md")
    assert "already exists at root" in content


def test_reopen_restores_from_archive() -> None:
    # The delivered-ticket restore still uses the `git rm -r --cached` + `git add`
    # pattern (now inside the helper); the completed/ archive is the source.
    content = read("commands/reopen.md")
    assert "git rm -r --cached" in content
    assert "completed/" in content


# ── FR-5: ticket ID resolution checks both locations ─────────────────────

def test_build_md_checks_completed() -> None:
    content = read("commands/build.md")
    assert ".tickets/completed/<arg>*/" in content or ".tickets/completed/" in content


def test_deliver_md_checks_completed() -> None:
    content = read("commands/deliver.md")
    assert ".tickets/completed/<arg>*/" in content or ".tickets/completed/" in content


def test_build_ticket_flow_checks_completed() -> None:
    content = read("context/flows/build-ticket.md")
    assert ".tickets/completed/" in content


def test_write_spec_ticket_flow_checks_completed() -> None:
    content = read("context/flows/write-spec-ticket.md")
    assert ".tickets/completed/" in content


def test_gate_md_checks_completed() -> None:
    content = read("commands/gate.md")
    assert ".tickets/completed/" in content


# ── FR-6: idempotency and partial-move guard ─────────────────────────────

def test_cancel_has_idempotency_guard() -> None:
    content = read("commands/cancel.md")
    assert "Idempotency" in content


def test_cancel_has_partial_cleanup_guard() -> None:
    # NEW CONTRACT: cancel is main-free and delegates removal to the helper, so the
    # guard is a "Partial-cleanup guard" (best-effort branch/worktree removal),
    # not the old main-side "Partial-move guard" over .tickets/completed/.
    content = read("commands/cancel.md")
    assert "Partial-cleanup guard" in content


# ── FR-8: /status shows completed tickets in distinct section ────────────

def test_status_skill_has_completed_section() -> None:
    content = read("skills/status/SKILL.md")
    assert "Completed Tickets" in content
    assert ".tickets/completed/*/status.md" in content


def test_status_skill_has_active_section() -> None:
    content = read("skills/status/SKILL.md")
    assert "Active Tickets" in content


def test_ticket_status_scans_completed_dir() -> None:
    content = read("commands/ticket-status.md")
    assert ".tickets/completed/*/status.md" in content
    assert "Completed Tickets" in content


# ── harness-reference.md documents new lifecycle ─────────────────────────

def test_harness_reference_has_completed_dir() -> None:
    content = read("context/harness-reference.md")
    assert "completed/" in content


def test_harness_reference_has_reopen_transition() -> None:
    content = read("context/harness-reference.md")
    assert "reopen" in content.lower()
    assert "solution" in content


def test_harness_reference_documents_archive_commit_pattern() -> None:
    # NEW CONTRACT: delivery still folds the completed/<slug>/ archive into the
    # squash via the `git rm -r --cached` + `git add` pattern (reopen-from-main
    # uses the same). But /cancel and /abandon are now MAIN-FREE — they append a
    # terminal ledger event and archive docs onto harness-tickets, so there is no
    # longer a `chore(ticket): XXXX archive → completed/` commit on main.
    content = read("context/harness-reference.md")
    assert "git rm -r --cached" in content
    assert "chore(ticket): XXXX archive → completed/" not in content
    assert "main-free" in content  # cancel/abandon documented as main-free
    assert "delivered` ledger event" in content
