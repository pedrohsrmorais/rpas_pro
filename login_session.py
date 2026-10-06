#!/usr/bin/env python3
"""login_session.py — Reutiliza sessão existente do eCAC via cookies salvos.

Tenta restaurar uma sessão anterior sem fazer login completo:
  1. Lê o JSON de sessão da pasta storage/
  2. Conecta ao Chrome via CDP (Playwright)
  3. Injeta os cookies salvos no contexto do navegador
  4. Navega para o eCAC e verifica se a sessão ainda é válida

Se a sessão estiver expirada ou inválida, retorna False e o chamador
deve acionar o login_ecac.py para fazer o login completo.

Uso standalone:
    python login_session.py --certificado "Studio Varejo" --storage "C:/RPA/sch_ecac_pro/storage"

Uso como módulo:
    from login_session import tentar_sessao
    ok = tentar_sessao("Studio Varejo", pasta_storage="C:/RPA/sch_ecac_pro/storage")
"""

from __future__ import annotations

import json
import logging
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

def _setup_logger() -> logging.Logger:
    base_dir = Path(__file__).resolve().parent
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"session_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

    logger = logging.getLogger("login_session")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    logger.propagate = False
    return logger


logger = _setup_logger()

# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------
URL_ECAC_HOME = "https://cav.receita.fazenda.gov.br/eCAC/publico/login.aspx"
URL_ECAC_BASE = "cav.receita.fazenda.gov.br"

# Tempo máximo de validade de uma sessão (em horas). Após isso, considera expirada.
SESSION_MAX_AGE_HORAS = 8

REMOTE_DEBUGGING_PORT = 9222

# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def _normalizar_nome(valor: str) -> str:
    texto = (valor or "").replace("\xa0", " ").strip().upper()
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


def _slug_certificado(nome: str) -> str:
    return _normalizar_nome(nome).replace(" ", "_").lower()


def _encontrar_arquivo_sessao(certificado_nome: str, pasta_storage: str | Path) -> Optional[Path]:
    """Localiza o arquivo JSON de sessão para o certificado informado."""
    pasta = Path(pasta_storage)
    if not pasta.exists():
        logger.warning(f"Pasta storage não existe: {pasta}")
        return None

    slug = _slug_certificado(certificado_nome)
    candidato = pasta / f"session_{slug}.json"
    if candidato.exists():
        return candidato

    # Busca qualquer arquivo session_*.json se não encontrou pelo slug
    arquivos = sorted(pasta.glob("session_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if arquivos:
        logger.info(f"Arquivo de sessão para '{certificado_nome}' não encontrado pelo slug — usando o mais recente: {arquivos[0]}")
        return arquivos[0]

    return None


def _carregar_sessao(arquivo: Path) -> Optional[dict]:
    """Carrega e valida o JSON de sessão."""
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Falha ao ler sessão em '{arquivo}': {e}")
        return None

    login_at_str = dados.get("login_at", "")
    if not login_at_str:
        logger.warning("Sessão sem timestamp 'login_at'.")
        return None

    try:
        login_at = datetime.fromisoformat(login_at_str)
    except ValueError:
        logger.warning(f"Timestamp inválido: {login_at_str}")
        return None

    idade = datetime.now() - login_at
    max_age = timedelta(hours=SESSION_MAX_AGE_HORAS)
    if idade > max_age:
        logger.warning(
            f"Sessão expirada: login feito há {idade.total_seconds() / 3600:.1f}h "
            f"(máximo: {SESSION_MAX_AGE_HORAS}h)"
        )
        return None

    logger.info(
        f"Sessão carregada: certificado='{dados.get('certificado_nome')}', "
        f"login há {idade.total_seconds() / 60:.0f} minutos"
    )
    return dados


def _checar_porta_cdp(porta: int) -> bool:
    """Verifica se há um Chrome com CDP ativo na porta informada."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/json/version", timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _injetar_cookies_e_navegar(cookies: list[dict], porta: int) -> bool:
    """Injeta os cookies no contexto do Playwright e verifica acesso ao eCAC."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright não instalado. Execute: pip install playwright")
        return False

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}")
            try:
                contexto = browser.contexts[0]

                # Formatar cookies para o Playwright
                cookies_pw = []
                for c in cookies:
                    cookie = {
                        "name":     c.get("nome", ""),
                        "value":    c.get("valor", ""),
                        "domain":   c.get("dominio", ""),
                        "path":     c.get("path", "/"),
                        "httpOnly": c.get("http_only", False),
                        "secure":   c.get("secure", False),
                    }
                    samesite = c.get("samesite", "")
                    if samesite in ("Strict", "Lax", "None"):
                        cookie["sameSite"] = samesite
                    expira = c.get("expira", -1)
                    if expira and expira > 0:
                        cookie["expires"] = expira
                    if cookie["name"] and cookie["value"] and cookie["domain"]:
                        cookies_pw.append(cookie)

                if cookies_pw:
                    contexto.add_cookies(cookies_pw)
                    logger.info(f"{len(cookies_pw)} cookie(s) injetado(s) no contexto.")
                else:
                    logger.warning("Nenhum cookie válido para injetar.")

                # Navega para o eCAC e verifica se está logado
                page = contexto.pages[0] if contexto.pages else contexto.new_page()
                page.goto(URL_ECAC_HOME, timeout=30000, wait_until="domcontentloaded")
                time.sleep(3)

                url_atual = page.url.lower()
                logger.info(f"URL após injeção de cookies: {url_atual}")

                # Verifica se está na área autenticada (não voltou para login)
                if URL_ECAC_BASE in url_atual and "login" not in url_atual:
                    logger.info("Sessão válida — usuário está autenticado no eCAC.")
                    return True

                # Tenta verificar via conteúdo da página
                try:
                    conteudo = page.content().lower()
                    if "sair" in conteudo or "encerrar sessão" in conteudo or "minha conta" in conteudo:
                        logger.info("Sessão válida — elementos de usuário autenticado encontrados.")
                        return True
                except Exception:
                    pass

                logger.info("Sessão expirada ou inválida — login completo necessário.")
                return False

            finally:
                browser.close()

    except Exception as e:
        logger.warning(f"Falha ao conectar via CDP / injetar cookies: {e}")
        return False


