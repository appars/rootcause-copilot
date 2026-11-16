"""Safe handling of uploaded files.

Uploaded logs and documents are UNTRUSTED. We validate extension, size and
content, we never execute anything, and we only ever read them as text.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import config


class UploadError(ValueError):
    """User-facing upload problem (unsupported type, empty, too large, unreadable)."""


def sanitize_filename(filename: str, max_len: int = 100) -> str:
    """Strip any path, replace unusual characters, keep the extension. 'C:\\x\\..\\a b?.log' -> 'a_b_.log'."""
    name = Path(str(filename or "").replace("\\", "/")).name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).lstrip(".")
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    stem = re.sub(r"_+", "_", stem)[: max_len - len(ext) - 1] or "upload"
    return f"{stem}.{ext}" if ext else stem


def validate_upload(filename: str, data: bytes | None, allowed: set[str],
                    max_bytes: int = config.MAX_UPLOAD_BYTES) -> str:
    """Return the lower-case extension or raise UploadError with a friendly message."""
    name = Path(filename or "").name
    ext = Path(name).suffix.lower()
    if not name or not ext:
        raise UploadError("The file has no name or extension.")
    if ext not in allowed:
        raise UploadError(f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(allowed))}.")
    if data is None or len(data) == 0:
        raise UploadError(f"'{name}' is empty.")
    if len(data) > max_bytes:
        raise UploadError(f"'{name}' is {len(data) / 1024 / 1024:.1f} MB; the limit is "
                          f"{max_bytes / 1024 / 1024:.1f} MB. Upload a smaller excerpt (e.g. the incident window).")
    return ext


def decode_text(filename: str, data: bytes) -> str:
    """Decode a text upload. Rejects content that looks binary."""
    if b"\x00" in data[:4096]:
        raise UploadError(f"'{filename}' looks like a binary file, not text.")
    text = data.decode("utf-8", errors="replace")
    if not text.strip():
        raise UploadError(f"'{filename}' contains no readable text.")
    return text.replace("\r\n", "\n")


def extract_pdf_text(filename: str, data: bytes) -> str:
    """Extract text from a PDF. Corrupt or image-only PDFs raise UploadError."""
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:  # pragma: no cover
        raise UploadError("PDF support is not installed (pypdf missing).") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise UploadError(f"'{filename}' is password-protected; it cannot be indexed.")
        pages = [(p.extract_text() or "") for p in reader.pages]
    except UploadError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as exc:
        raise UploadError(f"'{filename}' could not be read as a PDF (it may be corrupt): {type(exc).__name__}") from exc
    text = "\n".join(pages).strip()
    if not text:
        raise UploadError(f"No text could be extracted from '{filename}'. It may be a scanned/image-only PDF; "
                          "it was NOT indexed.")
    return text


def read_document(filename: str, data: bytes) -> str:
    ext = validate_upload(filename, data, config.ALLOWED_DOC_EXTENSIONS)
    if ext == ".pdf":
        return extract_pdf_text(filename, data)
    return decode_text(filename, data)
