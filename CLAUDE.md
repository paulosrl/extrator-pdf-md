# PDF Cleaner for LLM

## Visão geral
Sistema web que converte PDFs em Markdown limpo e otimizado para uso com LLMs. Remove cabeçalhos, rodapés, selos institucionais e outros ruídos estruturais comuns em documentos jurídicos brasileiros (PJe, Polícia Civil, MP-PA). Suporta OCR para páginas escaneadas, extração de tabelas, e refinamento opcional via GPT-4.1-mini. Reporta a redução percentual de tokens (tiktoken) entre o PDF original e o Markdown gerado.

## Stack técnica
- **Linguagem:** Python 3.11+
- **Framework principal:** FastAPI (API REST + WebSocket) + Celery (worker assíncrono)
- **Banco de dados:** PostgreSQL 15 (async via asyncpg, sync via psycopg2)
- **Migrations:** Alembic
- **Fila/broker:** Redis 7
- **PDF:** pdfplumber (extração), pdf2image + pytesseract (OCR), Pillow (imagens)
- **IA:** OpenAI gpt-4.1-mini (opcional, refinamento de Markdown)
- **Tokens:** tiktoken / cl100k_base
- **Auth:** JWT (python-jose + bcrypt)
- **Frontend:** HTML/JS puro (single-file: `frontend/index.html`)
- **Infraestrutura:** Docker Compose (4 serviços: postgres, redis, backend, worker)
- **Gerenciador de pacotes:** pip (requirements.txt)
- **Testes:** nenhum implementado ainda
- **CI/CD:** nenhum configurado

## Estrutura de pastas
```
extrator-pdf-md/
├── docker-compose.yml          # Orquestra postgres, redis, migrate, backend, worker
├── .env / .env.example         # Variáveis de ambiente
├── frontend/
│   └── index.html              # SPA single-file (HTML/JS/CSS sem bundler)
└── backend/
    ├── Dockerfile
    ├── requirements.txt
    ├── alembic.ini
    ├── alembic/
    │   └── versions/           # 7 migrations (0001–0007)
    └── app/
        ├── main.py             # Entrypoint FastAPI, monta routers e serve frontend
        ├── config.py           # Settings via pydantic-settings (lê .env)
        ├── database.py         # Engine async + sync, Base, SessionLocal
        ├── celery_app.py       # Instância Celery configurada com Redis
        ├── dependencies.py     # get_current_user (JWT → User)
        ├── models/
        │   ├── user.py         # Model User
        │   └── job.py          # Model ProcessingJob + enum JobStatus
        ├── schemas/            # Pydantic schemas (auth, job, user)
        ├── routers/
        │   ├── auth.py         # POST /auth/register, POST /auth/login
        │   ├── upload.py       # POST /upload
        │   ├── jobs.py         # GET /jobs, GET /jobs/{id}, GET /jobs/{id}/download[/raw]
        │   └── ws.py           # WS /ws/{job_id} (progresso em tempo real)
        ├── services/
        │   ├── progress.py     # Publica eventos de progresso no Redis (pub/sub)
        │   └── storage.py      # Salva/recupera arquivos em STORAGE_PATH (/data)
        └── workers/
            ├── tasks.py        # Celery task: process_pdf (orquestra o pipeline completo)
            └── pipeline/
                ├── detector.py         # Detecta páginas com/sem camada de texto
                ├── extractor.py        # Extrai blocos de texto com pdfplumber (x_tolerance adaptativo, filtros boilerplate)
                ├── markdown_builder.py # Monta o Markdown final a partir dos blocos
                ├── ocr.py              # Executa pytesseract nas páginas escaneadas
                ├── images.py           # Extrai texto de imagens embutidas no PDF
                ├── llm_refine.py       # Refinamento via GPT-4.1-mini (chunking automático)
                └── tokens.py           # Conta tokens com tiktoken (cl100k_base)
```

