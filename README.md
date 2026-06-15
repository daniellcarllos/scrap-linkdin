# LinkedIn Profile Scraper

Ferramenta Python para coletar, organizar e armazenar dados públicos de perfil LinkedIn — criada para apoiar a atualização de currículo profissional.

> **Aviso ético:** Este projeto coleta apenas dados públicos do próprio perfil do usuário, sem login, sem credenciais e sem contornar mecanismos de proteção do LinkedIn.

---

## Estrutura do projeto

```
scrap-linkdin/
├── main.py            # Ponto de entrada (CLI)
├── scraper.py         # Requisição HTTP ética ao LinkedIn
├── parser.py          # Extração de dados (HTML / TXT / PDF)
├── database.py        # Persistência SQLite
├── queries.py         # Consultas e geração de currículo
├── exemplos_sql.sql   # Consultas SQL de referência
├── requirements.txt   # Dependências Python
├── coleta.log         # Log automático de execuções
├── data/
│   └── linkedin_profile.db   # Banco SQLite (gerado automaticamente)
└── output/            # Arquivos de currículo gerados
    ├── curriculo_*.md
    ├── curriculo_*.json
    ├── curriculo_*.txt
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
```

---

## Como executar

### Opção A — Coleta direta via URL (pode ser bloqueada)

```bash
python main.py --url https://www.linkedin.com/in/danielcdasilva
```

> O LinkedIn bloqueia scraping automatizado com frequência. Se isso ocorrer, use a **Opção B**.

### Opção B — Importação de arquivo exportado manualmente (recomendada)

1. Abra seu perfil no navegador
2. Exporte em um dos formatos:

   **PDF nativo** (melhor opção):
   - Clique em "Mais" → "Salvar como PDF"
   - Salve como `perfil.pdf` na pasta do projeto

   **HTML da página**:
   - Ctrl+S (ou Cmd+S) → "Página completa"
   - Salve como `perfil.html` na pasta do projeto

   **Texto copiado**:
   - Selecione o texto do perfil (Ctrl+A), cole em um arquivo `perfil.txt`

3. Execute:

```bash
python main.py --arquivo perfil.pdf
python main.py --arquivo perfil.html
python main.py --arquivo perfil.txt
```

---

## Consultas e exportações

```bash
# Listar todas as coletas realizadas
python main.py --listar

# Gerar currículo em Markdown
python main.py --curriculo md

# Gerar currículo em JSON
python main.py --curriculo json

# Gerar currículo em texto simples
python main.py --curriculo txt

# Exportar para CSV (requer pandas)
python main.py --csv

# Comparar duas coletas (detecta mudanças no perfil)
python main.py --comparar 1 2

# Usar uma coleta específica para geração
python main.py --coleta 3 --curriculo md
```

---

## Banco de dados SQLite

O banco é criado automaticamente em `data/linkedin_profile.db`.

### Schema

| Tabela        | Descrição                                   |
|---------------|---------------------------------------------|
| `perfil`      | Dados principais do perfil (1 por coleta)   |
| `experiencias`| Histórico profissional                      |
| `formacoes`   | Formação acadêmica                          |
| `competencias`| Habilidades e skills                        |
| `certificacoes`| Certificados e licenças                    |
| `dados_brutos`| HTML/texto original e JSON extraído         |

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

**Engenheiro de Software Sênior**
📍 São Paulo, SP, Brasil
🔗 https://www.linkedin.com/in/danielcdasilva

---

## Sobre
Profissional com experiência em...

---

## Experiência Profissional

### Software Engineer
**Empresa X** · jan. 2022 – presente

...

## Competências
Python, SQL, AWS, Docker, Kubernetes
```

---

## Logs

Toda execução é registrada em `coleta.log`:

```
2025-01-15 10:32:01 [INFO] main — Acessando URL: https://...
2025-01-15 10:32:03 [INFO] database — Perfil salvo com id=1
2025-01-15 10:32:03 [INFO] database — 5 experiência(s) salva(s).
```

---

## Tratamento de erros

| Situação                   | Comportamento                                    |
|----------------------------|--------------------------------------------------|
| LinkedIn bloqueia (429/403/999) | Exibe instruções de importação manual       |
| Redirect para login         | Detectado e tratado como bloqueio               |
| Arquivo não encontrado      | Mensagem clara com o caminho esperado           |
| PDF sem pdfplumber          | Orienta instalação da dependência               |
| Banco inexistente           | Criado automaticamente na primeira execução     |
| Campos ausentes no HTML     | Armazenados como NULL, não interrompem execução |

---

## Melhorias futuras

1. **Geração de PDF** — currículo formatado com `reportlab` ou `weasyprint`
2. **Exportação DOCX** — via `python-docx`
3. **Dashboard** — interface web com Streamlit
4. **Reescrita com IA** — usar Claude API para reescrever experiências orientadas a resultados
5. **Banco vetorial** — busca semântica no histórico com `chromadb`
6. **Comparação visual** — diff colorido entre versões do perfil
7. **Agendamento** — coleta periódica automatizada
8. **Suporte a múltiplos perfis** — monitorar mais de um perfil

---

## Requisitos legais e éticos

- Apenas dados públicos, sem autenticação
- Sem contorno de CAPTCHA, Cloudflare ou outros mecanismos de proteção
- Sem coleta de dados de terceiros
- Uso exclusivamente pessoal para atualização curricular
- Respeitando os [Termos de Uso do LinkedIn](https://www.linkedin.com/legal/user-agreement)
