# PDF Cleaner for LLM

Converte PDFs em Markdown limpo e otimizado para LLMs. Remove cabeçalhos, rodapés, numeração de páginas e outros ruídos estruturais. Extrai texto de imagens via OCR e converte tabelas para Markdown. Reporta a redução percentual de tokens (tiktoken). Opcionalmente refina o resultado via GPT-4.1-mini.

## Requisitos

- [Docker](https://docs.docker.com/get-docker/) >= 24
- [Docker Compose](https://docs.docker.com/compose/install/) >= 2.20
- (Opcional) Chave de API da OpenAI para refinamento com IA

## Estrutura

```
extrator-pdf-md/
├── docker-compose.yml
├── .env                  # criado a partir de .env.example
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/          # migrations do banco
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── workers/
│       │   ├── tasks.py
│       │   └── pipeline/ # detector, ocr, extractor, markdown_builder, llm_refine, tokens
│       └── routers/      # auth, upload, jobs, ws
└── frontend/
    └── index.html
```

## Configuração

### 1. Copiar o arquivo de variáveis de ambiente

```bash
cp .env.example .env
```

### 2. Editar o `.env`

Abra o `.env` e ajuste os valores conforme necessário:

```dotenv
# Banco de dados (padrão funciona com Docker Compose)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/pdfcleaner
SYNC_DATABASE_URL=postgresql+psycopg2://postgres:postgres@postgres:5432/pdfcleaner

# Redis (padrão funciona com Docker Compose)
REDIS_URL=redis://redis:6379/0

# JWT — TROQUE este valor antes de usar em qualquer ambiente não-local
JWT_SECRET=change-me-in-production-use-a-long-random-string
JWT_ALGORITHM=HS256
JWT_EXPIRE_HOURS=168

# Armazenamento de arquivos (dentro do container; não alterar)
STORAGE_PATH=/data

# Limites de upload
MAX_FILE_SIZE_MB=200
MAX_PAGES=1000

# Credenciais do PostgreSQL (devem bater com DATABASE_URL acima)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=pdfcleaner

# OpenAI (opcional — deixe em branco para desabilitar refinamento com IA)
OPENAI_API_KEY=
```

> O campo `OPENAI_API_KEY` é opcional. Se não for preenchido, o botão "Refinar com IA" na interface simplesmente não funcionará.

## Subir o projeto

```bash
docker-compose up --build
```

Isso irá:
1. Iniciar o PostgreSQL e o Redis
2. Executar as migrations do banco (`alembic upgrade head`)
3. Subir o servidor FastAPI na porta **8000**
4. Subir o worker Celery (2 concorrências)

Na primeira execução o build pode levar alguns minutos (instala Tesseract OCR, Poppler e dependências Python).

## Acessar a aplicação

Abra o navegador em:

```
http://localhost:8000
```

A interface permite:
- Criar conta e fazer login
- Fazer upload de PDFs (até 200 MB / 1000 páginas)
- Acompanhar o progresso em tempo real via WebSocket
- Baixar o Markdown gerado
- Visualizar o histórico de processamentos com métricas de redução de tokens

## API

A documentação interativa da API está disponível em:

```
http://localhost:8000/docs
```

Endpoints principais:

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `POST` | `/auth/register` | Criar conta |
| `POST` | `/auth/login` | Autenticar (retorna JWT) |
| `POST` | `/upload` | Enviar PDF para processamento |
| `GET` | `/jobs` | Listar jobs do usuário |
| `GET` | `/jobs/{id}` | Status e métricas de um job |
| `GET` | `/jobs/{id}/download` | Baixar Markdown final |
| `GET` | `/jobs/{id}/download/raw` | Baixar Markdown local (pré-refinamento IA) |
| `GET` | `/jobs/{id}/download/rawtext` | Baixar texto bruto com tags de página |
| `WS` | `/ws/{job_id}` | WebSocket de progresso em tempo real |

## Pipeline de processamento

```
Upload PDF
    │
    ▼
1. Detecção de camada de texto
    │
    ├── Páginas escaneadas → OCR (pytesseract, pt+en)
    │
    ▼
2. Extração de conteúdo (pdfplumber)
    │   ├── x_tolerance adaptativo por página
    │   ├── Filtros de boilerplate (cabeçalhos, rodapés, selos institucionais)
    │   ├── Extração de tabelas
    │   └── Extração de texto de imagens embutidas
    │
    ▼
3. Geração do Markdown
    │   ├── Headings validados (ratio de tamanho de fonte)
    │   └── Correção de artefatos OCR
    │
    ├── [opcional] Refinamento GPT-4.1-mini
    │
    ▼
4. Contagem de tokens (tiktoken / cl100k_base)
    │
    ▼
Markdown salvo + métricas no banco
```

## Parar e remover containers

```bash
# Parar mantendo os dados
docker-compose down

# Parar e remover volumes (apaga banco e arquivos processados)
docker-compose down -v
```

## Reconstruir após mudanças no código

O volume `./backend:/app_src` está montado com reload ativo no backend. Mudanças em arquivos Python são aplicadas automaticamente pelo Uvicorn.

Para mudanças no `requirements.txt` ou no `Dockerfile`:

```bash
docker-compose up --build
```

## Logs

```bash
# Todos os serviços
docker-compose logs -f

# Apenas o worker Celery
docker-compose logs -f worker

# Apenas o backend
docker-compose logs -f backend
```

## Solução de problemas

**Erro `OPENAI_API_KEY não configurada` ao tentar usar refinamento IA**
Adicione a chave no `.env`: `OPENAI_API_KEY=sk-...` e reinicie com `docker-compose up`.

**Banco não inicializado / erro de migration**
```bash
docker-compose run --rm migrate alembic upgrade head
```

**Arquivo PDF recusado**
- Tamanho máximo: 200 MB (configurável via `MAX_FILE_SIZE_MB` no `.env`)
- Páginas máximas: 1000 (configurável via `MAX_PAGES` no `.env`)
- O arquivo deve ter extensão `.pdf`

**WebSocket desconectando durante processamento longo**
O timeout do WebSocket é de 5 minutos. PDFs muito grandes com OCR + refinamento IA podem ultrapassar esse limite. Atualize a página — o job continua em background e o resultado estará disponível no histórico.
