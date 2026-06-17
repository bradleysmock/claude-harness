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
    content = read("context/flows/deliver-ticket.md")
    assert "mv .tickets/XXXX-<slug>/ .tickets/completed/XXXX-<slug>/" in content
    assert "git rm -r --cached .tickets/XXXX-<slug>/" in content
    assert "git add -- .tickets/completed/XXXX-<slug>/" in content


def test_deliver_ticket_step6_idempotency_guard() -> None:
    content = read("context/flows/deliver-ticket.md")
    assert "Idempotency" in content
    assert "already archived" in content or "already exists" in content


def test_deliver_ticket_step6_partial_move_guard() -> None:
    content = read("context/flows/deliver-ticket.md")
    assert "Partial-move guard" in content


# ── FR-2: cancel archives ticket to completed/ ────────────────────────────

def test_cancel_step2_confirm_shows_archive() -> None:
    content = read("commands/cancel.md")
    assert "mv .tickets/XXXX-<slug>/ .tickets/completed/XXXX-<slug>/   (archive)" in content


def test_cancel_step8_archive_uses_os_mv() -> None:
    content = read("commands/cancel.md")
    assert "mv .tickets/XXXX-<slug>/ .tickets/completed/XXXX-<slug>/" in content
    assert "git rm -r --cached .tickets/XXXX-<slug>/" in content
    assert "git add -- .tickets/completed/XXXX-<slug>/" in content
    assert "chore(ticket): XXXX archive → completed/" in content


def test_cancel_archive_is_separate_commit() -> None:
    content = read("commands/cancel.md")
    assert "never amend" in content or "separate commit" in content


def test_cancel_step9_no_longer_says_preserved() -> None:
    content = read("commands/cancel.md")
    assert "preserved for reference — delete it manually" not in content


# ── FR-3: only done/cancelled tickets are archived ────────────────────────

def test_cancel_step1_rejects_done_or_cancelled() -> None:
    content = read("commands/cancel.md")
    assert "must not be `done` or `cancelled`" in content


# ── FR-4: /reopen moves ticket back to root ──────────────────────────────

def test_reopen_command_exists() -> None:
    assert (ROOT / "commands/reopen.md").exists()


def test_reopen_sets_status_to_solution() -> None:
    content = read("commands/reopen.md")
    assert "status: solution" in content or "status → solution" in content


def test_reopen_uses_os_mv() -> None:
    content = read("commands/reopen.md")
    assert "mv .tickets/completed/XXXX-<slug>/ .tickets/XXXX-<slug>/" in content


def test_reopen_handles_partial_move_back() -> None:
    content = read("commands/reopen.md")
    assert "already exists at root" in content


def test_reopen_commit_removes_completed_path() -> None:
    content = read("commands/reopen.md")
    assert "git rm -r --cached .tickets/completed/XXXX-<slug>/" in content


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


def test_cancel_has_partial_move_guard() -> None:
    content = read("commands/cancel.md")
    assert "Partial-move guard" in content


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
    content = read("context/harness-reference.md")
    assert "git rm -r --cached" in content
    assert "chore(ticket): XXXX archive → completed/" in content
