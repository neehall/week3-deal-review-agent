"""Parses an uploaded deal document (PDF, DOCX, or TXT) into plain text.

This is a *read* tool: it never modifies the source file, only extracts text.
"""

from __future__ import annotations

from pathlib import Path


class DocumentLoadError(Exception):
    """Raised when a document can't be parsed into usable text."""


def load_document(file_path: str) -> str:
    path = Path(file_path)
    if not path.exists():
        raise DocumentLoadError(f"File not found: {file_path}")

    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            text = _load_pdf(path)
        elif suffix == ".docx":
            text = _load_docx(path)
        elif suffix in (".txt", ".md"):
            text = path.read_text(encoding="utf-8", errors="ignore")
        else:
            raise DocumentLoadError(f"Unsupported file type: {suffix}")
    except DocumentLoadError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface any parser failure as a load error
        raise DocumentLoadError(f"Failed to parse {path.name}: {exc}") from exc

    text = text.strip()
    if not text:
        raise DocumentLoadError(f"No extractable text found in {path.name}.")
    return text


def _load_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _load_docx(path: Path) -> str:
    import docx

    document = docx.Document(str(path))
    return "\n".join(p.text for p in document.paragraphs)
