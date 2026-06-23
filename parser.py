"""
parser.py — Extração e normalização de dados de perfil LinkedIn.

Suporta três fontes:
  - HTML bruto (de scraping direto ou arquivo .html exportado)
  - Texto puro (.txt exportado do navegador)
  - PDF (.pdf exportado do LinkedIn)
"""

import re
import json
import logging
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Utilitários de normalização de texto
# ──────────────────────────────────────────────

def _limpar(texto: Optional[str]) -> Optional[str]:
    if not texto:
        return None
    return re.sub(r"\s+", " ", texto).strip()


def _extrair_periodo(texto: str) -> str:
    """Tenta isolar padrões de período dentro de uma string."""
    padrao = r"(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\.?\s+\d{4}"
    matches = re.findall(padrao, texto, re.IGNORECASE)
    if len(matches) >= 2:
        return f"{matches[0]} – {matches[-1]}"
    if len(matches) == 1:
        return f"{matches[0]} – presente"
    # fallback: anos soltos (grupo não-capturante para retornar os 4 dígitos)
    anos = re.findall(r"\b(?:19|20)\d{2}\b", texto)
    if anos:
        return " – ".join(dict.fromkeys(anos))
    return texto.strip()


# ──────────────────────────────────────────────
# Parser HTML (scraping direto ou arquivo .html)
# ──────────────────────────────────────────────

def _texto(tag) -> Optional[str]:
    return _limpar(tag.get_text(" ", strip=True)) if tag else None


def parsear_html(html: str, url: str = "") -> dict:
    """
    Extrai dados de perfil a partir de HTML do LinkedIn.

    Estratégias em ordem de prioridade:
      1. Texto limpo injetado pelo scraper_browser (inner_text do React)
      2. JSON-LD embutido na página
      3. Meta tags Open Graph
      4. Seletores CSS (versão pública estática)
    """
    # ── 0. Texto limpo do React SPA (injetado pelo scraper_browser) ──
    if "<!-- LINKEDIN_INNER_TEXT_START -->" in html:
        inicio = html.index("<linkedin-text>") + len("<linkedin-text>")
        fim    = html.index("</linkedin-text>")
        texto_limpo = html[inicio:fim].strip()
        logger.info("Usando inner_text do browser (%d chars).", len(texto_limpo))
        dados = _parse_inner_text_linkedin(texto_limpo, url=url)
        # Garante listas
        for chave in ("experiencias", "formacoes", "competencias", "certificacoes"):
            dados.setdefault(chave, [])
        return dados

    soup = BeautifulSoup(html, "lxml")
    dados: dict = {"url": url}

    # ── 1. JSON-LD (perfil público sem JS) ──────────────────────────
    json_ld = _extrair_json_ld(soup)
    if json_ld:
        dados.update(_parse_json_ld(json_ld))

    # ── 2. Meta tags Open Graph (fallback leve) ──────────────────────
    if not dados.get("nome"):
        og_title = soup.find("meta", property="og:title")
        if og_title:
            dados["nome"] = _limpar(og_title.get("content", ""))

    if not dados.get("resumo"):
        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            dados["resumo"] = _limpar(og_desc.get("content", ""))

    # ── 3. Seletores CSS da versão pública estática ───────────────────
    _parse_seletores_css(soup, dados)

    # ── 4. Garantia de listas ─────────────────────────────────────────
    for chave in ("experiencias", "formacoes", "competencias", "certificacoes"):
        dados.setdefault(chave, [])

    return dados


def _extrair_json_ld(soup: BeautifulSoup) -> Optional[dict]:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            obj = json.loads(tag.string or "")
            if isinstance(obj, dict) and obj.get("@type") == "Person":
                return obj
            if isinstance(obj, list):
                for item in obj:
                    if isinstance(item, dict) and item.get("@type") == "Person":
                        return item
        except (json.JSONDecodeError, AttributeError):
            continue
    return None


def _parse_json_ld(obj: dict) -> dict:
    dados: dict = {}
    dados["nome"] = _limpar(obj.get("name"))
    dados["titulo"] = _limpar(obj.get("jobTitle"))
    dados["localizacao"] = _limpar(
        obj.get("address", {}).get("addressLocality")
        if isinstance(obj.get("address"), dict)
        else None
    )
    dados["resumo"] = _limpar(obj.get("description"))

    experiencias = []
    for item in obj.get("worksFor", []):
        if isinstance(item, dict):
            experiencias.append({
                "cargo":    _limpar(item.get("roleName")),
                "empresa":  _limpar(item.get("name")),
                "periodo":  _limpar(item.get("startDate", "")),
                "descricao": None,
            })
    dados["experiencias"] = experiencias

    formacoes = []
    for item in obj.get("alumniOf", []):
        if isinstance(item, dict):
            formacoes.append({
                "instituicao": _limpar(item.get("name")),
                "curso":       _limpar(item.get("description")),
                "periodo":     None,
                "descricao":   None,
            })
    dados["formacoes"] = formacoes

    dados["competencias"] = [
        _limpar(k) for k in obj.get("knowsAbout", []) if k
    ]
    return dados


