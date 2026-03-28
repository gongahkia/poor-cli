"""
PDF reader for poor-cli.

Extracts text from PDF files with page-range support.
Uses pymupdf (fitz) if available, falls back to pdfplumber, then basic extraction.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MAX_PAGES_PER_REQUEST = 20


def read_pdf(
    file_path: str,
    pages: Optional[str] = None,
    max_pages: int = MAX_PAGES_PER_REQUEST,
) -> str:
    """Read text from a PDF file.

    Args:
        file_path: Path to the PDF file.
        pages: Optional page range string (e.g., "1-5", "3", "10-20").
               1-indexed. If None, reads up to max_pages from start.
        max_pages: Maximum pages to read per request.

    Returns:
        Extracted text with page markers.
    """
    path = Path(file_path).resolve()
    if not path.exists():
        return f"error: file not found: {file_path}"
    if not path.suffix.lower() == ".pdf":
        return f"error: not a PDF file: {file_path}"

    start_page, end_page = _parse_page_range(pages)

    # try pymupdf first
    try:
        return _read_with_pymupdf(path, start_page, end_page, max_pages)
    except ImportError:
        pass

    # try pdfplumber
    try:
        return _read_with_pdfplumber(path, start_page, end_page, max_pages)
    except ImportError:
        pass

    return (
        "error: no PDF library available. Install one of:\n"
        "  pip install pymupdf\n"
        "  pip install pdfplumber"
    )


def _parse_page_range(pages: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    """Parse page range string into (start, end) 0-indexed."""
    if not pages:
        return None, None
    pages = pages.strip()
    if "-" in pages:
        parts = pages.split("-", 1)
        start = int(parts[0].strip()) - 1
        end = int(parts[1].strip()) # end is exclusive
        return max(0, start), end
    else:
        page = int(pages.strip()) - 1
        return max(0, page), page + 1


def _read_with_pymupdf(path: Path, start: Optional[int], end: Optional[int], max_pages: int) -> str:
    import fitz # pymupdf
    doc = fitz.open(str(path))
    total = doc.page_count
    s = start or 0
    e = min(end or total, total)
    if e - s > max_pages:
        e = s + max_pages
    parts = [f"[PDF: {path.name} | {total} pages | showing {s+1}-{e}]"]
    for i in range(s, e):
        page = doc[i]
        text = page.get_text().strip()
        parts.append(f"\n--- Page {i+1} ---\n{text}")
    doc.close()
    if e < total:
        parts.append(f"\n[... {total - e} more pages. Use pages=\"{e+1}-{min(e+max_pages, total)}\" to continue]")
    return "\n".join(parts)


def _read_with_pdfplumber(path: Path, start: Optional[int], end: Optional[int], max_pages: int) -> str:
    import pdfplumber
    with pdfplumber.open(str(path)) as pdf:
        total = len(pdf.pages)
        s = start or 0
        e = min(end or total, total)
        if e - s > max_pages:
            e = s + max_pages
        parts = [f"[PDF: {path.name} | {total} pages | showing {s+1}-{e}]"]
        for i in range(s, e):
            page = pdf.pages[i]
            text = (page.extract_text() or "").strip()
            parts.append(f"\n--- Page {i+1} ---\n{text}")
        if e < total:
            parts.append(f"\n[... {total - e} more pages. Use pages=\"{e+1}-{min(e+max_pages, total)}\" to continue]")
    return "\n".join(parts)
