"""
database.py — Criação e acesso ao banco SQLite.
Gerencia todas as operações de persistência do projeto.
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "data" / "linkedin_profile.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def criar_tabelas() -> None:
    """Cria o schema completo do banco caso ainda não exista."""
    ddl = """
    CREATE TABLE IF NOT EXISTS perfil (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        url         TEXT    NOT NULL,
        nome        TEXT,
        titulo      TEXT,
        localizacao TEXT,
        resumo      TEXT,
        data_coleta TEXT    NOT NULL
    );

    CREATE TABLE IF NOT EXISTS experiencias (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        perfil_id  INTEGER NOT NULL REFERENCES perfil(id),
        cargo      TEXT,
        empresa    TEXT,
        periodo    TEXT,
        descricao  TEXT
    );

    CREATE TABLE IF NOT EXISTS formacoes (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        perfil_id    INTEGER NOT NULL REFERENCES perfil(id),
        instituicao  TEXT,
        curso        TEXT,
        periodo      TEXT,
        descricao    TEXT
    );

    CREATE TABLE IF NOT EXISTS competencias (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        perfil_id   INTEGER NOT NULL REFERENCES perfil(id),
        competencia TEXT
    );

    CREATE TABLE IF NOT EXISTS certificacoes (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        perfil_id    INTEGER NOT NULL REFERENCES perfil(id),
        nome         TEXT,
        instituicao  TEXT,
        data_emissao TEXT,
        descricao    TEXT
    );

    CREATE TABLE IF NOT EXISTS projetos (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        perfil_id    INTEGER NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
        titulo       TEXT,
        descricao    TEXT,
        tecnologias  TEXT,
        periodo      TEXT
    );

    CREATE TABLE IF NOT EXISTS publicacoes (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        perfil_id        INTEGER NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
        conteudo         TEXT,
        data_publicacao  TEXT
    );

    CREATE TABLE IF NOT EXISTS artigos (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        perfil_id        INTEGER NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
        titulo           TEXT,
        resumo           TEXT,
        tempo_leitura    TEXT,
        data_publicacao  TEXT
    );

    CREATE TABLE IF NOT EXISTS projetos_ia (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        perfil_id    INTEGER NOT NULL REFERENCES perfil(id) ON DELETE CASCADE,
        modelo       TEXT,
        resultado_json TEXT,
        markdown     TEXT,
        data_geracao TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS dados_brutos (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        perfil_id     INTEGER NOT NULL REFERENCES perfil(id),
        origem        TEXT,
        conteudo_bruto TEXT,
        json_extraido TEXT,
        data_coleta   TEXT    NOT NULL
    );
    """
    with get_connection() as conn:
        conn.executescript(ddl)
    logger.info("Tabelas verificadas/criadas com sucesso.")


def salvar_perfil(dados: dict) -> int:
    """Insere um registro de coleta e retorna o perfil_id gerado."""
    agora = datetime.now().isoformat()
    sql = """
        INSERT INTO perfil (url, nome, titulo, localizacao, resumo, data_coleta)
        VALUES (:url, :nome, :titulo, :localizacao, :resumo, :data_coleta)
    """
    with get_connection() as conn:
        cur = conn.execute(sql, {**dados, "data_coleta": agora})
        perfil_id = cur.lastrowid
    logger.info("Perfil salvo com id=%s", perfil_id)
    return perfil_id


def salvar_experiencias(perfil_id: int, lista: list[dict]) -> None:
    sql = """
        INSERT INTO experiencias (perfil_id, cargo, empresa, periodo, descricao)
        VALUES (:perfil_id, :cargo, :empresa, :periodo, :descricao)
    """
    rows = [{**e, "perfil_id": perfil_id} for e in lista]
    with get_connection() as conn:
        conn.executemany(sql, rows)
    logger.info("%d experiência(s) salva(s).", len(rows))


def salvar_formacoes(perfil_id: int, lista: list[dict]) -> None:
    sql = """
        INSERT INTO formacoes (perfil_id, instituicao, curso, periodo, descricao)
        VALUES (:perfil_id, :instituicao, :curso, :periodo, :descricao)
    """
    rows = [{**f, "perfil_id": perfil_id} for f in lista]
    with get_connection() as conn:
        conn.executemany(sql, rows)
    logger.info("%d formação(ões) salva(s).", len(rows))


def salvar_competencias(perfil_id: int, lista: list[str]) -> None:
    sql = "INSERT INTO competencias (perfil_id, competencia) VALUES (?, ?)"
    with get_connection() as conn:
        conn.executemany(sql, [(perfil_id, c) for c in lista])
    logger.info("%d competência(s) salva(s).", len(lista))


def salvar_certificacoes(perfil_id: int, lista: list[dict]) -> None:
    sql = """
        INSERT INTO certificacoes (perfil_id, nome, instituicao, data_emissao, descricao)
        VALUES (:perfil_id, :nome, :instituicao, :data_emissao, :descricao)
    """
    rows = [{**c, "perfil_id": perfil_id} for c in lista]
    with get_connection() as conn:
        conn.executemany(sql, rows)
    logger.info("%d certificação(ões) salva(s).", len(rows))


def salvar_projetos(perfil_id: int, lista: list[dict]) -> None:
    sql = """
        INSERT INTO projetos (perfil_id, titulo, descricao, tecnologias, periodo)
        VALUES (:perfil_id, :titulo, :descricao, :tecnologias, :periodo)
    """
    rows = [{**p, "perfil_id": perfil_id} for p in lista]
    with get_connection() as conn:
        conn.executemany(sql, rows)
    logger.info("%d projeto(s) salvo(s).", len(rows))


def salvar_publicacoes(perfil_id: int, lista: list[dict]) -> None:
    sql = """
        INSERT INTO publicacoes (perfil_id, conteudo, data_publicacao)
        VALUES (:perfil_id, :conteudo, :data_publicacao)
    """
    rows = [{**p, "perfil_id": perfil_id} for p in lista]
    with get_connection() as conn:
        conn.executemany(sql, rows)
    logger.info("%d publicação(ões) salva(s).", len(rows))


def salvar_artigos(perfil_id: int, lista: list[dict]) -> None:
    sql = """
        INSERT INTO artigos (perfil_id, titulo, resumo, tempo_leitura, data_publicacao)
        VALUES (:perfil_id, :titulo, :resumo, :tempo_leitura, :data_publicacao)
    """
    rows = [{**a, "perfil_id": perfil_id} for a in lista]
    with get_connection() as conn:
        conn.executemany(sql, rows)
    logger.info("%d artigo(s) salvo(s).", len(rows))


def salvar_sintese_projetos(perfil_id: int, modelo: str, resultado: dict, markdown: str) -> int:
    """Salva resultado da síntese de projetos por IA."""
    sql = """
        INSERT INTO projetos_ia (perfil_id, modelo, resultado_json, markdown, data_geracao)
        VALUES (?, ?, ?, ?, ?)
    """
    with get_connection() as conn:
        cur = conn.execute(sql, (
            perfil_id,
            modelo,
            json.dumps(resultado, ensure_ascii=False),
            markdown,
            datetime.now().isoformat(),
        ))
        return cur.lastrowid


def carregar_sintese_projetos(perfil_id: int) -> dict | None:
    """Carrega a síntese de projetos mais recente para um perfil."""
    sql = """
        SELECT resultado_json, markdown, modelo, data_geracao
        FROM projetos_ia
        WHERE perfil_id = ?
        ORDER BY id DESC LIMIT 1
    """
    with get_connection() as conn:
        row = conn.execute(sql, (perfil_id,)).fetchone()
    if not row:
        return None
    return {
        "resultado": json.loads(row["resultado_json"]),
        "markdown":  row["markdown"],
        "modelo":    row["modelo"],
        "data_geracao": row["data_geracao"],
    }


def salvar_dados_brutos(perfil_id: int, origem: str, conteudo: str, dados_json: dict) -> None:
    sql = """
        INSERT INTO dados_brutos (perfil_id, origem, conteudo_bruto, json_extraido, data_coleta)
        VALUES (?, ?, ?, ?, ?)
    """
    with get_connection() as conn:
        conn.execute(sql, (
            perfil_id,
            origem,
            conteudo[:50_000],          # limita tamanho do raw
            json.dumps(dados_json, ensure_ascii=False),
            datetime.now().isoformat(),
        ))
    logger.info("Dados brutos salvos (origem=%s).", origem)


def salvar_coleta_completa(dados: dict, origem: str, conteudo_bruto: str) -> int:
    """
    Persiste todos os dados de uma coleta de forma atômica.
    Retorna o perfil_id gerado.
    """
    criar_tabelas()

    perfil_id = salvar_perfil({
        "url":        dados.get("url", ""),
        "nome":       dados.get("nome"),
        "titulo":     dados.get("titulo"),
        "localizacao": dados.get("localizacao"),
        "resumo":     dados.get("resumo"),
    })

    if dados.get("experiencias"):
        salvar_experiencias(perfil_id, dados["experiencias"])
    if dados.get("formacoes"):
        salvar_formacoes(perfil_id, dados["formacoes"])
    if dados.get("competencias"):
        salvar_competencias(perfil_id, dados["competencias"])
    if dados.get("certificacoes"):
        salvar_certificacoes(perfil_id, dados["certificacoes"])
    if dados.get("projetos"):
        salvar_projetos(perfil_id, dados["projetos"])
    if dados.get("publicacoes"):
        salvar_publicacoes(perfil_id, dados["publicacoes"])
    if dados.get("artigos"):
        salvar_artigos(perfil_id, dados["artigos"])

    salvar_dados_brutos(perfil_id, origem, conteudo_bruto, dados)
    return perfil_id
