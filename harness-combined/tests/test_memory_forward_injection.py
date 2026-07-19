"""Memory forward-injection: proactive `gotchas` retrieval + `target_file` column.

Mirrors the 0052 migration tests. Covers the design's Verification section:

1. Back-compat: a DB with `resolution` but no `target_file` migrates once via the
   generalized `_migrate_column`; legacy record/retrieve round-trips unchanged.
2. gotchas filter: `escalated` records excluded by default; only `passed` surface,
   and their `resolution` appears in the narrative.
3. Area proximity: an exact-`target_file` record ranks above same-language records
   elsewhere.
4. Language fence: a record whose gate is outside a language's gate set does not
   surface for that language.
5. Empty corpus: `gotchas` on a fresh DB returns empty.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from memory import SQLiteFailureMemory, _tokenise  # noqa: E402  (path set above)

ERRORS = "app.py:12: error: Missing return type annotation [no-untyped-def]"


def _mem(tmp_path: Path) -> SQLiteFailureMemory:
    return SQLiteFailureMemory(str(tmp_path / "memory.db"))


# ── 1. Back-compat migration (resolution present, target_file absent) ──────────

def _make_resolution_only_db(path: Path) -> None:
    """Create a table WITH resolution but WITHOUT target_file (post-0052, pre-this)."""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE failure_records (
            id TEXT PRIMARY KEY, spec_id TEXT NOT NULL, gate TEXT NOT NULL,
            errors_text TEXT NOT NULL, tokens_json TEXT NOT NULL,
            outcome TEXT NOT NULL, attempt INTEGER NOT NULL, timestamp TEXT NOT NULL,
            resolution TEXT
        );
        """
    )
    rid = hashlib.sha256(b"legacy").hexdigest()[:16]
    conn.execute(
        "INSERT INTO failure_records "
        "(id, spec_id, gate, errors_text, tokens_json, outcome, attempt, timestamp, resolution) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (rid, "legacy-spec", "type_check", ERRORS,
         json.dumps(_tokenise(f"gate:type_check {ERRORS}")), "passed", 1,
         "2026-01-01T00:00:00+00:00", "added annotation"),
    )
    conn.commit()
    conn.close()


def test_resolution_only_db_migrates_target_file_and_stays_retrievable(tmp_path):
    db = tmp_path / "resonly.db"
    _make_resolution_only_db(db)

    mem = SQLiteFailureMemory(str(db))
    cols = {row[1] for row in sqlite3.connect(str(db)).execute("PRAGMA table_info(failure_records)")}
    assert "target_file" in cols, "migration must add the target_file column"
    assert "resolution" in cols, "resolution column must survive the migration"

    # Legacy error-keyed retrieval is unchanged.
    narratives = mem.retrieve_similar(ERRORS, "type_check")
    assert narratives, "legacy rows remain retrievable after migration"
    assert "Resolution: added annotation" in narratives[0]

    # New records with a target_file work on the migrated db and are gotcha-retrievable.
    mem.record("s2", "type_check", ERRORS, attempt=1, outcome="passed",
               resolution="fixed it", target_file="app.py")
    hits = mem.retrieve_gotchas("app.py", "return annotation", "python")
    assert any("fixed it" in h for h in hits)


def test_repeat_init_is_noop(tmp_path):
    db = str(tmp_path / "memory.db")
    SQLiteFailureMemory(db)
    SQLiteFailureMemory(db)  # second construction must not raise


def test_fresh_db_has_target_file_column(tmp_path):
    _mem(tmp_path)
    cols = {row[1] for row in
            sqlite3.connect(str(tmp_path / "memory.db")).execute("PRAGMA table_info(failure_records)")}
    assert "target_file" in cols


# ── 2. gotchas filter: only passed surface; resolution is injected ─────────────

def test_gotchas_filters_to_passed_and_surfaces_resolution(tmp_path):
    mem = _mem(tmp_path)
    mem.record("s-pass", "type_check", ERRORS, attempt=2, outcome="passed",
               resolution="added -> None on parse()", target_file="src/app.py")
    mem.record("s-esc", "type_check", "app.py:9: some other failure", attempt=3,
               outcome="escalated", resolution=None, target_file="src/app.py")

    hits = mem.retrieve_gotchas("src/app.py", "return annotation parse", "python", limit=5)
    joined = "\n".join(hits)
    assert "added -> None on parse()" in joined, "resolution of the passed record must surface"
    assert "fixed by" in joined
    assert "some other failure" not in joined, "escalated records must not surface"


