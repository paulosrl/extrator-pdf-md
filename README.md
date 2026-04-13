# PDF Cleaner for LLM

Converte PDFs em Markdown limpo e otimizado para LLMs. Remove cabeçalhos, rodapés, numeração de páginas e outros ruídos estruturais. Extrai texto de imagens via OCR e converte tabelas para Markdown. Reporta a redução percentual de tokens (tiktoken). Opcionalmente refina o resultado via GPT-4.1-mini.

## Requisitos

- [Docker Engine](https://docs.docker.com/engine/install/) >= 24
- **Docker Compose v2** (plugin `docker compose`, não o antigo `docker-compose`)
- (Opcional) Chave de API da OpenAI para refinamento com IA

> **Importante:** O projeto requer Docker Compose **v2** (comando `docker compose`, com espaço). A versão legada v1 (`docker-compose`, com hífen, pacote Python) é incompatível com Docker Engine >= 25 e causará erros como `KeyError: 'ContainerConfig'`. Veja a seção [Solução de problemas](#solução-de-problemas) se encontrar esse erro.

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

## Configuração inicial (primeira vez em uma máquina nova)

### 1. Instalar o Docker corretamente

Siga o guia oficial para o seu sistema operacional:

- **Linux (Ubuntu/Debian):** https://docs.docker.com/engine/install/ubuntu/
- **macOS:** instale o [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- **Windows (WSL2):** instale o [Docker Desktop](https://www.docker.com/products/docker-desktop/) com integração WSL2 habilitada

Após instalar, **verifique que o Compose v2 está disponível:**

```bash
docker compose version
# Deve retornar: Docker Compose version v2.x.x
```

Se o comando acima falhar (ou retornar v1.x), veja [Instalar Docker Compose v2](#instalar-docker-compose-v2).

### 2. Corrigir permissões do Docker (Linux/WSL2)

No Linux, o socket do Docker pertence ao grupo `docker`. Sem isso, qualquer comando `docker` falha com `Permission denied`.

```bash
# Adicionar seu usuário ao grupo docker (executar uma única vez)
sudo usermod -aG docker $USER

# Aplicar sem precisar fazer logout
newgrp docker

# Verificar se funcionou
docker info
```

> Em WSL2, após rodar `newgrp docker`, pode ser necessário fechar e reabrir o terminal.

### 3. Copiar o arquivo de variáveis de ambiente

```bash
cp .env.example .env
```

### 4. Editar o `.env`

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
docker compose up --build
```

> **Atenção:** use `docker compose` (com espaço), não `docker-compose` (com hífen).

Isso vai inicializar a orquestração completa. A arquitetura é dividida nos seguintes containers:

### Papel de cada Container:
- 🐘 **`postgres`**: Banco de dados relacional. Armazena usuários, histórico de processos, métricas de tokens e onde os dados são persistidos.
- 🟥 **`redis`**: Banco de dados em memória super rápido atuando como "mensageiro" (message broker) para as filas do Celery administrar tarefas.
- 🛠️ **`migrate`**: Container pontual focado apenas em atualizar a estrutura do banco de dados (Alembic). Ele roda, constrói as tabelas necessárias e **se desliga** automaticamente (`code 0`).
- ⚡ **`backend`**: Servidor da API ([FastAPI](https://fastapi.tiangolo.com/)). É quem hospeda as rotas de acesso, valida tokens (JWT), serve o site visual (`index.html`) e coordena o recebimento dos arquivos PDF. 
- ⚙️ **`worker`**: Operário focado no trabalho pesado ([Celery](https://docs.celeryq.dev/)). Fica escutando as tarefas longas em segundo plano, como ler páginas do PDF, rodar IA e extrair OCR, liberando a API para não travar.

> **Tempo de build:** Na primeira execução, o build de criação do `backend` e `worker` pode levar mais de alguns minutos pois requer instalação dos pacotes grossos do Tesseract OCR, Poppler, etc.

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
docker compose down

# Parar e remover volumes (apaga banco e arquivos processados)
docker compose down -v
```

## Reconstruir após mudanças no código

O volume `./backend:/app_src` está montado com reload ativo no backend. Mudanças em arquivos Python são aplicadas automaticamente pelo Uvicorn.

Para mudanças no `requirements.txt` ou no `Dockerfile`:

```bash
docker compose up --build
```

## Logs

```bash
# Todos os serviços
docker compose logs -f

# Apenas o worker Celery
docker compose logs -f worker

# Apenas o backend
docker compose logs -f backend
```

## Solução de problemas

### `Permission denied` ao rodar qualquer comando docker

**Sintoma:** `PermissionError(13, 'Permission denied')` ao tentar conectar ao socket Docker.

**Causa:** Seu usuário não pertence ao grupo `docker`.

**Solução:**
```bash
sudo usermod -aG docker $USER
newgrp docker
```

Se persistir após isso (comum em WSL2), aplique temporariamente:
```bash
sudo chmod 666 /var/run/docker.sock
```

> Esse `chmod` é temporário — volta ao normal após reiniciar o sistema. A solução permanente é o `usermod` acima.

---

### `KeyError: 'ContainerConfig'` ao subir containers

**Sintoma:** Erro como `container.image_config['ContainerConfig']` ao rodar `docker-compose up`.

**Causa:** Você está usando o `docker-compose` legado (v1, pacote Python) com Docker Engine >= 25. Eles são incompatíveis.

**Solução:** Instale o Docker Compose v2 e use `docker compose` (com espaço):

```bash
# Verificar versão atual
docker compose version   # deve retornar v2.x.x

# Se não funcionar, instalar o plugin (no Ubuntu 24.04 o nome mudou para docker-compose-v2)
sudo apt-get update && sudo apt-get install -y docker-compose-plugin || sudo apt-get install -y docker-compose-v2
```

Se não puder instalar o plugin, o contorno é remover os containers existentes antes de subir:
```bash
docker rm -f $(docker ps -aq --filter "name=extrator-pdf-md") 2>/dev/null || true
docker-compose up --build
```

---

### Instalar Docker Compose v2

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y docker-compose-plugin
# Nota: Se estiver no Ubuntu 24.04 (Noble) ou mais recente, use o novo nome do pacote:
sudo apt-get install -y docker-compose-v2
docker compose version
```

**Alternativa (qualquer Linux):**
```bash
DOCKER_CONFIG=${DOCKER_CONFIG:-$HOME/.docker}
mkdir -p $DOCKER_CONFIG/cli-plugins
curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o $DOCKER_CONFIG/cli-plugins/docker-compose
chmod +x $DOCKER_CONFIG/cli-plugins/docker-compose
docker compose version
```

---

### Erro `OPENAI_API_KEY não configurada` ao usar refinamento IA

Adicione a chave no `.env`:
```
OPENAI_API_KEY=sk-...
```
Reinicie com `docker compose up`.

---

### Banco não inicializado / erro de migration

```bash
docker compose run --rm migrate alembic upgrade head
```

---

### Container "migrate" mostrando `exited - code 0`

Isso **não é um erro**! É o comportamento **esperado e indica sucesso**. O container `migrate` funciona como uma tarefa pontual: ele liga, roda as migrações (cria/atualiza as tabelas do banco) e depois se encerra propositalmente, devolvendo o código de sucesso `0`. Apenas quando ele finaliza é que o `backend` e o `worker` sobem e continuam rodando continuamente.

---

### Arquivo PDF recusado

- Tamanho máximo: 200 MB (configurável via `MAX_FILE_SIZE_MB` no `.env`)
- Páginas máximas: 1000 (configurável via `MAX_PAGES` no `.env`)
- O arquivo deve ter extensão `.pdf`

---

### WebSocket desconectando durante processamento longo

O timeout do WebSocket é de 5 minutos. PDFs muito grandes com OCR + refinamento IA podem ultrapassar esse limite. Atualize a página — o job continua em background e o resultado estará disponível no histórico.