def _parse_inner_text_linkedin(texto: str, url: str = "") -> dict:
    """
    Processa o texto anotado gerado pelo scraper_browser.

    Formato esperado:
      [CABECALHO]
      ... texto do cabeçalho do perfil ...

      [SECAO:EXPERIÊNCIA]
      ... texto da sub-página /details/experience/ ...

      [SECAO:FORMAÇÃO]
      ...
    """
    dados: dict = {"url": url, "experiencias": [], "formacoes": [],
                   "competencias": [], "certificacoes": [], "artigos": []}

    # Divide pelas marcações de seção linha a linha (sem regex split)
    blocos: dict = {}
    secao_atual = "cabecalho"
    buffer: list = []

    for linha in texto.splitlines():
        stripped = linha.strip()
        if stripped == "[CABECALHO]":
            if buffer:
                blocos[secao_atual] = "\n".join(buffer)
            secao_atual = "cabecalho"
            buffer = []
        elif stripped.startswith("[SECAO:") and stripped.endswith("]"):
            if buffer:
                blocos[secao_atual] = "\n".join(buffer)
            secao_atual = stripped[7:-1].lower()  # "[SECAO:EXPERIÊNCIA]" → "experiência"
            buffer = []
        else:
            buffer.append(linha)

    if buffer:
        blocos[secao_atual] = "\n".join(buffer)

    # ── Cabeçalho: nome, título, localização, resumo ──────────────────
    if "cabecalho" in blocos:
        _extrair_cabecalho(blocos["cabecalho"], dados)

    # ── Experiências ──────────────────────────────────────────────────
    for chave in ("experiência", "experiencia"):
        if chave in blocos:
            linhas = _linhas_uteis(blocos[chave])
            dados["experiencias"] = _parse_experiencias_inner_text(linhas)
            break

    # ── Formação ──────────────────────────────────────────────────────
    for chave in ("formação", "formacao"):
        if chave in blocos:
            linhas = _linhas_uteis(blocos[chave])
            dados["formacoes"] = _parse_formacoes_inner_text(linhas)
            break

    # ── Competências ──────────────────────────────────────────────────
    for chave in ("competências", "competencias"):
        if chave in blocos:
            linhas = _linhas_uteis(blocos[chave])
            dados["competencias"] = _parse_competencias_inner_text(linhas)
            break

    # ── Certificações ─────────────────────────────────────────────────
    for chave in ("certificações", "certificacoes"):
        if chave in blocos:
            linhas = _linhas_uteis(blocos[chave])
            dados["certificacoes"] = _parse_certificacoes_inner_text(linhas)
            break

    # ── Projetos ──────────────────────────────────────────────────────
    if "projetos" in blocos:
        linhas = _linhas_uteis(blocos["projetos"])
        dados["projetos"] = _parse_projetos_inner_text(linhas)

    # ── Publicações ───────────────────────────────────────────────────
    for chave in ("publicações", "publicacoes", "atividade recente"):
        if chave in blocos:
            linhas = _linhas_uteis(blocos[chave])
            dados["publicacoes"] = _parse_publicacoes_inner_text(linhas)
            break

    # ── Artigos ───────────────────────────────────────────────────────
    for chave in ("artigos", "articles"):
        if chave in blocos:
            linhas = _linhas_uteis(blocos[chave])
            dados["artigos"] = _parse_artigos_inner_text(linhas)
            break

    # ── Pós-processamento: remove endorsers de competências ───────────
    # LinkedIn exibe cert/instituição como "endorser" de cada skill;
    # esses nomes aparecem como linhas soltas na seção de competências.
    _filtrar_endorsers_competencias(dados)

    return dados


def _filtrar_endorsers_competencias(dados: dict) -> None:
    """Remove nomes de certs e instituições que aparecem como endorsers de skills."""
    exclusoes: set[str] = set()
    for c in dados.get("certificacoes", []):
        if c.get("nome"):
            exclusoes.add(c["nome"].lower())
    for f in dados.get("formacoes", []):
        if f.get("instituicao"):
            exclusoes.add(f["instituicao"].lower())
    dados["competencias"] = [
        c for c in dados.get("competencias", [])
        if c.lower() not in exclusoes
    ]


def _linhas_uteis(texto: str) -> list[str]:
    """Retorna linhas não-vazias de um bloco de texto."""
    return [l.strip() for l in texto.splitlines() if l.strip()]


def _extrair_cabecalho(texto: str, dados: dict) -> None:
    """Extrai nome, título, localização e resumo do bloco de cabeçalho."""
    linhas = _linhas_uteis(texto)

    # Remove tokens de navegação do início
    nav = {"início", "minha rede", "vagas", "mensagens", "notificações",
           "para negócios", "learning", "publicar", "eu", "pular para pesquisa",
           "pular para conteúdo principal", "skip to conteúdo principal",
           "skip to à parte", "skip to rodapé", "0 notificação"}
    # Remove nav e dígitos intercalados em loop único
    while linhas and (linhas[0].lower() in nav or linhas[0].isdigit() or linhas[0] == "·"):
        linhas.pop(0)

    if not linhas:
        return

    dados["nome"]   = linhas[0] if len(linhas) > 0 else None
    dados["titulo"] = linhas[1] if len(linhas) > 1 else None

    # Localização: linha curta com vírgula ou estado brasileiro
    for linha in linhas[2:10]:
        if any(c in linha for c in [", ", "Brasil", "Brazil"]) and len(linha) < 60:
            dados["localizacao"] = linha
            break

    # Sobre: seção marcada por "Sobre" no próprio cabeçalho
    try:
        idx_sobre = next(i for i, l in enumerate(linhas) if l.strip().lower() == "sobre")
        linhas_sobre = []
        for l in linhas[idx_sobre + 1:]:
            if l.lower() in ("ver mais", "ver menos", "… mais", "mostrar mais"):
                break
            if l.startswith("Principais") or l.startswith("Em destaque"):
                break
            linhas_sobre.append(l)
        if linhas_sobre:
            dados["resumo"] = " ".join(linhas_sobre).strip()
    except StopIteration:
        pass


# Tokens de UI do LinkedIn que devem ser ignorados nos blocos de seção
_UI_TOKENS = {
    "ver mais", "ver menos", "mostrar mais", "mostrar menos",
    "adicionar", "editar", "meses", "seguir", "conectar",
    "disponível para", "aberto para", "em tempo integral",
}

_REGEX_PERIODO = re.compile(
    # "jan de 2022", "jan. 2022", "jan 2022" (com ou sem "de")
    r"(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\.?\s+(?:de\s+)?\d{4}"
    r"|\d{4}\s*[-–]\s*\d{4}"
    r"|\d{4}\s*[-–]\s*(presente|atual|o momento)",
    re.I,
)


def _e_periodo(linha: str) -> bool:
    """Retorna True se a linha parece ser um período de tempo."""
    return bool(_REGEX_PERIODO.search(linha)) or "presente" in linha.lower()


def _e_vinculo_com_duracao(linha: str) -> bool:
    """Detecta 'Tempo integral · 11 a 5 m' — formato LinkedIn compacto (nov/2025+).

    O LinkedIn passou a combinar tipo de vínculo + duração abreviada em uma linha só,
    separados por '·'. Exemplos: 'Tempo integral · 11 a 5 m', 'Estágio · 6 m'.
    """
    return bool(re.match(
        r"^(tempo integral|meio período|freelance|autônomo|contrato|"
        r"temporário|estágio|aprendiz|voluntário)"
        r"\s*·\s*\d+\s*(a|ano|anos)(\s*\d+\s*(m|mês|meses))?\s*$",
        linha, re.I | re.UNICODE,
    ))


