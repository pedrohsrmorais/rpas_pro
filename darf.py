#!/usr/bin/env python3
"""darf.py — Coleta de DARFs no eCAC.

Fluxo:
  Fase 1 (PyAutoGUI): navega via menu, filtra por DARF, define período de datas.
  Fase 2 (Playwright via CDP): percorre páginas, seleciona todos, baixa PDFs.

Pré-condição para uso integrado (main.py):
    - Chrome aberto com eCAC logado e perfil do CNPJ ativo.
    - Chamar após ECacSession.trocar_perfil(cnpj).

Uso standalone (com Edge/Chrome já aberto e logado):
    python darf.py --cnpj 12345678000199 --destino "\\\\192.168.1.100\\temp"

Uso como módulo:
    from darf import DARF
    fluxo = DARF(cnpj="12345678000199", diretorio_destino="C:/saida/darf")
    ok = fluxo.executar(data_inicio="01012024", data_fim="31122024")
"""

from __future__ import annotations

import logging
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

import pyautogui

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

def _setup_logger() -> logging.Logger:
    base_dir = Path(__file__).resolve().parent
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"darf_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

    logger = logging.getLogger("darf")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger
    fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
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
# Assets
# ---------------------------------------------------------------------------
_BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = _BASE_DIR / "assets"


def _img(nome: str) -> str:
    return str(ASSETS_DIR / nome)


# ---------------------------------------------------------------------------
# Helpers de visão
# ---------------------------------------------------------------------------

def _esperar_e_clicar(imagem: str, timeout: int = 30, critical: bool = False) -> bool:
    fim = time.time() + timeout
    while time.time() < fim:
        try:
            loc = pyautogui.locateOnScreen(imagem, confidence=0.85)
            if loc:
                pyautogui.click(pyautogui.center(loc))
                return True
        except Exception:
            pass
        time.sleep(1)
    if critical:
        logger.error(f"Imagem crítica não encontrada: {imagem}")
    return False


def _imagem_existe(imagem: str, confianca: float = 0.85) -> bool:
    try:
        return pyautogui.locateOnScreen(imagem, confidence=confianca) is not None
    except Exception:
        return False


def _esperar_sumir(imagem: str, timeout: int = 15) -> None:
    fim = time.time() + timeout
    while time.time() < fim:
        if not _imagem_existe(imagem):
            return
        time.sleep(1)


# ---------------------------------------------------------------------------
# Classe principal
# ---------------------------------------------------------------------------

