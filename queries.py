"""
queries.py — Consultas ao banco SQLite e geração de saídas estruturadas.

Funções disponíveis:
  - listar_coletas()          → histórico de coletas
  - carregar_ultima_coleta()  → dados da coleta mais recente
  - carregar_coleta(id)       → dados de uma coleta específica
  - comparar_coletas(id1,id2) → diferenças entre duas coletas
  - gerar_curriculo_md(id)    → Markdown pronto para currículo
  - gerar_curriculo_json(id)  → JSON estruturado
  - gerar_curriculo_txt(id)   → texto simples
  - exportar_csv()            → exporta experiências para CSV via pandas
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from database import get_connection, criar_tabelas, carregar_sintese_projetos

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


# ──────────────────────────────────────────────
# Consultas básicas
# ──────────────────────────────────────────────

def listar_coletas() -> list[dict]:
    """Retorna resumo de todas as coletas já realizadas."""
    criar_tabelas()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, url, nome, titulo, data_coleta FROM perfil ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def carregar_coleta(perfil_id: int) -> dict:
    """Carrega todos os dados de uma coleta pelo seu ID."""
    with get_connection() as conn:
        perfil = conn.execute(
            "SELECT * FROM perfil WHERE id = ?", (perfil_id,)
        ).fetchone()
        if not perfil:
            raise ValueError(f"Coleta id={perfil_id} não encontrada.")

        dados = dict(perfil)

        dados["experiencias"] = [
            dict(r) for r in conn.execute(
                "SELECT * FROM experiencias WHERE perfil_id = ?", (perfil_id,)
            ).fetchall()
        ]
        dados["formacoes"] = [
            dict(r) for r in conn.execute(
                "SELECT * FROM formacoes WHERE perfil_id = ?", (perfil_id,)
            ).fetchall()
        ]
        dados["competencias"] = [
            r["competencia"] for r in conn.execute(
                "SELECT competencia FROM competencias WHERE perfil_id = ?", (perfil_id,)
            ).fetchall()
        ]
        dados["certificacoes"] = [
            dict(r) for r in conn.execute(
                "SELECT * FROM certificacoes WHERE perfil_id = ?", (perfil_id,)
            ).fetchall()
        ]
        dados["projetos"] = [
            dict(r) for r in conn.execute(
                "SELECT * FROM projetos WHERE perfil_id = ?", (perfil_id,)
            ).fetchall()
        ]
        dados["publicacoes"] = [
            dict(r) for r in conn.execute(
                "SELECT * FROM publicacoes WHERE perfil_id = ?", (perfil_id,)
            ).fetchall()
        ]
        dados["artigos"] = [
            dict(r) for r in conn.execute(
                "SELECT * FROM artigos WHERE perfil_id = ?", (perfil_id,)
            ).fetchall()
        ]

    return dados


def carregar_ultima_coleta() -> dict:
    """Carrega os dados da coleta mais recente."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM perfil ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        raise ValueError("Nenhuma coleta encontrada no banco.")
    return carregar_coleta(row["id"])


# ──────────────────────────────────────────────
# Comparação entre coletas
# ──────────────────────────────────────────────

