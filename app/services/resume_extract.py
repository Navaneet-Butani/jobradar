"""Phase 3 Task 3 — resume text extraction.

Takes an uploaded PDF/DOCX/TXT and returns plain text. Extraction only:
no OCR, no layout reconstruction, no cloud API. The text feeds the LLM
that tailors bullets for a packet, so wording matters and formatting
does not.
"""

import io
import logging
import re

from docx import Document
from pypdf import PdfReader

from ..core.exceptions import ValidationError

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024   # a text resume is a few KB; 5 MB is generous
MIN_TEXT_CHARS = 200                 # below this the file is almost certainly a scan
MAX_TEXT_CHARS = 20000               # keeps the LLM prompt inside the free-tier budget

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")


def _collapse_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(data: bytes) -> str:
    document = Document(io.BytesIO(data))
    parts = [p.text for p in document.paragraphs]
    # Plenty of resumes lay everything out in a borderless table.
    for table in document.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    return "\n".join(parts)


def extract_resume_text(filename: str, data: bytes) -> str:
    """Extract plain text from an uploaded resume. Raises ValidationError on bad input."""
    name = (filename or "").lower()

    if not data:
        raise ValidationError("The uploaded file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValidationError(f"Resume is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    if not name.endswith(SUPPORTED_EXTENSIONS):
        raise ValidationError(f"Unsupported file type — upload one of: {', '.join(SUPPORTED_EXTENSIONS)}")

    try:
        if name.endswith(".pdf"):
            text = _extract_pdf(data)
        elif name.endswith(".docx"):
            text = _extract_docx(data)
        else:
            text = data.decode("utf-8", errors="replace")
    except ValidationError:
        raise
    except Exception as e:
        logger.warning(f"Resume extraction failed for {filename}: {e}")
        raise ValidationError("Couldn't read that file — it may be corrupt or password-protected")

    text = _collapse_whitespace(text)

    if len(text) < MIN_TEXT_CHARS:
        raise ValidationError(
            "Almost no text came out of that file. If it's a scanned/image PDF, "
            "export a text-based PDF or paste the resume as .txt instead."
        )

    return text[:MAX_TEXT_CHARS]
