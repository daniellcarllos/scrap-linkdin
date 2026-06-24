"""
pdf_generator.py — Geração de currículo em PDF otimizado para ATS.

Segue boas práticas de Applicant Tracking Systems (sistemas automatizados
que triam currículos antes de chegar a um recrutador humano):

  - Layout em coluna única, sem tabelas de posicionamento, sem caixas de texto
  - Fonte padrão do PDF (Helvetica) — sem fontes decorativas/customizadas
  - Sem imagens, ícones, gráficos ou elementos rasterizados
  - Texto sempre selecionável (nunca é uma imagem do currículo)
  - Dados de contato em texto corrido no topo — NUNCA em cabeçalho/rodapé,
    pois muitos ATS não leem essas áreas
  - Títulos de seção em texto simples e padronizado (RESUMO, EXPERIÊNCIA
    PROFISSIONAL, etc.) — sem depender de cor ou imagem para hierarquia
  - Bullets com caractere padrão "-" em vez de símbolos Unicode decorativos
  - Datas em formato textual simples, sem ícones de calendário
"""

import re
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

_FONTE = "Helvetica"
_FONTE_BOLD = "Helvetica-Bold"


def _estilos() -> dict:
    base = getSampleStyleSheet()
    return {
        "nome": ParagraphStyle(
            "Nome", parent=base["Normal"], fontName=_FONTE_BOLD,
            fontSize=18, leading=22, spaceAfter=2,
        ),
        "titulo_prof": ParagraphStyle(
            "TituloProf", parent=base["Normal"], fontName=_FONTE,
            fontSize=11, leading=14, spaceAfter=2,
            textColor=colors.HexColor("#333333"),
        ),
        "contato": ParagraphStyle(
            "Contato", parent=base["Normal"], fontName=_FONTE,
            fontSize=9.5, leading=13, spaceAfter=10,
            textColor=colors.HexColor("#333333"),
        ),
        "secao": ParagraphStyle(
            "Secao", parent=base["Normal"], fontName=_FONTE_BOLD,
            fontSize=12, leading=16, spaceBefore=12, spaceAfter=4,
            textColor=colors.HexColor("#1a1a1a"),
        ),
        "subsecao": ParagraphStyle(
            "Subsecao", parent=base["Normal"], fontName=_FONTE_BOLD,
            fontSize=10.5, leading=14, spaceBefore=8, spaceAfter=2,
            textColor=colors.HexColor("#1a1a1a"),
        ),
        "subtitulo": ParagraphStyle(
            "Subtitulo", parent=base["Normal"], fontName=_FONTE_BOLD,
            fontSize=10.5, leading=14, spaceAfter=0,
        ),
        "meta": ParagraphStyle(
            "Meta", parent=base["Normal"], fontName=_FONTE,
            fontSize=9.5, leading=13, spaceAfter=4,
            textColor=colors.HexColor("#555555"),
        ),
        "corpo": ParagraphStyle(
            "Corpo", parent=base["Normal"], fontName=_FONTE,
            fontSize=10, leading=14, spaceAfter=8, alignment=TA_LEFT,
        ),
        "bullet": ParagraphStyle(
            "Bullet", parent=base["Normal"], fontName=_FONTE,
            fontSize=10, leading=14, spaceAfter=2, leftIndent=12,
        ),
    }


def _escape(texto: str | None) -> str:
    """Escapa caracteres especiais do XML usado pelo Paragraph do reportlab."""
    if not texto:
        return ""
    return (
        texto.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
    )


def _md_inline(texto: str) -> str:
    """Converte **bold** e *itálico*/_itálico_ markdown simples para tags reportlab."""
    texto = _escape(texto)
    texto = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", texto)
    texto = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*(?!\*)", r"<i>\1</i>", texto)
    texto = re.sub(r"_(.+?)_", r"<i>\1</i>", texto)
    return texto


def _markdown_para_flowables(md: str, estilos: dict) -> list:
    """Converte o markdown simples gerado por ai_synthesizer em flowables do reportlab."""
    flowables = []
    for linha in md.split("\n"):
        linha = linha.strip()
        if not linha:
            continue
        if linha.startswith("#### "):
            flowables.append(Spacer(1, 4))
            flowables.append(Paragraph(_md_inline(linha[5:]), estilos["subtitulo"]))
            continue
        if linha.startswith("### "):
            flowables.append(Spacer(1, 6))
            flowables.append(Paragraph(_md_inline(linha[4:]).upper(), estilos["subsecao"]))
            continue
        if linha.startswith("## "):
            continue  # título da seção já é adicionado pelo chamador
        if linha.startswith("- "):
            flowables.append(Paragraph(f"- {_md_inline(linha[2:])}", estilos["bullet"]))
            continue
        flowables.append(Paragraph(_md_inline(linha), estilos["corpo"]))
    return flowables


