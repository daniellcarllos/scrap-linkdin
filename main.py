"""
main.py — Ponto de entrada da aplicação LinkedIn Profile Scraper.

Uso:
  # Coleta com login automático via .env (RECOMENDADO)
  python main.py --url https://www.linkedin.com/in/danielcdasilva --login

  # Coleta interativa (você faz login manualmente na janela que abre)
  python main.py --url https://www.linkedin.com/in/danielcdasilva --interativo

  # Importação de arquivo local exportado do LinkedIn
  python main.py --arquivo perfil.pdf
  python main.py --arquivo perfil.html
  python main.py --arquivo perfil.txt

  # Consultas e exportações
  python main.py --listar
  python main.py --curriculo md       # Gera Markdown
  python main.py --curriculo json     # Gera JSON
  python main.py --curriculo txt      # Gera texto
  python main.py --csv                # Exporta CSV
  python main.py --comparar 1 2       # Compara coletas 1 e 2
  python main.py --coleta 3 --curriculo md  # Usa coleta específica
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich import print as rprint

import os

import database
import parser as lk_parser
import pdf_generator
import queries
import scraper
import scraper_browser
import ai_synthesizer
from scraper import BloqueioLinkedInError, AcessoLinkedInError

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("coleta.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)
console = Console()

URL_PADRAO = "https://www.linkedin.com/in/danielcdasilva"


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="LinkedIn Profile Scraper — coleta e organiza dados públicos do perfil.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    grupo_entrada = ap.add_mutually_exclusive_group()
    grupo_entrada.add_argument(
        "--url", metavar="URL",
        help="URL pública do perfil LinkedIn (padrão: perfil de Daniel).",
    )
    grupo_entrada.add_argument(
        "--arquivo", metavar="ARQUIVO",
        help="Arquivo local exportado do LinkedIn (.pdf, .html, .txt).",
    )

    ap.add_argument(
        "--login", action="store_true",
        help="Usa credenciais do .env para fazer login automático no LinkedIn.",
    )
    ap.add_argument(
        "--interativo", action="store_true",
        help="Abre navegador visível para login manual. "
             "Salva sessão — próximas execuções não precisam logar de novo.",
    )
    ap.add_argument(
        "--visivel", action="store_true",
        help="Com --login: abre o navegador visível (útil para acompanhar o login).",
    )
    ap.add_argument(
        "--browser", action="store_true",
        help="Navegador headless sem login (normalmente bloqueado pelo LinkedIn).",
    )
    ap.add_argument(
        "--usar-chrome", action="store_true",
        help="Com --browser: usa Chrome instalado com sessão existente (Chrome deve estar fechado).",
    )

    ap.add_argument(
        "--listar", action="store_true",
        help="Lista todas as coletas armazenadas.",
    )
    ap.add_argument(
        "--curriculo", choices=["md", "json", "txt", "pdf"],
        help=(
            "Gera arquivo de currículo no formato indicado.\n"
            "'pdf' segue boas práticas de ATS e pede confirmação dos dados "
            "pessoais de contato (telefone, email, site/portfólio) antes de gerar."
        ),
    )
    ap.add_argument(
        "--csv", action="store_true",
        help="Exporta dados para CSV via pandas.",
    )
    ap.add_argument(
        "--comparar", nargs=2, type=int, metavar=("ID1", "ID2"),
        help="Compara duas coletas e exibe diferenças.",
    )
    ap.add_argument(
        "--coleta", type=int, metavar="ID",
        help="ID da coleta a usar nas operações de consulta/exportação.",
    )
    ap.add_argument(
        "--projetos", action="store_true",
        help=(
            "Gera seção 'Projetos Executados e Impactos' usando Claude AI.\n"
            "Analisa experiências, projetos do LinkedIn e publicações.\n"
            "Requer ANTHROPIC_API_KEY no .env."
        ),
    )

    return ap


# ──────────────────────────────────────────────
# Ações
# ──────────────────────────────────────────────

def acao_coletar_url(url: str, usar_browser: bool = False,
                     usar_chrome: bool = False, visivel: bool = False) -> None:
    if usar_browser:
        _acao_coletar_browser(url, usar_chrome=usar_chrome, visivel=visivel)
        return

    console.rule("[bold blue]Coleta via URL (requests)")
    console.print(f"  URL: {url}")

    try:
        html = scraper.buscar_perfil_publico(url)
    except BloqueioLinkedInError as exc:
        console.print(f"\n[bold red]{exc}")
        console.print(scraper.MENSAGEM_BLOQUEIO)
        sys.exit(1)
    except AcessoLinkedInError as exc:
        console.print(f"\n[bold red]Erro de acesso:[/bold red] {exc}")
        sys.exit(1)

    console.print("  HTML recebido — extraindo dados...")
    dados = lk_parser.parsear_html(html, url=url)
    _salvar_e_resumir(dados, origem="url", conteudo_bruto=html)


def _acao_coletar_browser(url: str, usar_chrome: bool, visivel: bool) -> None:
    modo = "Chrome com sua sessão" if usar_chrome else "Chromium headless"
    console.rule(f"[bold blue]Coleta via navegador — {modo}")
    console.print(f"  URL: {url}")

    if usar_chrome:
        console.print(
            "\n  [yellow]Atenção:[/yellow] feche o Google Chrome antes de continuar.\n"
            "  O Playwright precisa acesso exclusivo ao perfil do Chrome.\n"
            "  Pressione ENTER quando o Chrome estiver fechado..."
        )
        input()

    console.print("  Abrindo navegador e carregando perfil...")

    try:
        html = scraper_browser.buscar_perfil_com_browser(
            url,
            usar_chrome_local=usar_chrome,
            headless=not visivel,
        )
    except RuntimeError as exc:
        console.print(f"[bold red]{exc}")
        sys.exit(1)
    except Exception as exc:
        console.print(f"[bold red]Erro ao usar navegador:[/bold red] {exc}")
        sys.exit(1)

    if not html or len(html) < 500:
        console.print("[bold red]Página retornou HTML vazio ou muito pequeno.")
        console.print("  Tente com [bold]--visivel[/bold] para ver o que aconteceu no navegador.")
        sys.exit(1)

    console.print(f"  HTML capturado ({len(html):,} caracteres) — extraindo dados...")
    dados = lk_parser.parsear_html(html, url=url)
    origem = "browser-chrome" if usar_chrome else "browser-chromium"
    _salvar_e_resumir(dados, origem=origem, conteudo_bruto=html)


def acao_importar_arquivo(caminho: str) -> None:
    console.rule("[bold blue]Importação de arquivo local")
    console.print(f"  Arquivo: {caminho}")

    try:
        dados, conteudo_bruto = lk_parser.parsear_arquivo(caminho, url=URL_PADRAO)
    except FileNotFoundError as exc:
        console.print(f"[bold red]{exc}")
        sys.exit(1)
    except RuntimeError as exc:
        console.print(f"[bold red]{exc}")
        sys.exit(1)

    _salvar_e_resumir(dados, origem=caminho, conteudo_bruto=conteudo_bruto)


def _salvar_e_resumir(dados: dict, origem: str, conteudo_bruto: str) -> None:
    database.criar_tabelas()
    perfil_id = database.salvar_coleta_completa(dados, origem, conteudo_bruto)

    console.rule("[bold green]Resumo da Coleta")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Campo",  style="bold cyan")
    table.add_column("Valor")

    table.add_row("ID da Coleta",   str(perfil_id))
    table.add_row("Nome",           dados.get("nome") or "—")
    table.add_row("Título",         dados.get("titulo") or "—")
    table.add_row("Localização",    dados.get("localizacao") or "—")
    table.add_row("Experiências",   str(len(dados.get("experiencias", []))))
    table.add_row("Formações",      str(len(dados.get("formacoes", []))))
    table.add_row("Competências",   str(len(dados.get("competencias", []))))
    table.add_row("Certificações",  str(len(dados.get("certificacoes", []))))

    console.print(table)

    resumo = dados.get("resumo")
    if resumo:
        console.print(Panel(
            resumo[:400] + ("..." if len(resumo) > 400 else ""),
            title="Sobre",
            border_style="cyan",
        ))

    console.print(f"\n[green]Coleta id={perfil_id} salva com sucesso.[/green]")
    console.print("  Use [bold]python main.py --curriculo md[/bold] para gerar o currículo.")


def acao_coletar_com_login(url: str, visivel: bool = False) -> None:
    console.rule("[bold blue]Coleta com login automático (.env)")
    console.print(f"  URL: {url}")

    # Valida credenciais antes de abrir o navegador
    email = os.getenv("LINKEDIN_EMAIL", "").strip()
    if not email or email == "seu_email@exemplo.com":
        console.print(
            "\n[bold red]Credenciais não configuradas.[/bold red]\n\n"
            "Edite o arquivo [bold].env[/bold] e preencha:\n"
            "  LINKEDIN_EMAIL=seu_email@linkedin.com\n"
            "  LINKEDIN_PASSWORD=sua_senha\n"
        )
        sys.exit(1)

    console.print(f"  Conta: [cyan]{email}[/cyan]")
    modo = "visível" if visivel else "headless"
    console.print(f"  Modo:  {modo}\n")

    try:
        html = scraper_browser.buscar_perfil_com_login(url, headless=not visivel)
    except ValueError as exc:
        console.print(f"[bold red]{exc}")
        sys.exit(1)
    except RuntimeError as exc:
        console.print(f"[bold red]{exc}")
        sys.exit(1)

    if not html or len(html) < 1000:
        console.print(
            "[bold red]HTML capturado muito pequeno.[/bold red]\n"
            "Tente com [bold]--visivel[/bold] para ver o que aconteceu:\n"
            "  python main.py --url <URL> --login --visivel"
        )
        sys.exit(1)

    console.print(f"  HTML capturado ({len(html):,} chars) — extraindo dados...")
    dados = lk_parser.parsear_html(html, url=url)
    _salvar_e_resumir(dados, origem="browser-login", conteudo_bruto=html)


def acao_coletar_interativo(url: str) -> None:
    console.rule("[bold blue]Coleta interativa com navegador")
    console.print(f"  URL: {url}")
    console.print(
        "\n  [cyan]O navegador abrirá agora.[/cyan]\n"
        "  Se não estiver logado no LinkedIn, faça login normalmente.\n"
        "  A sessão é salva em [bold]data/sessao_linkedin/[/bold] — "
        "próximas execuções não precisam de login.\n"
    )

    try:
        html = scraper_browser.buscar_perfil_interativo(url)
    except RuntimeError as exc:
        console.print(f"[bold red]{exc}")
        sys.exit(1)

    if not html or len(html) < 1000:
        console.print("[bold red]HTML capturado muito pequeno — algo deu errado.")
        sys.exit(1)

    console.print(f"  HTML capturado ({len(html):,} chars) — extraindo dados...")
    dados = lk_parser.parsear_html(html, url=url)
    _salvar_e_resumir(dados, origem="browser-interativo", conteudo_bruto=html)


def acao_listar() -> None:
    coletas = queries.listar_coletas()
    if not coletas:
        console.print("[yellow]Nenhuma coleta encontrada. Execute uma coleta primeiro.[/yellow]")
        return

    table = Table(title="Coletas armazenadas", show_lines=True)
    table.add_column("ID",         style="bold")
    table.add_column("Nome")
    table.add_column("Título")
    table.add_column("Data da Coleta")
    table.add_column("URL")

    for c in coletas:
        table.add_row(
            str(c["id"]),
            c.get("nome") or "—",
            c.get("titulo") or "—",
            c.get("data_coleta") or "—",
            c.get("url") or "—",
        )

    console.print(table)


def obter_dados_pessoais_confirmados() -> dict:
    """
    Garante que os dados pessoais de contato (telefone, email, site/portfólio,
    cidade/estado) estejam disponíveis antes de gerar o PDF.

    Sempre pergunta se o usuário quer atualizar os dados já cadastrados, e
    sempre exibe um resumo para confirmação antes de salvar qualquer alteração
    no banco.
    """
    atuais = database.carregar_dados_pessoais()

    if atuais:
        console.print("\n[bold]Dados pessoais cadastrados atualmente:[/bold]")
        console.print(f"  Telefone       : {atuais.get('telefone') or '—'}")
        console.print(f"  Email          : {atuais.get('email') or '—'}")
        console.print(f"  Site/Portfólio : {atuais.get('site_portfolio') or '—'}")
        console.print(f"  Cidade/Estado  : {atuais.get('cidade_estado') or '—'}")
        console.print(f"  Atualizado em  : {atuais.get('atualizado_em') or '—'}\n")

        if not Confirm.ask("Deseja atualizar esses dados antes de gerar o currículo?", default=False):
            return atuais
    else:
        console.print(
            "\n[yellow]Nenhum dado pessoal cadastrado ainda. "
            "Vamos cadastrar agora para incluir no PDF.[/yellow]\n"
        )

    base = atuais or {}
    telefone = Prompt.ask("Telefone (com DDD)", default=base.get("telefone") or "")
    email = Prompt.ask("Email", default=base.get("email") or "")
    site = Prompt.ask("Site / Portfólio (opcional)", default=base.get("site_portfolio") or "")
    cidade = Prompt.ask("Cidade/Estado (opcional)", default=base.get("cidade_estado") or "")

    novos = {
        "telefone":       telefone.strip() or None,
        "email":          email.strip() or None,
        "site_portfolio": site.strip() or None,
        "cidade_estado":  cidade.strip() or None,
    }

    console.print("\n[bold]Confirme os dados antes de salvar:[/bold]")
    console.print(f"  Telefone       : {novos['telefone'] or '—'}")
    console.print(f"  Email          : {novos['email'] or '—'}")
    console.print(f"  Site/Portfólio : {novos['site_portfolio'] or '—'}")
    console.print(f"  Cidade/Estado  : {novos['cidade_estado'] or '—'}\n")

    if Confirm.ask("Salvar estes dados no banco?", default=True):
        database.salvar_dados_pessoais(novos)
        console.print("[green]Dados pessoais salvos.[/green]\n")
        return novos

    console.print("[yellow]Alterações descartadas — usando dados anteriores (se houver).[/yellow]\n")
    return atuais or novos


def acao_gerar_pdf(perfil_id: int | None) -> None:
    """Gera o currículo em PDF otimizado para ATS, com cadastro/confirmação de contato."""
    try:
        dados = queries.carregar_coleta(perfil_id) if perfil_id else queries.carregar_ultima_coleta()
    except ValueError as exc:
        console.print(f"[bold red]{exc}")
        sys.exit(1)

    dados_contato = obter_dados_pessoais_confirmados()

    sintese = database.carregar_sintese_projetos(dados["id"])
    if sintese:
        dados["_sintese_markdown"] = sintese["markdown"]

    caminho = pdf_generator.gerar_curriculo_pdf(dados, dados_contato)
    console.print(f"  Arquivo salvo: {caminho}")


def acao_curriculo(fmt: str, perfil_id: int | None) -> None:
    console.rule(f"[bold blue]Gerando currículo — formato {fmt.upper()}")
    try:
        if fmt == "md":
            queries.gerar_curriculo_md(perfil_id)
        elif fmt == "json":
            queries.gerar_curriculo_json(perfil_id)
        elif fmt == "txt":
            queries.gerar_curriculo_txt(perfil_id)
        elif fmt == "pdf":
            acao_gerar_pdf(perfil_id)
    except ValueError as exc:
        console.print(f"[bold red]{exc}")
        sys.exit(1)
    console.print("[green]Geração concluída.[/green]")


def acao_sintetizar_projetos(perfil_id: int | None) -> None:
    """Gera e salva a síntese de 'Projetos Executados e Impactos' via Claude AI."""
    console.rule("[bold blue]Síntese de Projetos Executados (IA)")

    try:
        dados = queries.carregar_coleta(perfil_id) if perfil_id else queries.carregar_ultima_coleta()
    except ValueError as exc:
        console.print(f"[bold red]{exc}")
        sys.exit(1)

    console.print(f"  Perfil: [cyan]{dados.get('nome')}[/cyan] (coleta id={dados['id']})")
    console.print(f"  Experiências: {len(dados.get('experiencias', []))} | "
                  f"Projetos: {len(dados.get('projetos', []))} | "
                  f"Publicações: {len(dados.get('publicacoes', []))} | "
                  f"Artigos: {len(dados.get('artigos', []))}")
    console.print()

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    usar_ia = bool(api_key)

    if usar_ia:
        console.print("  Modo: [green]Claude AI[/green] (ANTHROPIC_API_KEY detectado)")
        try:
            resultado = ai_synthesizer.sintetizar_projetos(dados)
        except (ValueError, RuntimeError) as exc:
            console.print(f"[bold red]{exc}")
            sys.exit(1)
    else:
        console.print(
            "  Modo: [yellow]Heurístico[/yellow] "
            "(sem ANTHROPIC_API_KEY — adicione ao .env para síntese com IA)"
        )
        resultado = ai_synthesizer.sintetizar_projetos_heuristico(dados)

    markdown = ai_synthesizer.gerar_markdown_projetos(resultado)

    database.criar_tabelas()
    sintese_id = database.salvar_sintese_projetos(
        dados["id"],
        modelo=ai_synthesizer.MODELO_PADRAO,
        resultado=resultado,
        markdown=markdown,
    )

    # Salva arquivo markdown dedicado
    from pathlib import Path
    from datetime import datetime
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    arquivo = output_dir / f"projetos_{dados['id']}_{ts}.md"
    arquivo.write_text(markdown, encoding="utf-8")

    console.print(f"\n[green]Síntese salva![/green] (id={sintese_id})")
    console.print(f"  Arquivo: {arquivo}")
    console.print(f"  Projetos identificados: {len(resultado.get('projetos', []))}")
    console.print()
    console.print(
        "  Use [bold]python main.py --curriculo md[/bold] para gerar o currículo completo\n"
        "  com a seção de Projetos Executados incluída automaticamente."
    )


def acao_comparar(id1: int, id2: int) -> None:
    console.rule(f"[bold blue]Comparando coleta {id1} × {id2}")
    try:
        diffs = queries.comparar_coletas(id1, id2)
    except ValueError as exc:
        console.print(f"[bold red]{exc}")
        sys.exit(1)

    if diffs["campos"]:
        console.print("\n[bold yellow]Campos alterados:[/bold yellow]")
        for campo, vals in diffs["campos"].items():
            console.print(f"  [cyan]{campo}[/cyan]:")
            console.print(f"    antes : {vals['antes']}")
            console.print(f"    depois: {vals['depois']}")
    else:
        console.print("  Nenhuma alteração em campos de perfil.")

    for entidade in ("experiencias", "competencias", "certificacoes"):
        novos    = diffs["novos"].get(entidade, [])
        removidos = diffs["removidos"].get(entidade, [])
        if novos:
            console.print(f"\n[green]Novos em {entidade}:[/green] {novos}")
        if removidos:
            console.print(f"\n[red]Removidos de {entidade}:[/red] {removidos}")


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

def main() -> None:
    ap = build_parser()
    args = ap.parse_args()

    database.criar_tabelas()

    # Coleta
    if args.arquivo:
        acao_importar_arquivo(args.arquivo)
        return

    if args.url:
        if args.login:
            acao_coletar_com_login(args.url, visivel=args.visivel)
        elif args.interativo:
            acao_coletar_interativo(args.url)
        else:
            acao_coletar_url(
                args.url,
                usar_browser=args.browser,
                usar_chrome=args.usar_chrome,
                visivel=args.visivel,
            )
        return

    # Nenhuma fonte de entrada foi dada — verifica ações de consulta
    if args.listar:
        acao_listar()
        return

    if args.comparar:
        acao_comparar(*args.comparar)
        return

    if args.curriculo:
        acao_curriculo(args.curriculo, args.coleta)
        return

    if args.csv:
        console.rule("[bold blue]Exportando CSV")
        queries.exportar_csv(args.coleta)
        console.print("[green]Exportação concluída.[/green]")
        return

    if args.projetos:
        acao_sintetizar_projetos(args.coleta)
        return

    # Sem argumentos: tenta a URL padrão
    console.print(Panel(
        f"Nenhum argumento fornecido.\n\n"
        f"Tentando acessar URL padrão: {URL_PADRAO}\n\n"
        f"Use [bold]python main.py --help[/bold] para ver todas as opções.",
        title="LinkedIn Profile Scraper",
        border_style="blue",
    ))
    acao_coletar_url(URL_PADRAO)


if __name__ == "__main__":
    main()
