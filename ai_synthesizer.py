"""
ai_synthesizer.py — Síntese de "Projetos Executados e Impactos" via Claude API.

Gera conteúdo estruturado para o currículo a partir de:
  - Experiências profissionais (descrições ricas do LinkedIn)
  - Projetos registrados na seção /details/projects/
  - Publicações recentes (posts do perfil)
  - Competências e resumo do perfil

Organiza os impactos em três dimensões:
  1. Inteligência Artificial
  2. Agilidade & Transformação Digital
  3. Gestão de Equipes & Liderança

Requer: ANTHROPIC_API_KEY no arquivo .env
"""

import json
import logging
import os

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

MODELO_PADRAO = "claude-sonnet-4-6"

_PROMPT_SISTEMA = """\
Você é um especialista em desenvolvimento de carreira e criação de currículos executivos.
Seu papel é analisar dados brutos de um perfil LinkedIn e gerar uma seção de
"Projetos Executados e Impactos" clara, objetiva e orientada a resultados.
Responda SEMPRE com JSON válido, sem nenhum texto antes ou depois."""

_PROMPT_USUARIO = """\
Analise os dados do perfil profissional abaixo e gere uma seção estruturada de
"Projetos Executados e Impactos" para incluir no currículo.

{contexto}

## O que gerar

Produza um JSON com a seguinte estrutura exata:

{{
  "projetos": [
    {{
      "titulo": "Nome objetivo do projeto",
      "contexto": "Empresa · Período (ex: 3e Soluções · 2022–presente)",
      "descricao": "O que foi realizado em 2-3 frases ativas e mensuráveis",
      "categoria": "IA" | "Agilidade" | "Gestão de Equipes" | "Transformação Digital" | "Dados & Cloud",
      "impactos": [
        "Impacto mensurável 1 (ex: Reduziu em X% o tempo de...)",
        "Impacto mensurável 2"
      ],
      "tecnologias": ["Python", "AWS", "LLMs"]
    }}
  ],
  "resumo_impactos": {{
    "ia": "Parágrafo de 2-3 linhas sobre contribuições em IA e automação",
    "agilidade": "Parágrafo de 2-3 linhas sobre entrega ágil e transformação digital",
    "gestao_equipes": "Parágrafo de 2-3 linhas sobre liderança e desenvolvimento de times"
  }}
}}

## Regras
- Baseie-se SOMENTE nas informações fornecidas — não invente dados
- Identifique entre 4 e 10 projetos concretos executados
- Priorize projetos com impacto mensurável em IA, agilidade, equipes ou cloud
- Use verbos no passado ativo: "Implementou", "Liderou", "Reduziu", "Automatizou"
- Para impactos sem número exato, use termos como "significativamente", "em larga escala"
- Cada tecnologia deve ser um item separado no array
- Responda SOMENTE com o JSON, sem markdown, sem texto adicional"""


