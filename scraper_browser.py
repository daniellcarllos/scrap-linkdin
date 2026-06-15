"""
scraper_browser.py — Coleta via navegador real (Playwright).

Modos de operação:
  1. Login automático via .env  (padrão quando há credenciais)
     — Lê LINKEDIN_EMAIL e LINKEDIN_PASSWORD do .env
     — Faz login, salva sessão em data/sessao_linkedin/
     — Reutiliza sessão nas próximas execuções (não loga de novo)

  2. Login interativo (--interativo)
     — Abre navegador visível, usuário faz login manualmente
     — Sessão também é salva para reutilização

  3. Chromium headless sem login
     — Sem credenciais, acesso público apenas
     — LinkedIn normalmente bloqueia com authwall
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SESSAO_DIR = Path(__file__).parent / "data" / "sessao_linkedin"

# URLs do LinkedIn
_URL_LOGIN    = "https://www.linkedin.com/login"
_URL_FEED     = "https://www.linkedin.com/feed/"
_INDICADOR_LOGADO = "https://www.linkedin.com/feed"


def _credenciais() -> tuple[str, str]:
    """Lê email e senha do .env. Levanta erro claro se ausentes."""
    email = os.getenv("LINKEDIN_EMAIL", "").strip()
    senha = os.getenv("LINKEDIN_PASSWORD", "").strip()

    if not email or email == "seu_email@exemplo.com":
        raise ValueError(
            "LINKEDIN_EMAIL não configurado.\n"
            "Edite o arquivo .env e preencha suas credenciais."
        )
    if not senha or senha == "sua_senha_aqui":
        raise ValueError(
            "LINKEDIN_PASSWORD não configurado.\n"
            "Edite o arquivo .env e preencha suas credenciais."
        )
    return email, senha


def _esta_logado(page) -> bool:
    """Retorna True se a página atual indica sessão ativa."""
    url = page.url
    return (
        "feed" in url
        or "mynetwork" in url
        or "in/" in url
        or "jobs" in url
    ) and "login" not in url and "authwall" not in url


def _fazer_login(page, email: str, senha: str) -> None:
    """
    Navega para a tela de login e preenche as credenciais.
    As credenciais vêm do .env — nunca são expostas nos logs.
    """
    from playwright.sync_api import TimeoutError as PWTimeout

    logger.info("Navegando para tela de login...")
    page.goto(_URL_LOGIN, wait_until="domcontentloaded", timeout=20_000)

    try:
        page.wait_for_selector("#username", timeout=10_000)
    except PWTimeout:
        raise RuntimeError("Tela de login não carregou. Verifique sua conexão.")

    # Preenche email
    page.fill("#username", email)
    page.wait_for_timeout(500)

    # Preenche senha
    page.fill("#password", senha)
    page.wait_for_timeout(300)

    # Clica em Entrar
    page.click('button[type="submit"]')
    logger.info("Credenciais enviadas — aguardando resposta do LinkedIn...")

    # Aguarda redirecionamento pós-login (até 30s)
    try:
        page.wait_for_url(
            lambda u: "feed" in u or "checkpoint" in u or "challenge" in u,
            timeout=30_000,
        )
    except PWTimeout:
        raise RuntimeError(
            "LinkedIn não redirecionou após login. "
            "Verifique as credenciais no .env."
        )

    url_pos_login = page.url

    if "checkpoint" in url_pos_login or "challenge" in url_pos_login:
        raise RuntimeError(
            "LinkedIn solicitou verificação de segurança (CAPTCHA ou 2FA).\n"
            "Use o modo interativo para resolver manualmente:\n"
            "  python main.py --url <URL> --interativo"
        )

    if "login" in url_pos_login or "authwall" in url_pos_login:
        raise RuntimeError(
            "Login falhou. Verifique email e senha no arquivo .env."
        )

    logger.info("Login realizado com sucesso.")


def _rolar_pagina(page) -> None:
    """Rola a página gradualmente para ativar lazy-load das seções do perfil."""
    page.wait_for_timeout(1_000)
    altura = page.evaluate("document.body.scrollHeight")
    posicao = 0
    passo = 700

    while posicao < altura:
        page.evaluate(f"window.scrollTo(0, {posicao})")
        page.wait_for_timeout(400)
        posicao += passo
        altura = page.evaluate("document.body.scrollHeight")

    # Volta ao topo para garantir captura completa
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(800)


def _capturar_perfil(page, url: str) -> str:
    """
    Captura o perfil navegando pelas sub-páginas de cada seção.

    O LinkedIn separa cada seção em URLs específicas:
      /details/experience/, /details/education/, /details/skills/, etc.

    Essa abordagem é muito mais confiável que tentar rolar a página principal,
    que tem feed de posts no meio e lazy-load imprevisível.
    """
    # Garante que a URL base não tem trailing slash nem query string
    url_base = url.rstrip("/").split("?")[0]

    # Coleta texto de cada seção individualmente
    secoes_coletadas = {}

    # 1. Cabeçalho do perfil (nome, título, localização, resumo)
    logger.info("Capturando cabeçalho do perfil...")
    texto_cabecalho = _get_inner_text(page, url_base)
    secoes_coletadas["cabecalho"] = texto_cabecalho

    # 2. Sub-páginas de cada seção
    sub_paginas = {
        "experience":     "Experiência",
        "education":      "Formação",
        "skills":         "Competências",
        "certifications": "Certificações",
        "projects":       "Projetos",
    }

    for slug, nome in sub_paginas.items():
        url_secao = f"{url_base}/details/{slug}/"
        logger.info("Capturando %s: %s", nome, url_secao)
        texto = _get_inner_text(page, url_secao)
        if texto:
            secoes_coletadas[slug] = texto
            logger.info("  → %d caracteres capturados.", len(texto))
        else:
            logger.warning("  → seção vazia ou não encontrada.")

    # 3. Publicações recentes (atividade do perfil)
    url_atividade = f"{url_base}/recent-activity/all/"
    logger.info("Capturando publicações: %s", url_atividade)
    texto_pub = _get_inner_text_com_scroll(page, url_atividade)
    if texto_pub:
        secoes_coletadas["publicacoes"] = texto_pub
        logger.info("  → %d caracteres de publicações capturados.", len(texto_pub))

    # Monta o texto anotado que o parser vai processar
    partes = [
        "<!-- LINKEDIN_INNER_TEXT_START -->",
        "<linkedin-text>",
        f"[CABECALHO]\n{secoes_coletadas.get('cabecalho', '')}",
    ]
    for slug, nome in sub_paginas.items():
        if slug in secoes_coletadas:
            partes.append(f"\n[SECAO:{nome.upper()}]\n{secoes_coletadas[slug]}")
    if "publicacoes" in secoes_coletadas:
        partes.append(f"\n[SECAO:PUBLICAÇÕES]\n{secoes_coletadas['publicacoes']}")
    partes.append("</linkedin-text>")
    partes.append("<!-- LINKEDIN_INNER_TEXT_END -->")

    return "\n".join(partes)


def _get_inner_text(page, url: str) -> str:
    """Navega para uma URL e retorna o inner_text do body após carregar."""
    from playwright.sync_api import TimeoutError as PWTimeout

    try:
        page.goto(url, wait_until="load", timeout=20_000)
    except PWTimeout:
        logger.warning("Timeout ao carregar %s", url)
        return ""

    page.wait_for_timeout(2_500)

    try:
        return page.inner_text("body") or ""
    except Exception as exc:
        logger.warning("Erro ao extrair inner_text: %s", exc)
        return ""


def _get_inner_text_com_scroll(page, url: str, n_scrolls: int = 5) -> str:
    """
    Navega para uma URL, rola a página N vezes para carregar mais conteúdo
    (lazy-load / infinite scroll) e retorna o inner_text completo.
    Usado especialmente para a página de publicações recentes.
    """
    from playwright.sync_api import TimeoutError as PWTimeout

    try:
        page.goto(url, wait_until="load", timeout=20_000)
    except PWTimeout:
        logger.warning("Timeout ao carregar %s", url)
        return ""

    page.wait_for_timeout(3_000)

    for _ in range(n_scrolls):
        page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
        page.wait_for_timeout(1_500)

    try:
        return page.inner_text("body") or ""
    except Exception as exc:
        logger.warning("Erro ao extrair inner_text: %s", exc)
        return ""


# ──────────────────────────────────────────────
# Funções públicas
# ──────────────────────────────────────────────

def buscar_perfil_com_login(url: str, headless: bool = True) -> str:
    """
    Faz login no LinkedIn com as credenciais do .env e captura o perfil.

    Reutiliza sessão salva em data/sessao_linkedin/ quando disponível,
    evitando login repetido a cada execução.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright não instalado. Execute:\n"
            "  pip install playwright && playwright install chromium"
        )

    email, senha = _credenciais()
    SESSAO_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(SESSAO_DIR),
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
            locale="pt-BR",
            viewport={"width": 1280, "height": 900},
            ignore_https_errors=True,
        )

        page = context.new_page()

        # Verifica se a sessão salva ainda é válida
        logger.info("Verificando sessão salva...")
        page.goto(_URL_FEED, wait_until="domcontentloaded", timeout=15_000)
        page.wait_for_timeout(2_000)

        if not _esta_logado(page):
            logger.info("Sessão expirada ou inexistente — fazendo login...")
            _fazer_login(page, email, senha)
            page.wait_for_timeout(2_000)
        else:
            logger.info("Sessão ativa reutilizada — login não necessário.")

        html = _capturar_perfil(page, url)
        context.close()

    return html