## Arquivos-chave para entender o projeto
- `backend/app/workers/tasks.py` — orquestra todo o pipeline de 6 etapas; ponto central da lógica de negócio
- `backend/app/workers/pipeline/extractor.py` — coração do sistema: extração, detecção de boilerplate, x_tolerance adaptativo, heading detection por ratio de font size
- `backend/app/workers/pipeline/markdown_builder.py` — converte blocos extraídos em Markdown válido, com validação de headings e correção de artefatos OCR
- `backend/app/workers/pipeline/llm_refine.py` — integração com OpenAI, chunking para documentos grandes, system prompt especializado em documentos jurídicos
- `backend/app/models/job.py` — modelo central `ProcessingJob` com todos os campos de métricas
- `backend/app/config.py` — todas as variáveis de configuração em um único lugar
- `docker-compose.yml` — topologia completa dos serviços e dependências de inicialização

## Comandos do dia a dia
```bash
# Subir tudo (primeira vez ou após mudar requirements.txt/Dockerfile)
docker-compose up --build

# Subir sem rebuild (mudanças só em .py — reload automático)
docker-compose up

# Derrubar mantendo dados
docker-compose down

# Derrubar e apagar banco + arquivos processados
docker-compose down -v

# Ver logs em tempo real
docker-compose logs -f
docker-compose logs -f worker   # só o Celery
docker-compose logs -f backend  # só o FastAPI

# Rodar migration manualmente (se necessário)
docker-compose run --rm migrate alembic upgrade head

# Criar nova migration
docker-compose run --rm migrate alembic revision --autogenerate -m "descricao"
```

## Variáveis de ambiente necessárias
- `DATABASE_URL` — connection string async para o PostgreSQL (asyncpg)
- `SYNC_DATABASE_URL` — connection string sync para o PostgreSQL (psycopg2, usada no worker Celery)
- `REDIS_URL` — URL do Redis (broker Celery + pub/sub de progresso)
- `JWT_SECRET` — segredo para assinar tokens JWT; **trocar em produção**
- `JWT_ALGORITHM` — algoritmo JWT (padrão: `HS256`)
- `JWT_EXPIRE_HOURS` — expiração do token em horas (padrão: `168` = 7 dias)
- `STORAGE_PATH` — diretório de armazenamento de arquivos dentro do container (padrão: `/data`)
- `MAX_FILE_SIZE_MB` — limite de tamanho de upload em MB (padrão: `200`)
- `MAX_PAGES` — limite de páginas por PDF (padrão: `1000`)
- `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` — credenciais do PostgreSQL (devem bater com DATABASE_URL)
- `OPENAI_API_KEY` — chave da API OpenAI; **opcional** — se vazio, refinamento IA é desabilitado silenciosamente
- `OPENAI_MODEL` — modelo OpenAI a usar (padrão: `gpt-4.1-mini`)

## Convenções adotadas no projeto
- **Commits:** `tipo: descrição em português` (ex: `feat:`, `fix:`, `chore:`, `docs:`)
- **Nomenclatura Python:** snake_case para funções/variáveis, PascalCase para classes, UPPER_SNAKE para constantes e regex compilados
- **Routers:** um arquivo por domínio (auth, upload, jobs, ws)
- **Pipeline:** cada etapa é um módulo independente em `workers/pipeline/`
- **Migrations:** prefixadas com número sequencial de 4 dígitos (`0001_initial.py`, `0002_...`)
- **Schemas Pydantic:** separados dos models SQLAlchemy (pasta `schemas/` vs `models/`)
- **Progresso em tempo real:** via Redis pub/sub → WebSocket (não polling)

