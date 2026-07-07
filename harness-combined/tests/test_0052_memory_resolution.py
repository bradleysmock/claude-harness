"""FR-4 / FR-5: failure memory carries an optional resolution summary.

Covers: resolution round-trips through record()/retrieve; records with no
resolution render unchanged; a legacy database (table created WITHOUT the
resolution column) migrates in place and stays retrievable; the MCP `memory`
tool accepts and forwards the resolution argument.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from memory import SQLiteFailureMemory, _tokenise  # noqa: E402  (path set above)

ERRORS = "server.py:12: error: Missing return type annotation [no-untyped-def]"


def _mem(tmp_path: Path) -> SQLiteFailureMemory:
    return SQLiteFailureMemory(str(tmp_path / "memory.db"))


def test_resolution_round_trips(tmp_path):
    mem = _mem(tmp_path)
    mem.record("s1", "type_check", ERRORS, attempt=1, outcome="passed",
               resolution="added -> None return annotation on parse()")
    narratives = mem.retrieve_similar(ERRORS, "type_check")
    assert narratives, "a matching record should be retrieved"
    assert "Resolution: added -> None return annotation on parse()" in narratives[0]


def test_record_without_resolution_has_no_resolution_line(tmp_path):
    mem = _mem(tmp_path)
    mem.record("s1", "type_check", ERRORS, attempt=1, outcome="passed")
    narratives = mem.retrieve_similar(ERRORS, "type_check")
    assert narratives
    assert "Resolution:" not in narratives[0]


def test_empty_string_resolution_treated_as_none(tmp_path):
    mem = _mem(tmp_path)
    mem.record("s1", "lint", ERRORS, attempt=1, outcome="passed", resolution="")
    narratives = mem.retrieve_similar(ERRORS, "lint")
    assert narratives and "Resolution:" not in narratives[0]


def _make_legacy_db(path: Path) -> None:
    """Create a failure_records table WITHOUT the resolution column (pre-0052)."""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE failure_records (
            id TEXT PRIMARY KEY, spec_id TEXT NOT NULL, gate TEXT NOT NULL,
            errors_text TEXT NOT NULL, tokens_json TEXT NOT NULL,
            outcome TEXT NOT NULL, attempt INTEGER NOT NULL, timestamp TEXT NOT NULL
        );
        """
    )
    rid = hashlib.sha256(b"legacy").hexdigest()[:16]
    conn.execute(
        "INSERT INTO failure_records VALUES (?,?,?,?,?,?,?,?)",
        (rid, "legacy-spec", "type_check", ERRORS,
         json.dumps(_tokenise(f"gate:type_check {ERRORS}")), "passed", 1, "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()


def test_legacy_db_migrates_and_stays_retrievable(tmp_path):
    db = tmp_path / "legacy.db"
    _make_legacy_db(db)

    # Opening through SQLiteFailureMemory must add the column via guarded ALTER.
    mem = SQLiteFailureMemory(str(db))
    cols = {row[1] for row in sqlite3.connect(str(db)).execute("PRAGMA table_info(failure_records)")}
    assert "resolution" in cols, "guarded migration must add the resolution column"

    narratives = mem.retrieve_similar(ERRORS, "type_check")
    assert narratives, "legacy rows must remain retrievable after migration"
    assert "Resolution:" not in narratives[0], "legacy row has no resolution to render"

    # New records with a resolution work on the migrated db.
    mem.record("s2", "type_check", ERRORS, attempt=1, outcome="passed", resolution="fixed it")
    again = mem.retrieve_similar(ERRORS, "type_check")
    assert any("Resolution: fixed it" in n for n in again)


def test_repeat_init_is_noop(tmp_path):
    db = str(tmp_path / "memory.db")
    SQLiteFailureMemory(db)
    # Second construction must not raise (migration guard makes ALTER a no-op).
    SQLiteFailureMemory(db)


def test_mcp_memory_tool_forwards_resolution(tmp_path):
    import server

    fn = getattr(server.memory, "fn", server.memory)
    out = fn(action="record", project_root=str(tmp_path), spec_id="s1", gate="lint",
             errors_text=ERRORS, attempt=1, outcome="passed", resolution="ran ruff --fix")
    assert out == "recorded"
    retrieved = fn(action="retrieve", project_root=str(tmp_path), errors_text=ERRORS, gate="lint")
    assert "Resolution: ran ruff --fix" in retrieved
