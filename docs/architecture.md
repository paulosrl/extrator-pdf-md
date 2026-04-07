# Arquitetura e Análise Técnica — PDF Cleaner for LLM

## O que o sistema faz

Converte PDFs (especialmente documentos jurídicos brasileiros do PJe, Polícia Civil, MP-PA) em
Markdown limpo e otimizado para uso com LLMs. Remove o "ruído" típico desses documentos
(cabeçalhos, rodapés, selos institucionais, assinaturas digitais) e reporta a redução percentual
de tokens antes/depois do processamento.

---

## Arquitetura geral

```
Browser (SPA vanilla JS)
    ↓ HTTP/WebSocket
FastAPI (API REST) — porta 8000
    ↓ enfileira task via Redis
Worker Celery (pipeline de 6 etapas)
    ↓
PostgreSQL (jobs + users) + volume /data (arquivos)
```

### Serviços Docker Compose

| Serviço    | Imagem                | Função                                         |
|------------|-----------------------|------------------------------------------------|
| `postgres` | postgres:15-alpine    | Banco de dados relacional                      |
| `redis`    | redis:7-alpine        | Broker Celery + pub/sub de progresso           |
| `migrate`  | (backend Dockerfile)  | Executa `alembic upgrade head` na inicialização|
| `backend`  | (backend Dockerfile)  | FastAPI + Uvicorn com hot-reload               |
| `worker`   | (backend Dockerfile)  | Celery worker, concurrency=2                   |

---

## Pipeline de processamento

Orquestrado em `backend/app/workers/tasks.py` — cada etapa publica progresso via Redis pub/sub
→ WebSocket → frontend em tempo real.

### Etapa 1 — Detecção (`detector.py`)
- Verifica cada página com `pdfplumber.extract_text()`
- Classifica: tem camada de texto vs. escaneada
- Retorna lista de `(page_index, has_text_layer)`

### Etapa 2 — OCR (`ocr.py`)
- Rasteriza páginas escaneadas via `pdf2image` a 200 DPI
- Roda Tesseract com idiomas `por+eng`
- Retorna `(page_index, ocr_text_or_None)`

### Etapa 3 — Extração (`extractor.py`) — coração do sistema
- **Boilerplate removal**: padrões regex específicos para documentos jurídicos (PA) + filtro de
  repetição (texto presente em ≥ 40% das páginas ou ≥ 70% globalmente é descartado)
- **Heading detection**: mediana do font size da página como baseline; blocos acima de um ratio
  são classificados como H1/H2/H3
- **x_tolerance adaptativo**: detecta PDFs com encoding char-by-char e usa 15pt de tolerância
  (em vez de 3pt padrão) para reconstruir palavras corretamente
- **Limpeza de artefatos**: "P ROMOTORIA" → "PROMOTORIA", "doEstado" → "do Estado",
  phantom spaces em palavras acentuadas, null bytes
- **Extração de tabelas**: usa `pdfplumber.find_tables()`

### Etapa 4 — Imagens embutidas (`images.py`)
- Extrai imagens do PDF, filtra por tamanho mínimo (150px) para ignorar logos/selos
- Roda Tesseract nas imagens grandes (documentos digitalizados como imagem)

### Etapa 5 — Montagem do Markdown (`markdown_builder.py`)
- Combina blocos de texto, tabelas e texto de imagens
- Formata headings com `#`/`##`/`###`
- Converte tabelas para pipe-delimited Markdown
- Valida headings (rejeita frases, labels de cargo, assinaturas)
- Remove artefatos OCR e linhas em branco excessivas

### Etapa 5b — Refinamento LLM (`llm_refine.py`) — opcional
- Ativado apenas se `use_llm=true` no upload
- Suporta OpenAI (`gpt-4.1-mini`) e Azure OpenAI
- Chunking automático para documentos > 80k chars (splits por parágrafo)
- System prompt calibrado para documentos jurídicos brasileiros (não resume, não altera conteúdo)
- Salva Markdown pré-LLM como `{job_id}_raw.md`

### Etapa 6 — Contagem de tokens (`tokens.py`)
- Encoding: `tiktoken cl100k_base`
- **Baseline** = texto bruto pdfplumber + OCR (o que o usuário copiaria manualmente)
- **Output** = Markdown limpo gerado
- `reduction_pct` clamped em `[-9999.99, 9999.99]` para caber em `NUMERIC(7,2)`

---

## Modelo de dados central — `ProcessingJob`

Chave primária UUID. Campos relevantes:

| Grupo       | Campos                                                                 |
|-------------|------------------------------------------------------------------------|
| Status      | `status` (enum: queued/ocr/extracting/done/error), `error_message`    |
| Arquivos    | `original_storage_path`, `output_storage_path`, `raw_output_path`     |
| Métricas    | `tokens_original`, `tokens_output`, `reduction_pct`, `llm_tokens_used`|
| Tamanhos    | `original_file_size`, `output_file_size` (BigInteger)                 |
| Páginas     | `pages_total`, `pages_ocr`, `pages_with_images`                       |
| LLM         | `use_llm` (bool), `llm_model` (string)                                |
| Tempo       | `duration_local_s`, `duration_llm_s`, `created_at`, `completed_at`   |

---

## API endpoints

| Método | Rota                          | Função                                 | Auth |
|--------|-------------------------------|----------------------------------------|------|
| POST   | `/auth/register`              | Cria usuário, retorna JWT              | Não  |
| POST   | `/auth/login`                 | Autentica, retorna JWT                 | Não  |
| POST   | `/upload`                     | Enfileira job de processamento         | Sim  |
| GET    | `/jobs`                       | Lista 50 jobs mais recentes do usuário | Sim  |
| GET    | `/jobs/{id}`                  | Detalhes de um job                     | Sim  |
| GET    | `/jobs/{id}/download`         | Download do Markdown final             | Sim  |
| GET    | `/jobs/{id}/download/raw`     | Download do Markdown pré-LLM          | Sim  |
| WS     | `/ws/{job_id}`                | Progresso em tempo real                | Sim  |
| GET    | `/health`                     | Health check                           | Não  |
| GET    | `/`                           | Serve o frontend (SPA)                 | Não  |

---

## Frontend (`frontend/index.html`)

SPA single-file em HTML + JS vanilla (sem framework/bundler):

- Drop zone para upload de PDF com validação de tipo e tamanho
- Checkbox para habilitar refinamento LLM + seletor de modelo
- Barra de progresso em tempo real via WebSocket
- Tabela de histórico com download dos resultados
- Cards de métricas: redução de tokens, tempo de processamento, tamanho dos arquivos
- Modo escuro/claro com CSS variables
- JWT armazenado em `localStorage`

---

## Fluxo completo resumido

```
1. POST /upload
   ├── Salva PDF em /data/{job_id}/original.pdf
   ├── Cria ProcessingJob (status: queued)
   └── Enfileira process_pdf(job_id) no Celery

2. Worker executa process_pdf:
   detector → ocr → extractor → images → markdown_builder → [llm_refine] → tokens

3. A cada etapa: Redis pub/sub → WS /ws/{job_id} → frontend

4. Resultado salvo em /data/{job_id}/output.md
   └── Métricas gravadas no banco

5. Usuário baixa via GET /jobs/{id}/download
```

---

## Débito técnico relevante

- Sem testes automatizados
- Sem CI/CD
- CORS aberto (`allow_origins=["*"]`) — ok para dev, restringir em produção
- Worker sem retry (`max_retries=0`)
- `import os` dentro da função `process_pdf` (deveria estar no topo)