def _e_duracao(linha: str) -> bool:
    """Retorna True se a linha é APENAS uma duração ('2 anos', '11 anos 5 meses')."""
    return bool(re.match(
        r"^\d+\s*(ano|anos|mês|meses|mes)(\s+\d+\s*(mês|meses|ano|anos))?\.?\s*$",
        linha, re.I,
    ))


def _parse_experiencias_inner_text(linhas: list[str]) -> list[dict]:
    """
    Analisa o bloco da sub-página /details/experience/ do LinkedIn.

    Estrutura real observada (LinkedIn 2024/2025):
      [nav e nome — já removidos]
      Experiência                          ← marcador de seção (skip)
      3e Soluções                          ← empresa
      11 anos 5 meses                      ← duração total na empresa (skip)
      Gerente de Tecnologia | Data & ...   ← cargo 1
      Tempo integral                       ← tipo (skip)
      jun de 2022 - o momento · 4 anos...  ← período cargo 1
      Fortaleza, Ceará, Brasil · No local  ← localização (skip)
      Aprimorar com IA                     ← UI (skip)
      [descrição...]
      Competências: Django, ...            ← competências do cargo (skip)
      Analista de TI senior               ← cargo 2 (mesma empresa)
      Tempo integral                       ← tipo (skip)
      out de 2019 - jun de 2022 · ...      ← período cargo 2
      [descrição...]
      Competências: ...                    ← skip
      [nova empresa...]
    """
    experiencias = []
    TIPOS_VINCULO = {"tempo integral", "meio período", "freelance", "autônomo",
                     "contrato", "temporário", "estágio", "aprendiz", "voluntário",
                     "aprimorar com ia", "no local", "híbrido", "remoto", "presencial"}
    SKIP_PREFIXOS = ("competências:", "skills:", "atividades e grupos:", "… mais",
                     "mostrar mais", "mostrar menos", "ver mais", "ver menos", "·")
    FOOTER_TOKENS = {"idioma do perfil", "sobre", "acessibilidade", "linkedin corporation"}

    # Pula nav/nome (até o marcador "Experiência")
    i = 0
    while i < len(linhas) and linhas[i].lower() not in ("experiência", "experiencias", "experience"):
        i += 1
    i += 1  # pula o próprio marcador "Experiência"

    empresa_atual = None

    while i < len(linhas):
        linha = linhas[i]
        linha_lower = linha.lower()

        # Fim da seção
        if linha_lower in FOOTER_TOKENS:
            break

        # Skip: linha vazia, UI, tipos de vínculo, prefixos de skip,
        # ou formato combinado "Tempo integral · 11 a 5 m" (LinkedIn nov/2025+)
        if (not linha or len(linha) < 2 or linha_lower in TIPOS_VINCULO
                or any(linha_lower.startswith(p) for p in SKIP_PREFIXOS)
                or _e_vinculo_com_duracao(linha)):
            i += 1
            continue

        # Duração total na empresa (ex: "11 anos 5 meses") — atualiza empresa_atual
        if _e_duracao(linha) and not _e_periodo(linha):
            i += 1
            continue

        # Período de cargo — pertence ao cargo em construção, não inicia um novo
        if _e_periodo(linha):
            i += 1
            continue

        # Possível empresa: heurística — se a próxima linha não nula for
        # uma duração total OU um vínculo combinado ("Tempo integral · Xa") → esta é empresa
        candidato_empresa = False
        for j in range(i + 1, min(i + 4, len(linhas))):
            if linhas[j].strip():
                nxt = linhas[j]
                if ((_e_duracao(nxt) and not _e_periodo(nxt))
                        or _e_vinculo_com_duracao(nxt)):
                    candidato_empresa = True
                break
        if candidato_empresa:
            empresa_atual = linha
            i += 1
            continue

        # Chegamos a um cargo
        cargo = linha
        periodo = None
        desc_linhas = []
        i += 1

        # Coleta tipo, período e descrição
        veio_pos_competencias = False
        veio_pos_periodo = False      # flag para pular localização logo após período
        while i < len(linhas):
            l = linhas[i]
            l_lower = l.lower()

            if l_lower in FOOTER_TOKENS:
                break

            # ── Período PRIMEIRO (pode conter "·") ─────────────────
            if _e_periodo(l):
                if not periodo:
                    periodo = re.split(r"\s*·\s*\d", l)[0].strip()
                veio_pos_competencias = False
                veio_pos_periodo = True
                i += 1
                continue

            # Linha logo após período costuma ser localização ("Fortaleza, Ceará, Brasil"
            # ou "Fortaleza e Região") — pula se for texto curto sem dígitos
            if veio_pos_periodo:
                veio_pos_periodo = False
                if len(l) < 70 and re.match(r'^[A-Za-zÀ-ÖØ-öø-ÿ\s,\.]+$', l):
                    i += 1
                    continue

            # Pula tipo de vínculo, UI, prefixos e formato combinado
            if l_lower in TIPOS_VINCULO or _e_vinculo_com_duracao(l):
                i += 1
                continue
            if any(l_lower.startswith(p) for p in SKIP_PREFIXOS):
                if l_lower.startswith("competências:"):
                    veio_pos_competencias = True
                i += 1
                continue
            # Pula localização com "·" (ex: "Fortaleza, CE · Presencial")
            if "·" in l:
                i += 1
                continue

            if _e_duracao(l):
                i += 1
                continue

            # Primeira linha real após "Competências:" é um novo cargo
            if veio_pos_competencias:
                break
            veio_pos_competencias = False

            # Nova empresa: próxima linha é duração total ou vínculo combinado
            prox_e_duracao = False
            for j in range(i + 1, min(i + 4, len(linhas))):
                if linhas[j].strip():
                    nxt_j = linhas[j]
                    prox_e_duracao = ((_e_duracao(nxt_j) and not _e_periodo(nxt_j))
                                      or _e_vinculo_com_duracao(nxt_j))
                    break
            if prox_e_duracao:
                break

            if l and not l.isdigit() and l != "·":
                desc_linhas.append(l)
            i += 1

        if cargo and empresa_atual:
            experiencias.append({
                "cargo":     cargo,
                "empresa":   empresa_atual,
                "periodo":   periodo,
                "descricao": " ".join(desc_linhas).strip() or None,
            })

    return experiencias


