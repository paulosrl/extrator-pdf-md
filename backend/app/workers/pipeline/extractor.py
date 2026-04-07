"""Extract text blocks from PDF, filtering repetitive headers/footers."""
import re
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import List, Optional, Tuple


import pdfplumber

# ---------------------------------------------------------------------------
# Boilerplate detection
# ---------------------------------------------------------------------------

# Patterns matched against normal (spaced) text
_BOILERPLATE_PATTERNS: List[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"^tribunal de justiça do estado",
        r"^pje\s*[-–]\s*processo judicial eletrônico",
        r"^processo judicial eletrônico$",
        r"^\d+\s*/\s*\d+$",
        r"^p\s*[áa]gina\s+\d+\s+(de|/)\s+\d+",
        r"\d+[aªº°]\s+(pj|vara|comarca|seccional)\b",
        r"^(pj|vara|comarca)\s+(criminal|civel|c[íi]vel)\b",
        r"\[intimação expedida de forma automática",
        # Institutional headers (police/MP documents)
        r"^governo\s+do\s+estado\b",        # "Governo do Estado (do Pará)" — truncated variants
        r"^secretaria\s+de\s+estado\b",     # "Secretaria de Estado..." (any form)
        r"^polícia\s+civil\s+do\s+estado",
        r"seccional\s*[-–]\s*\d+a?\s*risp",
        r"^\d+[aªº°]\s+seccional\b",
        r"^ministério\s+público\s+do\s+estado",
        # Address/footer lines in police docs
        r"^travessa\b",
        r"^protocolo\s+de\s+assinatura",
        r"^o\s+documento\s+acima\s+foi\s+assinado",
        r"^a\s+validação\s+deste\s+documento",
        r"^não\s+existem\s+biometrias",
        r"^deste\s+documento\s+poderá\s+ser",
        r"^do\(s\)\s+envolvido\(s\)\s+no\s+ato",
        r"^impressa\s+neste\s+documento",
        # MP document artifacts
        r"^mpp[aâ]$",
        r"^do\s+estado\s+do\s+pará$",
        r"^p\s*[áa]gina\s+\d+\s+de\s+\d+",
        # Boilerplate fragments that survive line splitting
        r"^no\s+ato\s+da\s+confecção\s+do\s+documento",
        r"^tal\s+(forma\s+)?impressa",
        r"^tal\s+impressa",
        r"^secretaria\s+de\s+estado\b",       # duplicate pattern — kept for safety
        r"^\d+[aªº°]\s*(seccional|risp)\b",
        r"^risp[,.]?\s+sob\s+a",               # "RISP, sob a presidência..." (header fragment)
        r"^envolvido\(s\)\s+no\s+ato",
        r"^de\s+tal\s+forma",
        r"^documento\s+poderá\s+ser\s+realizada",
        r"^qualquer\s+tempo\s+junto",
        r"^protocolo$",                        # lone "PROTOCOLO" line (split from full header)
        r"^defesa\s+social$",                  # "Defesa Social" header fragment
        # Signature block labels that appear alone as large text
        r"^eletronicamente$",
        r"^assinado$",
        r"^assinado\s+eletronicamente",
        # Police deposition form labels (sometimes merged by pdfplumber due to tight spacing)
        r"^autoridade\s+policial$",
        r"^autoridadepolicial$",
        # Page number and form field fragments
        r"^página$",                        # lone "Página" remnant after page-counter filter
        r"^nome\s+das?\s+testemunhas?$",    # police form field label
        r"^testemunha\s+\d+$",              # "TESTEMUNHA 1" / "TESTEMUNHA 2" form field
        r"^exibidor\b",                     # police form role label
        r"^\(a\)\s*//",                     # "(A) //CONDUTOR(A)" form remnant
        # Signature block header/footer fragments
        r"^e\s+defesa\b",                   # tail of "Secretaria de Estado ... e Defesa Social"
        r"^ato\s+(do|da)\s+documento",      # fragment of biometric protocol block
        r"^social$",                        # lone "Social" fragment from institutional header
        r"^testemunha$",                    # lone "TESTEMUNHA" form field label
        r"^deste$",                         # lone "deste" fragment from protocol block
        # OCR artifacts from police form signature blocks
        r"^autof\b",                        # OCR of "AUTO" form field label
        r"^-[A-ZÁÉÍÓÚÀÂÊÔÃÕÇÜ]",           # line starting with dash+letter (OCR artifact)
        r"^ístemunhas",                     # OCR of "TESTEMUNHAS" with mangled prefix
        r"^jndo\b",                         # OCR fragment of "RAIMUNDO" partial read
        r"^riminal\s+de\b",                 # OCR of "CRIMINAL DE SANTARÉM" with C cut
        r"^recebedor\b",                    # police form field label
        r"^ustiça\s+criminal\b",            # OCR of "JUSTIÇA CRIMINAL" with J cut
    ]
]

