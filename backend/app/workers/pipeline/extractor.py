"""Extract text blocks from PDF, filtering repetitive headers/footers."""
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import median, mean as _mean, stdev as _stdev
from typing import List, Optional, Tuple

import pdfplumber

# Suppress pdfminer noise (unknown page label styles, etc.)
logging.getLogger("pdfminer").setLevel(logging.ERROR)


# ---------------------------------------------------------------------------
# Minimal structural artifact checks (not document-type-specific)
# ---------------------------------------------------------------------------

def _is_structural_artifact(text: str) -> bool:
    """
    Reject only universal encoding/OCR structural artifacts — not document patterns.

    - Caret (^): positional OCR noise, never in legitimate Portuguese text.
    - Apostrophe inside short all-caps line: OCR artifact from signature stamps
      (e.g. "ESCRIVÃ' POLICIA"). Real Portuguese headings don't have mid-word apostrophes.
    """
    t = text.strip()
    if not t:
        return False
    if "^" in t:
        return True
    if "'" in t and t == t.upper() and len(t) < 60:
        return True
    return False


# ---------------------------------------------------------------------------
# Text cleaning helpers
# ---------------------------------------------------------------------------

_SPLIT_INITIAL_PAT = re.compile(
    r"\b([A-ZÁÉÍÓÚÀÂÊÔÃÕÇÜ])\s+([A-ZÁÉÍÓÚÀÂÊÔÃÕÇÜ]{2,})\b"
)

# Match lowercase immediately followed by uppercase — merged words (e.g. "doEstado")
_CAMEL_MERGE_PAT = re.compile(
    r"([a-záéíóúàâêôãõç])([A-ZÁÉÍÓÚÀÂÊÔÃÕÇÜ])"
)


def _fix_split_initials(text: str) -> str:
    """
    Merge decorative split-initial-caps: 'P ROMOTORIA DE J USTIÇA' → 'PROMOTORIA DE JUSTIÇA'.
    Only applied when ≥2 such patterns appear in the same line (font artifact signature).
    """
    matches = _SPLIT_INITIAL_PAT.findall(text)
    if len(matches) >= 2:
        text = _SPLIT_INITIAL_PAT.sub(r"\1\2", text)
    return text


def _split_camelcase_words(text: str) -> str:
    """
    Split merged words where lowercase directly precedes uppercase:
    'doEstado' → 'do Estado', 'celularencontrado' is unchanged (all lowercase).
    Handles cases where PDF word-spacing is < the default x_tolerance.
    """
    return _CAMEL_MERGE_PAT.sub(r"\1 \2", text)