def gerar_curriculo_pdf(dados: dict, dados_contato: dict | None = None, salvar: bool = True) -> Path:
    """
    Gera o currículo em PDF otimizado para ATS: coluna única, fonte padrão,
    sem imagens/tabelas de layout, texto sempre selecionável.

    Args:
        dados: dict retornado por queries.carregar_coleta() — pode incluir a
               chave opcional "_sintese_markdown" com a seção de Projetos.
        dados_contato: dict com telefone, email, site_portfolio, cidade_estado
                       (de database.carregar_dados_pessoais()).
        salvar: se True, escreve o arquivo em output/ e retorna o Path.
    """
    estilos = _estilos()
    elementos = []

    nome = dados.get("nome") or "Nome não disponível"
    titulo = dados.get("titulo") or ""

    elementos.append(Paragraph(_escape(nome), estilos["nome"]))
    if titulo:
        elementos.append(Paragraph(_escape(titulo), estilos["titulo_prof"]))

    # Contato em texto corrido no topo (nunca em cabeçalho/rodapé — ATS pode ignorar essas áreas)
    partes_contato = []
    if dados_contato:
        if dados_contato.get("telefone"):
            partes_contato.append(dados_contato["telefone"])
        if dados_contato.get("email"):
            partes_contato.append(dados_contato["email"])
        if dados_contato.get("cidade_estado"):
            partes_contato.append(dados_contato["cidade_estado"])
    if dados.get("url"):
        partes_contato.append(dados["url"])
    if dados_contato and dados_contato.get("site_portfolio"):
        partes_contato.append(dados_contato["site_portfolio"])

    if partes_contato:
        elementos.append(Paragraph(_escape(" | ".join(partes_contato)), estilos["contato"]))

    elementos.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#999999"), spaceAfter=8))

    if dados.get("resumo"):
        elementos.append(Paragraph("RESUMO", estilos["secao"]))
        elementos.append(Paragraph(_escape(dados["resumo"]), estilos["corpo"]))

    if dados.get("experiencias"):
        elementos.append(Paragraph("EXPERIÊNCIA PROFISSIONAL", estilos["secao"]))
        for exp in dados["experiencias"]:
            cargo = exp.get("cargo") or ""
            empresa = exp.get("empresa") or ""
            periodo = exp.get("periodo") or ""
            elementos.append(Paragraph(_escape(f"{cargo} — {empresa}"), estilos["subtitulo"]))
            if periodo:
                elementos.append(Paragraph(_escape(periodo), estilos["meta"]))
            desc = exp.get("descricao") or ""
            for linha in desc.split("\n"):
                linha = linha.strip().lstrip("•-·").strip()
                if linha:
                    elementos.append(Paragraph(f"- {_escape(linha)}", estilos["bullet"]))
            elementos.append(Spacer(1, 6))

    if dados.get("formacoes"):
        elementos.append(Paragraph("FORMAÇÃO ACADÊMICA", estilos["secao"]))
        for f in dados["formacoes"]:
            inst = f.get("instituicao") or ""
            curso = f.get("curso") or ""
            periodo = f.get("periodo") or ""
            elementos.append(Paragraph(_escape(inst), estilos["subtitulo"]))
            linha_meta = " · ".join(p for p in (curso, periodo) if p)
            if linha_meta:
                elementos.append(Paragraph(_escape(linha_meta), estilos["meta"]))
            elementos.append(Spacer(1, 4))

    if dados.get("certificacoes"):
        elementos.append(Paragraph("CERTIFICAÇÕES", estilos["secao"]))
        for c in dados["certificacoes"]:
            nome_c = c.get("nome") or ""
            inst = c.get("instituicao") or ""
            data = c.get("data_emissao") or ""
            linha = " — ".join(p for p in (nome_c, inst) if p)
            if data:
                linha += f" ({data})"
            elementos.append(Paragraph(f"- {_escape(linha)}", estilos["bullet"]))
        elementos.append(Spacer(1, 6))

    if dados.get("competencias"):
        elementos.append(Paragraph("COMPETÊNCIAS", estilos["secao"]))
        elementos.append(Paragraph(_escape(", ".join(dados["competencias"])), estilos["corpo"]))

    sintese_md = dados.get("_sintese_markdown")
    if sintese_md:
        elementos.append(Paragraph("PROJETOS EXECUTADOS E IMPACTOS", estilos["secao"]))
        elementos.extend(_markdown_para_flowables(sintese_md, estilos))

    nome_arquivo = OUTPUT_DIR / f"curriculo_{dados.get('id', 'x')}_{_timestamp()}.pdf"
    documento = SimpleDocTemplate(
        str(nome_arquivo),
        pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=f"Currículo - {nome}",
        author=nome,
    )
    documento.build(elementos)

    return nome_arquivo


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")