def test_gotchas_without_resolution_has_no_fixed_by_line(tmp_path):
    mem = _mem(tmp_path)
    mem.record("s1", "lint", ERRORS, attempt=1, outcome="passed", target_file="src/app.py")
    hits = mem.retrieve_gotchas("src/app.py", "annotation", "python")
    assert hits
    assert "fixed by" not in "\n".join(hits), "no resolution => no fix line"


# ── 3. Area proximity: exact target_file ranks above elsewhere ─────────────────

def test_area_proximity_exact_file_ranks_first(tmp_path):
    mem = _mem(tmp_path)
    # Record the "elsewhere" one first so timestamp order can't accidentally win.
    mem.record("s-far", "type_check", ERRORS, attempt=1, outcome="passed",
               resolution="far fix", target_file="other/thing.py")
    mem.record("s-here", "type_check", ERRORS, attempt=1, outcome="passed",
               resolution="here fix", target_file="src/app.py")

    hits = mem.retrieve_gotchas("src/app.py", "return annotation", "python", limit=5)
    assert len(hits) >= 2
    assert "here fix" in hits[0], "exact target_file match must rank first"
    assert any("far fix" in h for h in hits[1:])


def test_same_directory_ranks_above_elsewhere(tmp_path):
    mem = _mem(tmp_path)
    mem.record("s-far", "type_check", ERRORS, attempt=1, outcome="passed",
               resolution="far fix", target_file="other/thing.py")
    mem.record("s-sibling", "type_check", ERRORS, attempt=1, outcome="passed",
               resolution="sibling fix", target_file="src/helper.py")

    # Query a file in src/ that has no exact match; same-dir sibling should win.
    hits = mem.retrieve_gotchas("src/app.py", "return annotation", "python", limit=5)
    assert len(hits) >= 2
    assert "sibling fix" in hits[0], "same-directory match must rank above elsewhere"


# ── 4. Language fence: a gate outside the language set does not surface ─────────

def test_language_fence_excludes_foreign_gate(tmp_path):
    mem = _mem(tmp_path)
    # clippy is a rust gate, not in python's gate set.
    mem.record("s-rust", "clippy", "warning: needless clone", attempt=1,
               outcome="passed", resolution="removed clone", target_file="src/app.py")

    assert mem.retrieve_gotchas("src/app.py", "clone", "python") == [], \
        "a rust gate must not surface for language=python"
    # It surfaces for its own language.
    rust_hits = mem.retrieve_gotchas("src/app.py", "clone", "rust")
    assert any("removed clone" in h for h in rust_hits)


def test_unknown_language_returns_empty(tmp_path):
    mem = _mem(tmp_path)
    mem.record("s1", "type_check", ERRORS, attempt=1, outcome="passed",
               resolution="x", target_file="src/app.py")
    assert mem.retrieve_gotchas("src/app.py", "annotation", "cobol") == []


# ── 5. Empty corpus ───────────────────────────────────────────────────────────

def test_gotchas_empty_corpus_returns_empty(tmp_path):
    mem = _mem(tmp_path)
    assert mem.retrieve_gotchas("src/app.py", "anything", "python") == []


# ── Reactive path is preserved unchanged ───────────────────────────────────────

def test_record_target_file_does_not_break_retrieve_similar(tmp_path):
    mem = _mem(tmp_path)
    mem.record("s1", "type_check", ERRORS, attempt=1, outcome="passed",
               resolution="added annotation", target_file="src/app.py")
    narratives = mem.retrieve_similar(ERRORS, "type_check")
    assert narratives and "Resolution: added annotation" in narratives[0]


# ── MCP server tool wiring ─────────────────────────────────────────────────────

def test_mcp_memory_tool_gotchas_branch(tmp_path):
    import server

    fn = getattr(server.memory, "fn", server.memory)
    # Fresh corpus => empty gotchas block.
    empty = fn(action="gotchas", project_root=str(tmp_path),
               target_file="src/app.py", description="anything", language="python")
    assert empty == "", "empty corpus must yield an empty gotchas block"

    out = fn(action="record", project_root=str(tmp_path), spec_id="s1", gate="type_check",
             errors_text=ERRORS, attempt=1, outcome="passed",
             resolution="added -> None on parse()", target_file="src/app.py")
    assert out == "recorded"

    block = fn(action="gotchas", project_root=str(tmp_path),
               target_file="src/app.py", description="return annotation", language="python")
    assert "added -> None on parse()" in block
    assert "type_check" in block
