"""LLM-based Markdown refinement — suporta OpenAI direto e Azure OpenAI."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, NamedTuple, Optional

from openai import OpenAI

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
- Comentários HTML como <!-- page N --> e <!-- documento anexado -->
- Listas e estruturas de dados

Retorne APENAS o Markdown refinado, sem explicações, sem blocos de código envolvendo o resultado.\
"""

# Tamanho máximo por chunk (chars). Chunks menores permitem paralelismo maior
# e reduzem a latência percebida em documentos grandes.
_MAX_CHUNK_CHARS = 40_000  # ~10k tokens
_MAX_PARALLEL    = 4       # máximo de requisições LLM simultâneas


class RefineResult(NamedTuple):
    markdown: str
    tokens_used: int


def refine(
    markdown: str,
    model: str = "openai",
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> RefineResult:
    """
    Envia o markdown ao modelo escolhido para limpeza.
    model: "openai" | "azure-gpt-4.1" | "azure-gpt-5"
    Divide em chunks e os processa em paralelo quando há mais de um.
    progress_callback(done, total) é chamado a cada chunk concluído.
    """
    client, deployment = _build_client(model)
    use_temp = _supports_temperature(model)

    if len(markdown) <= _MAX_CHUNK_CHARS:
        if progress_callback:
            progress_callback(0, 1)
        result = _call(client, deployment, markdown, use_temp)
        if progress_callback:
            progress_callback(1, 1)
        return result

    chunks = _split_chunks(markdown, _MAX_CHUNK_CHARS)
    n = len(chunks)
    refined_parts: list[str | None] = [None] * n
    total_tokens = 0

    if progress_callback:
        progress_callback(0, n)

    with ThreadPoolExecutor(max_workers=min(_MAX_PARALLEL, n)) as pool:
        futures = {
            pool.submit(_call, client, deployment, chunk, use_temp): i
            for i, chunk in enumerate(chunks)
        }
        done_count = 0
        for future in as_completed(futures):
            i = futures[future]
            result = future.result()   # propaga exceções
            refined_parts[i] = result.markdown
            total_tokens += result.tokens_used
            done_count += 1
            if progress_callback:
                progress_callback(done_count, n)

    return RefineResult("\n\n".join(p for p in refined_parts if p is not None), total_tokens)


def _supports_temperature(model: str) -> bool:
    """Azure gpt-5 rejeita temperature != 1; OpenAI direto aceita."""
    return not model.startswith("azure-")


def _build_client(model: str) -> tuple[OpenAI, str]:
    """Retorna (cliente OpenAI, nome do deployment/model) conforme o provider."""
    if model.startswith("azure-"):
        if not settings.AZURE_OPENAI_API_KEY:
            raise ValueError("AZURE_OPENAI_API_KEY não configurada")
        if not settings.AZURE_OPENAI_ENDPOINT:
            raise ValueError("AZURE_OPENAI_ENDPOINT não configurado")
        endpoint = settings.AZURE_OPENAI_ENDPOINT.rstrip("/")
        client = OpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            base_url=f"{endpoint}/openai/v1/",
        )
        # azure-gpt-4.1 → deployment "gpt-4.1"; azure-gpt-5 → "gpt-5"
        deployment = model[len("azure-"):]
        return client, deployment

    # Provedor padrão: OpenAI direto
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY não configurada")
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return client, settings.OPENAI_MODEL


def _call(client: OpenAI, deployment: str, text: str, use_temperature: bool = True) -> RefineResult:
    kwargs = {}
    if use_temperature:
        kwargs["temperature"] = 0.1
    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        **kwargs,
    )
    refined = response.choices[0].message.content or text
    tokens = response.usage.total_tokens if response.usage else 0
    return RefineResult(refined, tokens)


def _split_chunks(text: str, max_chars: int) -> list[str]:
    """Divide texto em parágrafos em chunks de no máximo max_chars."""
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
        current_len += len(para) + 2

    if current:
        chunks.append("\n\n".join(current))

    return chunks
