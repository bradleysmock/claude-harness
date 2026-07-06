"""Integration tests for the /export command (commands/export.md).

The command's logic lives entirely in a single fenced ```python block. These tests
extract that block, run it against throwaway `.tickets/` fixture trees, and assert on
stdout, the written file, stderr, and the exit code. JSON is parsed and CSV is read
back through ``csv.reader`` so the schema contract and quoting are verified for real.
"""
from __future__ import annotations

import csv
import importlib.util
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

COMMAND_FILE = Path(__file__).parent.parent / "commands" / "export.md"
_DEVNULL = subprocess.DEVNULL

SCHEMA = [
    "ticket", "title", "status", "updated", "branch",
    "problem_summary", "solution_summary", "commits", "commits_truncated",
]


def _extract_script() -> str:
    text = COMMAND_FILE.read_text(encoding="utf-8")
    blocks = re.findall(r"```python\n(.*?)\n```", text, re.DOTALL)
    assert len(blocks) == 1, "commands/export.md must contain exactly one ```python block"
    return blocks[0]


SCRIPT = _extract_script()


def _write_ticket(
    root: Path,
    dirname: str,
    *,
    status: str = "done",
    title: str = "A ticket",
    updated: str = "2026-06-01",
    branch: str | None = None,
    problem: str | None = None,
    solution: str | None = None,
    completed: bool = False,
) -> Path:
    base = root / ".tickets" / "completed" if completed else root / ".tickets"
    d = base / dirname
    d.mkdir(parents=True, exist_ok=True)
    lines = [
        f"status: {status}",
        f"ticket: {dirname[:4]}",
        f"title: {title}",
    ]
    if branch is not None:
        lines.append(f"branch: {branch}")
    lines.append(f"updated: {updated}")
    (d / "status.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if problem is not None:
        (d / "problem.md").write_text(problem, encoding="utf-8")
    if solution is not None:
        (d / "solution.md").write_text(solution, encoding="utf-8")
    return d


def _run(root: Path, tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    script = tmp_path / "_export.py"
    script.write_text(SCRIPT, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=root, capture_output=True, text=True,
    )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True,
                   stdout=_DEVNULL, stderr=_DEVNULL)


def _init_git_repo(root: Path) -> None:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "dev@example.com")
    _git(root, "config", "user.name", "Dev")


