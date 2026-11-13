"""Text extraction from uploaded study material (TXT, MD, PDF, DOCX) with strict validation."""

from __future__ import annotations

import io
import zipfile
from pathlib import PurePath
from typing import Any

from app.core.errors import PayloadTooLargeError, UnprocessableError

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


def extract_text(filename: str, data: bytes, *, max_bytes: int, max_chars: int) -> tuple[str, dict[str, Any]]:
    ext = PurePath(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UnprocessableError(
            f"Unsupported file type '{ext or 'unknown'}'.", hint="Upload a .txt, .md, .pdf or .docx file."
        )
    if len(data) > max_bytes:
        raise PayloadTooLargeError(f"File is larger than the {max_bytes / 1_048_576:.0f} MB upload limit.")
    if not data:
        raise UnprocessableError("The uploaded file is empty.")

    pages = None
    if ext in (".txt", ".md"):
        if b"\x00" in data[:4096]:
            raise UnprocessableError("This file looks binary, not text.")
        text = data.decode("utf-8", errors="replace")
    elif ext == ".pdf":
        if not data.startswith(b"%PDF"):
            raise UnprocessableError("This file is not a valid PDF.")
        text, pages = _pdf(data)
    else:
        if not zipfile.is_zipfile(io.BytesIO(data)):
            raise UnprocessableError("This file is not a valid DOCX document.")
        text = _docx(data)

    text = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").splitlines()).strip()
    if not text:
        raise UnprocessableError(
            "No extractable text found.", hint="Scanned/image-only documents are not supported (no OCR)."
        )
    truncated = len(text) > max_chars
    return text[:max_chars], {"filename": filename, "extension": ext, "bytes": len(data), "characters": len(text),
                              "pages": pages, "truncated": truncated}


def _pdf(data: bytes) -> tuple[str, int]:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise UnprocessableError("Encrypted PDFs are not supported.")
        return "\n\n".join((page.extract_text() or "") for page in reader.pages), len(reader.pages)
    except PyPdfError as exc:
        raise UnprocessableError(f"Could not read the PDF: {exc}") from exc


def _docx(data: bytes) -> str:
    from docx import Document

    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:
        raise UnprocessableError(f"Could not read the DOCX file: {exc}") from exc
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    return "\n".join(parts)
