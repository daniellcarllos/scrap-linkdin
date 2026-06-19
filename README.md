# LinkedIn Profile Scraper

Ferramenta Python para coletar, organizar e armazenar dados do **próprio** perfil LinkedIn — com parser robusto para a SPA do LinkedIn e síntese automática por IA de "Projetos Executados e Impactos" para apoiar a atualização de currículo profissional.

> **Aviso ético:** Este projeto coleta apenas dados do próprio perfil do usuário, autenticado com as próprias credenciais, sem contornar CAPTCHA ou outros mecanismos de proteção do LinkedIn. Uso exclusivamente pessoal.

---

## Funcionalidades

- **Coleta via navegador (Playwright)** — login automático ou interativo, sessão salva entre execuções
- **Parser robusto para SPA React** — extrai dados de `inner_text`, já que o LinkedIn não expõe HTML estável
- **Seções coletadas:** Experiência, Formação, Competências, Certificações, Projetos e Publicações recentes
- **Banco SQLite com histórico** — cada coleta é versionada; permite comparar mudanças do perfil ao longo do tempo
- **Síntese de "Projetos Executados e Impactos" por IA** — usa Claude (`claude-sonnet-4-6`) para gerar uma seção de currículo organizada por **Inteligência Artificial · Agilidade · Gestão de Equipes**, com fallback heurístico (sem API key) por palavras-chave
- **Geração de currículo** em Markdown, JSON e TXT
- **Exportação CSV** via pandas

---

## Estrutura do projeto

```
scrap-linkdin/
├── main.py              # Ponto de entrada (CLI)
├── scraper.py           # Requisição HTTP simples (fallback, sem login)
├── scraper_browser.py   # Coleta via Playwright (login + navegação de sub-páginas)
├── parser.py            # Extração de dados do inner_text do LinkedIn (SPA)
├── ai_synthesizer.py     # Síntese de Projetos Executados via Claude API / heurística
├── database.py          # Persistência SQLite
├── queries.py            # Consultas e geração de currículo
├── exemplos_sql.sql      # Consultas SQL de referência
├── requirements.txt      # Dependências Python
├── .env                  # Credenciais (NUNCA commitado — está no .gitignore)
├── coleta.log             # Log automático de execuções
├── data/
│   ├── linkedin_profile.db     # Banco SQLite (gerado automaticamente)
│   └── sessao_linkedin/         # Sessão de login do navegador (persistida)
└── output/                # Currículos e sínteses gerados
    ├── curriculo_*.md
    ├── curriculo_*.json
    ├── curriculo_*.txt
    ├── projetos_*.md       # Seção de Projetos Executados isolada
    └── experiencias_*.csv
```

---

## Instalação

```bash
# 1. Clone ou copie o projeto
cd scrap-linkdin

# 2. Crie um ambiente virtual (recomendado)
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Instale o navegador do Playwright
playwright install chromium
```

### Configuração do `.env`

Crie um arquivo `.env` na raiz do projeto:

```env
LINKEDIN_EMAIL=seu-email@exemplo.com
LINKEDIN_PASSWORD=sua-senha

# Opcional — ativa síntese de projetos via Claude AI (em vez do modo heurístico)
ANTHROPIC_API_KEY=sk-ant-...
```

> O `.env` está no `.gitignore` e nunca deve ser commitado. Senhas nunca aparecem nos logs (são mascaradas como `***`).

---

## Como executar

### Coleta completa via navegador (recomendada)

Faz login automático com as credenciais do `.env`, navega pelas sub-páginas do perfil (`/details/experience/`, `/details/skills/`, `/details/certifications/`, `/details/projects/`, `/recent-activity/all/`) e salva tudo no banco.

```bash
python main.py --url https://www.linkedin.com/in/seu-usuario --login
```

```bash
# Login visível (acompanhar o processo no navegador)
python main.py --url https://www.linkedin.com/in/seu-usuario --login --visivel
```

A sessão de login é salva em `data/sessao_linkedin/` — execuções futuras reaproveitam a sessão sem precisar logar de novo.

### Login interativo (primeira execução / 2FA)

Abre o navegador para você logar manualmente (útil se houver verificação em duas etapas):

```bash
python main.py --url https://www.linkedin.com/in/seu-usuario --interativo
```

### Importação de arquivo exportado manualmente (sem navegador)

```bash
python main.py --arquivo perfil.pdf
python main.py --arquivo perfil.html
python main.py --arquivo perfil.txt
```

---

## Síntese de Projetos Executados e Impactos (IA)

Gera uma seção de currículo a partir de experiências, projetos e publicações, organizada em três dimensões: **Inteligência Artificial**, **Agilidade**, **Gestão de Equipes**.

```bash
python main.py --projetos --coleta <id>
```

- Se `ANTHROPIC_API_KEY` estiver definido no `.env`, usa o Claude para gerar descrições e impactos mensuráveis.
- Caso contrário, usa um classificador heurístico por palavras-chave (sem custo de API).