def comparar_coletas(id1: int, id2: int) -> dict:
    """
    Compara dois snapshots e retorna um dict com as diferenças.
    Útil para identificar mudanças no perfil ao longo do tempo.
    """
    c1 = carregar_coleta(id1)
    c2 = carregar_coleta(id2)

    diffs: dict = {"coleta_antiga": id1, "coleta_nova": id2, "campos": {}, "novos": {}, "removidos": {}}

    # Campos simples
    for campo in ("nome", "titulo", "localizacao", "resumo"):
        v1, v2 = c1.get(campo), c2.get(campo)
        if v1 != v2:
            diffs["campos"][campo] = {"antes": v1, "depois": v2}

    # Experiências
    emps1 = {e["empresa"] for e in c1["experiencias"] if e.get("empresa")}
    emps2 = {e["empresa"] for e in c2["experiencias"] if e.get("empresa")}
    diffs["novos"]["experiencias"]    = list(emps2 - emps1)
    diffs["removidos"]["experiencias"] = list(emps1 - emps2)

    # Competências
    comp1 = set(c1["competencias"])
    comp2 = set(c2["competencias"])
    diffs["novos"]["competencias"]    = list(comp2 - comp1)
    diffs["removidos"]["competencias"] = list(comp1 - comp2)

    # Certificações
    cert1 = {c["nome"] for c in c1["certificacoes"] if c.get("nome")}
    cert2 = {c["nome"] for c in c2["certificacoes"] if c.get("nome")}
    diffs["novos"]["certificacoes"]    = list(cert2 - cert1)
    diffs["removidos"]["certificacoes"] = list(cert1 - cert2)

    return diffs


# ──────────────────────────────────────────────
# Geração de currículo em Markdown
# ──────────────────────────────────────────────

def gerar_curriculo_md(perfil_id: int | None = None, salvar: bool = True) -> str:
    dados = carregar_coleta(perfil_id) if perfil_id else carregar_ultima_coleta()

    linhas: list[str] = []
    _h = lambda n, t: linhas.append(f"{'#' * n} {t}\n")
    _p = lambda t: linhas.append(f"{t}\n")
    _hr = lambda: linhas.append("---\n")

    _h(1, dados.get("nome") or "Nome não disponível")
    if dados.get("titulo"):
        _p(f"**{dados['titulo']}**")
    if dados.get("localizacao"):
        _p(f"📍 {dados['localizacao']}")
    if dados.get("url"):
        _p(f"🔗 [{dados['url']}]({dados['url']})")

    if dados.get("resumo"):
        _hr()
        _h(2, "Sobre")
        _p(dados["resumo"])

    if dados.get("experiencias"):
        _hr()
        _h(2, "Experiência Profissional")
        for exp in dados["experiencias"]:
            cargo   = exp.get("cargo") or ""
            empresa = exp.get("empresa") or ""
            periodo = exp.get("periodo") or ""
            desc    = exp.get("descricao") or ""
            linhas.append(f"### {cargo}")
            linhas.append(f"**{empresa}** · {periodo}\n")
            if desc:
                _p(desc)

    if dados.get("formacoes"):
        _hr()
        _h(2, "Formação Acadêmica")
        for form in dados["formacoes"]:
            inst    = form.get("instituicao") or ""
            curso   = form.get("curso") or ""
            periodo = form.get("periodo") or ""
            linhas.append(f"### {inst}")
            linhas.append(f"{curso} · {periodo}\n")

    if dados.get("certificacoes"):
        _hr()
        _h(2, "Certificações")
        for cert in dados["certificacoes"]:
            nome = cert.get("nome") or ""
            inst = cert.get("instituicao") or ""
            data = cert.get("data_emissao") or ""
            linhas.append(f"- **{nome}** — {inst} ({data})")
        linhas.append("")

    if dados.get("competencias"):
        _hr()
        _h(2, "Competências")
        _p(", ".join(dados["competencias"]))

    # Seção de Projetos Executados (gerada por IA, se disponível)
    sintese = carregar_sintese_projetos(dados["id"])
    if sintese:
        _hr()
        linhas.append(sintese["markdown"])

    md = "\n".join(linhas)

    if salvar:
        nome_arquivo = OUTPUT_DIR / f"curriculo_{dados['id']}_{_timestamp()}.md"
        nome_arquivo.write_text(md, encoding="utf-8")
        logger.info("Currículo Markdown salvo em %s", nome_arquivo)
        print(f"  Arquivo salvo: {nome_arquivo}")

    return md


# ──────────────────────────────────────────────
# Geração de currículo em JSON
# ──────────────────────────────────────────────

