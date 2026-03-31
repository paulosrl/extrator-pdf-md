"""Token counting using tiktoken (cl100k_base — compatible with GPT-4/Claude)."""
import tiktoken

_encoder = None


def _get_encoder():
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def count(text: str) -> int:
    return len(_get_encoder().encode(text))


def extract_raw_text(pdf_path: str) -> str:
    """
    Extract all raw text from PDF using pdfplumber's simple extract_text().
    This represents what a user would get without any processing — the full
    text layer including boilerplate, headers, footers, etc.
    """
    import pdfplumber
    texts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                texts.append(text)
    return "\n".join(texts)


