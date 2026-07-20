"""Integration test for ticket 0062's full round-trip (FR-4/FR-5 Test Plan row).

Simulates Step 7 (round 1) and Step 7a (round 2) exactly as build-ticket.md now
instructs: parse a critic report using the mandated header grammar
(critic-brief.md Step 4), embed a trailing marker per finding, harvest the prior
round's markers, and reconcile — across two rounds including a clean round 1.
"""
from __future__ import annotations

from pathlib import Path

from gates.critic_finding_parser import parse_critic_findings
from gates.critic_reconciler import (
    harvest_keys,
    latest_section,
    marker_for_key,
    reconcile,
)
from gates.finding import Finding, finding_key


def _persist_round(report_text: str, worktree_root: Path) -> tuple[str, list[Finding]]:
    """Mirror build-ticket.md's persist step: parse, mark, return the section text + findings."""
    findings = parse_critic_findings(report_text, worktree_root)
    lines = report_text.splitlines()
    out_lines = []
    finding_iter = iter(findings)
    current = next(finding_iter, None)
    for line in lines:
        out_lines.append(line)
        if current is not None and line.startswith("**") and f"**{current.severity}**" in line:
            out_lines[-1] = line + " " + marker_for_key(finding_key(current))
            current = next(finding_iter, None)
    return "\n".join(out_lines), findings


def test_two_round_fixture_one_fixed_one_persisted_one_new(tmp_path: Path) -> None:
    worktree_root = tmp_path
    (worktree_root / "a.py").write_text("x = 1\n")
    (worktree_root / "b.py").write_text("y = 2\n")
    (worktree_root / "c.py").write_text("z = 3\n")

    round1_report = (
        "**BLOCKER** · Core / Dimension 1 · `a.py:1`\n\n"
        "This one gets fixed.\n\n"
        "**MAJOR** · Core / Dimension 2 · `b.py:2`\n\n"
        "This one persists.\n"
    )
    section1, curr1 = _persist_round(round1_report, worktree_root)
    round1_result = reconcile([], curr1)
    assert round1_result.fixed == []
    assert round1_result.persisted == []
    assert len(round1_result.new) == 2

    critic_findings_md = f"## Round 1 — 2026-07-20\n\n{section1}\n"

    round2_report = (
        "**MAJOR** · Core / Dimension 2 · `b.py:2`\n\n"
        "Still here, persisted.\n\n"
        "**BLOCKER** · Core / Dimension 3 · `c.py:3`\n\n"
        "Freshly introduced.\n"
    )
    section2, curr2 = _persist_round(round2_report, worktree_root)

    prev_keys = harvest_keys(latest_section(critic_findings_md))
    prev = [Finding(file=k[0], line=k[1], severity=k[2], code=k[3], message="") for k in prev_keys]

    round2_result = reconcile(prev, curr2)
    assert len(round2_result.fixed) == 1
    assert round2_result.fixed[0][0] == "a.py"
    assert len(round2_result.persisted) == 1
    assert round2_result.persisted[0].file == "b.py"
    assert len(round2_result.new) == 1
    assert round2_result.new[0].file == "c.py"

    critic_findings_md += f"\n## Round 2 — 2026-07-20\n\n{section2}\n"
    assert "harness-finding-key" in critic_findings_md


def test_three_round_fixture_persisted_finding_is_not_double_counted_as_fixed(
    tmp_path: Path,
) -> None:
    """Regression: a finding surviving 3 rounds must reconcile round 3 as persisted,
    not fixed — a full-file (unscoped) harvest would see the key's marker twice
    (embedded fresh in both round 1 and round 2) and misclassify one occurrence
    as fixed even though the finding never went away."""
    worktree_root = tmp_path
    (worktree_root / "a.py").write_text("x = 1\n")

    report = "**BLOCKER** · Core / Dimension 1 · `a.py:1`\n\nStill unresolved.\n"

    section1, curr1 = _persist_round(report, worktree_root)
    critic_findings_md = f"## Round 1 — 2026-07-20\n\n{section1}\n"
    reconcile([], curr1)  # round 1: no prior round

    section2, curr2 = _persist_round(report, worktree_root)
    prev2 = [
        Finding(file=k[0], line=k[1], severity=k[2], code=k[3], message="")
        for k in harvest_keys(latest_section(critic_findings_md))
    ]
    round2_result = reconcile(prev2, curr2)
    assert round2_result.fixed == []
    assert len(round2_result.persisted) == 1
    critic_findings_md += f"\n## Round 2 — 2026-07-20\n\n{section2}\n"

    section3, curr3 = _persist_round(report, worktree_root)
    prev3 = [
        Finding(file=k[0], line=k[1], severity=k[2], code=k[3], message="")
        for k in harvest_keys(latest_section(critic_findings_md))
    ]
    round3_result = reconcile(prev3, curr3)
    assert round3_result.fixed == [], (
        "the still-unresolved finding must not be misreported as fixed at round 3"
    )
    assert len(round3_result.persisted) == 1
    assert round3_result.new == []