def sintetizar_projetos(dados_perfil: dict, modelo: str = MODELO_PADRAO) -> dict:
    """
    Chama Claude para gerar a síntese de projetos e impactos.

    Args:
        dados_perfil: dict com nome, resumo, experiencias, projetos,
                      competencias, publicacoes (de carregar_coleta())
        modelo: model ID do Claude a usar

    Returns:
        dict com keys 'projetos' (list) e 'resumo_impactos' (dict)

    Raises:
        RuntimeError: se anthropic não estiver instalado
        ValueError: se ANTHROPIC_API_KEY não estiver configurado
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "Pacote 'anthropic' não instalado.\n"
            "Execute: pip install anthropic\n"
            "Ou: pip install -r requirements.txt"
        )

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY não configurado.\n"
            "Adicione ao arquivo .env:\n"
            "  ANTHROPIC_API_KEY=sk-ant-..."
        )

    client = anthropic.Anthropic(api_key=api_key)
    contexto = _montar_contexto(dados_perfil)
    prompt = _PROMPT_USUARIO.format(contexto=contexto)

    logger.info("Chamando Claude %s para síntese de projetos...", modelo)

    message = client.messages.create(
        model=modelo,
        max_tokens=4096,
        system=_PROMPT_SISTEMA,
        messages=[{"role": "user", "content": prompt}],
    )

    texto = message.content[0].text.strip()

    # Remove possível wrapper markdown
    if "```" in texto:
        start = texto.find("{")
        end = texto.rfind("}") + 1
        texto = texto[start:end]

    resultado = json.loads(texto)
    logger.info(
        "Síntese concluída: %d projeto(s) identificado(s).",
        len(resultado.get("projetos", [])),
    )
    return resultado


def gerar_markdown_projetos(resultado: dict) -> str:
    """
    Converte o JSON de síntese em seção Markdown para o currículo.

    Organiza os projetos por categoria, com resumo executivo no topo de cada
    dimensão (IA, Agilidade, Gestão de Equipes).
    """
    linhas: list[str] = ["## Projetos Executados e Impactos", ""]

    resumo = resultado.get("resumo_impactos", {})
    projetos = resultado.get("projetos", [])

    # Mapa de categoria → label exibido + chave de resumo
    categorias = [
        ("IA",                    "Inteligência Artificial",         "ia"),
        ("Dados & Cloud",         "Dados & Cloud Engineering",       None),
        ("Agilidade",             "Agilidade & Transformação Digital","agilidade"),
        ("Transformação Digital", "Agilidade & Transformação Digital","agilidade"),
        ("Gestão de Equipes",     "Gestão de Equipes & Liderança",   "gestao_equipes"),
    ]

    # Renderiza seções agrupadas por label
    labels_renderizados: set[str] = set()

    for cat_raw, label, resumo_key in categorias:
        if label in labels_renderizados:
            continue

        # Coleta projetos deste label (pode cobrir múltiplas cat_raw)
        labels_deste = {c for c, l, _ in categorias if l == label}
        projs = [p for p in projetos if p.get("categoria", "") in labels_deste]
        if not projs:
            continue

        labels_renderizados.add(label)
        linhas += [f"### {label}", ""]

        if resumo_key and resumo_key in resumo:
            linhas += [f"_{resumo[resumo_key]}_", ""]

        for p in projs:
            linhas.append(f"#### {p['titulo']}")
            if p.get("contexto"):
                linhas.append(f"*{p['contexto']}*")
            linhas.append("")

            if p.get("descricao"):
                linhas.append(p["descricao"])
                linhas.append("")

            impactos = p.get("impactos", [])
            if impactos:
                linhas.append("**Impactos:**")
                for imp in impactos:
                    linhas.append(f"- {imp}")
                linhas.append("")

            techs = p.get("tecnologias", [])
            if techs:
                linhas.append(f"**Tecnologias:** {', '.join(techs)}")
                linhas.append("")

    # Projetos fora das categorias mapeadas
    cats_mapeadas = {c for c, _, _ in categorias}
    outros = [p for p in projetos if p.get("categoria", "") not in cats_mapeadas]
    if outros:
        linhas += ["### Outros Projetos Relevantes", ""]
        for p in outros:
            desc = p.get("descricao", "") or ""
            linhas.append(f"- **{p['titulo']}** — {desc[:180]}")
        linhas.append("")

    return "\n".join(linhas)


def _limpar_desc_heuristica(desc: str) -> str:
    """Remove artefatos de formatação bruta do LinkedIn."""
    import re
    # Remove prefixo de endereço no início ("maestro lisboa 1020 Texto real...")
    desc = re.sub(r"^\s*(?:[\w\s]{3,40})\s+\d{3,5}\s+", "", desc.strip(), flags=re.I)
    # Insere espaço em junções sem espaço: "implantaçãoAtuação" → "implantação Atuação"
    desc = re.sub(r"([a-záéíóúàâãêôõü])([A-ZÁÉÍÓÚÀÂÃÊÔÕÜ])", r"\1 \2", desc)

    linhas = []
    for l in desc.replace("•\t", "\n").replace("•", "\n").split("\n"):
        l = l.strip().lstrip("-·\t").strip()
        if not l or len(l) < 15:
            continue
        if re.match(r"^[\w\s]{3,40}\s+\d{3,5}$", l):  # linha só com endereço
            continue
        linhas.append(l)
    resultado = " ".join(linhas)
    return re.sub(r"\s+", " ", resultado).strip()


def _extrair_bullets(desc: str) -> list[str]:
    """Extrai linhas de bullet do texto bruto como impactos."""
    import re
    impactos = []
    for l in desc.replace("•\t", "\n- ").replace("•", "\n- ").split("\n"):
        l = l.strip().lstrip("-·\t").strip()
        if 30 < len(l) < 200 and not l.endswith(":"):
            # Ignora linhas que parecem endereço ou artefato
            if not re.match(r"^[\w\s]+ \d{4}$", l):
                impactos.append(l)
    return impactos[:4]


def sintetizar_projetos_heuristico(dados_perfil: dict) -> dict:
    """
    Fallback sem API: extrai projetos e classifica impactos via heurísticas
    de palavras-chave nas descrições de experiência e projetos.

    Produz o mesmo formato JSON que `sintetizar_projetos()` para que
    `gerar_markdown_projetos()` funcione identicamente.
    """
    KW_IA = {
        "ia", "llm", "llms", "machine learning", "deep learning", "agente",
        "agentes", "nlp", "inteligência artificial", "automação", "modelo",
        "modelos", "tensorflow", "pytorch", "openai", "gpt", "claude",
        "análise preditiva", "dados inteligentes", "visão computacional",
    }
    KW_AGIL = {
        "ágil", "agile", "scrum", "kanban", "sprint", "mvp", "ci/cd",
        "devops", "entrega contínua", "iteração", "deploy", "modernização",
        "transformação digital", "automação de processos", "integração",
        "pipeline", "arquitetura serverless", "cloud-native",
    }
    KW_GESTAO = {
        "liderança", "time", "equipe", "squad", "gestão", "stakeholder",
        "stakeholders", "mentoria", "treinamento", "onboarding", "avaliação",
        "multidisciplinar", "recrutamento", "desenvolvimento de pessoas",
        "alinhamento", "estratégica", "estratégico",
    }
    KW_DADOS = {
        "data engineering", "data lake", "pipeline", "etl", "spark", "pyspark",
        "big data", "aws", "azure", "cloud", "serverless", "arquitetura",
        "banco de dados", "sql", "nosql", "engenharia de dados",
    }

    def _detectar(texto: str) -> str:
        t = texto.lower()
        scores = {
            "IA":                 sum(1 for k in KW_IA if k in t),
            "Gestão de Equipes":  sum(1 for k in KW_GESTAO if k in t),
            "Dados & Cloud":      sum(1 for k in KW_DADOS if k in t),
            "Agilidade":          sum(1 for k in KW_AGIL if k in t),
        }
        melhor = max(scores, key=scores.get)
        return melhor if scores[melhor] > 0 else "Transformação Digital"

    def _extrair_impactos(desc: str) -> list[str]:
        impactos = []
        for linha in desc.replace("•\t", "\n").replace("- ", "\n").split("\n"):
            l = linha.strip().lstrip("•-·").strip()
            if 25 < len(l) < 250 and not l.endswith(":"):
                impactos.append(l)
        return impactos[:4]

    projetos_out = []

    # 1. Projetos do LinkedIn (/details/projects/)
    for p in dados_perfil.get("projetos", []):
        desc = p.get("descricao") or ""
        techs = [t.strip() for t in (p.get("tecnologias") or "").split(",") if t.strip()]
        projetos_out.append({
            "titulo":      p.get("titulo", ""),
            "contexto":    p.get("periodo") or "",
            "descricao":   desc[:400],
            "categoria":   _detectar(desc + " " + p.get("titulo", "")),
            "impactos":    _extrair_impactos(desc),
            "tecnologias": techs,
        })

    # 2. Um projeto por cargo nas experiências (com descrição rica)
    for exp in dados_perfil.get("experiencias", []):
        desc_raw = exp.get("descricao") or ""
        if len(desc_raw) < 80:
            continue
        desc     = _limpar_desc_heuristica(desc_raw)
        cargo    = exp.get("cargo", "")
        emp      = exp.get("empresa", "")
        per      = exp.get("periodo", "")
        cat      = _detectar(desc + " " + cargo)
        impactos = _extrair_impactos(desc_raw)   # usa texto bruto para detectar bullets

        projetos_out.append({
            "titulo":      f"Liderança técnica e projetos — {cargo}",
            "contexto":    f"{emp} · {per}",
            "descricao":   desc[:400],
            "categoria":   cat,
            "impactos":    impactos,
            "tecnologias": [],
        })

    # 3. Publicações como projetos (se houver)
    for pub in dados_perfil.get("publicacoes", [])[:5]:
        conteudo = pub.get("conteudo", "")
        if len(conteudo) < 100:
            continue
        cat = _detectar(conteudo)
        projetos_out.append({
            "titulo":      "Publicação — " + conteudo[:60].rstrip() + "...",
            "contexto":    "",
            "descricao":   conteudo[:350],
            "categoria":   cat,
            "impactos":    [],
            "tecnologias": [],
        })

    resumo = {
        "ia": (
            "Atuação em projetos de Inteligência Artificial e automação inteligente, "
            "incluindo sistemas multi-agente com LLMs, pipelines de dados e soluções "
            "cloud-native na AWS. Forte viés prático em aplicação de IA para ganho de eficiência operacional."
        ),
        "agilidade": (
            "Liderança de transformação digital com adoção de arquiteturas modernas "
            "(serverless, cloud-native, CI/CD), entregas iterativas e automação de "
            "processos críticos para redução de lead time e custos."
        ),
        "gestao_equipes": (
            "Mais de 10 anos de liderança de times técnicos multidisciplinares, "
            "com foco em desenvolvimento de pessoas, alinhamento estratégico com "
            "stakeholders e cultura de alta performance orientada a resultados."
        ),
    }

    return {"projetos": projetos_out, "resumo_impactos": resumo}


def _montar_contexto(dados: dict) -> str:
    """Monta o contexto do perfil em formato compacto para o prompt."""
    linhas = [
        f"## Perfil: {dados.get('nome', 'N/A')}",
        f"**Cargo atual:** {dados.get('titulo', '')}",
        f"**Localização:** {dados.get('localizacao', '')}",
        "",
        "### Resumo Profissional",
        dados.get("resumo") or "N/A",
        "",
        "### Experiências Profissionais",
    ]

    for e in dados.get("experiencias", []):
        linhas.append(f"\n**{e.get('cargo', '')}** @ {e.get('empresa', '')} ({e.get('periodo', '')})")
        desc = e.get("descricao") or ""
        if desc:
            # Limita a 600 chars para não explodir o contexto
            linhas.append(desc[:600] + ("..." if len(desc) > 600 else ""))

    projetos = dados.get("projetos", [])
    if projetos:
        linhas += ["", "### Projetos LinkedIn (/details/projects/)"]
        for p in projetos:
            linhas.append(f"\n**{p.get('titulo', '')}**")
            desc = p.get("descricao") or ""
            if desc:
                linhas.append(desc[:500] + ("..." if len(desc) > 500 else ""))
            if p.get("tecnologias"):
                linhas.append(f"Tecnologias: {p['tecnologias']}")

    comps = dados.get("competencias", [])
    if comps:
        linhas += ["", f"### Competências", ", ".join(comps)]

    pubs = dados.get("publicacoes", [])
    if pubs:
        linhas += ["", "### Publicações Recentes (posts LinkedIn)"]
        for pub in pubs[:8]:
            conteudo = pub.get("conteudo", "")[:350]
            if conteudo:
                linhas.append(f"\n---\n{conteudo}")

    return "\n".join(linhas)
