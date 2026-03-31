"""OCR scanned pages using pytesseract."""
from typing import List, Optional, Tuple

import pytesseract
from pdf2image import convert_from_path


class OCRError(Exception):
    pass


def run_ocr(
    pdf_path: str,
    pages_data: List[Tuple[int, bool]],
    progress_callback=None,
) -> List[Tuple[int, Optional[str]]]:
    """
    For pages with has_text=False, run pytesseract OCR.
    Returns list of (page_index, ocr_text_or_None).
    ocr_text is None for pages that already had a text layer (use pdfplumber for those).
    Raises OCRError on failure.
    """
    scanned_indices = [i for i, has_text in pages_data if not has_text]
    if not scanned_indices:
        return [(i, None) for i, _ in pages_data]

    # Convert only scanned pages to images (1-based for pdf2image)
    page_images = {}
    for page_idx in scanned_indices:
        try:
            images = convert_from_path(
                pdf_path,
                first_page=page_idx + 1,
                last_page=page_idx + 1,
                dpi=200,
            )
            page_images[page_idx] = images[0]
        except Exception as e:
            raise OCRError(f"Erro ao converter página {page_idx + 1} para imagem: {e}")

    results = []
    for page_idx, has_text in pages_data:
        if has_text:
            results.append((page_idx, None))
        else:
            try:
                text = pytesseract.image_to_string(
                    page_images[page_idx], lang="por+eng"
                )
                results.append((page_idx, text))
                if progress_callback:
                    progress_callback(page_idx)
            except Exception as e:
                raise OCRError(f"OCR falhou na página {page_idx + 1}: {e}")

    return results