# Patterns matched against text with ALL whitespace removed
_BOILERPLATE_NOSPACE: List[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"estedocumentofoigerado",      # "Este documento foi gerado"
        r"númerododocumento",
        r"assinadoeletronicamentepor",
        r"https?://",
        r"num\.\d+.*pág\.",
        r"núm\.\d+.*pág\.",
        r"protocolo(de)?assinatura",
        r"coletabiométrica",
        r"bancodedadosdosistemasisp",
        r"validaçãodestedo(c|cu)mento",
        r"nãoexistembiometrias",
        r"documentofoiassinadopelacol",
        r"página\d+de\d+",
        r"página\d+/\d+",
        r"consultadocumento",
        r"listview\.seam",
        r"pje\.tjpa\.jus\.br",
        r"cep\d{5}",
        r"protocolodeassinaturasbiometricas",
        r"doestadodopará",
        r"secretariadeestadode",         # "Secretaria de Estado de..." (merged variant)
        r"noatodaconfecção",
        r"documentoassinadoeletronicamente",   # "DOCUMENTO ASSINADO ELETRONICAMENTE [hash]"
        r"documentoassinado",                  # merged variant "DOCUMENTOASSINADO..."
        r"assinaturasbiometricas",             # partial fragment without "protocolo" prefix
        r"segurançapública",                   # "Segurança Pública e Defesa Social" header
        r"//condutor",                         # "(A) //CONDUTOR(A)" form field merged
    ]
]


