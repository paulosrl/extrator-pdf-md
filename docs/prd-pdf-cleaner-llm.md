# PRD: PDF Cleaner for LLM

**Status:** Rascunho  
**Data:** 2026-03-28

---

## 1. Contexto e Problema

Usuários de IA que anexam PDFs diretamente em prompts ou pipelines RAG enfrentam três problemas concretos: (1) consumo excessivo de tokens com conteúdo inútil (cabeçalhos, rodapés, numeração de páginas, metadados), (2) perda de contexto útil porque janelas de contexto são preenchidas com ruído, e (3) perda de informação relevante em imagens embutidas no PDF que LLMs baseados em texto simplesmente ignoram.

PDFs de documentos técnicos, relatórios jurídicos e acadêmicos podem ter até 40–60% do conteúdo total composto por elementos estruturais não-semânticos. Em um documento de 1000 páginas processado com GPT-4o, isso representa potencialmente dezenas de milhares de tokens desperdiçados por chamada.

A solução proposta é um pipeline automatizado que recebe o PDF bruto, realiza OCR se necessário, extrai conteúdo semântico útil (incluindo texto de imagens), e entrega um arquivo `.md` limpo e otimizado para consumo por LLMs — com relatório de redução de tokens.

---

## 2. Usuários-Alvo

| Persona | Perfil | Necessidade |
|---------|--------|-------------|
| Desenvolvedor RAG | Engenheiro que alimenta bases vetoriais com PDFs | Reduzir ruído no chunking e embedding |
| Pesquisador/Analista | Usuário que anexa PDFs em prompts de LLMs | Economizar tokens e melhorar respostas |
| Operador jurídico/técnico | Profissional com PDFs extensos (laudos, relatórios) | Extrair conteúdo sem perder informação |
| Desenvolvedor de agentes | Cria pipelines automatizados com PDFs | Input limpo e padronizado para agentes |

---

## 3. Requisitos Funcionais

### 3.1 Upload e Validação

- **RF-01:** O sistema deve aceitar upload de arquivos PDF via interface web, com tamanho máximo de 200 MB e até 1000 páginas.
- **RF-02:** O sistema deve rejeitar arquivos não-PDF com mensagem de erro descritiva antes de iniciar processamento.
- **RF-03:** O sistema deve exibir barra de progresso em tempo real durante todo o pipeline de processamento.

### 3.2 Detecção e OCR

- **RF-04:** O sistema deve detectar automaticamente se o PDF contém camada de texto (texto selecionável) ou é imagem escaneada.
- **RF-05:** Se o PDF não tiver camada de texto em qualquer página, o sistema deve executar OCR via `pytesseract` com suporte a português e inglês.
- **RF-06:** O sistema deve concluir e validar o OCR com sucesso antes de prosseguir para extração — se OCR falhar, o pipeline para e retorna erro com detalhes da página problemática.
- **RF-07:** PDFs mistos (algumas páginas com texto, outras escaneadas) devem ter OCR aplicado apenas nas páginas sem camada de texto.

### 3.3 Extração de Conteúdo Útil

- **RF-08:** O sistema deve remover automaticamente: numeração de páginas, cabeçalhos repetitivos, rodapés repetitivos, metadados de documento, marcas d'água textuais.
- **RF-09:** O sistema deve identificar e extrair imagens embutidas no PDF e aplicar OCR/visão computacional para extrair texto dessas imagens.
- **RF-10:** O texto extraído de imagens deve ser inserido no `.md` final na posição correspondente à sua localização original no documento (inline, não em apêndice).
- **RF-11:** O sistema deve preservar a hierarquia de títulos e seções identificada no documento original, mapeando para headings Markdown (`#`, `##`, `###`).
- **RF-12:** Tabelas identificadas no PDF devem ser convertidas para formato Markdown de tabela.

### 3.4 Saída e Relatório

- **RF-13:** O sistema deve gerar um arquivo `.md` com o conteúdo limpo, disponível para download imediato após processamento.
- **RF-14:** O sistema deve exibir relatório estatístico ao final contendo:
  - Total de tokens estimados no arquivo original (usando `tiktoken`, modelo `cl100k_base`)
  - Total de tokens estimados no arquivo `.md` gerado
  - Percentual de redução: `"Você economizou XX% de tokens"`
  - Número de páginas processadas / com OCR / com imagens extraídas