A síntese é salva no banco e incluída **automaticamente** na próxima geração de currículo (`--curriculo md`).

---

## Consultas e exportações

```bash
# Listar todas as coletas realizadas
python main.py --listar

# Gerar currículo em Markdown (inclui seção de Projetos se houver síntese salva)
python main.py --curriculo md

# Gerar currículo em JSON
python main.py --curriculo json

# Gerar currículo em texto simples
python main.py --curriculo txt

# Exportar para CSV (requer pandas)
python main.py --csv

# Comparar duas coletas (detecta mudanças no perfil)
python main.py --comparar 1 2

# Usar uma coleta específica para qualquer operação
python main.py --coleta 3 --curriculo md
```

---

## Banco de dados SQLite

O banco é criado automaticamente em `data/linkedin_profile.db`.

### Schema

| Tabela          | Descrição                                          |
|-----------------|-----------------------------------------------------|
| `perfil`        | Dados principais do perfil (1 registro por coleta)  |
| `experiencias`  | Histórico profissional                              |
| `formacoes`     | Formação acadêmica                                  |
| `competencias`  | Habilidades e skills                                |
| `certificacoes` | Certificados e licenças                             |
| `projetos`      | Projetos registrados em `/details/projects/`        |
| `publicacoes`   | Posts recentes do perfil (`/recent-activity/all/`)  |
| `projetos_ia`   | Sínteses geradas (JSON + Markdown) por coleta       |
| `dados_brutos`  | Texto bruto original e JSON extraído                |

### Consultar diretamente

```bash
sqlite3 data/linkedin_profile.db

# No prompt do SQLite:
.tables
.mode column
.headers on
SELECT nome, titulo, data_coleta FROM perfil;
```

Veja mais exemplos em [`exemplos_sql.sql`](exemplos_sql.sql).

---

## Exemplo de saída — currículo Markdown

```markdown
# Daniel Carlos da Silva

**Gerente de Tecnologia | Liderança de Times | Cloud & Data**
📍 Fortaleza, Ceará, Brasil
🔗 https://www.linkedin.com/in/danielcdasilva

---

## Sobre
Profissional com experiência em...

---

## Experiência Profissional

### Gerente de Tecnologia | Data & Cloud Engineering Manager
**3e Soluções** · jun de 2022 - o momento

...

## Competências
Python, AWS, Django, Scrum, ...

---

## Projetos Executados e Impactos

### Inteligência Artificial

#### Sistema Multi-Agente de IA para Análise de Licitações
Desenvolvimento de uma solução baseada em agentes inteligentes para...

**Impactos:**
- Redução de esforço manual na triagem de oportunidades
- Maior padronização na avaliação e tomada de decisão

**Tecnologias:** Python, LLMs, AWS, agentes autônomos
```

---

## Logs

Toda execução é registrada em `coleta.log`:

```
2026-06-15 17:45:39 [INFO] scraper_browser — Capturando Experiência: https://...
2026-06-15 17:46:10 [INFO] database — Perfil salvo com id=6
2026-06-15 17:46:10 [INFO] database — 4 formação(ões) salva(s).
2026-06-15 17:46:10 [INFO] database — 22 publicação(ões) salva(s).
```

---

## Tratamento de erros

| Situação                          | Comportamento                                      |
|------------------------------------|-----------------------------------------------------|
| LinkedIn bloqueia / pede CAPTCHA   | Use `--interativo` para resolver manualmente uma vez|
| Credenciais ausentes/placeholder   | `_credenciais()` levanta `ValueError` antes do login|
| Sessão expirada                    | Detectada automaticamente; refaz login              |
| Arquivo não encontrado             | Mensagem clara com o caminho esperado               |
| PDF sem pdfplumber                 | Orienta instalação da dependência                    |
| `ANTHROPIC_API_KEY` ausente        | `--projetos` usa modo heurístico automaticamente     |
| Banco inexistente                  | Criado automaticamente na primeira execução          |
| Mudança de layout do LinkedIn      | Parser isola heurísticas por seção; ajustes pontuais  |

---

## Melhorias futuras

1. **Geração de PDF** — currículo formatado com `reportlab` ou `weasyprint`
2. **Exportação DOCX** — via `python-docx`
3. **Dashboard** — interface web com Streamlit
4. **Banco vetorial** — busca semântica no histórico com `chromadb`
5. **Comparação visual** — diff colorido entre versões do perfil
6. **Agendamento** — coleta periódica automatizada
7. **Suporte a múltiplos perfis** — monitorar mais de um perfil

---

## Requisitos legais e éticos

- Apenas o próprio perfil, autenticado com as próprias credenciais
- Sem contorno de CAPTCHA, Cloudflare ou outros mecanismos de proteção
- Sem coleta de dados de terceiros
- Uso exclusivamente pessoal para atualização curricular
- Respeitando os [Termos de Uso do LinkedIn](https://www.linkedin.com/legal/user-agreement)
