"""Extract plain text from a resume file (PDF, DOCX, or TXT)."""

from __future__ import annotations

from pathlib import Path


class UnsupportedResumeError(ValueError):
    """Raised when the resume file type is not supported."""


def parse_resume(path: str | Path) -> str:
    """Return the plain-text content of a resume file.

    Supports .pdf, .docx and .txt / .md.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Resume file not found: {p}")

    suffix = p.suffix.lower()
    if suffix == ".pdf":
        text = _parse_pdf(p)
    elif suffix == ".docx":
        text = _parse_docx(p)
    elif suffix in (".txt", ".md"):
        text = p.read_text(encoding="utf-8", errors="ignore")
    else:
        raise UnsupportedResumeError(
            f"Unsupported resume type '{suffix}'. Use .pdf, .docx, .txt or .md."
        )

    text = text.strip()
    if not text:
        raise ValueError(f"No text could be extracted from {p}.")
    return text


def _parse_pdf(p: Path) -> str:
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(p) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n".join(pages)


def _parse_docx(p: Path) -> str:
    import docx

    document = docx.Document(str(p))
    return "\n".join(para.text for para in document.paragraphs)