def _is_boilerplate(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    # Caret is a positional OCR artifact — never in legitimate Portuguese legal text
    if "^" in t:
        return True
    # Apostrophe inside an all-caps short line = OCR artifact from signature stamps
    # e.g. "ESCRIVÃ' POLICIA", "NOME' ÍSTEMUNHAS" — not present in real document text
    if "'" in t and t == t.upper() and len(t) < 60:
        return True
    for pat in _BOILERPLATE_PATTERNS:
        if pat.search(t):
            return True
    t_compact = re.sub(r"\s+", "", t)
    for pat in _BOILERPLATE_NOSPACE:
        if pat.search(t_compact):
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
    """
    Clean a raw extracted text line:
    - Remove null bytes (font ligature encoding artifacts)
    - Optionally split CamelCase-merged words (used for normal-x_tol pages)
    - Merge decorative split initials
    """
    text = text.replace("\x00", "")
    if fix_camelcase:
        text = _split_camelcase_words(text)
    text = _fix_split_initials(text)
    return text.strip()


# ---------------------------------------------------------------------------
# Adaptive x_tolerance detection
# ---------------------------------------------------------------------------

def _detect_x_tolerance(page) -> float:
    """
    Detect appropriate x_tolerance for word extraction on this page.

    Some PDFs position each character individually (char-spaced encoding),
    creating intra-word gaps of 3–10pt. Normal PDFs have chars touching
    (gap ≈ 0pt) with word-space gaps of 2–5pt.

    Returns:
        15.0  — char-spaced page (each char is its own text element)
         3.0  — normal page (chars within words touch or nearly touch)
    """
    chars = page.chars
    if not chars:
        return 3.0

    lines: defaultdict = defaultdict(list)
    for c in chars:
        lines[round(c["top"])].append(c)

    n_near_zero = 0   # gap ≤ 0.5pt  (chars touching — normal encoding)
    n_large = 0       # gap 2–12pt   (char-spaced encoding)

    for y_key in sorted(lines.keys())[:40]:
        line = sorted(lines[y_key], key=lambda c: c["x0"])
        for i in range(1, len(line)):
            gap = line[i]["x0"] - line[i - 1]["x1"]
            if gap <= 0.5:
                n_near_zero += 1
            elif 2.0 <= gap <= 12.0:
                n_large += 1

    total = n_near_zero + n_large
    if total == 0:
        return 3.0

    # When most adjacent-char gaps are in the 2–12pt range the page uses
    # character-by-character positioning → need high x_tolerance to reassemble words.
    if n_large / total > 0.50:
        return 15.0

    return 3.0


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
    Filters repetitive headers/footers.
    """
    ocr_map = {page_idx: text for page_idx, text in ocr_results if text is not None}

    all_blocks: List[TextBlock] = []
    table_regions: List[Tuple[int, float, float]] = []

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        all_font_sizes = []
        raw_blocks: List[TextBlock] = []

        for page_idx, page in enumerate(pdf.pages):
            page_h = page.height or 1

            # --- OCR path ---------------------------------------------------
            if page_idx in ocr_map:
                ocr_text = ocr_map[page_idx]
                lines = [l.strip() for l in ocr_text.splitlines() if l.strip()]
                for i, line in enumerate(lines):
                    line = _clean_line(line)
                    if not line or _is_boilerplate(line):
                        continue
                    if len(line) < 3:
                        continue
                    y_norm = i / max(len(lines), 1)
                    raw_blocks.append(TextBlock(
                        page=page_idx,
                        y_top=y_norm,
                        y_bottom=y_norm + 0.02,
                        text=line,
                        font_size=12.0,
                    ))
                continue

            # --- pdfplumber path --------------------------------------------

            # Detect the encoding style of this page to pick x_tolerance
            x_tol = _detect_x_tolerance(page)
            # On normal pages apply CamelCase splitting to recover merged words
            fix_cc = x_tol < 10.0

            # Extract tables first
            tables = page.extract_tables()
            table_bboxes = []
            for table in (page.find_tables() or []):
                bbox = table.bbox
                y_top_norm = bbox[1] / page_h
                y_bottom_norm = bbox[3] / page_h
                table_bboxes.append((y_top_norm, y_bottom_norm))
                table_regions.append((page_idx, y_top_norm, y_bottom_norm))

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

            # Extract words with adaptive x_tolerance
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
                text = _clean_line(raw_text, fix_camelcase=fix_cc)
                if not text or _is_boilerplate(text):
                    continue
                if len(text) < 3:
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
            # Must have enough meaningful characters and a minimum absolute font size
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

    filtered = _filter_repetitive(raw_blocks, total_pages)
    return filtered, raw_blocks


# ---------------------------------------------------------------------------
# Repetitive header/footer removal
# ---------------------------------------------------------------------------

def _filter_repetitive(blocks: List[TextBlock], total_pages: int) -> List[TextBlock]:
    """
    Remove blocks that are repetitive headers, footers, or page numbers.

    Strategy 1 — positional: text in top 20% or bottom 20% of page appearing
    on ≥40% of pages is considered a header/footer.

    Strategy 2 — global: text appearing on ≥70% of ALL pages is boilerplate.

    Strategy 3 — page numbers: digit-only lines on ≥30% of pages are removed.
    """
    import re as _re

    if total_pages < 3:
        return blocks

    positional_counts: defaultdict = defaultdict(int)
    global_counts: defaultdict = defaultdict(int)

    for block in blocks:
        if block.is_table or not block.text:
            continue
        text = block.text.strip()
        if not text:
            continue

        global_counts[text] += 1

        if block.y_top <= 0.20 or block.y_bottom >= 0.80:
            positional_counts[text] += 1

    repetitive: set = set()

    for text, count in positional_counts.items():
        if count / total_pages >= 0.40:
            repetitive.add(text)

    for text, count in global_counts.items():
        if count / total_pages >= 0.70:
            repetitive.add(text)
        if _re.fullmatch(r"[\d\s\-/|.]+", text) and count / total_pages >= 0.30:
            repetitive.add(text)

    return [
        b for b in blocks
        if b.is_table or b.text.strip() not in repetitive
    ]
