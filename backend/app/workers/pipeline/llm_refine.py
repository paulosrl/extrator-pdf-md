"""LLM-based Markdown refinement using OpenAI gpt-4.1-mini."""
from __future__ import annotations

from typing import NamedTuple

from app.config import settings

_SYSTEM_PROMPT = """\
Você é um especialista em processamento de documentos jurídicos brasileiros.
Receberá um documento Markdown extraído automaticamente de um PDF via OCR/pdfplumber.

Sua tarefa é APENAS limpar e estruturar o texto. Regras absolutas:
- NÃO resuma, NÃO omita nenhum conteúdo, NÃO adicione informações que não existem
- Mantenha nomes próprios, números de processo, datas e valores exatamente como estão
- Mantenha toda a linguagem jurídica sem alterações

O que você DEVE corrigir:
1. Palavras fundidas sem espaço (ex: "AUTORIDADEPOLICIAL" → "AUTORIDADE POLICIAL", "doEstado" → "do Estado")
2. Parágrafos quebrados no meio de frases — una as linhas que formam uma mesma frase/parágrafo
3. Artefatos OCR residuais: caracteres isolados sem sentido, sequências como "^^^", "Wí/", "bt Cj"
4. Headings semanticamente incorretos — se um texto claramente não é título (ex: nome de pessoa, rótulo de formulário), rebaixe para parágrafo normal
5. Espaçamento excessivo entre seções — máximo uma linha em branco entre blocos

O que você DEVE preservar:
- Toda tabela em formato Markdown
- Headings que são seções reais do documento
- Comentários HTML como <!-- documento anexado -->
- Listas e estruturas de dados

Retorne APENAS o Markdown refinado, sem explicações, sem blocos de código envolvendo o resultado.\
"""

# Max tokens to send per chunk. gpt-4.1-mini has 1M context but we keep chunks
# manageable to control cost and latency.
_MAX_CHUNK_CHARS = 80_000  # ~20k tokens, well within limits


class RefineResult(NamedTuple):
    markdown: str
    tokens_used: int


def refine(markdown: str) -> RefineResult:
    """
    Send the markdown through GPT-4.1-mini for cleanup.
    Splits into chunks if the document is very large.
    Returns refined markdown and total tokens consumed.
    """
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY não configurada")

    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    if len(markdown) <= _MAX_CHUNK_CHARS:
        return _call(client, markdown)

    # Split into chunks on double newlines to avoid breaking mid-paragraph
    chunks = _split_chunks(markdown, _MAX_CHUNK_CHARS)
    refined_parts: list[str] = []
    total_tokens = 0
    for chunk in chunks:
        result = _call(client, chunk)
        refined_parts.append(result.markdown)
        total_tokens += result.tokens_used

    return RefineResult("\n\n".join(refined_parts), total_tokens)


def _call(client, text: str) -> RefineResult:
    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0.1,  # low temperature for deterministic cleanup
    )
    refined = response.choices[0].message.content or text
    tokens = response.usage.total_tokens if response.usage else 0
    return RefineResult(refined, tokens)


def _split_chunks(text: str, max_chars: int) -> list[str]:
    """Split text on double newlines into chunks of at most max_chars."""
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) > max_chars and current:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(para)
        current_len += len(para) + 2  # +2 for the \n\n separator

    if current:
        chunks.append("\n\n".join(current))

    return chunks
