import pytest

import config
from memory import document_repository
from tools.document_search import chunk_text, ingest_document, ingest_sample_documents, search_knowledge_base
from tools.uploads import UploadError, decode_text, extract_pdf_text, validate_upload

ERR = config.SAMPLE_DATA_DIR / "error_samples"


def test_empty_file_rejected():
    with pytest.raises(UploadError, match="empty"):
        validate_upload("empty.log", b"", config.ALLOWED_LOG_EXTENSIONS)


def test_oversized_file_rejected():
    data = (ERR / "too_large.log").read_bytes()
    assert len(data) > config.MAX_UPLOAD_BYTES
    with pytest.raises(UploadError, match="limit"):
        validate_upload("too_large.log", data, config.ALLOWED_LOG_EXTENSIONS)


def test_unsupported_extension_rejected():
    with pytest.raises(UploadError, match="Unsupported"):
        validate_upload("data.csv", b"a,b", config.ALLOWED_DOC_EXTENSIONS)


def test_binary_content_rejected():
    with pytest.raises(UploadError, match="binary"):
        decode_text("x.log", b"abc\x00\x01\x02")


def test_corrupt_pdf_rejected_and_recorded_as_failed(db):
    data = (ERR / "corrupt_report.pdf").read_bytes()
    with pytest.raises(UploadError):
        extract_pdf_text("corrupt_report.pdf", data)
    res = ingest_document("corrupt_report.pdf", data, db_path=db)
    assert res["status"] == "failed"
    doc = document_repository.list_documents(db)[0]
    assert doc["status"] == "failed" and doc["chunks"] == 0


def test_valid_pdf_extracts_text():
    data = (config.SAMPLE_DOCS_DIR / "sre_oncall_handbook.pdf").read_bytes()
    assert "approval" in extract_pdf_text("sre_oncall_handbook.pdf", data).lower()


def test_cannot_mark_indexed_without_text(db):
    with pytest.raises(ValueError):
        document_repository.add_document("x.md", "md", [], status="indexed", db_path=db)


def test_ingest_samples_and_search(db):
    res = ingest_sample_documents(db)
    assert res and all(r["status"] == "indexed" for r in res)
    assert ingest_sample_documents(db) == []  # idempotent
    hits = search_knowledge_base("connection pool timeout", db_path=db)
    assert hits[0]["filename"] == "runbook_database_connections.md"
    assert len({h["filename"] for h in hits}) == len(hits)  # one chunk per document


def test_chunking_respects_size():
    chunks = chunk_text("para\n\n" * 10 + "x" * 2500, size=900)
    assert all(len(c) <= 900 for c in chunks)
