"""Assemble clean Markdown from extracted blocks and image OCR texts."""
import re
from typing import Dict, List

from app.workers.pipeline.extractor import TextBlock

# Phantom-space split-word fix: single uppercase consonant before lowercase
# accented vowel continuation — artifact of certain PDF encodings.
# e.g. "N úmero:" → "Número:",  "Ú ltima:" → "Última:"
_PHANTOM_SPLIT_PAT = re.compile(
    r"\b([A-ZÁÉÍÓÚÀÂÊÔÃÕÇÜ])\s+([áéíóúàâêôãõç]\w*)"
)

# Decorative/separator-only content (including em-dash variants)
_SEPARATOR_ONLY = re.compile(r"^[-–—_=\s]+$")

# Characters that indicate OCR artifacts / corrupted text
# Apostrophe included: Portuguese headings don't use apostrophes; mid-word ' in all-caps is OCR noise.
# Forward slash included: heading fragments like "Wí/" are garbage.
_OCR_ARTIFACT_CHARS = frozenset("^~\\|°•·<>{}[]@$'/")

# Signature stamp pattern: "WORD:digits" (e.g. "LOUREIRO:03334945200")
_SIGNATURE_STAMP_PAT = re.compile(r"\w+:\d{5,}")

# Timestamp pattern in headings (e.g. "PERITO: 14:48:54")
_TIMESTAMP_PAT = re.compile(r"\d{1,2}:\d{2}:\d{2}")


def _is_valid_heading(text: str) -> bool:
    """
    Return True only if the text is a plausible section heading.
    Rejects OCR artifacts, body-text sentences, signature stamps, and
    single-word fragments that are role labels / person names.
    """
    n_alpha = sum(1 for c in text if c.isalpha())
    if n_alpha < 3:
        return False
    # OCR artifact characters
    if any(c in _OCR_ARTIFACT_CHARS for c in text):
        return False
    # Lines starting with // or similar OCR artifacts
    if text.startswith("//") or text.startswith("\\\\"):
        return False
    # Signature stamp (e.g. "SANTARÉM LOUREIRO:03334945200")
    if _SIGNATURE_STAMP_PAT.search(text):
        return False
    # Very long body-text sentences (>100 chars with multiple clause separators)
    if len(text) > 100 and text.count(";") >= 2:
        return False
    # Timestamp in heading → it's a form label, not a heading (e.g. "PERITO: 14:48:54")
    if _TIMESTAMP_PAT.search(text):
        return False
    # Unbalanced closing parenthesis → fragment (e.g. "DE LOCAL)")
    if text.count(")") > text.count("("):
        return False

    # Count "meaningful words" — words with ≥3 alphabetic characters
    # Threshold of 3 (not 2) eliminates 2-char OCR fragments like "bt", "Jn", "DE"
    meaningful = [w for w in text.split() if sum(1 for c in w if c.isalpha()) >= 3]

    # Single-meaningful-word headings are only accepted when the word is
    # substantial (≥15 chars) or clearly part of an all-caps document structure.
    # This eliminates role labels ("TESTEMUNHA", "POLICIAL"), names ("ALICIA"),
    # and short OCR garbage ("Cícív", "escrivâq").
    if len(meaningful) < 2:
        if len(text) < 15:
            return False
        # Keep it only if the text is all uppercase (like "TESTEMUNHO", but ≥15 chars)
        # or a known heading keyword — otherwise demote
        if text != text.upper():
            return False

    return True


def table_to_markdown(table_data: List[List[str]]) -> str:
    if not table_data:
        return ""
    rows = []
    header = table_data[0]
    rows.append("| " + " | ".join(str(c).strip() for c in header) + " |")
    rows.append("| " + " | ".join("---" for _ in header) + " |")
    for row in table_data[1:]:
        padded = list(row) + [""] * (len(header) - len(row))
        rows.append("| " + " | ".join(str(c).strip() for c in padded) + " |")
    return "\n".join(rows)


def _clean_text(text: str) -> str:
    """Collapse internal whitespace, strip artifacts, and trim."""
    # Strip null bytes (ligature encoding artifacts)
    text = text.replace("\x00", "")
    text = text.strip()
    # Collapse multiple spaces/tabs into one
    text = re.sub(r"[ \t]+", " ", text)
    # Remove lines that are only whitespace or decorative separators (incl. em-dash)
    if _SEPARATOR_ONLY.fullmatch(text):
        return ""
    # Fix phantom-space split: "N úmero:" → "Número:" (single upper + accented lower)
    text = _PHANTOM_SPLIT_PAT.sub(r"\1\2", text)
    return text


def build(
    blocks: List[TextBlock],
    image_texts: Dict[int, List[str]],
) -> str:
    """
    Combine text blocks and image OCR texts into Markdown with paragraph joining.

    Consecutive text lines on the same page whose vertical gap is less than
    1.2× the line height are merged into a single paragraph (joined with a
    space).  Headings, tables, and large vertical gaps produce separate
    paragraphs separated by a blank line.
    """
    sorted_blocks = sorted(blocks, key=lambda b: (b.page, b.y_top))

    paragraphs: List[str] = []
    buf: List[str] = []       # accumulates lines of the current paragraph
    prev_block = None
    last_page = -1
    pages_with_images_done: set = set()

    def _flush() -> None:
        if buf:
            paragraphs.append(" ".join(buf))
            buf.clear()

    for block in sorted_blocks:
        if block.page != last_page and last_page >= 0:
            _flush()
            _flush_image_texts(last_page, image_texts, pages_with_images_done, paragraphs)
        last_page = block.page

        if block.is_table:
            _flush()
            md_table = table_to_markdown(block.table_data)
            if md_table:
                paragraphs.append(md_table)
            prev_block = None
            continue

        if block.is_heading:
            _flush()
            text = _clean_text(block.text)
            if text and _is_valid_heading(text):
                paragraphs.append(f"{'#' * block.heading_level} {text}")
            elif text:
                paragraphs.append(text)
            prev_block = None
            continue

        text = _clean_text(block.text)
        if not text:
            continue

        if prev_block is not None and prev_block.page == block.page:
            gap = block.y_top - prev_block.y_bottom
            lh = prev_block.y_bottom - prev_block.y_top
            ratio = gap / lh if lh > 0 else 999.0
            if ratio < 1.2:
                # Same paragraph: join with a space (handles same-line splits
                # with negative gap and normal line-wrap with ratio ≈ 0.2–0.5)
                buf.append(text)
            else:
                _flush()
                buf.append(text)
        else:
            _flush()
            buf.append(text)

        prev_block = block

    _flush()
    if last_page >= 0:
        _flush_image_texts(last_page, image_texts, pages_with_images_done, paragraphs)

    result = "\n\n".join(p for p in paragraphs if p.strip())
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _flush_image_texts(
    page_idx: int,
    image_texts: Dict[int, List[str]],
    done: set,
    parts: List[str],
) -> None:
    if page_idx in done or page_idx not in image_texts:
        return
    done.add(page_idx)
    for i, img_text in enumerate(image_texts[page_idx], 1):
        cleaned = _clean_text(img_text)
        if cleaned:
            parts.append(f"<!-- documento anexado (página {page_idx + 1}) -->")
            parts.append(cleaned)
