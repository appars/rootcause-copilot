"""
SQLite database access - the agent's DURABLE (long-term) memory.

Concept 1 - Persistent Agent Memory:
    Streamlit session_state disappears when the browser session ends or the
    app restarts. Everything written here survives restarts because it is
    stored in a file on disk (or on a Kubernetes PersistentVolume).

Rules followed in this module:
    * schema is created automatically on first use
    * every query is parameterised (no string formatting of SQL values)
    * API keys / secrets are NEVER stored here
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import config


class DatabaseError(RuntimeError):
    """Raised when the database cannot be opened or a query fails."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id               TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    service          TEXT NOT NULL,
    severity         TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'open',
    source           TEXT NOT NULL DEFAULT 'manual',
    description      TEXT DEFAULT '',
    symptoms         TEXT DEFAULT '',
    log_patterns     TEXT DEFAULT '[]',
    hypothesis       TEXT DEFAULT '',
    root_cause       TEXT DEFAULT '',
    resolution       TEXT DEFAULT '',
    lessons_learned  TEXT DEFAULT '',
    supporting_evidence TEXT DEFAULT '[]',
    recommended_actions TEXT DEFAULT '',
    evidence_assessment TEXT DEFAULT '',
    confidence       TEXT DEFAULT '',
    mode             TEXT DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS timeline_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id  TEXT NOT NULL,
    ts           TEXT NOT NULL,
    stage        TEXT NOT NULL,
    message      TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'ok',
    simulated    INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (incident_id) REFERENCES incidents(id)
);

CREATE TABLE IF NOT EXISTS investigation_results (
    incident_id  TEXT PRIMARY KEY,
    result_json  TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    FOREIGN KEY (incident_id) REFERENCES incidents(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id   TEXT NOT NULL,
    ts            TEXT NOT NULL,
    action        TEXT NOT NULL,
    decision      TEXT NOT NULL,
    reviewer      TEXT DEFAULT '',
    rationale     TEXT DEFAULT '',
    execution     TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT NOT NULL,
    doc_type    TEXT NOT NULL,
    chars       INTEGER NOT NULL DEFAULT 0,
    chunks      INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL,
    note        TEXT DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS doc_chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id      INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    text        TEXT NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS reports (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id  TEXT NOT NULL,
    markdown     TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_timeline_incident ON timeline_events(incident_id);
CREATE INDEX IF NOT EXISTS idx_audit_incident ON audit_log(incident_id);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON doc_chunks(doc_id);
"""


def resolve_db_path(db_path: str | Path | None = None) -> Path:
    return Path(db_path) if db_path else config.DB_PATH


@contextmanager
def connect(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open a short-lived connection, commit on success, always close.

    Short-lived connections are the simplest safe pattern for Streamlit,
    which re-runs the script on every interaction.
    """
    path = resolve_db_path(db_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=10)
    except (OSError, sqlite3.Error) as exc:  # pragma: no cover - environment specific
        raise DatabaseError(f"Cannot open database at {path}: {exc}") from exc
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise DatabaseError(f"Database operation failed: {exc}") from exc
    finally:
        conn.close()


# Columns added after v1.0. Existing databases are upgraded in place (ALTER TABLE ... ADD COLUMN).
MIGRATIONS = {
    "incidents": {
        "supporting_evidence": "TEXT DEFAULT '[]'",
        "recommended_actions": "TEXT DEFAULT ''",
        "evidence_assessment": "TEXT DEFAULT ''",
    },
}


def _migrate(conn: sqlite3.Connection) -> list[str]:
    added = []
    for table, columns in MIGRATIONS.items():
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, ddl in columns.items():
            if col not in existing:
                # Table/column names come from the constant above, never from user input.
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
                added.append(f"{table}.{col}")
    return added


def init_db(db_path: str | Path | None = None, seed: bool = True) -> Path:
    """Create tables if needed, upgrade older schemas and load fictional historical incidents once."""
    path = resolve_db_path(db_path)
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
    if seed:
        _seed_history(path)
    return path


def _seed_history(db_path: Path) -> None:
    """Load fictional past incidents so similar-incident retrieval works on day one."""
    if not config.SEED_INCIDENTS_FILE.exists():
        return
    with connect(db_path) as conn:
        already = conn.execute("SELECT COUNT(*) FROM incidents WHERE source = 'seed'").fetchone()[0]
        if already:
            return
        seeds = json.loads(config.SEED_INCIDENTS_FILE.read_text(encoding="utf-8"))
        for s in seeds:
            conn.execute(
                """INSERT OR IGNORE INTO incidents
                   (id, title, service, severity, status, source, description, symptoms,
                    log_patterns, hypothesis, root_cause, resolution, lessons_learned,
                    confidence, mode, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'closed', 'seed', ?, ?, ?, '', ?, ?, ?, 'confirmed', 'historical record', ?, ?)""",
                (
                    s["id"], s["title"], s["service"], s["severity"], s.get("description", ""),
                    s.get("symptoms", ""), json.dumps(s.get("log_patterns", [])),
                    s.get("root_cause", ""), s.get("resolution", ""), s.get("lessons_learned", ""),
                    s["created_at"], s["created_at"],
                ),
            )
