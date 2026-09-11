"""Tests for context_rank.py — local context packages (ticket 0076)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import context_rank
from context_rank import (
    Snippet,
    describe_environment,
    gather_context,
    get_or_generate_pack,
)


def _init_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "a"], cwd=tmp_path, check=True)
    return tmp_path


def _commit_all(repo: Path, message: str = "commit") -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=repo, check=True)


# ---------------------------------------------------------------------------
# FR-1/2/3 — ranking, memory.tokenize reuse, determinism
# ---------------------------------------------------------------------------

def test_needle_file_ranks_above_unrelated(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / "needle.py").write_text(
        "def resolve_ticket_status(ticket_number):\n    return ticket_number\n"
    )
    (tmp_path / "unrelated.py").write_text("def unrelated_thing():\n    pass\n")
    _commit_all(tmp_path)

    snippets = gather_context("resolve ticket status", str(tmp_path))
    assert snippets
    assert snippets[0].file == "needle.py"


def test_gather_context_is_deterministic(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("def resolve_ticket():\n    pass\n")
    _commit_all(tmp_path)
    first = gather_context("resolve ticket", str(tmp_path))
    second = gather_context("resolve ticket", str(tmp_path))
    assert first == second


def test_multi_term_query_uses_one_rg_invocation(tmp_path: Path, monkeypatch):
    """Regression: gather_context previously spawned one `rg` subprocess per
    query term — a real problem statement can yield dozens of terms."""
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text(
        "def resolve_ticket_status_for_gate_promotion_policy():\n    pass\n"
    )
    _commit_all(tmp_path)

    calls: list[list[str]] = []
    real_exec = context_rank._exec

    def _tracking_exec(command, cwd, timeout=context_rank._EXEC_TIMEOUT):
        calls.append(command)
        return real_exec(command, cwd, timeout)

    monkeypatch.setattr(context_rank, "_exec", _tracking_exec)
    query = "resolve ticket status for gate promotion policy and many other words here"
    gather_context(query, str(tmp_path))
    rg_calls = [c for c in calls if c[0] == "rg"]
    assert len(rg_calls) == 1


def test_reuses_memory_tokenize():
    import memory

    assert context_rank._query_terms("resolve_ticket status") == memory.tokenize(
        "resolve_ticket status"
    )


# ---------------------------------------------------------------------------
# FR-4/5 — own exec helper; degrade paths never raise or log
# ---------------------------------------------------------------------------

def test_rg_absent_yields_empty_pack(tmp_path: Path, monkeypatch):
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("def resolve_ticket():\n    pass\n")
    _commit_all(tmp_path)
    monkeypatch.setattr(context_rank.shutil, "which", lambda name: None)
    assert gather_context("resolve ticket", str(tmp_path)) == []


def test_describe_environment_reports_missing_tools(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(context_rank.shutil, "which", lambda name: None)
    message = describe_environment(str(tmp_path))
    assert message is not None
    assert "rg" in message


def test_describe_environment_none_when_everything_present(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(context_rank.shutil, "which", lambda name: "/usr/bin/" + name)
    assert describe_environment(str(tmp_path)) is None


def test_gather_context_never_raises_on_missing_project_root():
    assert gather_context("anything", "/definitely/does/not/exist") == []


# ---------------------------------------------------------------------------
# FR-6 — size caps
# ---------------------------------------------------------------------------

def test_max_snippets_respected(tmp_path: Path):
    _init_repo(tmp_path)
    for i in range(10):
        (tmp_path / f"file{i}.py").write_text(f"def resolve_ticket_{i}():\n    pass\n")
    _commit_all(tmp_path)
    snippets = gather_context("resolve ticket", str(tmp_path), max_snippets=3)
    assert len(snippets) <= 3


def test_total_lines_capped(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(context_rank, "MAX_TOTAL_LINES", 5)
    _init_repo(tmp_path)
    for i in range(10):
        (tmp_path / f"file{i}.py").write_text(f"def resolve_ticket_{i}():\n    pass\n")
    _commit_all(tmp_path)
    snippets = gather_context("resolve ticket", str(tmp_path), max_snippets=10)
    total = sum(s.lines[1] - s.lines[0] + 1 for s in snippets)
    assert total <= 5


# ---------------------------------------------------------------------------
# FR-7 — cache key reacts to query / HEAD / dirty-tree changes
# ---------------------------------------------------------------------------

def test_cache_reused_when_nothing_changed(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("def resolve_ticket():\n    pass\n")
    _commit_all(tmp_path)
    harness_dir = tmp_path / ".harness"
    harness_dir.mkdir()

    first = get_or_generate_pack("resolve ticket", str(tmp_path), "0001")
    pack_path = harness_dir / "context" / "0001.md"
    mtime_before = pack_path.stat().st_mtime_ns

    second = get_or_generate_pack("resolve ticket", str(tmp_path), "0001")
    assert second == first
    assert pack_path.stat().st_mtime_ns == mtime_before


def test_cache_invalidated_by_dirty_tree(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("def resolve_ticket():\n    pass\n")
    _commit_all(tmp_path)

    get_or_generate_pack("resolve ticket", str(tmp_path), "0001")
    pack_path = tmp_path / ".harness" / "context" / "0001.md"
    mtime_before = pack_path.stat().st_mtime_ns

    (tmp_path / "b.py").write_text("def resolve_ticket_two():\n    pass\n")
    get_or_generate_pack("resolve ticket", str(tmp_path), "0001")
    assert pack_path.stat().st_mtime_ns != mtime_before


def test_cache_invalidated_by_query_change(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("def resolve_ticket():\n    pass\n")
    _commit_all(tmp_path)

    first = get_or_generate_pack("resolve ticket", str(tmp_path), "0001")
    second = get_or_generate_pack("a totally different query", str(tmp_path), "0001")
    assert first != second


# ---------------------------------------------------------------------------
# FR-10 — .harness/context/ pack written correctly
# ---------------------------------------------------------------------------

def test_pack_written_to_harness_context(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("def resolve_ticket():\n    pass\n")
    _commit_all(tmp_path)
    get_or_generate_pack("resolve ticket", str(tmp_path), "0042")
    assert (tmp_path / ".harness" / "context" / "0042.md").exists()


def test_snippet_dataclass_fields():
    snippet = Snippet(file="a.py", lines=(1, 3), text="x", score=2.0)
    assert snippet.file == "a.py"
    assert snippet.lines == (1, 3)