def _load_module(tmp_path: Path) -> ModuleType:
    """Import the extracted script as a module to unit-test its serializers."""
    script = tmp_path / "_export_mod.py"
    script.write_text(SCRIPT, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("export_cmd", script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- #
# Structure / security markers
# --------------------------------------------------------------------------- #

def test_command_file_has_single_python_block():
    # Exactly one block (enforced in _extract_script) and it is argparse-driven.
    assert "argparse" in SCRIPT
    # QUOTE_ALL is the CSV contract; --end-of-options is the option-injection guard.
    # These two are behaviour-defining guarantees worth pinning in source; the rest
    # of the behaviour is asserted by executing the script below.
    assert "csv.QUOTE_ALL" in SCRIPT
    assert "--end-of-options" in SCRIPT
    # no dynamic code execution primitives
    for forbidden in ("eval" + "(", "exec" + "("):
        assert forbidden not in SCRIPT


# --------------------------------------------------------------------------- #
# FR-1 end-to-end + FR-10 JSON shape
# --------------------------------------------------------------------------- #

def test_default_json_array_of_completed_tickets(tmp_path):
    root = tmp_path / "proj"
    _write_ticket(root, "0001-feat-a", status="done", title="First")
    _write_ticket(root, "0002-fix-b", status="cancelled", title="Second")
    r = _run(root, tmp_path)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert isinstance(data, list)
    assert [rec["ticket"] for rec in data] == ["0001", "0002"]
    for rec in data:
        assert list(rec.keys()) == SCHEMA


# --------------------------------------------------------------------------- #
# FR-3 default filter / FR-4 --all
# --------------------------------------------------------------------------- #

def test_default_excludes_in_flight_statuses(tmp_path):
    root = tmp_path / "proj"
    _write_ticket(root, "0001-feat-done", status="done")
    _write_ticket(root, "0002-feat-cancelled", status="cancelled")
    for i, st in enumerate(
        ["problem", "requirements", "solution", "implementing",
         "review-ready", "changes-requested"], start=3,
    ):
        _write_ticket(root, f"{i:04d}-feat-{st}", status=st)
    r = _run(root, tmp_path)
    assert r.returncode == 0, r.stderr
    statuses = {rec["status"] for rec in json.loads(r.stdout)}
    assert statuses == {"done", "cancelled"}


def test_all_flag_includes_every_status(tmp_path):
    root = tmp_path / "proj"
    _write_ticket(root, "0001-feat-done", status="done")
    _write_ticket(root, "0002-feat-impl", status="implementing")
    _write_ticket(root, "0003-feat-sol", status="solution")
    r = _run(root, tmp_path, "--all")
    assert r.returncode == 0, r.stderr
    statuses = {rec["status"] for rec in json.loads(r.stdout)}
    assert statuses == {"done", "implementing", "solution"}


# --------------------------------------------------------------------------- #
# FR-6 summaries
# --------------------------------------------------------------------------- #

def test_problem_and_solution_summaries_extracted_and_stripped(tmp_path):
    root = tmp_path / "proj"
    _write_ticket(
        root, "0001-feat-a", status="done",
        problem="# Problem Statement\n\n## Problem\n\n   The core problem paragraph.   \n\n## Impact\nx\n",
        solution="# Solution\n\n## Approach\n\nThe chosen approach paragraph.\n\n## Components\ny\n",
    )
    rec = json.loads(_run(root, tmp_path).stdout)[0]
    assert rec["problem_summary"] == "The core problem paragraph."
    assert rec["solution_summary"] == "The chosen approach paragraph."


def test_solution_summary_null_when_heading_absent(tmp_path):
    root = tmp_path / "proj"
    _write_ticket(
        root, "0001-feat-a", status="done",
        solution="# Solution\n\n## Overview\n\nNo approach heading here.\n",
    )
    rec = json.loads(_run(root, tmp_path).stdout)[0]
    assert rec["solution_summary"] is None


def test_missing_solution_file_yields_null_without_error(tmp_path):
    root = tmp_path / "proj"
    _write_ticket(root, "0001-feat-a", status="done", solution=None)
    r = _run(root, tmp_path)
    assert r.returncode == 0, r.stderr
    rec = json.loads(r.stdout)[0]
    assert rec["solution_summary"] is None


def test_problem_summary_null_when_file_or_heading_absent(tmp_path):
    # Symmetric to the solution-summary null cases (FR-6): no problem.md at all,
    # and a problem.md whose `## Problem` heading is missing, both yield null.
    root = tmp_path / "proj"
    _write_ticket(root, "0001-feat-none", status="done", problem=None)
    _write_ticket(root, "0002-feat-noheading", status="done",
                  problem="# Ticket\n\n## Impact\n\nOnly an impact section.\n")
    data = {rec["ticket"]: rec for rec in json.loads(_run(root, tmp_path).stdout)}
    assert data["0001"]["problem_summary"] is None
    assert data["0002"]["problem_summary"] is None


# --------------------------------------------------------------------------- #
# FR-6 commits (branch absent) + C-09 truncation
# --------------------------------------------------------------------------- #

def test_commits_empty_when_branch_absent(tmp_path):
    root = tmp_path / "proj"
    _write_ticket(root, "0001-feat-a", status="done", branch=None)
    rec = json.loads(_run(root, tmp_path).stdout)[0]
    assert rec["commits"] == []
    assert rec["commits_truncated"] is False


def test_commits_truncated_flag(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _init_git_repo(root)
    _git(root, "checkout", "-q", "-b", "ticket/0001-feat-many")
    for i in range(50):
        _git(root, "commit", "-q", "--allow-empty", "-m", f"commit {i}")
    # a second branch with only three commits, cut from an early point
    _git(root, "checkout", "-q", "-B", "ticket/0002-feat-few",
         "ticket/0001-feat-many~47")
    _write_ticket(root, "0001-feat-many", status="done", branch="ticket/0001-feat-many")
    _write_ticket(root, "0002-feat-few", status="done", branch="ticket/0002-feat-few")
    data = {rec["ticket"]: rec for rec in json.loads(_run(root, tmp_path).stdout)}
    assert len(data["0001"]["commits"]) == 50
    assert data["0001"]["commits_truncated"] is True
    assert len(data["0002"]["commits"]) == 3
    assert data["0002"]["commits_truncated"] is False


# --------------------------------------------------------------------------- #
# FR-7 completed/ discovery
# --------------------------------------------------------------------------- #

def test_includes_tickets_from_completed_dir(tmp_path):
    root = tmp_path / "proj"
    _write_ticket(root, "0001-feat-root", status="done")
    _write_ticket(root, "0002-feat-archived", status="done", completed=True)
    tickets = {rec["ticket"] for rec in json.loads(_run(root, tmp_path).stdout)}
    assert tickets == {"0001", "0002"}


# --------------------------------------------------------------------------- #
# Schema contract (JSON + CSV)
# --------------------------------------------------------------------------- #

def test_json_field_names_match_schema(tmp_path):
    root = tmp_path / "proj"
    _write_ticket(root, "0001-feat-a", status="done")
    rec = json.loads(_run(root, tmp_path).stdout)[0]
    assert list(rec.keys()) == SCHEMA


def test_csv_header_matches_schema_order(tmp_path):
    root = tmp_path / "proj"
    _write_ticket(root, "0001-feat-a", status="done")
    r = _run(root, tmp_path, "--format", "csv")
    assert r.returncode == 0, r.stderr
    rows = list(csv.reader(io.StringIO(r.stdout)))
    assert rows[0] == SCHEMA


# --------------------------------------------------------------------------- #
# FR-2 / FR-9 CSV quoting round-trip
# --------------------------------------------------------------------------- #

def test_csv_quotes_commas_and_quotes(tmp_path):
    # A realistic title carrying a comma and quote characters must round-trip.
    root = tmp_path / "proj"
    nasty = 'Ticket export (JSON/CSV), "quoted" edition'
    _write_ticket(root, "0001-feat-a", status="done", title=nasty)
    r = _run(root, tmp_path, "--format", "csv")
    assert r.returncode == 0, r.stderr
    rows = list(csv.reader(io.StringIO(r.stdout)))
    assert rows[0] == SCHEMA
    assert rows[1][SCHEMA.index("title")] == nasty


def test_csv_serializer_quotes_newline_field(tmp_path):
    # No status.md field carries a newline, so exercise the serializer directly:
    # QUOTE_ALL must quote a field with a comma, newline, and quote so it survives
    # a csv.reader round-trip.
    mod = _load_module(tmp_path)
    record = {
        "ticket": "0001", "title": 'a, b "c"\nd', "status": "done",
        "updated": "2026-06-01", "branch": "", "problem_summary": None,
        "solution_summary": None, "commits": [], "commits_truncated": False,
    }
    text = mod.to_csv([record])
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == SCHEMA
    assert rows[1][SCHEMA.index("title")] == 'a, b "c"\nd'
    # QUOTE_ALL: an empty field is emitted as "" and reads back as ""
    assert rows[1][SCHEMA.index("problem_summary")] == ""


# --------------------------------------------------------------------------- #
# FR-5 output destination
# --------------------------------------------------------------------------- #

def test_output_file_written_and_stdout_empty(tmp_path):
    root = tmp_path / "proj"
    _write_ticket(root, "0001-feat-a", status="done")
    out = tmp_path / "report.json"
    r = _run(root, tmp_path, "--output", str(out))
    assert r.returncode == 0, r.stderr
    assert r.stdout == ""
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data[0]["ticket"] == "0001"


# --------------------------------------------------------------------------- #
# Security: dir-name guard + output containment
# --------------------------------------------------------------------------- #

def test_malicious_dir_names_are_skipped(tmp_path):
    root = tmp_path / "proj"
    _write_ticket(root, "0001-feat-a", status="done")
    for bad in ["..", "0001; echo pwned", "$(touch x)", "completed-extra", "_standards.md"]:
        try:
            (root / ".tickets" / bad).mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
    tickets = {rec["ticket"] for rec in json.loads(_run(root, tmp_path).stdout)}
    assert tickets == {"0001"}


def test_output_inside_tickets_is_rejected(tmp_path):
    root = tmp_path / "proj"
    _write_ticket(root, "0001-feat-a", status="done")
    inside = root / ".tickets" / "leak.json"
    r = _run(root, tmp_path, "--output", str(inside))
    assert r.returncode != 0
    assert not inside.exists()
    assert "tickets" in r.stderr.lower()


def test_output_outside_tickets_proceeds(tmp_path):
    root = tmp_path / "proj"
    _write_ticket(root, "0001-feat-a", status="done")
    outside = tmp_path / "out.json"
    r = _run(root, tmp_path, "--output", str(outside))
    assert r.returncode == 0, r.stderr
    assert outside.exists()


# --------------------------------------------------------------------------- #
# Shell safety: an injection payload in a branch name never executes
# --------------------------------------------------------------------------- #

def test_branch_shell_injection_is_not_executed(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _init_git_repo(root)
    _git(root, "commit", "-q", "--allow-empty", "-m", "root")
    _write_ticket(root, "0001-feat-a", status="done",
                  branch="foo; touch INJECTED")
    r = _run(root, tmp_path)
    assert r.returncode == 0, r.stderr
    assert not (root / "INJECTED").exists()
    rec = json.loads(r.stdout)[0]
    assert rec["commits"] == []


def test_branch_option_injection_cannot_write_files(tmp_path):
    # A branch value starting with '-' must never be parsed by git as an option:
    # `git log --output=<file>` would otherwise write an arbitrary file, bypassing
    # the --output containment guard. The leading-'-' reject + --end-of-options
    # neutralize it, and the record's commits come back empty.
    root = tmp_path / "proj"
    root.mkdir()
    _init_git_repo(root)
    _git(root, "commit", "-q", "--allow-empty", "-m", "root")
    pwned = tmp_path / "pwned.txt"
    _write_ticket(root, "0001-feat-a", status="done",
                  branch=f"--output={pwned}")
    r = _run(root, tmp_path)
    assert r.returncode == 0, r.stderr
    assert not pwned.exists()
    rec = json.loads(r.stdout)[0]
    assert rec["commits"] == []
    assert rec["commits_truncated"] is False
