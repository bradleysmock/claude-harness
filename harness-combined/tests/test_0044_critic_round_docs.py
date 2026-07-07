"""
Content-verification tests for the critic agent's round-cap contract (ticket 0044).

Guards agreement between agents/critic.md and its callers:
  - agents/critic.md must describe Round as caller-supplied, with the design phase
    limited to 2 rounds by /problem Phase 5 and the code phase set per the caller's
    repair loop with no agent-side cap (FR-1).
  - agents/critic.md must not instruct any behavior change keyed on the round number
    beyond echoing it in the report header (FR-2).
  - agents/critic.md must contain no unqualified "capped at 2" claim, while
    context/flows/build-ticket.md Step 7a still documents rounds beyond 2 (FR-3).
"""
import re
from pathlib import Path

REPO = Path(__file__).parent.parent
CRITIC = REPO / "agents" / "critic.md"
BUILD_TICKET = REPO / "context" / "flows" / "build-ticket.md"


def _section(content: str, start: str, end: str | None = None) -> str:
    i = content.find(start)
    assert i >= 0, f"Section '{start}' not found"
    if end is None:
        return content[i:]
    j = content.find(end, i + len(start))
    return content[i:j] if j >= 0 else content[i:]


def test_critic_md_exists():
    assert CRITIC.exists(), "agents/critic.md must exist"


# --- FR-1: per-phase, caller-supplied round semantics ---

def test_round_is_caller_supplied():
    content = CRITIC.read_text()
    assert "caller-supplied" in content, \
        "critic.md must describe the Round parameter as caller-supplied"


def test_design_phase_round_limit_owned_by_problem():
    # Normalize markdown formatting (backticks) so `/problem` matches /problem.
    content = CRITIC.read_text().lower().replace("`", "")
    assert "design phase" in content, "critic.md must name the design phase round semantics"
    assert "/problem phase 5" in content, \
        "critic.md must attribute the design-phase 2-round limit to /problem Phase 5"
    assert "2 rounds" in content, "critic.md must state the design phase is limited to 2 rounds"


def test_code_phase_has_no_agent_side_cap():
    content = CRITIC.read_text()
    lower = content.lower()
    assert "code phase" in lower, "critic.md must name the code phase round semantics"
    assert "no cap" in lower, \
        "critic.md must state the code phase has no agent-side cap on rounds"
    # An explicit acknowledgement that rounds beyond 2 are legitimate in the code phase.
    assert "round 3" in lower, \
        "critic.md must acknowledge Round 3 (and beyond) as legitimate in the code phase"


# --- FR-2: no round-conditional behavior instruction ---

def test_no_round_conditional_behavior_instruction():
    content = CRITIC.read_text()
    lower = content.lower()
    # The agent must explicitly disclaim any behavior change keyed on the round number.
    assert "do not alter" in lower and "round number" in lower, \
        "critic.md must instruct the agent not to alter its review based on the round number"
    # Guard against a resurfacing conditional directive keyed on a specific round,
    # e.g. "Round 2:" or "if round == 2" used as a behavior switch.
    assert not re.search(r"if\s+round\b", lower), \
        "critic.md must not contain an 'if round' behavior conditional"
    # Search the lowercased text and tolerate leading markdown markers (list/emphasis/
    # heading), so the capitalized label form — '- **Round 2:**', '## Round 3:' — is
    # caught, not just a bare 'round 2:' line.
    assert not re.search(r"^[\s#>*_-]*round\s+[23]\s*:", lower, re.MULTILINE), \
        "critic.md must not contain a per-round behavior directive like 'Round 2:'"


# --- FR-3: no unqualified cap; caller flow still documents rounds beyond 2 ---

def test_critic_md_has_no_unqualified_cap_claim():
    content = CRITIC.read_text().lower()
    assert "capped at 2" not in content, \
        "critic.md must not contain the unqualified 'capped at 2' claim"


def test_build_ticket_step7a_documents_rounds_beyond_two():
    assert BUILD_TICKET.exists(), "context/flows/build-ticket.md must exist"
    content = BUILD_TICKET.read_text()
    step7a = _section(content, "### Step 7a", "### Step 7b")
    assert "N+1" in step7a, \
        "build-ticket.md Step 7a must document re-spawning the critic at Round N+1"
    assert "MAX_REPAIR_ATTEMPTS" in step7a, \
        "build-ticket.md Step 7a must document up to MAX_REPAIR_ATTEMPTS repair rounds"
