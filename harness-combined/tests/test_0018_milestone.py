"""Tests for the /milestone command and the /ticket-list --milestone filter (ticket 0018).

Both commands are prose files whose logic lives in a single inline ``python`` block.
These tests extract that block verbatim (single source of truth — no duplicated
script) and run it as a subprocess against fixture ``.tickets/`` trees, asserting
rendered output and exit codes. Plus content tests for the ``milestone:`` template
change in commands/problem.md.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


# ── shared helpers ───────────────────────────────────────────────────────────
def extract_script(command: str) -> str:
    text = (ROOT / "commands" / command).read_text(encoding="utf-8")
    blocks = re.findall(r"```python\n(.*?)```", text, re.S)
    assert len(blocks) == 1, f"expected exactly one python block in {command}, found {len(blocks)}"
    return blocks[0]


def load_module(tmp_path: Path, command: str, mod_name: str):
    """Import a shipped inline script as a module (its __name__ guard keeps main()
    from running on import) so its helpers can be exercised directly."""
    script_path = tmp_path / f"{mod_name}.py"
    script_path.write_text(extract_script(command), encoding="utf-8")
    spec = importlib.util.spec_from_file_location(mod_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def milestone_mod(tmp_path: Path):
    return load_module(tmp_path, "milestone.md", "milestone_mod")


def write_status(directory: Path, fields: dict[str, str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "status.md").write_text(
        "".join(f"{k}: {v}\n" for k, v in fields.items()), encoding="utf-8"
    )


def make_root(tmp_path: Path, open_tickets=None, completed_tickets=None,
              milestones_body: str | None = None) -> Path:
    root = tmp_path / "repo"
    (root / ".tickets").mkdir(parents=True, exist_ok=True)
    for name, fields in open_tickets or []:
        write_status(root / ".tickets" / name, fields)
    for name, fields in completed_tickets or []:
        write_status(root / ".tickets" / "completed" / name, fields)
    if milestones_body is not None:
        (root / ".tickets" / "_milestones.md").write_text(milestones_body, encoding="utf-8")
    return root


def tk(name, ticket, status, title, milestone=None, effort=None):
    fields = {"ticket": ticket, "status": status, "title": title, "updated": "2026-06-21"}
    if milestone is not None:
        fields["milestone"] = milestone
    if effort is not None:
        fields["effort"] = effort
    return (name, fields)


def run_milestone(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    script_path = cwd / "_milestone_script.py"
    script_path.write_text(extract_script("milestone.md"), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(script_path), *args],
        cwd=str(cwd), capture_output=True, text=True,
    )


def run_ticket_list(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    script_path = cwd / "_ticket_list_script.py"
    script_path.write_text(extract_script("ticket-list.md"), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(script_path), *args],
        cwd=str(cwd), capture_output=True, text=True,
    )


MILESTONES = "## milestone: v2.0\nThe 2.0 release.\n\n## milestone: alpha\nEarly work.\n"


def sample_root(tmp_path: Path) -> Path:
    return make_root(
        tmp_path,
        open_tickets=[
            tk("0001-a", "0001", "solution", "Alpha one", milestone="v2.0", effort="small"),
            tk("0002-b", "0002", "implementing", "V2 two", milestone="v2.0", effort="large"),
            tk("0003-c", "0003", "solution", "Alpha work", milestone="alpha", effort="medium"),
            tk("0004-d", "0004", "solution", "Untagged", effort="small"),  # no milestone
        ],
        completed_tickets=[
            tk("0005-e", "0005", "done", "V2 done", milestone="v2.0", effort="large"),
        ],
        milestones_body=MILESTONES,
    )


# ── FR-8: _milestones.md absent → setup message, no crash ────────────────────
def test_missing_milestones_file_setup_message(tmp_path):
    root = make_root(tmp_path, open_tickets=[tk("0001-a", "0001", "solution", "A")])
    proc = run_milestone(root)
    assert proc.returncode == 0, proc.stderr
    assert "No milestones defined" in proc.stdout
    assert ".tickets/_milestones.md" in proc.stdout


# ── FR-1 / FR-1b: parse `## milestone:` headings, ignore other headings ──────
def test_parse_milestones_prefix_only(tmp_path):
    mod = milestone_mod(tmp_path)
    body = "## milestone: v2.0\ndesc\n\n## Notes\nnot a milestone\n\n## milestone: alpha\n"
    p = tmp_path / "_milestones.md"
    p.write_text(body, encoding="utf-8")
    names, warnings = mod.parse_milestones(p)
    assert names == ["v2.0", "alpha"]
    assert warnings == []


# ── content-safety: invalid definition name is charset-validated + skipped ────
def test_parse_milestones_invalid_name_skipped(tmp_path):
    mod = milestone_mod(tmp_path)
    p = tmp_path / "_milestones.md"
    p.write_text("## milestone: good\n## milestone: bad name\n## milestone: a|b\n", encoding="utf-8")
    names, warnings = mod.parse_milestones(p)
    assert names == ["good"]  # out-of-charset names dropped, never admitted as rows
    assert any("bad name" in w for w in warnings)
    assert any("a|b" in w for w in warnings)


# ── FR-2 / FR-3: single-pass field read, first milestone value wins ──────────
def test_status_first_milestone_value_wins(tmp_path):
    mod = milestone_mod(tmp_path)
    d = tmp_path / "t"
    d.mkdir()
    (d / "status.md").write_text(
        "ticket: 0001\nstatus: solution\nmilestone: v2.0\nmilestone: alpha\n", encoding="utf-8"
    )
    fields = mod.parse_status_file(d / "status.md")
    assert fields["milestone"] == "v2.0"


# ── FR-4 / FR-12: summary lists all defined milestones, sorted alphabetically ─
def test_summary_all_milestones_sorted(tmp_path):
    proc = run_milestone(sample_root(tmp_path))
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "alpha" in out and "v2.0" in out
    assert out.index("alpha") < out.index("v2.0")  # alphabetical


# ── FR-4: completion %, done, remaining, remaining-effort in summary ─────────
def test_summary_counts_and_effort(tmp_path):
    # v2.0: total 3 (0001 small non-done, 0002 large non-done, 0005 large done)
    #   done=1, remaining=2, remaining_pts = small(1)+large(8) = 9, pct = round(1/3*100)=33
    proc = run_milestone(sample_root(tmp_path))
    assert proc.returncode == 0, proc.stderr
    row = next(line for line in proc.stdout.splitlines() if line.startswith("| v2.0 "))
    assert "33%" in row
    assert "9" in row  # remaining effort points


# ── FR-10b: done ticket's effort excluded from remaining sum ─────────────────
def test_done_ticket_excluded_from_remaining_effort(tmp_path):
    root = make_root(
        tmp_path,
        open_tickets=[tk("0001-a", "0001", "solution", "A", milestone="m", effort="small")],
        completed_tickets=[tk("0002-b", "0002", "done", "B", milestone="m", effort="large")],
        milestones_body="## milestone: m\n",
    )
    proc = run_milestone(root)
    assert proc.returncode == 0, proc.stderr
    row = next(line for line in proc.stdout.splitlines() if line.startswith("| m "))
    # remaining effort = small(1) only; large(8) done ticket excluded
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert "1" in cells and "8" not in cells


# ── FR-10: missing effort treated as zero + warning count ────────────────────
def test_missing_effort_warning(tmp_path):
    root = make_root(
        tmp_path,
        open_tickets=[
            tk("0001-a", "0001", "solution", "A", milestone="m"),  # no effort
            tk("0002-b", "0002", "solution", "B", milestone="m"),  # no effort
        ],
        milestones_body="## milestone: m\n",
    )
    proc = run_milestone(root)
    assert proc.returncode == 0, proc.stderr
    assert "2 tickets have no effort estimate" in proc.stdout


# ── FR-11: milestone with zero tickets → 0% + "no tickets assigned" ──────────
def test_empty_milestone_zero_percent(tmp_path):
    root = make_root(
        tmp_path,
        open_tickets=[tk("0001-a", "0001", "solution", "A")],  # untagged
        milestones_body="## milestone: empty\n",
    )
    proc = run_milestone(root)
    assert proc.returncode == 0, proc.stderr
    row = next(line for line in proc.stdout.splitlines() if line.startswith("| empty "))
    assert "0%" in row
    assert "no tickets assigned" in proc.stdout


# ── FR-5: detail view lists tickets with #, title, status, effort ────────────
def test_detail_view(tmp_path):
    proc = run_milestone(sample_root(tmp_path), "v2.0")
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    for tkid in ("0001", "0002", "0005"):
        assert tkid in out
    assert "0003" not in out  # alpha ticket not in v2.0 detail
    assert "Alpha one" in out  # title shown


# ── FR-7: untagged ticket absent from milestone views ────────────────────────
def test_untagged_excluded(tmp_path):
    proc = run_milestone(sample_root(tmp_path), "v2.0")
    assert proc.returncode == 0, proc.stderr
    assert "Untagged" not in proc.stdout
    assert "0004" not in proc.stdout


# ── FR-AC: milestone in status.md but not defined → not in summary, detail 404 ─
def test_undefined_milestone_summary_and_detail(tmp_path):
    root = make_root(
        tmp_path,
        open_tickets=[tk("0001-a", "0001", "solution", "A", milestone="ghost")],
        milestones_body="## milestone: real\n",
    )
    summary = run_milestone(root)
    assert summary.returncode == 0, summary.stderr
    assert "ghost" not in summary.stdout  # undefined milestone gets no summary row
    detail = run_milestone(root, "ghost")
    assert "milestone not found" in detail.stdout or "milestone not found" in detail.stderr


# ── FR-VAL: shell-metacharacter milestone value flagged invalid, never executed ─
def test_invalid_name_rejected(tmp_path):
    mod = milestone_mod(tmp_path)
    assert mod.valid_name("v2.0") is True
    assert mod.valid_name("alpha-1_2.3") is True
    assert mod.valid_name("$(echo pwned)") is False
    assert mod.valid_name("a; rm -rf /") is False
    assert mod.valid_name("a b") is False
    assert mod.valid_name("x" * 41) is False  # > NAME_MAX
    assert mod.valid_name("") is False


def test_cli_invalid_name_arg_rejected(tmp_path):
    root = sample_root(tmp_path)
    proc = run_milestone(root, "$(echo)")
    assert proc.returncode == 1
    assert "invalid" in proc.stderr.lower()


# ── FR-DUP / FR-DUP-ERR: duplicate heading warns on stderr, stdout unaffected ─
def test_duplicate_heading_warns_on_stderr(tmp_path):
    root = make_root(
        tmp_path,
        open_tickets=[tk("0001-a", "0001", "solution", "A", milestone="v2.0", effort="small")],
        milestones_body="## milestone: v2.0\n## milestone: v2.0\n",
    )
    proc = run_milestone(root)
    assert proc.returncode == 0, proc.stderr
    # warning on stderr, not stdout
    assert "duplicate" in proc.stderr.lower()
    assert "duplicate" not in proc.stdout.lower()
    # counts not split: exactly one v2.0 summary row
    v2_rows = [ln for ln in proc.stdout.splitlines() if ln.startswith("| v2.0 ")]
    assert len(v2_rows) == 1


# ── NFR-3: milestone name > 30 chars truncated with … in summary ─────────────
def test_long_name_truncated(tmp_path):
    long_name = "m" + "n" * 34  # 35 chars, valid charset
    root = make_root(
        tmp_path,
        open_tickets=[tk("0001-a", "0001", "solution", "A", milestone=long_name, effort="small")],
        milestones_body=f"## milestone: {long_name}\n",
    )
    proc = run_milestone(root)
    assert proc.returncode == 0, proc.stderr
    assert "…" in proc.stdout
    assert long_name not in proc.stdout  # full untruncated name not present


# ── /ticket-list --milestone filter ──────────────────────────────────────────
def tl(name, ticket, status, title, milestone=None, effort=None):
    fields = {"ticket": ticket, "status": status, "title": title, "updated": "2026-06-21"}
    if milestone is not None:
        fields["milestone"] = milestone
    if effort is not None:
        fields["effort"] = effort
    return (name, fields)


def tl_root(tmp_path: Path) -> Path:
    return make_root(
        tmp_path,
        open_tickets=[
            tl("0001-a", "0001", "solution", "V2 one", milestone="v2.0"),
            tl("0002-b", "0002", "solution", "V2 two", milestone="v2.0"),
            tl("0003-c", "0003", "solution", "Alpha", milestone="alpha"),
            tl("0004-d", "0004", "solution", "Untagged"),
        ],
        milestones_body="## milestone: v2.0\n## milestone: alpha\n",
    )


# ── FR-6: --milestone shows only matching tickets ────────────────────────────
def test_ticket_list_milestone_filter(tmp_path):
    proc = run_ticket_list(tl_root(tmp_path), "--milestone", "v2.0")
    assert proc.returncode == 0, proc.stderr
    assert "| 0001 |" in proc.stdout
    assert "| 0002 |" in proc.stdout
    assert "| 0003 |" not in proc.stdout  # alpha excluded
    assert "| 0004 |" not in proc.stdout  # untagged excluded


# ── FR-7: untagged still shows in unfiltered ticket-list ─────────────────────
def test_ticket_list_untagged_in_unfiltered(tmp_path):
    proc = run_ticket_list(tl_root(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert "| 0004 |" in proc.stdout


# ── FR-9: no match → milestone-specific message ──────────────────────────────
def test_ticket_list_milestone_no_match(tmp_path):
    proc = run_ticket_list(tl_root(tmp_path), "--milestone", "nonesuch")
    assert proc.returncode == 0, proc.stderr
    assert "No tickets found for milestone 'nonesuch'." in proc.stdout


# ── FR-AC: undefined milestone annotated "(undefined)" in ticket-list ────────
def test_ticket_list_undefined_milestone_annotated(tmp_path):
    root = make_root(
        tmp_path,
        open_tickets=[tl("0001-a", "0001", "solution", "Ghost work", milestone="ghost")],
        milestones_body="## milestone: real\n",
    )
    proc = run_ticket_list(root, "--milestone", "ghost")
    assert proc.returncode == 0, proc.stderr
    assert "| 0001 |" in proc.stdout  # ticket still shown
    assert "(undefined)" in proc.stdout


# ── ticket-list --milestone validates the name argument ──────────────────────
def test_ticket_list_milestone_invalid_arg(tmp_path):
    proc = run_ticket_list(tl_root(tmp_path), "--milestone", "$(echo)")
    assert proc.returncode == 1
    assert "invalid" in proc.stderr.lower()


# ── content: problem.md template carries milestone: field ────────────────────
def test_problem_template_has_milestone_field():
    text = (ROOT / "commands" / "problem.md").read_text(encoding="utf-8")
    assert "milestone:" in text
