"""The consent ledger — one process, one sqlite file, no services.

Schema stores human-designated outcome labels per shape. The grader reads
aggregate counts per shape_key to compute P(safe|shape). The local-ledger
design (no egress, no daemon) is what makes RiskShape data-stays-on-prem by
default — the property the enterprise self-host buyer pays for.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .shape import ActionShape

_SCHEMA_VERSION = "1"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS labels (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    shape_key     TEXT    NOT NULL,
    tool_name     TEXT    NOT NULL,
    signature     TEXT    NOT NULL,
    capability    TEXT    NOT NULL,
    outcome       TEXT    NOT NULL CHECK (outcome IN ('safe', 'unsafe')),
    session_id    TEXT,
    designated_at TEXT    NOT NULL,
    note          TEXT
);
CREATE INDEX IF NOT EXISTS idx_shape_outcome ON labels(shape_key, outcome);
CREATE INDEX IF NOT EXISTS idx_shape ON labels(shape_key);
CREATE INDEX IF NOT EXISTS idx_designated_at ON labels(designated_at);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class LabelRow:
    id: int
    shape_key: str
    tool_name: str
    signature: str
    capability: str
    outcome: str
    session_id: str | None
    designated_at: str
    note: str | None


@dataclass(frozen=True)
class ShapeStats:
    """Aggregate grade inputs for one shape."""

    shape_key: str
    tool_name: str
    signature: str
    capability: str
    safe: int
    unsafe: int

    @property
    def total(self) -> int:
        return self.safe + self.unsafe

    @property
    def p_safe(self) -> float:
        t = self.total
        if t == 0:
            return 0.0
        return self.safe / t

    @property
    def seen(self) -> bool:
        return self.total > 0


class Ledger:
    """A thin sqlite-backed consent ledger.

    Thread-safe per-process via a re-entrant lock around connection access;
    each call opens a short-lived connection (file-based sqlite serializes
    writes at the file level, so cross-process is safe too).
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = str(db_path)
        self._lock = threading.RLock()

    # -- lifecycle ---------------------------------------------------------

    def init_schema(self) -> None:
        """Create the db file + schema + meta rows. Idempotent."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)",
                ("schema_version", _SCHEMA_VERSION),
            )
            conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)",
                ("initialized_at", _utcnow_iso()),
            )
            conn.commit()

    def is_initialized(self) -> bool:
        if not Path(self.db_path).exists():
            return False
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT value FROM meta WHERE key='schema_version'"
                ).fetchone()
                return row is not None
        except sqlite3.DatabaseError:
            return False

    # -- writes ------------------------------------------------------------

    def record_label(
        self,
        shape: ActionShape,
        outcome: str,
        *,
        session_id: str | None = None,
        note: str | None = None,
        designated_at: str | None = None,
    ) -> int:
        """Record one human-designated outcome label for a shape.

        ``outcome`` must be 'safe' or 'unsafe'. Returns the inserted row id.
        """
        if outcome not in ("safe", "unsafe"):
            raise ValueError(f"outcome must be 'safe' or 'unsafe', got {outcome!r}")
        ts = designated_at or _utcnow_iso()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO labels
                   (shape_key, tool_name, signature, capability, outcome, session_id, designated_at, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    shape.key,
                    shape.tool_name,
                    shape.signature,
                    shape.capability_scope,
                    outcome,
                    session_id,
                    ts,
                    note,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    # -- reads -------------------------------------------------------------

    def stats_for(self, shape_key: str) -> ShapeStats | None:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT tool_name, signature, capability,
                          SUM(outcome='safe') AS s, SUM(outcome='unsafe') AS u
                   FROM labels WHERE shape_key=? GROUP BY shape_key""",
                (shape_key,),
            ).fetchall()
        if not rows:
            return None
        tn, sig, cap, s, u = rows[0]
        return ShapeStats(
            shape_key=shape_key,
            tool_name=tn,
            signature=sig,
            capability=cap,
            safe=int(s or 0),
            unsafe=int(u or 0),
        )

    def list_shapes(self) -> list[ShapeStats]:
        """Aggregate stats for every shape that has >=1 label, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT shape_key, tool_name, signature, capability,
                          SUM(outcome='safe') AS s, SUM(outcome='unsafe') AS u,
                          MAX(designated_at) AS last_seen
                   FROM labels GROUP BY shape_key
                   ORDER BY last_seen DESC"""
            ).fetchall()
        out: list[ShapeStats] = []
        for shape_key, tn, sig, cap, s, u, _last in rows:
            out.append(
                ShapeStats(
                    shape_key=shape_key,
                    tool_name=tn,
                    signature=sig,
                    capability=cap,
                    safe=int(s or 0),
                    unsafe=int(u or 0),
                )
            )
        return out

    def list_labels(self, limit: int = 200) -> list[LabelRow]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, shape_key, tool_name, signature, capability,
                          outcome, session_id, designated_at, note
                   FROM labels ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            LabelRow(
                id=r[0], shape_key=r[1], tool_name=r[2], signature=r[3],
                capability=r[4], outcome=r[5], session_id=r[6],
                designated_at=r[7], note=r[8],
            )
            for r in rows
        ]

    def count(self, shape_key: str, outcome: str | None = None) -> int:
        q = "SELECT COUNT(*) FROM labels WHERE shape_key=?"
        args: tuple = (shape_key,)
        if outcome is not None:
            q += " AND outcome=?"
            args = (shape_key, outcome)
        with self._connect() as conn:
            row = conn.execute(q, args).fetchone()
            return int(row[0]) if row else 0

    def reset(self) -> None:
        """Drop all labels (keeps schema + meta). For tests / demo reset."""
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM labels")
            conn.commit()

    # -- internals ---------------------------------------------------------

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            # WAL keeps the ledger snappy under a live agent session.
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
            except sqlite3.OperationalError:
                pass
            yield conn
        finally:
            conn.close()


__all__ = ["Ledger", "LabelRow", "ShapeStats"]