def _parse_formacoes_inner_text(linhas: list[str]) -> list[dict]:
    """
    Analisa o bloco da sub-página /details/education/ do LinkedIn.

    Estrutura real:
      Formação acadêmica       ← marcador (skip)
      Universidade de ...      ← instituição
      Pós-graduação Lato ..., Artificial Intelligence  ← curso
      jan de 2026 – dez de 2026  ← período
      Nível de formação: ...   ← skip
      Atividades e grupos: ... ← skip
      [descrição...]
      … mais                   ← skip
      Competências: ...        ← skip
      [próxima instituição...]
    """
    formacoes = []
    SKIP_PREFIXOS = ("competências:", "skills:", "atividades e grupos:", "nível de formação:",
                     "… mais", "mostrar mais", "ver mais", "ver menos", "·")
    FOOTER_TOKENS = {"idioma do perfil", "sobre", "acessibilidade", "linkedin corporation"}

    i = 0
    # Pula nav/nome até o marcador de seção
    while i < len(linhas) and linhas[i].lower() not in ("formação acadêmica", "education", "formação"):
        i += 1
    i += 1  # pula o marcador

    while i < len(linhas):
        linha = linhas[i]
        linha_lower = linha.lower()

        if linha_lower in FOOTER_TOKENS:
            break
        if not linha or len(linha) < 2 or linha.isdigit() or linha == "·":
            i += 1
            continue
        if any(linha_lower.startswith(p) for p in SKIP_PREFIXOS):
            i += 1
            continue
        if _e_periodo(linha) or _e_duracao(linha):
            i += 1
            continue

        instituicao = linha
        curso = None
        periodo = None
        desc_linhas = []
        i += 1

        # Curso (próxima linha não-período)
        if i < len(linhas):
            l = linhas[i]
            if not _e_periodo(l) and not any(l.lower().startswith(p) for p in SKIP_PREFIXOS):
                curso = l
                i += 1

        # Período e descrição
        while i < len(linhas):
            l = linhas[i]
            l_lower = l.lower()

            if l_lower in FOOTER_TOKENS:
                break
            if any(l_lower.startswith(p) for p in SKIP_PREFIXOS) or l == "·" or l.isdigit():
                i += 1
                continue
            if _e_periodo(l):
                if not periodo:
                    periodo = l.strip()
                i += 1
                continue
            if _e_duracao(l):
                i += 1
                continue
            # Próxima instituição: curta, sem período
            if len(l.split()) <= 6 and not l.endswith((".", "!", "?")) and not _e_periodo(l):
                break
            if l:
                desc_linhas.append(l)
            i += 1

        formacoes.append({
            "instituicao": instituicao,
            "curso":       curso,
            "periodo":     periodo,
            "descricao":   " ".join(desc_linhas).strip() or None,
        })

    return formacoes


def _pular_nav(linhas: list[str], marcador_secao: str) -> list[str]:
    """
    Remove todo o conteúdo de navegação e encontra o início real da seção.
    Retorna a lista de linhas a partir da linha APÓS o marcador.
    """
    marcadores = {
        "competências", "competencias", "skills", "habilidades",
        "licenças e certificações", "licencas e certificacoes", "certifications",
        "certificações", "certificacoes",
        "licenças e certificados",
    }
    # Tenta encontrar o marcador específico da seção
    for i, linha in enumerate(linhas):
        if linha.lower() in marcadores or linha.lower() == marcador_secao.lower():
            return linhas[i + 1:]
    # Fallback: pula apenas o nav padrão (primeiras ~20 linhas)
    NAV = {"início","minha rede","vagas","mensagens","notificações","para negócios",
           "learning","publicar","eu","pular para pesquisa","pular para conteúdo principal",
           "skip to conteúdo principal","skip to à parte","skip to rodapé","0 notificação"}
    i = 0
    while i < len(linhas) and (linhas[i].lower() in NAV or linhas[i].isdigit() or linhas[i] == "·"):
        i += 1
    # Pula nome e título (próximas 2 linhas com texto)
    skip = 0
    while i < len(linhas) and skip < 2:
        if linhas[i].strip():
            skip += 1
        i += 1
    return linhas[i:]


def _parse_competencias_inner_text(linhas: list[str]) -> list[str]:
    """
    Analisa o bloco da sub-página /details/skills/ do LinkedIn.

    Estrutura real:
      [nav + nome]
      Competências    ← marcador
      Python          ← competência
      N endossos      ← skip
      Gerente de Tecnologia | ...  ← cargo associado (skip)
      3e Soluções     ← empresa associada (skip)
      FastAPI         ← próxima competência
      ...
    """
    FOOTER = {"idioma do perfil", "sobre", "acessibilidade", "linkedin corporation"}
    SKIP_TOKENS = {"endossado", "endossar", "adicionar", "editar", "ver mais",
                   "ver todas as competências", "mostrar mais", "mostrar menos", "· "}
    CAT_LABELS = {"todos", "conhecimento do setor", "ferramentas e tecnologias",
                  "competências interpessoais", "você adicionou o número máximo de competências",
                  "gerenciar competências", "adicionar competência", "adicionar seção",
                  "disponível para"}
    SKIP_PREFIXOS_COMP = ("exibir todos os", "exibir perfil completo")

    # Pula até o marcador "Competências"
    linhas_uteis = _pular_nav(linhas, "competências")

    competencias = []
    i = 0
    while i < len(linhas_uteis):
        linha = linhas_uteis[i]
        l_lower = linha.lower()

        if l_lower in FOOTER:
            break
        if not linha or linha.isdigit() or linha == "·" or l_lower in SKIP_TOKENS:
            i += 1
            continue
        if l_lower in CAT_LABELS:
            i += 1
            continue
        if any(l_lower.startswith(p) for p in SKIP_PREFIXOS_COMP):
            i += 1
            continue
        # Pula linhas com "endosso" ou contadores numéricos
        if re.match(r"^\d+\s+endoss", l_lower):
            i += 1
            continue
        # Pula nomes de cargo e empresa (linhas que contêm "·" ou são longas com "|")
        if "·" in linha or ("|" in linha and len(linha) > 30):
            i += 1
            continue
        # Heurística: competência é linha curta sem vírgula e sem período
        if len(linha) < 60 and "," not in linha and not _e_periodo(linha) and not _e_duracao(linha):
            competencias.append(linha)
        i += 1

    # Remove duplicatas mantendo ordem
    vistos = set()
    return [c for c in competencias if not (c in vistos or vistos.add(c))]