- **RF-15:** O sistema deve armazenar o histórico de processamentos por usuário no banco de dados, com metadados do job.

### 3.5 Interface Web (V1)

- **RF-16:** A interface deve ter uma única tela com: área de upload drag-and-drop, botão de processamento, progresso em tempo real via WebSocket, e painel de resultado com download e estatísticas.
- **RF-17:** O sistema deve suportar processamento assíncrono — o usuário pode fechar a aba e retornar; o job continua e o resultado fica disponível no histórico.

---

## 4. Arquitetura e Stack

```
[Browser]
    │ HTTP upload (multipart)
    ▼
[FastAPI — Web Server]
    │ Enfileira job
    ▼
[Celery Worker]
    ├─ Detecta texto → pytesseract (OCR se necessário)
    ├─ Extrai conteúdo útil → pdfplumber + lógica de filtragem
    ├─ Extrai imagens → pdf2image → pytesseract / vision
    ├─ Gera .md limpo
    └─ Calcula tokens → tiktoken
    │ Persiste resultado
    ▼
[PostgreSQL + pgvector]
    │ (jobs, documentos, estatísticas; pgvector reservado para V2)
    
[Redis] — broker do Celery + cache de progresso

[MinIO ou volume Docker] — armazenamento dos arquivos PDF e .md gerados
```

**Decisões técnicas:**

| Decisão | Razão |
|---------|-------|
| FastAPI | Async nativo, suporte a WebSocket para progresso em tempo real |
| Celery + Redis | Jobs longos (OCR de 1000 páginas) não podem bloquear HTTP request |
| pdfplumber | Melhor extração estrutural (tabelas, layout) vs PyMuPDF para textos simples |
| pytesseract + Tesseract | OCR local, sem custo por chamada, LGPD-safe |
| tiktoken `cl100k_base` | Compatível com GPT-4/Claude; estimativa confiável de tokens |
| pgvector | Já no stack; preparado para V2 (busca semântica sobre documentos processados) |
| Docker Compose | Ubuntu + todos os serviços isolados, reproducível |

⚠️ Assumido: extração de texto de imagens usa `pytesseract` (OCR). Se qualidade for insuficiente para imagens complexas (diagramas, gráficos), V2 avalia integração com modelo de visão (ex: GPT-4o Vision ou LLaVA local).

---

## 5. Modelo de Dados

### Entidade `users`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | UUID PK | |
| `email` | VARCHAR(255) UNIQUE | |
| `created_at` | TIMESTAMPTZ | |

### Entidade `processing_jobs`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | UUID PK | |
| `user_id` | UUID FK → users | |
| `status` | ENUM(`queued`, `ocr`, `extracting`, `done`, `error`) | Estado atual do pipeline |
| `original_filename` | VARCHAR(500) | |
| `original_storage_path` | TEXT | Caminho no volume/MinIO |
| `output_storage_path` | TEXT | Caminho do .md gerado; NULL até conclusão |
| `pages_total` | INTEGER | |
| `pages_ocr` | INTEGER | Páginas que passaram por OCR |
| `pages_with_images` | INTEGER | |
| `tokens_original` | INTEGER | Estimativa tiktoken do PDF bruto |
| `tokens_output` | INTEGER | Estimativa tiktoken do .md gerado |
| `reduction_pct` | NUMERIC(5,2) | Percentual de redução de tokens |
| `error_message` | TEXT | NULL se sucesso |
| `created_at` | TIMESTAMPTZ | |
| `completed_at` | TIMESTAMPTZ | |

---

## 6. Fluxos Principais

### 6.1 Pipeline de Processamento

```
UPLOAD recebido → valida extensão e tamanho
  → ERRO: retorna 400 com mensagem
  → OK: salva arquivo no storage, cria job (status=queued), retorna job_id

WORKER pega job
  → status = "ocr"
  → detecta páginas sem camada de texto
      → tem páginas sem texto: executa pytesseract por página
          → OCR falha em página X: job.status = "error", job.error_message = "OCR falhou na página X: [detalhe]" — PARA
          → OCR OK em todas: continua
      → todas com texto: pula OCR
  → status = "extracting"
  → pdfplumber: extrai blocos de texto por página
  → aplica filtros de remoção (cabeçalhos, rodapés, números de página)
      → heurística: bloco que aparece em ≥ 80% das páginas na mesma posição → remove
  → extrai imagens embutidas
      → para cada imagem: pytesseract → texto; insere no .md na posição relativa
  → converte tabelas para Markdown
  → monta .md final com hierarquia de headings
  → calcula tokens (tiktoken) do PDF original e do .md
  → salva .md no storage, atualiza job (status=done, métricas)

FRONTEND polling / WebSocket recebe status updates → exibe progresso
→ status=done: exibe botão download + painel estatístico
```