# ---------------------------------------------------------------------------
# Ponto de entrada público
# ---------------------------------------------------------------------------

def tentar_sessao(
    certificado_nome: str = "Studio Varejo",
    pasta_storage: Optional[str | Path] = None,
    porta_cdp: int = REMOTE_DEBUGGING_PORT,
) -> bool:
    """Tenta reutilizar uma sessão existente do eCAC.

    Args:
        certificado_nome: Nome do certificado (ex: "Studio Varejo").
        pasta_storage:    Pasta onde os arquivos session_*.json estão.
        porta_cdp:        Porta do Chrome com depuração remota ativa.

    Returns:
        True se a sessão foi restaurada com sucesso.
        False se a sessão expirou, não existe ou o Chrome não está acessível.
    """
    logger.info(f"=== Tentando reutilizar sessão para '{certificado_nome}' ===")

    if not pasta_storage:
        logger.warning("pasta_storage não informada — sessão não pode ser verificada.")
        return False

    # 1) Verifica se Chrome está com CDP ativo
    if not _checar_porta_cdp(porta_cdp):
        logger.info(f"Chrome com CDP não encontrado na porta {porta_cdp}.")
        return False

    # 2) Localiza arquivo de sessão
    arquivo = _encontrar_arquivo_sessao(certificado_nome, pasta_storage)
    if not arquivo:
        logger.info(f"Nenhum arquivo de sessão encontrado para '{certificado_nome}'.")
        return False

    # 3) Carrega e valida a sessão
    sessao = _carregar_sessao(arquivo)
    if not sessao:
        return False

    # 4) Injeta cookies e verifica acesso
    cookies = sessao.get("cookies", [])
    porta = sessao.get("porta_cdp", porta_cdp)

    if not cookies:
        logger.warning("Sessão sem cookies — login completo necessário.")
        return False

    return _injetar_cookies_e_navegar(cookies, porta)


# ---------------------------------------------------------------------------
# Execução standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Tenta reutilizar sessão eCAC existente")
    parser.add_argument(
        "--certificado",
        default="Studio Varejo",
        help="Nome do certificado",
    )
    parser.add_argument(
        "--storage",
        required=True,
        help="Pasta com os arquivos de sessão JSON (ex: C:\\RPA\\sch_ecac_pro\\storage)",
    )
    parser.add_argument(
        "--porta",
        type=int,
        default=REMOTE_DEBUGGING_PORT,
        help=f"Porta CDP do Chrome (padrão: {REMOTE_DEBUGGING_PORT})",
    )
    args = parser.parse_args()

    ok = tentar_sessao(
        certificado_nome=args.certificado,
        pasta_storage=args.storage,
        porta_cdp=args.porta,
    )
    print(f"\n{'✔ Sessão reutilizada com sucesso' if ok else '✘ Sessão inválida ou expirada'}")
    sys.exit(0 if ok else 1)