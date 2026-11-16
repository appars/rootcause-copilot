"""Knowledge base: ingest runbooks/reports and search them with simple keyword scoring.

No vector database is used on purpose - setup stays reliable on student
laptops. The scoring is a small TF-IDF so students can follow it.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import config
from memory import document_repository as docs
from tools.incident_retriever import tokenize
from tools.uploads import UploadError, read_document, sanitize_filename

CHUNK_CHARS = 900


def chunk_text(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Split on blank lines, then pack paragraphs into chunks of ~size characters."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for p in paragraphs:
        while len(p) > size:                     # very long paragraph: hard split
            chunks.append(p[:size])
            p = p[size:]
        if len(current) + len(p) + 2 > size and current:
            chunks.append(current)
            current = p
        else:
            current = f"{current}\n\n{p}" if current else p
    if current:
        chunks.append(current)
    return chunks


def ingest_document(filename: str, data: bytes, db_path: str | Path | None = None) -> dict[str, Any]:
    """Extract, chunk and store. Failures are recorded honestly as 'failed', never as 'indexed'."""
    name = sanitize_filename(filename)
    doc_type = Path(name).suffix.lower().lstrip(".")
    try:
        text = read_document(name, data)
    except UploadError as exc:
        docs.add_document(name, doc_type or "unknown", [], status="failed", note=str(exc), db_path=db_path)
        return {"filename": name, "status": "failed", "message": str(exc), "chunks": 0, "chars": 0}
    chunks = chunk_text(text)
    doc_id = docs.add_document(name, doc_type, chunks, status="indexed", db_path=db_path)
    return {"filename": name, "status": "indexed", "doc_id": doc_id, "chunks": len(chunks),
            "chars": sum(len(c) for c in chunks), "message": f"Indexed {len(chunks)} chunk(s)."}


def ingest_sample_documents(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    results = []
    for path in sorted(config.SAMPLE_DOCS_DIR.glob("*")):
        if path.name.lower() == "readme.md":
            continue
        if path.suffix.lower() in config.ALLOWED_DOC_EXTENSIONS and not docs.document_exists(path.name, db_path):
            results.append(ingest_document(path.name, path.read_bytes(), db_path))
    return results


def search_knowledge_base(query: str, top_k: int = 3, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Keyword (TF-IDF-style) search. Returns [] when nothing is relevant - that is a valid answer."""
    chunks = docs.all_chunks(db_path)
    q_terms = tokenize(query)
    if not chunks or not q_terms:
        return []
    chunk_tokens = [tokenize(c["text"]) for c in chunks]
    n = len(chunks)
    idf = {t: math.log((n + 1) / (1 + sum(1 for ct in chunk_tokens if t in ct))) + 1 for t in q_terms}
    scored = []
    for c, ct in zip(chunks, chunk_tokens):
        hits = q_terms & ct
        # Relevance filter: weak matches are NOT returned, so irrelevant documents never reach the LLM context.
        if len(hits) < min(config.KB_MIN_MATCHED_TERMS, len(q_terms)):
            continue
        score = sum(idf[t] for t in hits) / math.sqrt(len(ct) + 1)
        scored.append({"filename": c["filename"], "chunk": c["chunk_index"], "score": round(score, 3),
                       "matched_terms": sorted(hits)[:8], "snippet": c["text"][:600]})
    scored.sort(key=lambda r: r["score"], reverse=True)
    best_per_file: list[dict[str, Any]] = []
    for r in scored:                      # keep the best chunk of each document
        if all(b["filename"] != r["filename"] for b in best_per_file):
            best_per_file.append(r)
    return best_per_file[: max(1, min(int(top_k), 5))]
