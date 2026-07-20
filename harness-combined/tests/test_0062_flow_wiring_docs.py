"""Content-verification tests for ticket 0062's build-ticket.md wiring.

Asserts, via structural substrings, that context/flows/build-ticket.md's Step 7
(round 1) and Step 7a (each repair round) call gates.critic_reconciler.reconcile()
and announce a summary before their respective skip/success branches, and that
Step 7's persisted section embeds a per-finding marker.
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent
BUILD_TICKET_FLOW = ROOT / "context" / "flows" / "build-ticket.md"


def _step7_and_7a_text() -> str:
    text = BUILD_TICKET_FLOW.read_text()
    start = text.index("## Step 7 —")
    end = text.index("### Step 7b —")
    return text[start:end]


def test_step7_embeds_marker_before_append():
    section = _step7_and_7a_text()
    assert "marker_for_key" in section
    assert "finding_key" in section
    assert "parse_critic_findings" in section


def test_step7a_reconcile_call_precedes_skip_to_7c():
    section = _step7_and_7a_text()
    reconcile_idx = section.index("reconcile(prev=[]")
    skip_idx = section.index("go to **Step 7b.5**")
    assert reconcile_idx < skip_idx, (
        "Step 7a's reconcile+announce call must sit before the skip-to-7b.5 branch"
    )


def test_step7a_round1_summary_line_present():
    section = _step7_and_7a_text()
    assert "Round 1: F fixed, P persisted, N new BLOCKER/MAJOR." in section


def test_repair_loop_reconcile_precedes_success_check():
    section = _step7_and_7a_text()
    harvest_idx = section.index("harvest_keys")
    success_check_idx = section.index("If the new report has no BLOCKER and no MAJOR findings")
    assert harvest_idx < success_check_idx, (
        "the repair-loop reconcile call must sit before the round's success check"
    )


def test_repair_loop_summary_line_present():
    section = _step7_and_7a_text()
    assert "Round N+1: F fixed, P persisted, N new BLOCKER/MAJOR." in section


def test_other_steps_unmodified_markers_absent():
    text = BUILD_TICKET_FLOW.read_text()
    before_step7 = text[: text.index("## Step 7 —")]
    after_7a = text[text.index("### Step 7b —") :]
    assert "critic_reconciler" not in before_step7
    assert "critic_reconciler" not in after_7a
