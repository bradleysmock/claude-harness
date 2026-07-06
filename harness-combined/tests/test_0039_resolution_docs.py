"""Docs-consistency guards for ticket 0039 — worktree-first ticket resolution
and branch-only post-claim commits.

These are grep-style invariants over the flow/command/skill markdown (the same
pattern as ``test_multidev_ticketing_docs.py``). Resolution and commit targeting
are performed by the model reading these flows, so a hook cannot enforce intent —
these assertions keep future edits honest by anchoring on stable phrases.
"""

from pathlib import Path

ROOT = Path(__file__).parent.parent

# The five resolver flows that must cite the single resolution rule (FR-2).
RESOLVER_FLOWS = [
    "commands/autopilot.md",
    "context/flows/build-ticket.md",
    "context/flows/write-spec-ticket.md",
    "commands/gate.md",
    "context/flows/deliver-ticket.md",
]

# The post-claim commit-target flows (FR-3/FR-4/FR-5). None of these may commit
# ticket state to main between claim and delivery — every ticket-dir commit here
# must be branch-side (`git -C .worktrees/...`). `/deliver`, `/cancel`, `/abandon`,
# and the claim itself legitimately touch main and are excluded.
COMMIT_TARGET_FLOWS = [
    "context/flows/autopilot-ticket.md",
    "skills/review/SKILL.md",
    "commands/refine.md",
    "context/spec-remediation.md",
]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ── FR-1: harness-reference.md defines one worktree-first resolution rule ──────
def test_reference_has_ticket_resolution_section() -> None:
    c = read("context/harness-reference.md")
    assert "### Ticket resolution" in c


def test_resolution_rule_is_worktree_first_and_authoritative() -> None:
    c = read("context/harness-reference.md")
    # The rule names the worktree copy as authoritative and the root as claim/terminal only.
    assert "worktree-first" in c
    assert "authoritative" in c
    lower = c.lower()
    assert "worktree" in lower and "root" in lower


def test_resolution_rule_has_worked_example() -> None:
    assert "Worked example" in read("context/harness-reference.md")


# ── FR-2: every resolver flow cites the rule by name ─────────────────────────
def test_each_resolver_flow_cites_the_rule() -> None:
    for rel in RESOLVER_FLOWS:
        c = read(rel)
        assert "**Ticket resolution** rule" in c, f"{rel} does not cite the resolution rule"
        assert "harness-reference.md" in c, f"{rel} citation must point at harness-reference.md"


# ── FR-3: autopilot Step A commits changes-requested on the branch ───────────
def test_autopilot_step_a_commits_on_branch() -> None:
    c = read("context/flows/autopilot-ticket.md")
    assert "git -C .worktrees/XXXX-<slug> add .tickets/XXXX-<slug>/status.md" in c
    assert 'git -C .worktrees/XXXX-<slug> commit -m "chore(ticket): XXXX → changes-requested"' in c


def test_autopilot_step_a_has_no_root_main_commit() -> None:
    c = read("context/flows/autopilot-ticket.md")
    # The pre-redesign Step A committed the whole ticket dir to main.
    assert "git add .tickets/XXXX-slug/" not in c


def test_no_commit_target_flow_commits_ticket_state_to_main() -> None:
    # AC-2 (broad): between claim and delivery, no commit-target flow may run a
    # bare (non-`git -C`) add/commit of ticket state — that would land on main.
    # A branch-side `git -C .worktrees/... add/commit` does not match these bare
    # literals, so only a regression to a main-side commit trips the assertion.
    for rel in COMMIT_TARGET_FLOWS:
        c = read(rel)
        assert "git add .tickets/" not in c, f"{rel} has a bare (main-side) ticket-dir add"
        assert 'git commit -m "chore(ticket)' not in c, f"{rel} has a bare (main-side) ticket commit"


# ── FR-4: review Step 7 and refine commit on the branch only ─────────────────
def test_review_step7_commits_on_branch() -> None:
    c = read("skills/review/SKILL.md")
    assert 'git -C .worktrees/XXXX-<slug> commit -m "chore(ticket): XXXX → changes-requested"' in c
    # And no bare main-side commit of the transition survives.
    assert 'git commit -m "chore(ticket): XXXX → changes-requested"' not in c


def test_refine_commits_on_branch_not_main() -> None:
    c = read("commands/refine.md")
    # Both the interactive Step 5 and the non-interactive rule 6 use branch-side commits.
    assert 'git -C .worktrees/XXXX-<slug> commit -m "chore(ticket): XXXX refine solution"' in c
    # The old bare root-level add on its own line must be gone.
    assert "\ngit add .tickets/XXXX-<slug>/\n" not in c
    # Step 5 and rule 6 each named `main` as the commit target pre-redesign.
    assert "commit the change to `main`" not in c  # Step 5
    assert "commit it to `main`" not in c  # rule 6


# ── FR-5: pre-redesign "no worktree" remnants removed ────────────────────────
def test_spec_remediation_has_no_no_worktree_wording() -> None:
    c = read("context/spec-remediation.md")
    assert "no worktree" not in c.lower()
    assert "before any worktree is created" not in c


def test_build_ticket_step1_has_no_pre_worktree_remnant() -> None:
    assert "before any worktree is created" not in read("context/flows/build-ticket.md")


def test_spec_remediation_commits_on_branch() -> None:
    c = read("context/spec-remediation.md")
    assert "git -C .worktrees/XXXX-<slug> add .tickets/XXXX-<slug>/" in c


# ── Regression guard: harness-reference keeps the two-commits-on-main invariant ─
def test_reference_still_asserts_two_commits_on_main() -> None:
    c = read("context/harness-reference.md")
    assert "Two commits on `main`" in c
    assert "git merge --squash" in read("context/flows/deliver-ticket.md")
