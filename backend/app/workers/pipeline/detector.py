"""Detect whether each page in a PDF has a text layer or is scanned."""
from typing import List, Tuple

import pdfplumber


def detect_pages(pdf_path: str) -> List[Tuple[int, bool]]:
    """
    Returns list of (page_index, has_text_layer).
    page_index is 0-based.
    has_text_layer = True means the page has selectable text; False = scanned/image-only.
    """
    results = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            has_text = bool(text and text.strip())
            results.append((i, has_text))
    return results


def count_total_pages(pdf_path: str) -> int:
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)