### 6.2 Máquina de Estados do Job

```
queued → ocr → extracting → done
                           → error (em qualquer etapa)
```

---

## 7. Requisitos Não-Funcionais

| Atributo | Requisito |
|----------|-----------|
| Throughput de OCR | ≥ 10 páginas/minuto por worker (Tesseract padrão em CPU) |
| Latência resposta upload | ≤ 500ms para aceitar o job (processamento é async) |
| Tamanho máximo de arquivo | 200 MB por upload |
| Disponibilidade | 99% uptime (single node, sem HA em V1) |
| Segurança | Autenticação JWT (expiração 24h); arquivos isolados por user_id no storage |
| Privacidade | Processamento 100% local (sem chamadas a APIs externas em V1); LGPD-safe |
| Persistência de resultados | Arquivos gerados retidos por 7 dias; após isso, deletados automaticamente |
| Ambiente | Ubuntu 22.04 LTS, Docker Compose, sem dependência de GPU em V1 |

---

## 8. Critérios de Aceite

- [ ] Dado um PDF de 50 páginas com texto, quando processado, o .md gerado não contém numeração de páginas nem cabeçalhos/rodapés repetitivos.
- [ ] Dado um PDF escaneado (sem camada de texto), quando enviado, o OCR é executado e o .md final contém o texto extraído com ≥ 90% de fidelidade visual.
- [ ] Dado um PDF misto (30 páginas texto + 20 escaneadas), somente as 20 escaneadas passam por OCR; as demais são extraídas diretamente.
- [ ] Dado um PDF com imagens contendo texto, o conteúdo dessas imagens aparece no .md na posição correspondente.
- [ ] Dado um PDF de 1000 páginas, o job é enfileirado e processado sem timeout HTTP; o usuário pode acompanhar o progresso em tempo real.
- [ ] Ao final de qualquer processamento bem-sucedido, o relatório exibe: tokens originais, tokens do .md, e percentual de redução calculado corretamente.
- [ ] Se o OCR falhar em qualquer página, o job retorna status `error` com identificação da página problemática; nenhum arquivo parcial é entregue.
- [ ] O sistema rejeita arquivos não-PDF com mensagem de erro antes de qualquer processamento.

---

## 9. Métricas de Sucesso

| Métrica | Baseline atual | Meta | Fonte |
|---------|---------------|------|-------|
| Redução média de tokens | — (produto novo) | ≥ 30% de redução vs PDF bruto | Logs de jobs processados |
| Taxa de sucesso de jobs | — | ≥ 95% dos uploads concluídos sem erro | Tabela `processing_jobs` |
| Tempo médio de processamento (100 páginas texto) | — | ≤ 5 minutos | Logs Celery |
| Tempo médio de OCR (100 páginas escaneadas) | — | ≤ 15 minutos | Logs Celery |
| Adoção | 0 usuários | 20 usuários ativos em 60 dias pós-lançamento | Tabela `users` |

---

## 10. Fora do Escopo (V1)

- **Integração com Telegram** — será V2; requer camada de bot + fluxo conversacional de upload.
- **Busca semântica sobre documentos processados** — pgvector está no stack mas não será usado em V1; chunking + embedding = V2.
- **Suporte a outros formatos** (DOCX, HTML, EPUB) — apenas PDF em V1.
- **Processamento em GPU** (OCR acelerado, modelos de visão locais) — V1 roda 100% em CPU.
- **Multi-tenancy / planos pagos** — estrutura de `users` existe mas sem billing em V1.
- **Remoção inteligente de figuras decorativas** (logos, ícones) vs figuras com conteúdo — heurística simples em V1; modelo de classificação de imagens = V2.
- **API REST pública** para integração direta por desenvolvedores — V2.