## Fluxo de dados principal
```
1. POST /upload
   └── Salva PDF em /data/{job_id}/original.pdf
   └── Cria ProcessingJob no banco (status: queued)
   └── Enfileira task Celery: process_pdf(job_id)

2. Worker Celery executa process_pdf:
   ├── detector.detect_pages()     → identifica páginas escaneadas vs. com texto
   ├── ocr.run_ocr()               → pytesseract nas páginas escaneadas (pt+en)
   ├── extractor.extract()         → pdfplumber com x_tolerance adaptativo
   │   ├── filtra boilerplate (padrões regex + positional/global repetition)
   │   └── detecta headings por ratio de font size vs. mediana
   ├── images.extract_images()     → texto de imagens embutidas
   ├── markdown_builder.build()    → monta Markdown final
   ├── [opcional] llm_refine.refine() → GPT-4.1-mini com chunking
   └── tokens.count()              → tiktoken para medir redução

3. Progresso publicado no Redis a cada etapa → WS /ws/{job_id} → frontend

4. Resultado salvo em /data/{job_id}/output.md
   └── Métricas gravadas no banco (tokens_original, tokens_output, reduction_pct, etc.)

5. GET /jobs/{id}/download        → serve output.md
   GET /jobs/{id}/download/raw    → serve Markdown pré-refinamento (se use_llm=true)
```

## Integrações externas
- **OpenAI API** — `gpt-4.1-mini` para refinamento de Markdown; integração em `llm_refine.py`; completamente opcional
- **Tesseract OCR** — instalado no container Docker via apt; idiomas pt+en; acionado para páginas sem camada de texto
- **Poppler** — instalado no container Docker; usado pelo pdf2image para rasterizar páginas para OCR

## Regras de negócio críticas
- **Nunca alterar os padrões de boilerplate** em `extractor.py` sem testar com documentos PJe e da Polícia Civil do Pará — são altamente específicos e frágeis
- **Baseline de tokens** é calculado com o texto bruto do pdfplumber (inclui boilerplate) + OCR das páginas escaneadas, não só o Markdown gerado — isso garante que a métrica de redução reflita o benefício real da ferramenta
- **`reduction_pct`** é clamped em `[-9999.99, 9999.99]` para caber no campo `NUMERIC(7,2)` — PDFs quase vazios podem gerar valores extremos
- **`use_llm`** é definido no momento do upload; não pode ser alterado após o job ser criado
- **Autenticação:** todos os endpoints (exceto `/auth/register`, `/auth/login`, `/health`, `/`) exigem JWT válido
- **Isolamento de jobs por usuário:** queries de jobs sempre filtram por `user_id` — um usuário não acessa jobs de outro

## Débito técnico identificado
- Nenhum TODO/FIXME/HACK encontrado no código
- **Sem testes automatizados** — nenhum arquivo de teste existe no projeto
- **Sem CI/CD** — nenhum workflow GitHub Actions ou equivalente
- **CORS aberto** (`allow_origins=["*"]`) em `main.py` — aceitável para desenvolvimento, deve ser restrito em produção
- **`import os` dentro da função** `process_pdf` em `tasks.py` (linha 138) — deveria estar no topo do arquivo
- **Worker Celery sem retry** (`max_retries=0`) — falhas não são retentadas automaticamente

## O que NÃO fazer neste projeto
- Não usar `alembic autogenerate` sem revisar o diff — os tipos PostgreSQL customizados (UUID, Enum `jobstatus`) podem gerar migrations incorretas
- Não alterar os padrões regex de boilerplate em `extractor.py` sem conjunto de testes com PDFs reais
- Não mover a lógica de extração para async — o worker Celery usa sessão síncrona (psycopg2) intencionalmente
- Não adicionar dependências ao `requirements.txt` sem reconstruir a imagem Docker (`docker-compose up --build`)
- Não armazenar arquivos fora de `STORAGE_PATH` — o volume `pdf_data` é compartilhado entre `backend` e `worker`
- Não trocar o modelo OpenAI sem avaliar o system prompt — ele foi calibrado especificamente para `gpt-4.1-mini` e documentos jurídicos brasileiros
