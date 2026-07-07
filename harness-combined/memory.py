"""
SQLite-backed failure memory with BM25-only retrieval.
No embeddings — pure keyword search over gate error text.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS failure_records (
    id          TEXT PRIMARY KEY,
    spec_id     TEXT NOT NULL,
    gate        TEXT NOT NULL,
    errors_text TEXT NOT NULL,
    tokens_json TEXT NOT NULL,
    outcome     TEXT NOT NULL,
    attempt     INTEGER NOT NULL,
    timestamp   TEXT NOT NULL,
    resolution  TEXT
);
CREATE INDEX IF NOT EXISTS idx_gate ON failure_records(gate);
"""


# ── Tokeniser ─────────────────────────────────────────────────────────────────

def _tokenise(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return re.findall(
        r"[a-z]{2,3}\d{3,}"      # error codes: ts2345, b105, e501
        r"|[a-z][a-z0-9_]{1,}"   # identifiers: type_check, foo_bar
        r"|\d{2,}",               # numbers: line numbers
        text,
    )


# ── BM25 Index ────────────────────────────────────────────────────────────────

class BM25Index:
    K1 = 1.5
    B  = 0.75

    def __init__(self, documents: list[tuple[str, list[str]]]) -> None:
        self._ids   = [d[0] for d in documents]
        self._toks  = {d[0]: d[1] for d in documents}
        self._n     = len(documents)
        self._avgdl = (
            sum(len(t) for _, t in documents) / self._n if self._n else 1.0
        )
        self._df: dict[str, int] = {}
        for _, tokens in documents:
            for tok in set(tokens):
                self._df[tok] = self._df.get(tok, 0) + 1

    def rank(self, query_tokens: list[str], limit: int = 50) -> list[tuple[str, float]]:
        if not query_tokens or not self._ids:
            return []
        scores = [(rid, self._score(rid, query_tokens)) for rid in self._ids]
        scores = [(rid, s) for rid, s in scores if s > 0]
        scores.sort(key=lambda x: -x[1])
        return scores[:limit]

    def _score(self, record_id: str, query_tokens: list[str]) -> float:
        doc = self._toks.get(record_id, [])
        if not doc:
            return 0.0
        dl = len(doc)
        tf: dict[str, int] = {}
        for t in doc:
            tf[t] = tf.get(t, 0) + 1
        total = 0.0
        for token in query_tokens:
            n_q = self._df.get(token, 0)
            if n_q == 0:
                continue
            idf = math.log((self._n - n_q + 0.5) / (n_q + 0.5) + 1)
            tf_q = tf.get(token, 0)
            norm = tf_q * (self.K1 + 1) / (
                tf_q + self.K1 * (1 - self.B + self.B * dl / self._avgdl)
            )
            total += idf * norm
        return total


# ── Memory ────────────────────────────────────────────────────────────────────

class SQLiteFailureMemory:

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._init_db()

    def record(
        self,
        spec_id: str,
        gate: str,
        errors_text: str,
        attempt: int,
        outcome: str,
        resolution: str | None = None,
    ) -> None:
        record_id = hashlib.sha256(
            f"{spec_id}:{attempt}:{gate}:{errors_text[:200]}".encode()
        ).hexdigest()[:16]
        tokens = _tokenise(f"gate:{gate} {errors_text}")
        # Named columns (not positional VALUES) so the nullable resolution column
        # added in 0052 stays insert-safe.
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO failure_records
                   (id, spec_id, gate, errors_text, tokens_json, outcome,
                    attempt, timestamp, resolution)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    record_id, spec_id, gate, errors_text[:4000],
                    json.dumps(tokens), outcome, attempt,
                    datetime.now(UTC).isoformat(),
                    resolution or None,
                ),
            )

    def retrieve_similar(
        self, errors_text: str, gate: str, limit: int = 3
    ) -> list[str]:
        query_tokens = _tokenise(f"gate:{gate} {errors_text}")
        with self._connect() as conn:
            rows: list[Any] = conn.execute(
                """SELECT id, spec_id, gate, errors_text, tokens_json, outcome, resolution
                   FROM failure_records WHERE gate = ?
                   ORDER BY timestamp DESC LIMIT 300""",
                (gate,),
            ).fetchall()
        if not rows:
            return []

        docs = [(row[0], json.loads(row[4])) for row in rows]
        idx = BM25Index(docs)
        ranked = idx.rank(query_tokens, limit=limit)
        row_by_id: dict[str, Any] = {row[0]: row for row in rows}

        narratives: list[str] = []
        for rid, _ in ranked:
            row = row_by_id.get(rid)
            if not row:
                continue
            symbol = {"passed": "✓", "escalated": "⚠"}.get(row[5], "?")
            narrative = (
                f"Past {row[2]} failure [{symbol} {row[5]}]:\n"
                f"  Spec: {row[1]}\n"
                f"  Errors: {row[3][:300]}\n"
            )
            # Legacy rows (and escalated records) carry no resolution — render
            # exactly as before. When one is present it tells a future repair how
            # the failure was fixed, not merely that it was.
            resolution = row[6] if len(row) > 6 else None
            if resolution:
                narrative += f"  Resolution: {resolution}\n"
            narratives.append(narrative)
        return narratives

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate_resolution_column(conn)

    @staticmethod
    def _migrate_resolution_column(conn: sqlite3.Connection) -> None:
        """Add the nullable ``resolution`` column to databases created before 0052.

        CREATE TABLE IF NOT EXISTS names the column for fresh databases but never
        alters an existing table, so a pre-0052 memory.db lacks it. Guard the
        ALTER with a PRAGMA check so it runs exactly once and re-initialisation is
        a no-op.
        """
        columns = {row[1] for row in conn.execute("PRAGMA table_info(failure_records)")}
        if "resolution" not in columns:
            try:
                conn.execute("ALTER TABLE failure_records ADD COLUMN resolution TEXT")
            except sqlite3.OperationalError as exc:
                # Concurrent autopilots can both observe the column missing and
                # race to ALTER; the loser sees "duplicate column name". That is
                # the benign outcome we wanted — swallow only that case.
                if "duplicate column" not in str(exc).lower():
                    raise

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self._db_path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
