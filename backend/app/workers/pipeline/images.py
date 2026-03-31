"""Extract embedded images from PDF and run OCR on them."""
import io
import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import pdfplumber
import pytesseract
from PIL import Image

# Minimum source size (pixels) for an image to be considered a potential document.
# Tiny images are logos, stamps, QR codes — not attached documents.
_DOC_MIN_PX = 150

# Patterns that identify boilerplate lines in image OCR output.
# Applied after removing all whitespace from each line (handles spaced-out text).
_IMG_BOILERPLATE_NOSPACE = re.compile(
    r"estodocumentofoigerado"
    r"|númerododocumento"
    r"|assinadoeletronicamentepor"
    r"|consultadocumento"
    r"|listview\.seam"
    r"|pje\.tjpa\.jus\.br"
    r"|protocolo(de)?assinatura"
    r"|coletabiométrica"
    r"|bancodedadosdosistemasisp"
    r"|nãoexistembiometrias"
    r"|documentofoiassinado"
    r"|num\.\d"
    r"|pág\.\d"
    r"|https?://",
    re.IGNORECASE,
)


@dataclass
class ImageResult:
    page: int
    text: str           # OCR text (empty if failed or no text)
    extracted: bool     # True = PIL decode + OCR succeeded (even if no text)
    is_doc: bool        # True = large enough to be an attached document


def _clean_image_text(raw: str) -> str:
    """
    Filter OCR text from images line by line, removing boilerplate.
    Returns cleaned text or empty string if nothing remains.
    """
    kept = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        compact = re.sub(r"\s+", "", stripped)
        if _IMG_BOILERPLATE_NOSPACE.search(compact):
            continue
        kept.append(stripped)
    return "\n".join(kept).strip()


def _is_doc_size(img_meta: dict) -> bool:
    """True if the image source dimensions suggest a document (not a logo/stamp)."""
    src = img_meta.get("srcsize")  # (width, height) tuple from pdfplumber
    if src and len(src) == 2:
        return src[0] >= _DOC_MIN_PX and src[1] >= _DOC_MIN_PX
    # Fallback: use page-coordinate bounding box dimensions
    w = abs(img_meta.get("x1", 0) - img_meta.get("x0", 0))
    h = abs(img_meta.get("y1", 0) - img_meta.get("y0", 0))
    return w >= 72 and h >= 72  # 72 pts ≈ 1 inch


def extract_images(pdf_path: str) -> Tuple[Dict[int, List[str]], int, int]:
    """
    Returns (texts_dict, docs_found, docs_extracted).

    texts_dict      : {page_index: [ocr_text, ...]} — pages where OCR produced text.
    docs_found      : images large enough to be attached documents (>= _DOC_MIN_PX).
    docs_extracted  : of those, how many had text successfully OCR'd.
    """
    texts: Dict[int, List[str]] = {}
    docs_found = 0
    docs_extracted = 0

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            page_images = page.images
            if not page_images:
                continue

            for img_meta in page_images:
                is_doc = _is_doc_size(img_meta)
                if is_doc:
                    docs_found += 1

                try:
                    pil_img = _extract_pil_image(page, img_meta)
                    if pil_img is None:
                        continue
                    if pil_img.width < 50 or pil_img.height < 50:
                        continue

                    text = pytesseract.image_to_string(pil_img, lang="por+eng")
                    text = _clean_image_text(text)
                    if text:
                        texts.setdefault(page_idx, []).append(text)
                        if is_doc:
                            docs_extracted += 1
                except Exception:
                    continue

    return texts, docs_found, docs_extracted


def count_pages_with_images(pdf_path: str) -> int:
    count = 0
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            if page.images:
                count += 1
    return count


def _extract_pil_image(page, img_meta: dict):
    """Extract a PIL Image from a pdfplumber image metadata dict.

    pdfminer's read_bytes() returns already-decoded (decompressed) data.
    - /DCTDecode  → JPEG bytes   → Image.open() works directly
    - /JPXDecode  → JPEG2000     → Image.open() works if Pillow has openjpeg
    - /FlateDecode → raw pixels  → must reconstruct from width/height/colorspace
    - /CCITTFaxDecode, /JBIG2Decode → binary fax/JBIG2, typically non-text
    """
    try:
        pdf_obj = page.page_obj
        resources = pdf_obj.get("/Resources", {})
        xobjects = resources.get("/XObject", {})

        img_name = img_meta.get("name")
        if not img_name or img_name not in xobjects:
            return None

        xobj = xobjects[img_name]
        xobj = xobj.get_object()

        if xobj.get("/Subtype") != "/Image":
            return None

        data = xobj.read_bytes()

        # 1. Try direct PIL open (handles JPEG, PNG, JPEG2000, etc.)
        try:
            return Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            pass

        # 2. Raw pixel data (FlateDecode decoded) — reconstruct from dimensions
        width = int(xobj.get("/Width", 0))
        height = int(xobj.get("/Height", 0))
        if not (width and height):
            return None

        cs = str(xobj.get("/ColorSpace", "/DeviceRGB"))
        if "CMYK" in cs:
            mode, channels = "CMYK", 4
        elif "Gray" in cs or cs == "/DeviceGray":
            mode, channels = "L", 1
        else:
            mode, channels = "RGB", 3

        expected = width * height * channels
        if len(data) >= expected:
            try:
                img = Image.frombytes(mode, (width, height), data[:expected])
                return img.convert("RGB")
            except Exception:
                pass

        return None
    except Exception:
        return None
