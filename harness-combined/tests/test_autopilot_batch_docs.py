# harness-combined/tests/test_autopilot_batch_docs.py
"""Content-verification tests for autopilot batch mode (multi-ticket, one
integration worktree, one atomic push / one squashed commit per member).

These pin the structural contract of the markdown flows the same way
tests/test_0003_squash_delivery_docs.py pins single-ticket delivery, so the
prose that the model actually follows can't silently regress.
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ── autopilot.md dispatches to batch mode on ≥2 IDs ──────────────────────────
def test_autopilot_command_selects_batch_mode() -> None:
    c = read("commands/autopilot.md")
    assert "batch mode" in c.lower()
    assert "autopilot-batch.md" in c
    # single-ticket path is still routed to the ticket flow
    assert "autopilot-ticket.md" in c


def test_autopilot_batch_flow_exists() -> None:
    assert (ROOT / "context/flows/autopilot-batch.md").is_file()


# ── the batch flow's core invariants ─────────────────────────────────────────
def test_batch_flow_uses_one_integration_worktree() -> None:
    c = read("context/flows/autopilot-batch.md")
    assert "batch/<lead-slug>" in c
    assert ".worktrees/batch-<lead-slug>" in c
    # forked from main, since design artifacts live on the ticket branches
    assert "git worktree add .worktrees/batch-<lead-slug> -b batch/<lead-slug> main" in c


def test_batch_flow_imports_member_design_artifacts() -> None:
    c = read("context/flows/autopilot-batch.md")
    assert "checkout ticket/XXXX-<slug> -- .tickets/XXXX-<slug>/" in c


def test_batch_flow_delivers_via_helper_one_push() -> None:
    c = read("context/flows/autopilot-batch.md")
    assert "deliver-batch" in c
    assert "deliver_squash_batch" in c
    # one commit per member, delivered atomically
    assert "one squashed commit per member" in c or "one commit per member" in c.lower()


def test_batch_flow_no_partial_delivery_on_exhaustion() -> None:
    c = read("context/flows/autopilot-batch.md")
    assert "no partial delivery" in c.lower()


def test_batch_flow_avoids_sibling_rebase_churn() -> None:
    c = read("context/flows/autopilot-batch.md")
    assert "no member ever rebases another" in c.lower()


# ── build-ticket.md carries the batch-mode override ──────────────────────────
def test_build_ticket_has_batch_override() -> None:
    c = read("context/flows/build-ticket.md")
    assert "Batch-mode override" in c
    # override redirects writes to the shared batch worktree and skips the per-ticket critic
    assert ".worktrees/batch-<lead-slug>" in c
    assert "Skip Step 7" in c
