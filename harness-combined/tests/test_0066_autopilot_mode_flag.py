"""Content-verification for ticket 0066's explicit `MODE` branching.

`build-ticket.md` used to rely on `autopilot-ticket.md` narrating three
"watch for this condition" interception points. This ticket replaces that
prose cue with an explicit, unit-tested `is_autopilot_mode(MODE)` branch
(`mode_branch.py`) evaluated directly in `build-ticket.md`, and shrinks
`autopilot-ticket.md` down to the mode assignment, delegation line, and
Steps S/A/B.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BUILD = (_ROOT / "context" / "flows" / "build-ticket.md").read_text(encoding="utf-8")
_AUTOPILOT = (_ROOT / "context" / "flows" / "autopilot-ticket.md").read_text(
    encoding="utf-8"
)


def _section(doc: str, start_marker: str, end_marker: str) -> str:
    start = doc.index(start_marker)
    end = doc.index(end_marker, start + len(start_marker))
    return doc[start:end]


# ---------------------------------------------------------------------------
# build-ticket.md — three explicit MODE branches (FR-2, FR-3, FR-4, FR-6)
# ---------------------------------------------------------------------------


def test_step1_block_branches_explicitly_on_is_autopilot_mode() -> None:
    step1 = _section(_BUILD, "## Step 1 —", "## Step 1.9")
    assert "is_autopilot_mode(MODE)" in step1
    assert "Step S" in step1
    # The interactive stop-and-report text stays verbatim (FR-6, NFR-1).
    assert (
        "stop here — **before any implementation is written** (the "
        "claim-time worktree already exists; leave it holding only its "
        "design artifacts) — show the failing checks, and tell the lead "
        "to fix the design artifacts (or run `/refine XXXX`) and re-run "
        "`/build XXXX`."
    ) in step1


def test_step7d_branches_explicitly_on_is_autopilot_mode() -> None:
    step7d = _BUILD[_BUILD.index("### Step 7d —") :]
    assert "is_autopilot_mode(MODE)" in step7d
    assert "Step A" in step7d
    # The ask-the-lead path stays verbatim (FR-6, NFR-1).
    assert 'commit -m "chore(ticket): XXXX → changes-requested"' in step7d
    assert "Show the lead the residual BLOCKER / MAJOR findings" in step7d
    assert (
        "Auto-repair could not clear N BLOCKER / K MAJOR finding(s) after "
        "`MAX_REPAIR_ATTEMPTS` attempts — your input is needed."
    ) in step7d


def test_step7b_branches_explicitly_on_is_autopilot_mode() -> None:
    step7b = _section(_BUILD, "### Step 7b —", "### Step 7b.5")
    assert "is_autopilot_mode(MODE)" in step7b
    assert "Step B" in step7b
    # The lead-facing options message stays verbatim (FR-6, NFR-1).
    assert (
        "The post-build critic's BLOCKER/MAJOR findings were auto-repaired "
        "in N round(s) and re-verified clean. Options:"
    ) in step7b


def test_step7c_branches_explicitly_on_is_autopilot_mode() -> None:
    step7c = _section(_BUILD, "### Step 7c —", "### Step 7d")
    assert "is_autopilot_mode(MODE)" in step7c
    assert "Step B" in step7c
    # The lead-facing options message stays verbatim (FR-6, NFR-1).
    assert "The post-build critic found no BLOCKER/MAJOR findings. Options:" in step7c


def test_build_ticket_imports_mode_branch_predicate() -> None:
    assert "mode_branch.py" in _BUILD
    assert "is_autopilot_mode" in _BUILD


# ---------------------------------------------------------------------------
# autopilot-ticket.md — sets MODE=autopilot, drops interception prose (FR-1, FR-5)
# ---------------------------------------------------------------------------


def test_autopilot_ticket_sets_mode_signal() -> None:
    assert "MODE=autopilot" in _AUTOPILOT


def test_autopilot_ticket_drops_interception_prose() -> None:
    assert "Spec-BLOCK interception" not in _AUTOPILOT
    assert "Divergence condition" not in _AUTOPILOT
    assert "Clean-build interception" not in _AUTOPILOT


def test_autopilot_ticket_keeps_steps_s_a_b() -> None:
    assert "## Step S —" in _AUTOPILOT
    assert "## Step A —" in _AUTOPILOT
    assert "## Step B —" in _AUTOPILOT


def test_autopilot_ticket_keeps_delegation_line() -> None:
    assert "context/flows/build-ticket.md" in _AUTOPILOT
    assert "follow it exactly through Steps 1–7c" in _AUTOPILOT


def test_autopilot_ticket_shorter_than_before() -> None:
    # Regression guard on the removed interception block (AC in requirements.md):
    # the old "Steps 1-7c" section carried three multi-sentence interception
    # paragraphs; the replacement is a short delegation note. 95 lines was the
    # ticket-0066 pre-edit line count.
    assert len(_AUTOPILOT.splitlines()) < 95


# ---------------------------------------------------------------------------
# autopilot-batch.md — untouched (FR-7)
# ---------------------------------------------------------------------------


def test_autopilot_batch_docs_unaffected() -> None:
    batch = (_ROOT / "context" / "flows" / "autopilot-batch.md").read_text(
        encoding="utf-8"
    )
    assert "MODE=autopilot" not in batch
