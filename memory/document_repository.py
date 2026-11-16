"""Knowledge-base document metadata and text chunks (simple, transparent retrieval)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from memory.database import connect
from memory.incident_repository import now_iso


def add_document(filename: str, doc_type: str, chunks: list[str], status: str, note: str = "",
                 db_path: str | Path | None = None) -> int:
    """Store a document. status is 'indexed' only when text chunks were actually stored."""
    if status == "indexed" and not chunks:
        raise ValueError("A document cannot be marked indexed without any extracted text.")
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO documents (filename, doc_type, chars, chunks, status, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (filename, doc_type, sum(len(c) for c in chunks), len(chunks), status, note, now_iso()),
        )
        doc_id = int(cur.lastrowid)
        conn.executemany(
            "INSERT INTO doc_chunks (doc_id, chunk_index, text) VALUES (?, ?, ?)",
            [(doc_id, i, c) for i, c in enumerate(chunks)],
        )
    return doc_id


def list_documents(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM documents ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def document_exists(filename: str, db_path: str | Path | None = None) -> bool:
    with connect(db_path) as conn:
        row = conn.execute("SELECT 1 FROM documents WHERE filename = ? AND status = 'indexed'", (filename,)).fetchone()
    return row is not None


def all_chunks(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT c.doc_id, c.chunk_index, c.text, d.filename FROM doc_chunks c
               JOIN documents d ON d.id = c.doc_id WHERE d.status = 'indexed'"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_document_text(doc_id: int, db_path: str | Path | None = None) -> str:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT text FROM doc_chunks WHERE doc_id = ? ORDER BY chunk_index", (doc_id,)).fetchall()
    return "\n".join(r["text"] for r in rows)
