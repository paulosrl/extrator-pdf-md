Você é um engenheiro de software sênior encarregado de documentar este projeto para que outros desenvolvedores (humanos e IAs) possam entendê-lo rapidamente.

Siga este processo em ordem:

## PASSO 1 — Analise o codebase completo

Execute as seguintes explorações:

1. Liste a estrutura de pastas (2-3 níveis, ignorando node_modules, .git, __pycache__, dist, build, .venv)
2. Leia os arquivos de manifesto que existirem: `package.json`, `requirements.txt`, `pyproject.toml`, `Pipfile`, `go.mod`, `Cargo.toml`, `pom.xml`
3. Leia o `README.md` se existir
4. Leia o `.env.example` ou `.env.sample` se existir
5. Identifique o arquivo de entrada principal da aplicação (main.py, index.js, app.py, server.ts, etc.)
6. Leia os 3-5 arquivos mais centrais da aplicação (modelos, rotas, configuração)
7. Verifique se há testes e qual framework é usado
8. Verifique se há Docker, CI/CD (`.github/workflows/`, `docker-compose.yml`, `Dockerfile`)
9. Verifique o histórico recente de commits: `git log --oneline -20`
10. Verifique as branches existentes: `git branch -a`

## PASSO 2 — Gere o arquivo CLAUDE.md

Com base no que analisou, crie o arquivo `CLAUDE.md` na raiz do projeto com o seguinte conteúdo (preencha cada seção com informações reais encontradas no codebase — nunca deixe seções genéricas ou vazias):

```
# [Nome real do projeto]

## Visão geral
[2-3 frases descrevendo o que o sistema faz, para quem e qual problema resolve — inferido do README e do código]

## Stack técnica
[Liste apenas o que realmente existe no projeto]
- Linguagem:
- Framework principal:
- Banco de dados:
- Gerenciador de pacotes:
- Infraestrutura/Deploy:
- Testes:
- CI/CD:

## Estrutura de pastas
[Mapa real das pastas com descrição de cada uma]

## Arquivos-chave para entender o projeto
[Liste os 5-8 arquivos mais importantes com uma linha de descrição cada]
- `caminho/arquivo.ext` — o que faz

## Comandos do dia a dia
[Apenas comandos que realmente funcionam neste projeto]
- Iniciar em desenvolvimento:
- Rodar testes:
- Build de produção:
- Outros relevantes:

## Variáveis de ambiente necessárias
[Liste as variáveis encontradas no .env.example ou referenciadas no código]
- `VARIAVEL` — para que serve

## Convenções adotadas no projeto
[Inferidas do histórico de commits, estrutura de código e arquivos de configuração]
- Estilo de commits:
- Padrão de nomenclatura:
- Organização de arquivos:

## Fluxo de dados principal
[Descreva em 3-5 passos como os dados fluem de entrada até saída — ex: request → middleware → controller → service → banco]

## Integrações externas
[APIs, serviços de terceiros, webhooks identificados no código]

## Regras de negócio críticas
[O que a IA nunca deve alterar sem confirmação — inferido de comentários, nomes de funções críticas, validações]

## Débito técnico identificado
[TODOs, FIXMEs, comentários de atenção encontrados no código]

## O que NÃO fazer neste projeto
[Restrições inferidas da arquitetura e do código existente]
-
```

## PASSO 3 — Valide e informe

Após criar o arquivo:
1. Confirme que o `CLAUDE.md` foi salvo na raiz do projeto
2. Apresente um resumo de 3-4 linhas do que foi documentado
3. Liste qualquer seção que ficou incompleta por falta de informação no codebase e sugira o que o desenvolvedor deve preencher manualmente