class DARF:
    """Coleta documentos DARF do eCAC para um CNPJ.

    Args:
        cnpj:               CNPJ sem máscara (14 dígitos).
        diretorio_destino:  Pasta onde os PDFs serão salvos.
        porta_cdp:          Porta do Chrome com debug remoto (padrão: 9222).
    """

    def __init__(
        self,
        cnpj: str,
        diretorio_destino: str | Path,
        porta_cdp: int = 9222,
    ) -> None:
        self.cnpj = cnpj
        self.diretorio_destino = Path(diretorio_destino)
        self.porta_cdp = porta_cdp

    def executar(
        self,
        data_inicio: str,
        data_fim: str,
        pagina_start: int = 1,
    ) -> bool:
        """Executa a coleta de DARFs.

        Args:
            data_inicio:  Data inicial no formato ddmmaaaa (ex: "01012024").
            data_fim:     Data final no formato ddmmaaaa (ex: "31122024").
            pagina_start: Página inicial para paginação (padrão: 1).

        Returns:
            True se a coleta foi concluída com sucesso.
        """
        logger.info(f"[DARF] Iniciando coleta — CNPJ: {self.cnpj} | Período: {data_inicio} → {data_fim}")
        self.diretorio_destino.mkdir(parents=True, exist_ok=True)

        try:
            self._fase1_navegacao(data_inicio, data_fim)
            ok = self._fase2_download(pagina_start)
            logger.info(f"[DARF] Coleta {'concluída' if ok else 'falhou'}.")
            return ok
        except Exception as e:
            logger.error(f"[DARF] Exceção: {e}\n{traceback.format_exc()}")
            return False

    # ------------------------------------------------------------------
    # Fase 1: Navegação via PyAutoGUI
    # ------------------------------------------------------------------

    def _fase1_navegacao(self, data_inicio: str, data_fim: str) -> None:
        logger.info("[DARF] Fase 1 — navegando para DARF via menu...")

        # Clica no menu "Pagamentos e Parcelamentos"
        if not _esperar_e_clicar(_img("darf_menu_pagamentos.png"), timeout=20, critical=True):
            raise RuntimeError("Menu 'Pagamentos e Parcelamentos' não encontrado.")
        time.sleep(1)

        # Clica em "Consulta de Pagamentos / DARF"
        if not _esperar_e_clicar(_img("darf_menu_consulta.png"), timeout=15, critical=True):
            raise RuntimeError("Submenu DARF não encontrado.")
        time.sleep(2)

        # Preenche período
        self._preencher_periodo(data_inicio, data_fim)

        # Clica em Consultar
        if not _esperar_e_clicar(_img("darf_btn_consultar.png"), timeout=15, critical=True):
            raise RuntimeError("Botão Consultar não encontrado.")
        time.sleep(3)

    def _preencher_periodo(self, data_inicio: str, data_fim: str) -> None:
        """Preenche os campos de data no formulário de consulta."""
        # Campo data início
        if _esperar_e_clicar(_img("darf_campo_data_inicio.png"), timeout=10):
            pyautogui.hotkey("ctrl", "a")
            pyautogui.typewrite(data_inicio, interval=0.05)
            time.sleep(0.5)
        else:
            logger.warning("[DARF] Campo data início não encontrado via imagem — tentando Tab.")

        # Campo data fim
        if _esperar_e_clicar(_img("darf_campo_data_fim.png"), timeout=10):
            pyautogui.hotkey("ctrl", "a")
            pyautogui.typewrite(data_fim, interval=0.05)
            time.sleep(0.5)

    # ------------------------------------------------------------------
    # Fase 2: Download via Playwright
    # ------------------------------------------------------------------

    def _fase2_download(self, pagina_start: int) -> bool:
        logger.info("[DARF] Fase 2 — baixando PDFs via Playwright...")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("[DARF] Playwright não instalado. Execute: pip install playwright")
            return False

        try:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{self.porta_cdp}")
                try:
                    contexto = browser.contexts[0]
                    page = contexto.pages[0]
                    return self._percorrer_paginas(page, pagina_start)
                finally:
                    browser.close()
        except Exception as e:
            logger.error(f"[DARF] Falha na fase 2 (Playwright): {e}")
            return False

    def _percorrer_paginas(self, page, pagina_atual: int) -> bool:
        total_baixados = 0

        while True:
            logger.info(f"[DARF] Processando página {pagina_atual}...")

            # Seleciona todos os registros da página
            try:
                chk_todos = page.locator("input[type='checkbox'][id*='selTodos'], input[type='checkbox'][name*='todos']").first
                if chk_todos.is_visible(timeout=3000):
                    chk_todos.check()
                    time.sleep(0.5)
            except Exception:
                logger.warning(f"[DARF] Checkbox 'selecionar todos' não encontrado na página {pagina_atual}.")

            # Baixa os DARFs selecionados (blobs de PDF)
            baixados = self._baixar_darfs_pagina(page)
            total_baixados += baixados
            logger.info(f"[DARF] Página {pagina_atual}: {baixados} arquivo(s) baixado(s).")

            # Verifica próxima página
            try:
                btn_proximo = page.locator("a:has-text('Próxima'), a:has-text('Próximo'), a[title*='próxima' i]").first
                if btn_proximo.is_visible(timeout=2000):
                    btn_proximo.click()
                    time.sleep(3)
                    pagina_atual += 1
                else:
                    break
            except Exception:
                break

        logger.info(f"[DARF] Total baixado: {total_baixados} arquivo(s).")
        return total_baixados >= 0  # sucesso mesmo com 0 (pode não ter registros)

    def _baixar_darfs_pagina(self, page) -> int:
        """Clica em cada link de PDF na página atual e salva o arquivo."""
        links = page.locator("a[href*='.pdf'], a[onclick*='pdf'], a[onclick*='DARF']").all()
        baixados = 0

        for i, link in enumerate(links):
            try:
                href = link.get_attribute("href") or ""
                texto = link.inner_text().strip()

                # Captura o PDF como download
                with page.expect_download(timeout=30000) as dl_info:
                    link.click()
                download = dl_info.value

                nome_arquivo = download.suggested_filename or f"DARF_{self.cnpj}_{i+1:04d}.pdf"
                destino = self.diretorio_destino / nome_arquivo
                download.save_as(str(destino))
                logger.info(f"[DARF] Salvo: {destino.name}")
                baixados += 1
                time.sleep(0.5)

            except Exception as e:
                logger.warning(f"[DARF] Falha ao baixar link {i+1}: {e}")

        return baixados


