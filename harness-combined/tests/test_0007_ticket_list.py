"""Integration tests for the /ticket-list command (ticket 0007).

`commands/ticket-list.md` is a prose command whose logic lives in a single inline
``python`` block. These tests extract that block verbatim (single source of truth —
no duplicated script) and run it as a subprocess against fixture ``.tickets/`` trees,
asserting rendered table content and exit codes. Plus two content tests: the FR-13
`effort:` template change in commands/problem.md and the canonical VALID_STAGES
allow-list ownership.

Harness-tickets model (ticket "harness-feedback-gaps"): under the
`.harness-tickets` branch design, in-flight tickets no longer live on `main`, so
the script enumerates the in-flight set from the ledger (`ticket.py list-json`)
and **unions** it, de-duplicated by ticket number, with a `.tickets/*` scan. The
``run_cmd``-based tests below (which set no ``CLAUDE_PLUGIN_ROOT``) now exercise
the **legacy `.tickets/*` fallback** — still a supported source for tickets
claimed before migration and for local worktree copies. The
``test_ledger_*`` tests exercise the newly-introduced ledger-enumeration path via
a stub ``ticket.py`` that emits a fake ``list-json`` payload.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def extract_script() -> str:
    text = (ROOT / "commands" / "ticket-list.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```python\n(.*?)```", text, re.S)
    assert len(blocks) == 1, f"expected exactly one python block, found {len(blocks)}"
    return blocks[0]


def load_script_module(tmp_path: Path):
    """Import the shipped inline script as a module (its __name__ guard keeps
    main() from running on import) so its helpers can be exercised directly."""
    script_path = tmp_path / "ticket_list_mod.py"
    script_path.write_text(extract_script(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("ticket_list_mod", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_status(directory: Path, fields: dict[str, str] | None, *, zero_byte: bool = False,
                 no_file: bool = False) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    if no_file:
        return
    status_md = directory / "status.md"
    if zero_byte:
        status_md.write_text("", encoding="utf-8")
        return
    assert fields is not None
    status_md.write_text(
        "".join(f"{k}: {v}\n" for k, v in fields.items()), encoding="utf-8"
    )


def make_root(tmp_path: Path, open_tickets=None, completed_tickets=None) -> Path:
    root = tmp_path / "repo"
    (root / ".tickets").mkdir(parents=True, exist_ok=True)
    for name, fields, kw in open_tickets or []:
        write_status(root / ".tickets" / name, fields, **kw)
    for name, fields, kw in completed_tickets or []:
        write_status(root / ".tickets" / "completed" / name, fields, **kw)
    return root


def run_cmd(cwd: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    script_path = cwd / "_ticket_list_script.py"
    script_path.write_text(extract_script(), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(script_path), *flags],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


def field(name, ticket, status, title, effort=None, updated="2026-06-21"):
    fields = {"ticket": ticket, "status": status, "title": title, "updated": updated}
    if effort is not None:
        fields["effort"] = effort
    return (name, fields, {})


def sample_root(tmp_path: Path) -> Path:
    return make_root(
        tmp_path,
        open_tickets=[
            field("0001-alpha", "0001", "solution", "Alpha work", "small"),
            field("0002-beta", "0002", "implementing", "Beta work", "medium"),
            field("0003-gamma", "0003", "solution", "Gamma work", "large"),
        ],
        completed_tickets=[
            field("0004-delta", "0004", "done", "Delta done", "small"),
            field("0005-eps", "0005", "cancelled", "Eps cancelled", "medium"),
        ],
    )


# ── FR-1 / FR-2: all rows + columns ──────────────────────────────────────────
def test_no_flags_shows_all_with_columns(tmp_path):
    proc = run_cmd(sample_root(tmp_path))
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "| Ticket # | Status | Title | Effort | Updated |" in out
    for tk in ("0001", "0002", "0003", "0004", "0005"):
        assert f"| {tk} |" in out


# ── FR-3: --open ─────────────────────────────────────────────────────────────
def test_open_only(tmp_path):
    proc = run_cmd(sample_root(tmp_path), "--open")
    assert proc.returncode == 0, proc.stderr
    for tk in ("0001", "0002", "0003"):
        assert f"| {tk} |" in proc.stdout
    for tk in ("0004", "0005"):
        assert f"| {tk} |" not in proc.stdout


# ── FR-4: --completed ────────────────────────────────────────────────────────
def test_completed_only(tmp_path):
    proc = run_cmd(sample_root(tmp_path), "--completed")
    assert proc.returncode == 0, proc.stderr
    for tk in ("0004", "0005"):
        assert f"| {tk} |" in proc.stdout
    for tk in ("0001", "0002", "0003"):
        assert f"| {tk} |" not in proc.stdout


# ── FR-11 / FR-12: mutual exclusion ──────────────────────────────────────────
def test_open_and_completed_mutually_exclusive(tmp_path):
    proc = run_cmd(sample_root(tmp_path), "--open", "--completed")
    assert proc.returncode == 1
    assert "mutually exclusive" in proc.stderr
    assert "| 0001 |" not in proc.stdout


# ── FR-5a: --status filter ───────────────────────────────────────────────────
def test_status_filter(tmp_path):
    proc = run_cmd(sample_root(tmp_path), "--status", "solution")
    assert proc.returncode == 0, proc.stderr
    assert "| 0001 |" in proc.stdout
    assert "| 0003 |" in proc.stdout
    assert "| 0002 |" not in proc.stdout
    assert "| 0004 |" not in proc.stdout


# ── FR-5b: invalid stage ─────────────────────────────────────────────────────
def test_status_invalid_stage(tmp_path):
    proc = run_cmd(sample_root(tmp_path), "--status", "invalid_stage")
    assert proc.returncode == 1
    assert "invalid --status" in proc.stderr


# ── FR-5c: --status + --open ─────────────────────────────────────────────────
def test_status_and_open(tmp_path):
    proc = run_cmd(sample_root(tmp_path), "--status", "solution", "--open")
    assert proc.returncode == 0, proc.stderr
    assert "| 0001 |" in proc.stdout
    assert "| 0003 |" in proc.stdout
    assert "| 0002 |" not in proc.stdout  # open but not solution
    assert "| 0004 |" not in proc.stdout  # solution filter excludes done


# ── FR-6: ascending sort ─────────────────────────────────────────────────────
def test_sorted_ascending(tmp_path):
    root = make_root(
        tmp_path,
        open_tickets=[
            field("0003-c", "0003", "solution", "C"),
            field("0001-a", "0001", "solution", "A"),
            field("0002-b", "0002", "solution", "B"),
        ],
    )
    proc = run_cmd(root)
    assert proc.returncode == 0, proc.stderr
    positions = [proc.stdout.index(f"| {tk} |") for tk in ("0001", "0002", "0003")]
    assert positions == sorted(positions)


# ── FR-7 / FR-9: missing effort -> em dash ───────────────────────────────────
def test_missing_effort_dash(tmp_path):
    root = make_root(
        tmp_path,
        open_tickets=[field("0001-a", "0001", "solution", "A", effort=None)],
    )
    proc = run_cmd(root)
    assert proc.returncode == 0, proc.stderr
    row = next(line for line in proc.stdout.splitlines() if line.startswith("| 0001 |"))
    assert "—" in row  # effort cell rendered as em dash


# ── FR-8a: dir with no status.md is skipped ──────────────────────────────────
def test_missing_status_file_skipped(tmp_path):
    root = make_root(
        tmp_path,
        open_tickets=[
            field("0001-a", "0001", "solution", "A"),
            ("0002-nofile", None, {"no_file": True}),
        ],
    )
    proc = run_cmd(root)
    assert proc.returncode == 0, proc.stderr
    assert "| 0001 |" in proc.stdout
    assert "0002" not in proc.stdout


# ── FR-8b: zero-byte status.md -> all-dash row, no crash ─────────────────────
def test_zero_byte_status_all_dash(tmp_path):
    root = make_root(
        tmp_path,
        open_tickets=[("0001-empty", None, {"zero_byte": True})],
    )
    proc = run_cmd(root)
    assert proc.returncode == 0, proc.stderr
    assert "| — | — | — | — | — |" in proc.stdout


# ── extra-pipe: title with '|' is escaped ────────────────────────────────────
def test_title_pipe_escaped(tmp_path):
    root = make_root(
        tmp_path,
        open_tickets=[field("0001-a", "0001", "solution", "a|b")],
    )
    proc = run_cmd(root)
    assert proc.returncode == 0, proc.stderr
    assert "a\\|b" in proc.stdout
    # table structure intact: the data row still has 5 columns (6 pipes incl. the
    # escaped one, which does not open a new cell).
    row = next(line for line in proc.stdout.splitlines() if line.startswith("| 0001 |"))
    assert row.replace("\\|", "").count("|") == 6


# ── extra-nl: embedded newline -> single space ───────────────────────────────
def test_title_newline_to_space(tmp_path):
    # status.md is line-based (`key: value`), so a title value read from a matched
    # line can never physically carry a newline — the format terminates it. The
    # newline sanitization is defense-in-depth, so exercise sanitize_title directly.
    module = load_script_module(tmp_path)
    assert module.sanitize_title("line1\nline2") == "line1 line2"
    assert module.sanitize_title("a\r\nb") == "a b"
    assert module.sanitize_title("plain title") == "plain title"


# ── NFR-3: title > 39 chars truncated ────────────────────────────────────────
def test_long_title_truncated(tmp_path):
    long_title = "T" * 45
    root = make_root(
        tmp_path,
        open_tickets=[field("0001-a", "0001", "solution", long_title)],
    )
    proc = run_cmd(root)
    assert proc.returncode == 0, proc.stderr
    assert ("T" * 39 + "…") in proc.stdout
    assert ("T" * 40) not in proc.stdout


# ── NFR-3b: title of exactly 39 chars unchanged ──────────────────────────────
def test_title_exactly_39_unchanged(tmp_path):
    title = "E" * 39
    root = make_root(
        tmp_path,
        open_tickets=[field("0001-a", "0001", "solution", title)],
    )
    proc = run_cmd(root)
    assert proc.returncode == 0, proc.stderr
    assert title in proc.stdout
    assert "…" not in proc.stdout


# ── FR-10: summary line counts ───────────────────────────────────────────────
def test_summary_counts(tmp_path):
    proc = run_cmd(sample_root(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert "5 tickets (3 open, 2 completed)" in proc.stdout


def test_summary_counts_with_filter(tmp_path):
    proc = run_cmd(sample_root(tmp_path), "--open")
    assert proc.returncode == 0, proc.stderr
    assert "3 tickets (3 open, 0 completed)" in proc.stdout


# ── FR-12 (absent) / no-match: "No tickets found." ───────────────────────────
def test_no_tickets_dir(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = run_cmd(empty)
    assert proc.returncode == 0
    assert proc.stdout.strip() == "No tickets found."


def test_no_matching_status(tmp_path):
    proc = run_cmd(sample_root(tmp_path), "--status", "build")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "No tickets found."


# ── FR-13: problem.md template carries effort: small ─────────────────────────
def test_problem_template_has_effort_field():
    text = (ROOT / "commands" / "problem.md").read_text(encoding="utf-8")
    assert "effort: small" in text


# ── allow-list ownership: canonical VALID_STAGES, prose references it ─────────
def test_valid_stages_is_canonical():
    text = (ROOT / "commands" / "ticket-list.md").read_text(encoding="utf-8")
    assert "VALID_STAGES" in text
    # The prose must point at the constant rather than re-listing all seven stages
    # as prose outside the script. The full comma-joined stage list appears only
    # inside the python block (the tuple + its error message), not as prose.
    prose = text.split("```python", 1)[0]
    assert "VALID_STAGES" in prose


# ── harness-tickets model: ledger enumeration (new contract) ─────────────────
#
# Under the `.harness-tickets` branch design, in-flight tickets are no longer on
# `main`; the script enumerates them from the ledger via `ticket.py list-json` and
# unions that, de-duped by number, with the legacy `.tickets/*` scan. These tests
# stub `ticket.py list-json` (pointed at by CLAUDE_PLUGIN_ROOT) to drive the
# ledger path deterministically without a real ledger/git.


def write_ledger_stub(plugin_dir: Path, rows: list[dict]) -> None:
    """Create a stub `ticket.py` whose `list-json` subcommand prints ``rows`` — the
    shape the real `ticket.py list-json` emits from the ledger
    (``{number, slug, title, status, effort, depends_on, branch, completed, ...}``).
    ``rows`` is written to a sidecar JSON file the stub loads, so no test data is
    baked into the generated script body."""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "ledger_rows.json").write_text(json.dumps(rows), encoding="utf-8")
    (plugin_dir / "ticket.py").write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "if sys.argv[1:2] == ['list-json']:\n"
        "    print(Path(__file__).with_name('ledger_rows.json').read_text(encoding='utf-8'))\n"
        "    sys.exit(0)\n"
        "sys.exit(2)\n",
        encoding="utf-8",
    )


def write_failing_stub(plugin_dir: Path) -> None:
    """A stub `ticket.py` whose `list-json` exits non-zero — models an unreachable
    or erroring engine, which must degrade to the `.tickets/*` legacy scan."""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "ticket.py").write_text(
        "import sys\nsys.exit(1)\n", encoding="utf-8"
    )


def run_cmd_env(cwd: Path, plugin_dir: Path | None, *flags: str) -> subprocess.CompletedProcess[str]:
    """Like :func:`run_cmd`, but with an explicit ``CLAUDE_PLUGIN_ROOT`` (or its
    removal) so the ledger-enumeration branch of the script can be driven."""
    script_path = cwd / "_ticket_list_script.py"
    script_path.write_text(extract_script(), encoding="utf-8")
    env = dict(os.environ)
    if plugin_dir is not None:
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_dir)
    else:
        env.pop("CLAUDE_PLUGIN_ROOT", None)
    return subprocess.run(
        [sys.executable, str(script_path), *flags],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def ledger_row(number, status, title, effort=None, completed=False):
    row = {
        "number": number,
        "slug": f"{number}-{title.lower().replace(' ', '-')}",
        "title": title,
        "status": status,
        "owner": "dev@example.com",
        "effort": effort,
        "depends_on": "",
        "branch": f"ticket/{number}-slug",
        "completed": completed,
    }
    return row


def count_rows(stdout: str, ticket: str) -> int:
    return sum(1 for line in stdout.splitlines() if line.startswith(f"| {ticket} |"))


def test_ledger_only_in_flight_ticket_appears(tmp_path):
    """A newly-claimed in-flight ticket exists ONLY in the ledger (nothing on
    `main`). It must still be listed — this is the core of the new contract."""
    root = tmp_path / "repo"
    (root / ".tickets").mkdir(parents=True)  # present but empty of open tickets
    plugin = tmp_path / "plugin"
    write_ledger_stub(plugin, [ledger_row("0009", "implementing", "Ledger only work", "medium")])
    proc = run_cmd_env(root, plugin)
    assert proc.returncode == 0, proc.stderr
    assert "| 0009 |" in proc.stdout
    assert "Ledger only work" in proc.stdout
    assert "1 ticket (1 open, 0 completed)" in proc.stdout


def test_ledger_and_scan_union_dedup_scan_wins(tmp_path):
    """A number present in BOTH the ledger and a local `.tickets/` copy appears
    exactly once, and the richer scan row (carrying `updated`) wins the union."""
    root = make_root(
        tmp_path,
        open_tickets=[field("0001-alpha", "0001", "solution", "Local copy", "small")],
    )
    plugin = tmp_path / "plugin"
    # Ledger reports the same number with a *different* status and no `updated`.
    write_ledger_stub(plugin, [ledger_row("0001", "implementing", "Ledger copy", "large")])
    proc = run_cmd_env(root, plugin)
    assert proc.returncode == 0, proc.stderr
    assert count_rows(proc.stdout, "0001") == 1, "union must de-duplicate by number"
    row = next(line for line in proc.stdout.splitlines() if line.startswith("| 0001 |"))
    assert "solution" in row and "2026-06-21" in row, "scan row (richer) wins the union"
    assert "1 ticket (1 open, 0 completed)" in proc.stdout


def test_ledger_completed_ticket_routes_to_completed(tmp_path):
    """A ledger row flagged completed (delivered/cancelled) is a completed ticket:
    excluded by --open, included by --completed."""
    root = tmp_path / "repo"
    (root / ".tickets").mkdir(parents=True)
    plugin = tmp_path / "plugin"
    write_ledger_stub(
        plugin,
        [
            ledger_row("0007", "implementing", "Still going", "small", completed=False),
            ledger_row("0008", "cancelled", "Dropped", "medium", completed=True),
        ],
    )
    proc_all = run_cmd_env(root, plugin)
    assert proc_all.returncode == 0, proc_all.stderr
    assert "2 tickets (1 open, 1 completed)" in proc_all.stdout

    proc_open = run_cmd_env(root, plugin, "--open")
    assert "| 0007 |" in proc_open.stdout
    assert "| 0008 |" not in proc_open.stdout

    proc_done = run_cmd_env(root, plugin, "--completed")
    assert "| 0008 |" in proc_done.stdout
    assert "| 0007 |" not in proc_done.stdout


def test_ledger_status_filter_applies_to_ledger_rows(tmp_path):
    """--status filters the merged set, including ledger-sourced rows."""
    root = tmp_path / "repo"
    (root / ".tickets").mkdir(parents=True)
    plugin = tmp_path / "plugin"
    write_ledger_stub(
        plugin,
        [
            ledger_row("0011", "solution", "Design phase", "small"),
            ledger_row("0012", "implementing", "Build phase", "medium"),
        ],
    )
    proc = run_cmd_env(root, plugin, "--status", "solution")
    assert proc.returncode == 0, proc.stderr
    assert "| 0011 |" in proc.stdout
    assert "| 0012 |" not in proc.stdout


def test_ledger_failure_falls_back_to_scan(tmp_path):
    """When the engine errors (non-zero `list-json`), the `.tickets/*` legacy scan
    still renders — the ledger is additive, never load-bearing for local copies."""
    root = make_root(
        tmp_path,
        open_tickets=[field("0002-beta", "0002", "implementing", "Legacy scan", "medium")],
    )
    plugin = tmp_path / "plugin"
    write_failing_stub(plugin)
    proc = run_cmd_env(root, plugin)
    assert proc.returncode == 0, proc.stderr
    assert "| 0002 |" in proc.stdout
    assert "Legacy scan" in proc.stdout


def test_ledger_union_merges_distinct_numbers(tmp_path):
    """Legacy `.tickets/` ticket + ledger-only ticket both appear (union), sorted."""
    root = make_root(
        tmp_path,
        open_tickets=[field("0053-legacy", "0053", "implementing", "Pre-migration", "small")],
    )
    plugin = tmp_path / "plugin"
    write_ledger_stub(plugin, [ledger_row("0070", "solution", "New model", "medium")])
    proc = run_cmd_env(root, plugin)
    assert proc.returncode == 0, proc.stderr
    assert "| 0053 |" in proc.stdout  # legacy scan
    assert "| 0070 |" in proc.stdout  # ledger
    positions = [proc.stdout.index(f"| {tk} |") for tk in ("0053", "0070")]
    assert positions == sorted(positions), "merged rows stay ascending by number"
    assert "2 tickets (2 open, 0 completed)" in proc.stdout


def test_command_documents_ledger_source():
    """The prose must document ledger enumeration + the legacy-scan fallback."""
    text = (ROOT / "commands" / "ticket-list.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "list-json" in text, "must invoke `ticket.py list-json`"
    assert "harness-tickets" in lower and "ledger" in lower
    assert "legacy" in lower, "must frame the `.tickets/*` scan as a legacy fallback"
