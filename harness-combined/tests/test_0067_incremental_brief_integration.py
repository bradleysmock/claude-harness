"""Integration test for ticket 0067's Step 7a incremental-brief prep sub-step.

Mirrors test_0062_reconciliation_integration.py's `_persist_round` helper:
persist a round's critic report with markers, harvest the prior round's
findings via ticket 0062's parser (FR-3), build the incremental brief via
gates.incremental_scope (FR-9), and reconcile round N+1's response — proving a
prior finding OUTSIDE the round's diff is still surfaced to the critic (never
dropped by omission, FR-7) and correctly classified once the critic re-reports
it as still-present.
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
from gates.incremental_scope import format_incremental_brief, touched_files_from_diff


def _persist_round(report_text: str, worktree_root: Path) -> tuple[str, list[Finding]]:
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


# Round N's diff only touches a.py; b.py's finding lies entirely outside it.
ROUND_N_DIFF = """\
diff --git a/a.py b/a.py
index 1111111..2222222 100644
--- a/a.py
+++ b/a.py
@@ -1,1 +1,1 @@
-old
+new
"""


def test_prep_substep_surfaces_prior_finding_outside_diff_and_reconciles_correctly(
    tmp_path: Path,
) -> None:
    worktree_root = tmp_path
    (worktree_root / "a.py").write_text("x = 1\n")
    (worktree_root / "b.py").write_text("y = 2\n")
    (worktree_root / "c.py").write_text("z = 3\n")

    # Round N's critic report: a finding inside the diff and one outside it.
    round_n_report = (
        "**BLOCKER** · Core / Dimension 1 · `a.py:1`\n\n"
        "In-diff finding, will be fixed by round N+1.\n\n"
        "**MAJOR** · Core / Dimension 2 · `b.py:2`\n\n"
        "Outside-diff finding, must still be re-verified directly.\n"
    )
    round_n_section, _ = _persist_round(round_n_report, worktree_root)
    critic_findings_md = f"## Round {1} — 2026-07-20\n\n{round_n_section}\n"

    # --- Step 7a item 4b: the prep sub-step under test ---
    prior_findings = [
        f
        for f in parse_critic_findings(latest_section(critic_findings_md), worktree_root)
        if f.severity in ("BLOCKER", "MAJOR")
    ]
    assert {f.file for f in prior_findings} == {"a.py", "b.py"}

    touched = touched_files_from_diff(ROUND_N_DIFF, worktree_root)
    assert touched == ["a.py"]
    # b.py's finding is outside `touched` but still present in prior_findings —
    # the prep step never filters prior_findings by the diff's touched files.
    assert "b.py" in [f.file for f in prior_findings] and "b.py" not in touched

    brief = format_incremental_brief(prior_findings, ROUND_N_DIFF)
    assert "Mode: incremental" in brief
    assert "a.py:1" in brief
    assert "b.py:2" in brief

    # --- Round N+1's critic re-reads b.py directly (per critic-brief.md Step 3/4),
    # finds it unfixed, and re-emits it; a.py's finding is fixed (not re-emitted);
    # a genuinely new finding appears inside the diff's touched file. ---
    round_n1_report = (
        "**MAJOR** · Core / Dimension 2 · `b.py:2`\n\n"
        "Still present — re-verified directly, not dropped by diff scoping.\n\n"
        "**BLOCKER** · Core / Dimension 4 · `a.py:5`\n\n"
        "Freshly introduced by this round's own diff.\n"
    )
    curr = parse_critic_findings(round_n1_report, worktree_root)

    prev_keys = harvest_keys(latest_section(critic_findings_md))
    prev = [Finding(file=k[0], line=k[1], severity=k[2], code=k[3], message="") for k in prev_keys]

    result = reconcile(prev, curr)
    assert len(result.fixed) == 1
    assert result.fixed[0][0] == "a.py" and result.fixed[0][1] == 1
    assert len(result.persisted) == 1
    assert result.persisted[0].file == "b.py"
    assert len(result.new) == 1
    assert result.new[0].file == "a.py" and result.new[0].line == 5


def test_prep_substep_fail_closed_when_prior_findings_parses_empty(tmp_path: Path) -> None:
    """FR-10: an empty prior_findings parse from a non-empty prior round is a
    parser/format mismatch — the caller must fall back to a full-scope, unmarked
    round N+1 spawn rather than building an (incorrectly empty) incremental brief.
    """
    worktree_root = tmp_path
    malformed_section = "## Round 1 — 2026-07-20\n\nThe critic said something unparseable.\n"

    prior_findings = [
        f
        for f in parse_critic_findings(latest_section(malformed_section), worktree_root)
        if f.severity in ("BLOCKER", "MAJOR")
    ]
    assert prior_findings == []

    # The caller's fail-closed branch (build-ticket.md Step 7a item 4b) must
    # detect this and skip calling format_incremental_brief / touched_files_from_diff
    # entirely, spawning round N+1 as a full-scope round instead. This test proves
    # the emptiness is observable and unambiguous — it never crashes downstream.
    fallback_brief_would_be = format_incremental_brief(prior_findings, "")
    assert "No prior BLOCKER/MAJOR findings carried forward." in fallback_brief_would_be