def buscar_perfil_interativo(url: str) -> str:
    """
    Abre navegador visível para login manual.
    Salva a sessão para reutilização posterior.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        raise RuntimeError(
            "Playwright não instalado. Execute:\n"
            "  pip install playwright && playwright install chromium"
        )

    SESSAO_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(SESSAO_DIR),
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            locale="pt-BR",
            viewport={"width": 1280, "height": 900},
        )

        page = context.new_page()

        page.goto(_URL_FEED, wait_until="domcontentloaded", timeout=15_000)
        page.wait_for_timeout(2_000)

        if not _esta_logado(page):
            print("\n" + "=" * 60)
            print("  FAÇA LOGIN NO LINKEDIN NA JANELA ABERTA")
            print("  O script continuará automaticamente após o login.")
            print("=" * 60 + "\n")

            try:
                page.wait_for_url(
                    lambda u: "feed" in u and "login" not in u,
                    timeout=180_000,
                )
                print("  Login detectado — continuando...\n")
            except PWTimeout:
                raise RuntimeError("Tempo esgotado aguardando login manual.")

        html = _capturar_perfil(page, url)
        context.close()

    return html


def buscar_perfil_com_browser(
    url: str,
    usar_chrome_local: bool = False,
    headless: bool = True,
) -> str:
    """Acesso público sem login (geralmente bloqueado pelo LinkedIn)."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        raise RuntimeError("Playwright não instalado.")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="pt-BR",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            page.wait_for_selector("h1", timeout=8_000)
        except PWTimeout:
            pass
        _rolar_pagina(page)
        html = page.content()
        browser.close()

    return html
