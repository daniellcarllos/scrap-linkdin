"""
scraper.py — Acesso HTTP ao perfil público do LinkedIn.

Comportamento ético:
  - Sem login ou cookies de sessão.
  - Sem contorno de bloqueios (CAPTCHAs, Cloudflare, etc.).
  - Se o LinkedIn retornar 429/403/999, informa o usuário e sugere importação manual.
  - User-Agent de navegador comum para acesso público, não bot agressivo.
"""

import time
import logging
from typing import Optional

import requests
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

# Cabeçalhos de navegador padrão — acesso como qualquer usuário faria
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Códigos que indicam bloqueio ativo pelo LinkedIn
_CODIGOS_BLOQUEIO = {403, 429, 999}

# Mensagem de orientação exibida ao usuário quando o acesso é bloqueado
MENSAGEM_BLOQUEIO = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ACESSO BLOQUEADO PELO LINKEDIN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
O LinkedIn bloqueou a requisição automática.
Isso é comum e esperado — não é um erro do sistema.

Como prosseguir com importação manual:

  1. Abra seu perfil no navegador:
     https://www.linkedin.com/in/danielcdasilva

  2. Exporte uma das opções abaixo:
     a) PDF nativo:
        → "Mais" → "Salvar como PDF"
        → Salve como: perfil.pdf

     b) HTML da página:
        → Ctrl+S (ou Cmd+S) → "Página completa"
        → Salve como: perfil.html

     c) Texto copiado:
        → Selecione todo o texto (Ctrl+A)
        → Cole em um arquivo: perfil.txt

  3. Coloque o arquivo na pasta do projeto e execute:
     python main.py --arquivo perfil.pdf
     python main.py --arquivo perfil.html
     python main.py --arquivo perfil.txt
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


class BloqueioLinkedInError(Exception):
    """Levantada quando o LinkedIn bloqueia o acesso."""


class AcessoLinkedInError(Exception):
    """Levantada para erros de rede ou HTTP não esperados."""


def buscar_perfil_publico(url: str, timeout: int = 15) -> str:
    """
    Faz uma requisição GET à URL pública do perfil LinkedIn.

    Retorna o HTML da página em caso de sucesso.
    Levanta BloqueioLinkedInError se o acesso for bloqueado.
    Levanta AcessoLinkedInError para outros erros.

    Parâmetros
    ----------
    url     : URL pública do perfil (ex: https://www.linkedin.com/in/danielcdasilva)
    timeout : Timeout em segundos para a requisição
    """
    logger.info("Acessando URL: %s", url)

    # Pequena pausa para não parecer automatizado
    time.sleep(2)

    try:
        resposta = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
    except RequestException as exc:
        raise AcessoLinkedInError(f"Erro de rede ao acessar {url}: {exc}") from exc

    logger.info("HTTP %d recebido.", resposta.status_code)

    if resposta.status_code in _CODIGOS_BLOQUEIO:
        logger.warning("LinkedIn bloqueou o acesso (HTTP %d).", resposta.status_code)
        raise BloqueioLinkedInError(
            f"HTTP {resposta.status_code} — acesso bloqueado pelo LinkedIn."
        )

    if not resposta.ok:
        raise AcessoLinkedInError(
            f"HTTP {resposta.status_code} ao acessar {url}."
        )

    html = resposta.text
    logger.info("HTML recebido: %d caracteres.", len(html))

    # Heurística: LinkedIn às vezes retorna 200 com página de login
    if _parece_pagina_de_login(html):
        logger.warning("LinkedIn retornou página de login (redireccionamento implícito).")
        raise BloqueioLinkedInError(
            "LinkedIn redirecionou para página de login em vez do perfil público."
        )

    return html


def _parece_pagina_de_login(html: str) -> bool:
    """Detecta se o HTML retornado é a tela de login e não o perfil."""
    indicadores = [
        'name="session_key"',
        'id="username"',
        "authwall",
        "/checkpoint/lg/login",
    ]
    html_lower = html.lower()
    return sum(1 for ind in indicadores if ind in html_lower) >= 2