def gerar_curriculo_json(perfil_id: int | None = None, salvar: bool = True) -> str:
    dados = carregar_coleta(perfil_id) if perfil_id else carregar_ultima_coleta()

    # Remove campos internos do banco
    saida = {k: v for k, v in dados.items() if k not in ("id", "perfil_id")}
    saida["gerado_em"] = datetime.now().isoformat()

    texto = json.dumps(saida, ensure_ascii=False, indent=2)

    if salvar:
        nome_arquivo = OUTPUT_DIR / f"curriculo_{dados['id']}_{_timestamp()}.json"
        nome_arquivo.write_text(texto, encoding="utf-8")
        logger.info("Currículo JSON salvo em %s", nome_arquivo)
        print(f"  Arquivo salvo: {nome_arquivo}")

    return texto


# ──────────────────────────────────────────────
# Geração de currículo em texto simples
# ──────────────────────────────────────────────

def gerar_curriculo_txt(perfil_id: int | None = None, salvar: bool = True) -> str:
    dados = carregar_coleta(perfil_id) if perfil_id else carregar_ultima_coleta()

    linhas: list[str] = []
    _sep = lambda: linhas.append("=" * 60)
    _sub = lambda: linhas.append("-" * 40)

    linhas.append(dados.get("nome") or "")
    linhas.append(dados.get("titulo") or "")
    linhas.append(dados.get("localizacao") or "")
    linhas.append(dados.get("url") or "")
    linhas.append("")

    if dados.get("resumo"):
        _sep()
        linhas.append("SOBRE")
        _sep()
        linhas.append(dados["resumo"])
        linhas.append("")

    if dados.get("experiencias"):
        _sep()
        linhas.append("EXPERIÊNCIA PROFISSIONAL")
        _sep()
        for exp in dados["experiencias"]:
            linhas.append(exp.get("cargo") or "")
            linhas.append(f"{exp.get('empresa') or ''} | {exp.get('periodo') or ''}")
            if exp.get("descricao"):
                linhas.append(exp["descricao"])
            _sub()

    if dados.get("formacoes"):
        _sep()
        linhas.append("FORMAÇÃO ACADÊMICA")
        _sep()
        for f in dados["formacoes"]:
            linhas.append(f.get("instituicao") or "")
            linhas.append(f"{f.get('curso') or ''} | {f.get('periodo') or ''}")
            _sub()

    if dados.get("competencias"):
        _sep()
        linhas.append("COMPETÊNCIAS")
        _sep()
        linhas.append(", ".join(dados["competencias"]))
        linhas.append("")

    txt = "\n".join(linhas)

    if salvar:
        nome_arquivo = OUTPUT_DIR / f"curriculo_{dados['id']}_{_timestamp()}.txt"
        nome_arquivo.write_text(txt, encoding="utf-8")
        logger.info("Currículo TXT salvo em %s", nome_arquivo)
        print(f"  Arquivo salvo: {nome_arquivo}")

    return txt


# ──────────────────────────────────────────────
# Exportação CSV via pandas
# ──────────────────────────────────────────────

def exportar_csv(perfil_id: int | None = None) -> None:
    try:
        import pandas as pd
    except ImportError:
        print("pandas não instalado. Execute: pip install pandas")
        return

    dados = carregar_coleta(perfil_id) if perfil_id else carregar_ultima_coleta()
    pid   = dados["id"]

    if dados["experiencias"]:
        df = pd.DataFrame(dados["experiencias"])
        f  = OUTPUT_DIR / f"experiencias_{pid}.csv"
        df.to_csv(f, index=False, encoding="utf-8-sig")
        print(f"  CSV salvo: {f}")

    if dados["competencias"]:
        df = pd.DataFrame({"competencia": dados["competencias"]})
        f  = OUTPUT_DIR / f"competencias_{pid}.csv"
        df.to_csv(f, index=False, encoding="utf-8-sig")
        print(f"  CSV salvo: {f}")


# ──────────────────────────────────────────────
# Utilitários
# ──────────────────────────────────────────────

def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")