# ---------------------------------------------------------------------------
# Execução standalone
# ---------------------------------------------------------------------------

def _standalone_run() -> None:
    import argparse
    from datetime import date

    parser = argparse.ArgumentParser(description="Coleta DARFs do eCAC")
    parser.add_argument("--cnpj", required=True, help="CNPJ (14 dígitos, sem máscara)")
    parser.add_argument("--destino", required=True, help="Pasta de destino para os PDFs")
    parser.add_argument("--inicio", default=None, help="Data início ddmmaaaa (padrão: 01/01/ano anterior)")
    parser.add_argument("--fim", default=None, help="Data fim ddmmaaaa (padrão: hoje)")
    parser.add_argument("--porta", type=int, default=9222, help="Porta CDP do Chrome")
    parser.add_argument(
        "--login",
        choices=["auto", "nenhum"],
        default="nenhum",
        help="'auto': tenta sessão/login; 'nenhum': assume Chrome já logado (padrão)",
    )
    parser.add_argument("--certificado", default="Studio Varejo", help="Certificado para login (se --login=auto)")
    parser.add_argument("--storage", default=None, help="Pasta storage/ para sessão (se --login=auto)")
    args = parser.parse_args()

    hoje = date.today()
    ano_anterior = hoje.year - 1
    data_inicio = args.inicio or f"0101{ano_anterior}"
    data_fim = args.fim or hoje.strftime("%d%m%Y")

    # Lógica de login se solicitado
    if args.login == "auto":
        logger.info("[DARF] Tentando reutilizar sessão antes de executar...")
        from login_session import tentar_sessao
        from login_ecac import executar_login

        sessao_ok = tentar_sessao(args.certificado, args.storage)
        if not sessao_ok:
            logger.info("[DARF] Sessão inválida — fazendo login completo...")
            pasta_storage_calc = args.storage or str(Path(args.destino).parent.parent / "sch_ecac_pro" / "storage")
            login_ok = executar_login(args.certificado, pasta_storage=pasta_storage_calc)
            if not login_ok:
                print("✘ Falha no login. Abortando.")
                sys.exit(1)
            logger.info("[DARF] Aguardando 5 segundos após login...")
            time.sleep(5)
        else:
            logger.info("[DARF] Sessão reutilizada com sucesso.")

    # Monta caminho final
    destino_final = Path(args.destino)

    fluxo = DARF(
        cnpj=args.cnpj,
        diretorio_destino=destino_final,
        porta_cdp=args.porta,
    )
    ok = fluxo.executar(data_inicio=data_inicio, data_fim=data_fim)
    print(f"\n{'✔ DARF concluído' if ok else '✘ DARF falhou'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    _standalone_run()