def _clean_line(text: str, fix_camelcase: bool = False) -> str:
    """Strip null bytes, optionally split CamelCase, merge split initials."""
    text = text.replace("\x00", "")
    if fix_camelcase:
        text = _split_camelcase_words(text)
    text = _fix_split_initials(text)
    return text.strip()


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TextBlock:
    page: int
    y_top: float
    y_bottom: float
    text: str
    font_size: float = 0.0
    is_heading: bool = False
    heading_level: int = 0
    is_table: bool = False
    table_data: List[List[str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------

_Y_TOLERANCE = 5


def extract(
    pdf_path: str,
    ocr_results: List[Tuple[int, Optional[str]]],
) -> Tuple[List[TextBlock], List[TextBlock]]:
    """
    Extract text blocks from all pages.
    Uses OCR text for scanned pages, pdfplumber for text pages.
    Filters repetitive headers/footers via generic positional clustering.
    """
    ocr_map = {page_idx: text for page_idx, text in ocr_results if text is not None}

    all_font_sizes = []
    raw_blocks: List[TextBlock] = []

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)

        for page_idx, page in enumerate(pdf.pages):
            page_h = page.height or 1

            # --- OCR path ---------------------------------------------------
            if page_idx in ocr_map:
                ocr_text = ocr_map[page_idx]
                lines = [l.strip() for l in ocr_text.splitlines() if l.strip()]
                n_lines = max(len(lines), 1)
                for i, line in enumerate(lines):
                    line = _clean_line(line)
                    if not line or len(line) < 3:
                        continue
                    if _is_structural_artifact(line):
                        continue
                    y_norm = i / n_lines
                    raw_blocks.append(TextBlock(
                        page=page_idx,
                        y_top=y_norm,
                        y_bottom=y_norm + 0.02,
                        text=line,
                        font_size=12.0,
                    ))
                continue

            # --- pdfplumber path --------------------------------------------

            # x_tolerance=1 keeps word boundaries tight, preventing adjacent words
            # from merging (e.g. "dePolíciaRAIMUNDO" with x_tol=3).
            x_tol = 1.0

            # Extract tables first
            tables = page.extract_tables()
            table_bboxes = []
            for table in (page.find_tables() or []):
                bbox = table.bbox
                y_top_norm = bbox[1] / page_h
                y_bottom_norm = bbox[3] / page_h
                table_bboxes.append((y_top_norm, y_bottom_norm))

            for table_data, (y_top_n, y_bottom_n) in zip(tables, table_bboxes):
                cleaned = [
                    [cell or "" for cell in row]
                    for row in table_data
                    if any(cell for cell in row)
                ]
                if cleaned:
                    raw_blocks.append(TextBlock(
                        page=page_idx,
                        y_top=y_top_n,
                        y_bottom=y_bottom_n,
                        text="",
                        is_table=True,
                        table_data=cleaned,
                    ))

            # Extract words with tight x_tolerance for clean word separation
            words = page.extract_words(
                extra_attrs=["size"],
                x_tolerance=x_tol,
                y_tolerance=_Y_TOLERANCE,
            )
            if not words:
                continue

            lines_map: defaultdict = defaultdict(list)
            for word in words:
                y_norm_word = word["top"] / page_h
                in_table = any(
                    y_top <= y_norm_word <= y_bottom
                    for y_top, y_bottom in table_bboxes
                )
                if not in_table:
                    y_bucket = round(word["top"] / _Y_TOLERANCE) * _Y_TOLERANCE
                    lines_map[y_bucket].append(word)

            for y_bucket, line_words in sorted(lines_map.items()):
                line_words.sort(key=lambda w: w["x0"])
                raw_text = " ".join(w["text"] for w in line_words)
                text = _clean_line(raw_text, fix_camelcase=True)
                if not text or len(text) < 3:
                    continue
                if _is_structural_artifact(text):
                    continue
                # QR code / reversed-text artifacts: every token ≤ 3 chars
                # (e.g. "OIV ppa o moc edoc RQ etse edilaV" from ATPV-e QR codes)
                if all(len(w) <= 3 for w in text.split()):
                    continue
                avg_size = sum(w.get("size", 12) for w in line_words) / len(line_words)
                all_font_sizes.append(avg_size)
                y_top_norm = line_words[0]["top"] / page_h
                y_bottom_norm = line_words[0]["bottom"] / page_h

                raw_blocks.append(TextBlock(
                    page=page_idx,
                    y_top=y_top_norm,
                    y_bottom=y_bottom_norm,
                    text=text,
                    font_size=avg_size,
                ))

    # Detect heading levels using font size
    if all_font_sizes:
        med_size = median(all_font_sizes)
        for block in raw_blocks:
            if block.is_table or not block.text:
                continue
            n_alpha = sum(1 for c in block.text if c.isalpha())
            if n_alpha < 3 or block.font_size < 10.0:
                continue
            ratio = block.font_size / med_size if med_size > 0 else 1.0
            if ratio >= 1.8:
                block.is_heading = True
                block.heading_level = 1
            elif ratio >= 1.4:
                block.is_heading = True
                block.heading_level = 2
            elif ratio >= 1.3:
                block.is_heading = True
                block.heading_level = 3

    filtered = _filter_headers_footers(raw_blocks, total_pages)
    return filtered, raw_blocks


# ---------------------------------------------------------------------------
# Generic header/footer detection — no hard-coded document patterns
# ---------------------------------------------------------------------------

# Zone boundaries (normalised 0–1 page height)
_HEADER_ZONE = 0.18   # top 18% of page
_FOOTER_ZONE = 0.82   # bottom 18% of page

# Thresholds
_POSITIONAL_FREQ  = 0.18   # must appear on ≥18% of pages (≥2 occurrences min) in the zone
_POSITIONAL_STD   = 0.05   # y-position must vary < 5% of page height across pages
_GLOBAL_FREQ      = 0.70   # appears on ≥70% of ALL pages → boilerplate anywhere
_PAGENUM_FREQ     = 0.15   # page-number lines in zone on ≥15% of pages
_PAGENUM_ZONE     = 0.18   # zone for page-number detection

# Digit-only OR "Página N/M" style lines
_PAGE_NUM_PAT = re.compile(
    r"^(?:p[aá]gina\s+)?\d+(?:\s*[/|]\s*\d+|\s+de\s+\d+)?$",
    re.IGNORECASE,
)

# Normalization helpers for text-variant grouping
_NORM_NON_ALPHA = re.compile(r"[^a-záéíóúàâêôãõçü\s]", re.IGNORECASE)


def _norm_key(text: str) -> str:
    """
    Normalise text for header/footer grouping so that minor variants of the
    same repeated block are counted together instead of as separate entries.

    Steps:
    1. Lowercase
    2. Remove all non-alphabetic characters (digits, punctuation, special chars)
       — handles "Pág. 2" == "Pág. 6", OCR digit/letter confusions (1 vs I),
         dash/no-dash variants, CEP numbers, etc.
    3. Sort words alphabetically — handles multi-column reading-order variations
       where the same words appear in different sequences across pages
       (e.g. "Secretaria de Estado de Segurança" vs "de Estado de Segurança Secretaria")

    Intentionally lossy: used only for grouping/detection.
    Original texts are kept and used for actual block removal.
    """
    t = _NORM_NON_ALPHA.sub(" ", text.lower())
    words = sorted(set(t.split()))
    # Require at least 2 distinct words to avoid grouping single-token noise
    if len(words) < 2:
        return text.lower().strip()
    return " ".join(words)


def _filter_headers_footers(blocks: List[TextBlock], total_pages: int) -> List[TextBlock]:
    """
    Remove headers, footers, and page numbers detected purely from structure
    (position + frequency across pages) — works for any document type.

    Strategy A — POSITIONAL CLUSTERING:
        Text that appears in the top 12% or bottom 12% of the page on ≥35% of
        pages, with y-position variation (stdev) < 3% of page height → header/footer.
        Only the instances physically in the zone are removed; if the same text
        also appears in the body (e.g. a case number cited inline), those
        body instances are preserved.

    Strategy B — GLOBAL REPETITION:
        Text that appears on ≥70% of all pages regardless of position → boilerplate.
        All instances removed.

    Strategy C — PAGE NUMBERS:
        Lines containing only digits/punctuation in the top/bottom 15%, present
        on ≥25% of pages → navigation artifact, removed.
    """
    if total_pages < 3:
        return blocks

    # Group blocks by their NORMALISED text key so that minor variants of the
    # same repeated element (punctuation, numbers, spacing) are counted together.
    norm_groups: defaultdict = defaultdict(list)
    for b in blocks:
        if b.is_table or not b.text:
            continue
        norm_groups[_norm_key(b.text.strip())].append(b)

    # Minimum absolute page count to avoid false positives on short documents
    min_occ = max(2, int(total_pages * _POSITIONAL_FREQ))

    # Block ids to drop
    drop_ids: set = set()

    for nkey, blks in norm_groups.items():
        pages_seen = {b.page for b in blks}
        n_pages = len(pages_seen)
        freq = n_pages / total_pages
        y_tops = [b.y_top for b in blks]
        avg_y = _mean(y_tops)

        # B — Global repetition: same (normalised) content on ≥70% of pages
        if freq >= _GLOBAL_FREQ:
            for b in blks:
                drop_ids.add(id(b))
            continue

        # A — Positional clustering: consistent header/footer zone + tight y-spread
        if freq >= _POSITIONAL_FREQ and n_pages >= min_occ:
            if avg_y < _HEADER_ZONE or avg_y > _FOOTER_ZONE:
                y_std = _stdev(y_tops) if len(y_tops) > 1 else 0.0
                if y_std < _POSITIONAL_STD:
                    # Only remove block instances physically inside the zone;
                    # body-text occurrences of the same text are preserved.
                    for b in blks:
                        if b.y_top < _HEADER_ZONE or b.y_top > _FOOTER_ZONE:
                            drop_ids.add(id(b))
                    continue

        # C — Page numbers in header/footer zone
        if freq >= _PAGENUM_FREQ and n_pages >= 2:
            if avg_y < _PAGENUM_ZONE or avg_y > (1.0 - _PAGENUM_ZONE):
                if any(_PAGE_NUM_PAT.fullmatch(b.text.strip()) for b in blks):
                    for b in blks:
                        drop_ids.add(id(b))

    return [b for b in blocks if b.is_table or id(b) not in drop_ids]