def _parse_certificacoes_inner_text(linhas: list[str]) -> list[dict]:
    """
    Analisa o bloco da sub-página /details/certifications/ do LinkedIn.

    Estrutura real:
      [nav + nome]
      Licenças e certificações   ← marcador
      Nome da Certificação       ← nome
      Instituição emissora       ← instituição
      Emitido em mai. de 2022 –  ← data emissão
      ID da credencial: ABC      ← skip
      [próxima certificação...]
    """
    FOOTER = {"idioma do perfil", "sobre", "acessibilidade", "linkedin corporation"}
    SKIP_PREFIXOS = ("id da credencial", "código da credencial", "exibir credencial",
                     "mostrar credencial", "licenças e certificad", "… mais",
                     "mostrar mais", "ver mais", "competências:")

    linhas_uteis = _pular_nav(linhas, "licenças e certificações")

    certificacoes = []
    i = 0
    while i < len(linhas_uteis):
        linha = linhas_uteis[i]
        l_lower = linha.lower()

        if l_lower in FOOTER:
            break
        if not linha or len(linha) < 2 or linha.isdigit() or linha == "·":
            i += 1
            continue
        if any(l_lower.startswith(p) for p in SKIP_PREFIXOS):
            i += 1
            continue
        if _e_periodo(linha):
            i += 1
            continue

        nome = linha
        # Normaliza nomes com prefixo repetido (bug do LinkedIn: "Nome Parcial Nome Completo")
        _ws = nome.split()
        for _n in range(2, len(_ws) // 2 + 1):
            if _ws[:_n] == _ws[_n : _n * 2]:
                nome = " ".join(_ws[_n:])
                break
        instituicao = None
        data_emissao = None
        i += 1

        # Próxima linha = instituição (não é período)
        if i < len(linhas_uteis):
            l = linhas_uteis[i]
            if not _e_periodo(l) and not any(l.lower().startswith(p) for p in SKIP_PREFIXOS):
                instituicao = l
                i += 1

        # Data de emissão
        while i < len(linhas_uteis):
            l = linhas_uteis[i]
            l_lower = l.lower()
            # SKIP_PREFIXOS primeiro — evita que UUIDs em "Código da credencial ..."
            # sejam detectados como datas (ex: "4027-8978" parece "ano-ano")
            if any(l_lower.startswith(p) for p in SKIP_PREFIXOS) or l.isdigit():
                i += 1
                continue
            if _e_periodo(l) or "emitid" in l_lower or "expedid" in l_lower:
                if not data_emissao:  # não sobrescreve data já encontrada
                    data_emissao = l
                i += 1
                continue
            break

        certificacoes.append({
            "nome":        nome,
            "instituicao": instituicao,
            "data_emissao": data_emissao,
            "descricao":   None,
        })

        # LinkedIn repete o nome da cert (às vezes com grafia diferente) seguido de
        # um parágrafo de descrição. Detecta o par pelo padrão: linha não-skip
        # seguida de linha longa (> 100 chars). Pula os dois de uma vez.
        if (i < len(linhas_uteis)
                and i + 1 < len(linhas_uteis)
                and len(linhas_uteis[i + 1]) > 100):
            next_lower = linhas_uteis[i].lower()
            if (not any(next_lower.startswith(p) for p in SKIP_PREFIXOS)
                    and not _e_periodo(linhas_uteis[i])
                    and linhas_uteis[i] not in FOOTER):
                i += 2  # pula nome repetido + descrição

    return certificacoes


def _parse_projetos_inner_text(linhas: list[str]) -> list[dict]:
    """
    Analisa o bloco da sub-página /details/projects/ do LinkedIn.

    Estrutura real (quando há múltiplos projetos):
      Projetos                          ← marcador (skip)
      Nome do Projeto 1                 ← título
      fev de 2022 – o momento           ← período (logo após o título)
      Associados a 3e Soluções          ← afiliação (skip)
      Descrição linha 1                 ← descrição (pode ser multi-linha)
      Tecnologias: Python, LLMs, AWS    ← extraído para campo próprio
      Competências: ...                ← skip
      Nome do Projeto 2                 ← novo título — detectado por lookahead:
      ago de 2015 – o momento             a linha seguinte É um período
      ...

    Cada projeto é delimitado pela heurística: uma linha de título é sempre
    seguida (a 1-2 linhas de distância) por uma linha de período. Sem essa
    detecção, todos os projetos da página são fundidos em um só registro.
    """
    FOOTER_TOKENS = {"idioma do perfil", "sobre", "acessibilidade", "linkedin corporation"}
    SKIP_PREFIXOS = ("associados a", "competências:", "skills:")

    i = 0
    while i < len(linhas) and linhas[i].lower() not in ("projetos", "projects"):
        i += 1
    i += 1  # pula marcador

    def _prox_e_periodo(idx: int) -> bool:
        """Verifica se a próxima linha não vazia a partir de idx é um período."""
        for j in range(idx, min(idx + 3, len(linhas))):
            if linhas[j].strip():
                return _e_periodo(linhas[j])
        return False

    projetos = []
    while i < len(linhas):
        linha = linhas[i]
        l_lower = linha.lower()

        if l_lower in FOOTER_TOKENS:
            break
        if not linha or len(linha) < 3 or linha.isdigit() or linha == "·":
            i += 1
            continue

        titulo = linha
        desc_linhas: list[str] = []
        tecnologias = None
        periodo = None
        i += 1

        while i < len(linhas):
            l = linhas[i]
            l_lower = l.lower()
            if l_lower in FOOTER_TOKENS:
                break
            if not l:
                i += 1
                continue
            if _e_periodo(l):
                if not periodo:
                    periodo = l.strip()
                i += 1
                continue
            if l_lower.startswith("tecnologias:"):
                tecnologias = l[len("tecnologias:"):].strip()
                i += 1
                continue
            if any(l_lower.startswith(p) for p in SKIP_PREFIXOS):
                i += 1
                continue

            # Início de um NOVO projeto: só verifica depois que já temos um
            # período (ou seja, já estamos coletando a descrição) e a
            # próxima linha não vazia é, ela sim, um período.
            if periodo and _prox_e_periodo(i + 1):
                break

            desc_linhas.append(l)
            i += 1

        projetos.append({
            "titulo":      titulo,
            "descricao":   "\n".join(desc_linhas).strip() or None,
            "tecnologias": tecnologias,
            "periodo":     periodo,
        })

    return projetos


def _parse_publicacoes_inner_text(linhas: list[str]) -> list[dict]:
    """
    Analisa o bloco de atividade recente do LinkedIn (/recent-activity/all/).

    Cada post é delimitado por "Número da publicação no feed N".
    O corpo começa após a linha "Visível a todos, dentro ou fora do LinkedIn"
    e termina na seção de hashtags ("hashtag") ou botões de reação.
    """
    FOOTER_TOKENS = {"idioma do perfil", "sobre", "acessibilidade", "linkedin corporation"}
    REACAO_TOKENS = {"gostei", "curtir", "comentar", "compartilhar", "republicar", "enviar", "reagir"}

    _RE_PERIODO_PUB = re.compile(
        r"há\s+\d+\s+(semanas?|meses?|dias?|horas?|minutos?)", re.I
    )

    def _extrair_post(bloco: list[str]) -> dict | None:
        """
        Extrai corpo e data de um bloco de linhas de um único post.

        Estrutura real do bloco (após o delimitador "Número da publicação..."):
          [Nome repetido, cargo, timestamp, • Você, espaços]
          "Há 2 semanas • Editado • Visível a todos, dentro ou fora do LinkedIn"
          [CORPO DO POST — texto, emojis, bullets]
          "hashtag"           ← início da seção de tags
          "#Vaga"
          ...
          "Gostei / Comentar / ..."  ← reações (fim do bloco)
        """
        corpo: list[str] = []
        data_pub: str | None = None
        encontrou_inicio = False

        for l in bloco:
            ll = l.lower().strip()

            # Captura data antes de encontrar o início do corpo
            if not data_pub and _RE_PERIODO_PUB.search(ll):
                m = _RE_PERIODO_PUB.search(ll)
                data_pub = ll[m.start():].split("•")[0].strip()

            # Marcador de início: linha de visibilidade após timestamp
            if not encontrou_inicio:
                if "visível" in ll and ("todos" in ll or "linkedin" in ll):
                    encontrou_inicio = True
                continue

            # Fim: palavra "hashtag" solta (precede "#Tag")
            if ll == "hashtag":
                break
            # Fim: linha que começa com "#" (hashtag direto)
            if re.match(r'^#\w', l):
                break
            # Fim: botões de reação
            if ll in REACAO_TOKENS:
                break
            # Fim: "…mais", "Ative para ver a imagem maior"
            if ll in ("…mais", "ative para ver a imagem maior"):
                break
            # Skip: linhas com apenas dígitos (contadores de curtidas)
            if l.strip().isdigit():
                continue
            # Skip: "X comentários", "Y compartilhamentos"
            if re.match(r'^\d+\s+(comentário|compartilhamento|reação)', ll):
                continue

            if l.strip():
                corpo.append(l.strip())

        if not encontrou_inicio or not corpo:
            return None

        texto = "\n".join(corpo).strip()
        return {"conteudo": texto, "data_publicacao": data_pub} if len(texto) > 50 else None

    # ── Localiza início dos posts ────────────────────────────────
    publicacoes: list[dict] = []
    bloco_atual: list[str] = []
    em_posts = False

    for l in linhas:
        ll = l.lower().strip()

        if ll in FOOTER_TOKENS:
            break

        # Delimitador de início de post
        if "número da publicação no feed" in ll:
            if em_posts and bloco_atual:
                resultado = _extrair_post(bloco_atual)
                if resultado:
                    publicacoes.append(resultado)
            bloco_atual = []
            em_posts = True
            continue

        if em_posts:
            bloco_atual.append(l)

    # Último bloco
    if bloco_atual:
        resultado = _extrair_post(bloco_atual)
        if resultado:
            publicacoes.append(resultado)

    return publicacoes


def _parse_artigos_inner_text(linhas: list[str]) -> list[dict]:
    """
    Analisa o bloco de artigos do LinkedIn (/recent-activity/articles/).

    Os artigos aparecem no mesmo feed-card usado para posts (delimitado por
    "Número da publicação no feed N"), mas com título destacado e indicador
    de tempo de leitura ("N min de leitura") em vez do corpo completo do post.

    NOTA: estrutura inferida por analogia com o parser de publicações —
    como ainda não há captura real desta seção, deve ser validada/ajustada
    após a primeira coleta com artigos publicados.
    """
    FOOTER_TOKENS = {"idioma do perfil", "sobre", "acessibilidade", "linkedin corporation"}
    REACAO_TOKENS = {"gostei", "curtir", "comentar", "compartilhar", "republicar", "enviar", "reagir"}
    _RE_LEITURA = re.compile(r"^\d+\s*min\s+de\s+leitura", re.I)
    _RE_VISIBILIDADE = re.compile(r"há\s+\d+\s+(semanas?|meses?|dias?|horas?|minutos?)", re.I)

    def _extrair_artigo(bloco: list[str]) -> dict | None:
        titulo = None
        tempo_leitura = None
        data_pub = None
        resumo_linhas: list[str] = []

        for l in bloco:
            ll = l.lower().strip()

            if not l.strip():
                continue
            if ll in REACAO_TOKENS:
                break
            if ll in ("…mais", "ative para ver a imagem maior"):
                continue
            if l.strip().isdigit():
                continue
            if re.match(r'^\d+\s+(comentário|compartilhamento|reação)', ll):
                continue

            m_leitura = _RE_LEITURA.match(ll)
            if m_leitura:
                tempo_leitura = l.strip()
                continue

            if not data_pub and _RE_VISIBILIDADE.search(ll):
                m = _RE_VISIBILIDADE.search(ll)
                data_pub = ll[m.start():].split("•")[0].strip()

            if "visível" in ll and ("todos" in ll or "linkedin" in ll):
                continue
            if _RE_VISIBILIDADE.match(ll):
                continue

            # Primeira linha de conteúdo substancial é o título do artigo
            if not titulo and len(l.strip()) > 10:
                titulo = l.strip()
                continue

            if titulo:
                resumo_linhas.append(l.strip())

        if not titulo:
            return None

        return {
            "titulo": titulo,
            "resumo": " ".join(resumo_linhas).strip() or None,
            "tempo_leitura": tempo_leitura,
            "data_publicacao": data_pub,
        }

    artigos: list[dict] = []
    bloco_atual: list[str] = []
    em_posts = False

    for l in linhas:
        ll = l.lower().strip()

        if ll in FOOTER_TOKENS:
            break

        if "número da publicação no feed" in ll:
            if em_posts and bloco_atual:
                resultado = _extrair_artigo(bloco_atual)
                if resultado:
                    artigos.append(resultado)
            bloco_atual = []
            em_posts = True
            continue

        if em_posts:
            bloco_atual.append(l)

    if bloco_atual:
        resultado = _extrair_artigo(bloco_atual)
        if resultado:
            artigos.append(resultado)

    return artigos


def _parse_seletores_css(soup: BeautifulSoup, dados: dict) -> None:
    """
    Tenta extrair dados via seletores CSS presentes na versão pública
    sem JavaScript do LinkedIn. Preenche apenas campos ainda vazios.
    """
    # Nome
    if not dados.get("nome"):
        for sel in ("h1.top-card-layout__title", "h1.text-heading-xlarge", "h1"):
            tag = soup.select_one(sel)
            if tag:
                dados["nome"] = _texto(tag)
                break

    # Título
    if not dados.get("titulo"):
        for sel in (
            "div.top-card-layout__headline",
            "div.text-body-medium.break-words",
            ".pv-text-details__left-panel h2",
        ):
            tag = soup.select_one(sel)
            if tag:
                dados["titulo"] = _texto(tag)
                break

    # Localização
    if not dados.get("localizacao"):
        for sel in (
            "span.top-card__subline-item",
            ".pv-text-details__left-panel span.text-body-small",
        ):
            tags = soup.select(sel)
            for t in tags:
                texto = _texto(t)
                if texto and any(c in texto for c in [",", "Brasil", "Brazil", "SP", "RJ", "MG"]):
                    dados["localizacao"] = texto
                    break

    # Resumo / Sobre
    if not dados.get("resumo"):
        for sel in (
            "div.core-section-container__content p",
            "section.summary div.show-more-less-text",
            ".pv-about-section .pv-about__summary-text",
        ):
            tag = soup.select_one(sel)
            if tag:
                dados["resumo"] = _texto(tag)
                break

    # Experiências
    if not dados.get("experiencias"):
        dados["experiencias"] = _parse_experiencias_css(soup)

    # Formações
    if not dados.get("formacoes"):
        dados["formacoes"] = _parse_formacoes_css(soup)

    # Competências
    if not dados.get("competencias"):
        dados["competencias"] = _parse_competencias_css(soup)

    # Certificações
    if not dados.get("certificacoes"):
        dados["certificacoes"] = _parse_certificacoes_css(soup)


def _parse_experiencias_css(soup: BeautifulSoup) -> list[dict]:
    resultado = []
    seletores_secao = [
        "section#experience-section li",
        "section.experience-section li.experience-item",
        "li.experience-item",
        "div[data-section='experience'] li",
    ]
    for sel in seletores_secao:
        itens = soup.select(sel)
        if itens:
            for item in itens:
                cargo   = _texto(item.select_one("h3, .mr1.t-bold span, .experience-item__title"))
                empresa = _texto(item.select_one("p.experience-item__subtitle, .t-14.t-normal span"))
                periodo_tag = item.select_one(
                    "span.date-range, .experience-item__duration, .pvs-entity__caption-wrapper"
                )
                periodo = _extrair_periodo(_texto(periodo_tag) or "")
                desc    = _texto(item.select_one(
                    "div.experience-item__description, .pvs-list__item--line-separated p"
                ))
                if cargo or empresa:
                    resultado.append({
                        "cargo":    cargo,
                        "empresa":  empresa,
                        "periodo":  periodo,
                        "descricao": desc,
                    })
            break
    return resultado


def _parse_formacoes_css(soup: BeautifulSoup) -> list[dict]:
    resultado = []
    seletores_secao = [
        "section#education-section li",
        "li.education__list-item",
        "div[data-section='educationsDetails'] li",
    ]
    for sel in seletores_secao:
        itens = soup.select(sel)
        if itens:
            for item in itens:
                inst   = _texto(item.select_one("h3, .education__school-name"))
                curso  = _texto(item.select_one("span.education__item--degree-info, h4"))
                periodo_tag = item.select_one("span.date-range, .education__item--duration")
                periodo = _extrair_periodo(_texto(periodo_tag) or "")
                desc    = _texto(item.select_one("p.education-item__description"))
                if inst:
                    resultado.append({
                        "instituicao": inst,
                        "curso":       curso,
                        "periodo":     periodo,
                        "descricao":   desc,
                    })
            break
    return resultado


def _parse_competencias_css(soup: BeautifulSoup) -> list[str]:
    resultado = []
    seletores = [
        "li.skills-section__item span.skills-section__skill",
        "span.skill-category-entity__name",
        "li[class*='skill'] span",
    ]
    for sel in seletores:
        tags = soup.select(sel)
        if tags:
            resultado = [_limpar(t.get_text()) for t in tags if _limpar(t.get_text())]
            break
    return resultado


def _parse_certificacoes_css(soup: BeautifulSoup) -> list[dict]:
    resultado = []
    seletores_secao = [
        "section#certifications-section li",
        "li.certifications__list-item",
        "div[data-section='certifications'] li",
    ]
    for sel in seletores_secao:
        itens = soup.select(sel)
        if itens:
            for item in itens:
                nome  = _texto(item.select_one("h3, .certificate-title"))
                inst  = _texto(item.select_one("span.certifications__subtitle, p.t-14"))
                data  = _texto(item.select_one("span.date-range, time"))
                desc  = _texto(item.select_one("p"))
                if nome:
                    resultado.append({
                        "nome":        nome,
                        "instituicao": inst,
                        "data_emissao": data,
                        "descricao":   desc,
                    })
            break
    return resultado


# ──────────────────────────────────────────────
# Parser de texto puro (.txt)
# ──────────────────────────────────────────────

def parsear_texto(texto: str, url: str = "") -> dict:
    """
    Extrai dados a partir de um arquivo de texto exportado do perfil.
    Usa heurísticas de seção por palavras-chave em PT/EN.
    """
    dados: dict = {
        "url": url,
        "experiencias": [],
        "formacoes": [],
        "competencias": [],
        "certificacoes": [],
    }

    secoes = _dividir_secoes_texto(texto)

    dados["nome"]       = _limpar(secoes.get("nome"))
    dados["titulo"]     = _limpar(secoes.get("titulo"))
    dados["localizacao"] = _limpar(secoes.get("localizacao"))
    dados["resumo"]     = _limpar(secoes.get("sobre"))

    if "experiencia" in secoes:
        dados["experiencias"] = _parse_blocos_texto(secoes["experiencia"])
    if "formacao" in secoes:
        dados["formacoes"] = _parse_blocos_texto(secoes["formacao"], modo="formacao")
    if "competencias" in secoes:
        linhas = [_limpar(l) for l in secoes["competencias"].splitlines() if _limpar(l)]
        dados["competencias"] = linhas
    if "certificacoes" in secoes:
        dados["certificacoes"] = _parse_blocos_texto(secoes["certificacoes"], modo="certificacao")

    return dados


_MARCADORES_SECAO = {
    "sobre":        re.compile(r"^(sobre|about|resumo|summary)\s*$", re.I),
    "experiencia":  re.compile(r"^(experi[eê]ncia[s]?|experience[s]?)\s*$", re.I),
    "formacao":     re.compile(r"^(forma[cç][aã]o|educa[cç][aã]o|education)\s*$", re.I),
    "competencias": re.compile(r"^(compet[eê]ncias?|habilidades?|skills?)\s*$", re.I),
    "certificacoes": re.compile(r"^(certifica[cç][oõ]es?|licenses?|certifications?)\s*$", re.I),
}


def _dividir_secoes_texto(texto: str) -> dict:
    linhas = texto.splitlines()
    secoes: dict = {}
    secao_atual = None
    buffer: list = []

    # As primeiras linhas não-vazias costumam ser nome e título
    cabecalho = [l.strip() for l in linhas[:10] if l.strip()]
    if cabecalho:
        secoes["nome"] = cabecalho[0]
    if len(cabecalho) > 1:
        secoes["titulo"] = cabecalho[1]
    if len(cabecalho) > 2:
        secoes["localizacao"] = cabecalho[2]

    for linha in linhas:
        stripped = linha.strip()
        matched = False
        for chave, regex in _MARCADORES_SECAO.items():
            if regex.match(stripped):
                if secao_atual and buffer:
                    secoes[secao_atual] = "\n".join(buffer).strip()
                secao_atual = chave
                buffer = []
                matched = True
                break
        if not matched and secao_atual:
            buffer.append(linha)

    if secao_atual and buffer:
        secoes[secao_atual] = "\n".join(buffer).strip()

    return secoes


def _parse_blocos_texto(texto: str, modo: str = "experiencia") -> list[dict]:
    """Divide o texto em blocos separados por linha em branco e monta dicts."""
    blocos = re.split(r"\n{2,}", texto.strip())
    resultado = []
    for bloco in blocos:
        linhas = [l.strip() for l in bloco.splitlines() if l.strip()]
        if not linhas:
            continue
        if modo == "experiencia":
            resultado.append({
                "cargo":    linhas[0] if len(linhas) > 0 else None,
                "empresa":  linhas[1] if len(linhas) > 1 else None,
                "periodo":  _extrair_periodo(linhas[2]) if len(linhas) > 2 else None,
                "descricao": "\n".join(linhas[3:]) or None,
            })
        elif modo == "formacao":
            resultado.append({
                "instituicao": linhas[0] if len(linhas) > 0 else None,
                "curso":       linhas[1] if len(linhas) > 1 else None,
                "periodo":     _extrair_periodo(linhas[2]) if len(linhas) > 2 else None,
                "descricao":   "\n".join(linhas[3:]) or None,
            })
        elif modo == "certificacao":
            resultado.append({
                "nome":        linhas[0] if len(linhas) > 0 else None,
                "instituicao": linhas[1] if len(linhas) > 1 else None,
                "data_emissao": linhas[2] if len(linhas) > 2 else None,
                "descricao":   "\n".join(linhas[3:]) or None,
            })
    return resultado


# ──────────────────────────────────────────────
# Parser PDF
# ──────────────────────────────────────────────

def parsear_pdf(caminho: Path, url: str = "") -> dict:
    """
    Extrai texto de um PDF exportado do LinkedIn e delega ao parser de texto.
    Requer pdfplumber (incluso em requirements.txt).
    """
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError(
            "pdfplumber não está instalado. Execute: pip install pdfplumber"
        )

    texto_completo = []
    with pdfplumber.open(caminho) as pdf:
        for pagina in pdf.pages:
            texto_completo.append(pagina.extract_text() or "")

    texto = "\n".join(texto_completo)
    logger.info("PDF lido: %d caracteres extraídos.", len(texto))
    return parsear_texto(texto, url=url)


# ──────────────────────────────────────────────
# Detecção automática de fonte
# ──────────────────────────────────────────────

def parsear_arquivo(caminho: str | Path, url: str = "") -> tuple[dict, str]:
    """
    Detecta o tipo do arquivo e chama o parser adequado.
    Retorna (dados_extraidos, conteudo_bruto).
    """
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")

    sufixo = caminho.suffix.lower()

    if sufixo == ".pdf":
        dados = parsear_pdf(caminho, url=url)
        return dados, f"[PDF] {caminho.name}"

    conteudo = caminho.read_text(encoding="utf-8", errors="replace")

    if sufixo in (".html", ".htm"):
        dados = parsear_html(conteudo, url=url)
        return dados, conteudo

    # .txt ou qualquer outro
    dados = parsear_texto(conteudo, url=url)
    return dados, conteudo
