#!/usr/bin/env python3
"""ecac_session.py — Gerencia a sessão ativa no eCAC após o login.

Responsabilidades:
  - Trocar o perfil de atuação para um CNPJ (PyAutoGUI + assets/)
  - Voltar para a home entre serviços ou CNPJs
  - Verificar bloqueios pós-troca (sem procuração, CNPJ inválido)
  - Conectar o Playwright via CDP para os fluxos que precisam do DOM

Pré-condição: login_ecac.py já executou e o Chrome/Edge está aberto
na home do eCAC. Todas as imagens de referência devem estar em assets/.

Uso como módulo:
    from ecac_session import ECacSession
    sessao = ECacSession()
    sessao.trocar_perfil("12345678000199")
    context, page = sessao.conectar_playwright()
"""

from __future__ import annotations

import logging
import re
import time
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
    log_file = log_dir / f"ecac_session_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

    logger = logging.getLogger("ecac_session")
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
    """Retorna o caminho completo de uma imagem em assets/."""
    return str(ASSETS_DIR / nome)


# ---------------------------------------------------------------------------
# Helpers de visão (PyAutoGUI)
# ---------------------------------------------------------------------------

def esperar_e_clicar(imagem: str, timeout: int = 30, critical: bool = False) -> bool:
    """Aguarda a imagem aparecer na tela e clica no centro dela.

    Args:
        imagem:   Nome do arquivo PNG em assets/.
        timeout:  Tempo máximo de espera em segundos.
        critical: Se True, registra erro em caso de timeout.

    Returns:
        True se a imagem foi encontrada e clicada, False caso contrário.
    """
    caminho = _img(imagem)
    fim = time.time() + timeout
    while time.time() < fim:
        try:
            loc = pyautogui.locateOnScreen(caminho, confidence=0.85)
            if loc:
                pyautogui.click(pyautogui.center(loc))
                return True
        except Exception:
            pass
        time.sleep(1)
    if critical:
        logger.error(f"Imagem crítica não encontrada: {imagem}")
    return False


def imagem_existe(imagem: str, confianca: float = 0.85) -> bool:
    """Verifica se a imagem está visível na tela (sem clicar).

    Args:
        imagem:    Nome do arquivo PNG em assets/.
        confianca: Threshold de confiança (0.0–1.0).

    Returns:
        True se a imagem for encontrada na tela.
    """
    try:
        return pyautogui.locateOnScreen(_img(imagem), confidence=confianca) is not None
    except Exception:
        return False


def esperar_sumir(imagem: str, timeout: int = 15) -> None:
    """Aguarda a imagem desaparecer da tela.

    Args:
        imagem:  Nome do arquivo PNG em assets/.
        timeout: Tempo máximo de espera em segundos.
    """
    fim = time.time() + timeout
    while time.time() < fim:
        if not imagem_existe(imagem):
            return
        time.sleep(1)


# ---------------------------------------------------------------------------
# Exceções
# ---------------------------------------------------------------------------

class ECacSessionError(Exception):
    """Exceção base para erros de sessão eCAC."""


class CriticalImageNotFoundError(ECacSessionError):
    def __init__(self, imagem: str, descricao: str = "") -> None:
        super().__init__(f"Imagem crítica não encontrada: '{imagem}'. {descricao}")
        self.imagem = imagem


class CNPJBlockedMessageError(ECacSessionError):
    def __init__(self) -> None:
        super().__init__("Mensagem de pendência/bloqueio detectada no eCAC.")


class InvalidCNPJError(ECacSessionError):
    def __init__(self) -> None:
        super().__init__("CNPJ inválido ou não reconhecido pelo portal.")


class SemProcuracaoError(ECacSessionError):
    def __init__(self, cnpj: str = "") -> None:
        super().__init__(f"Sem procuração cadastrada para o CNPJ: {cnpj}")
        self.cnpj = cnpj


# ---------------------------------------------------------------------------
# Classe principal
# ---------------------------------------------------------------------------

class ECacSession:
    """Representa uma sessão autenticada no eCAC.

    Criada após login_ecac.py concluir. Mantém o CNPJ atualmente ativo
    no perfil e expõe os métodos comuns a todos os fluxos de coleta.

    Todas as imagens de referência devem estar na pasta assets/.
    """

    def __init__(self, porta_cdp: int = 9222) -> None:
        self.cnpj_atual: Optional[str] = None
        self.porta_cdp = porta_cdp
        self._playwright_page = None
        self._playwright_context = None
        self._playwright_browser = None

    # ------------------------------------------------------------------
    # Troca de perfil
    # ------------------------------------------------------------------

    def trocar_perfil(self, cnpj_bruto: str) -> bool:
        """Troca o perfil de atuação para o CNPJ informado via PyAutoGUI.

        Clica no botão de alterar perfil, preenche o CNPJ e confirma.
        Verifica bloqueios conhecidos após a troca.

        Args:
            cnpj_bruto: CNPJ com ou sem máscara.

        Returns:
            True se a troca foi bem-sucedida.

        Raises:
            CriticalImageNotFoundError: Se alguma imagem crítica não for encontrada.
            CNPJBlockedMessageError:    Se o eCAC exibir mensagem de pendência.
            InvalidCNPJError:           Se o CNPJ for recusado como inválido.
            SemProcuracaoError:         Se não houver procuração para este CNPJ.
        """
        cnpj = re.sub(r"\D", "", cnpj_bruto)
        logger.info(f"Trocando perfil para CNPJ: {cnpj}")

        # Clica no botão de alterar perfil de atuação
        if not esperar_e_clicar("perfil_acesso.png", timeout=30, critical=True):
            raise CriticalImageNotFoundError("perfil_acesso.png", "Botão de perfil não encontrado")
        time.sleep(1)

        # Preenche o campo CNPJ
        if not esperar_e_clicar("campo_cnpj.png", timeout=15, critical=True):
            raise CriticalImageNotFoundError("campo_cnpj.png", "Campo CNPJ não encontrado")
        pyautogui.hotkey("ctrl", "a")
        pyautogui.typewrite(cnpj, interval=0.02)
        time.sleep(0.5)
        pyautogui.press("tab")
        time.sleep(0.5)

        # Confirma a troca de perfil
        if not esperar_e_clicar("btn_alterar.png", timeout=10, critical=True):
            raise CriticalImageNotFoundError("btn_alterar.png", "Botão alterar não encontrado")

        # Aguarda o botão sumir (transição de perfil ocorreu)
        esperar_sumir("btn_alterar.png", timeout=15)
        time.sleep(1)

        # Verificações de bloqueio pós-troca
        if imagem_existe("sem_procuracao.png", confianca=0.85):
            logger.error(f"Sem procuração detectada para o CNPJ {cnpj}.")
            raise SemProcuracaoError(cnpj)

        if imagem_existe("mensagem_cnpj.png", confianca=0.9):
            logger.error(f"Mensagem de pendência detectada para o CNPJ {cnpj}.")
            raise CNPJBlockedMessageError()

        if imagem_existe("cnpj_invalido.png", confianca=0.9):
            logger.error(f"CNPJ {cnpj} inválido no portal.")
            raise InvalidCNPJError()

        self.cnpj_atual = cnpj
        logger.info(f"Perfil trocado com sucesso para {cnpj}.")
        return True

    # ------------------------------------------------------------------
    # Navegação de retorno
    # ------------------------------------------------------------------

    def voltar_home(self) -> bool:
        """Retorna para a home do eCAC clicando no botão Home.

        Usado entre serviços ou entre CNPJs de um lote para garantir
        um ponto de partida conhecido.

        Returns:
            True após navegação (melhor esforço).
        """
        logger.info("Voltando para a home do eCAC...")

        if esperar_e_clicar("btn_home.png", timeout=15, critical=False):
            time.sleep(3)
            logger.info("Home do eCAC alcançada.")
            return True

        # Fallback: recarrega a página com F5
        logger.warning("btn_home.png não encontrado — tentando F5.")
        pyautogui.press("f5")
        time.sleep(3)
        return True

    # ------------------------------------------------------------------
    # Playwright / CDP
    # ------------------------------------------------------------------

    def conectar_playwright(self):
        """Conecta o Playwright ao Chrome/Edge já aberto via CDP.

        Deve ser chamado pelos fluxos que precisam do DOM (DARF loop,
        Fontes Pagadoras, etc.). Retorna (context, page) do Playwright.

        Returns:
            Tupla (context, page) do Playwright.

        Raises:
            RuntimeError: Se não conseguir conectar ao Chrome via CDP.
        """
        if self._playwright_page is not None:
            return self._playwright_context, self._playwright_page

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Playwright não instalado. Execute: pip install playwright")

        try:
            playwright = sync_playwright().start()
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{self.porta_cdp}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()

            self._playwright_browser = browser
            self._playwright_context = context
            self._playwright_page = page
            self._playwright_instance = playwright
            logger.info(f"Playwright conectado via CDP na porta {self.porta_cdp}.")
            return context, page

        except Exception as e:
            raise RuntimeError(f"Falha ao conectar Playwright via CDP (porta {self.porta_cdp}): {e}") from e

    def encerrar_playwright(self) -> None:
        """Desconecta o Playwright sem fechar o Chrome/Edge."""
        try:
            if self._playwright_browser:
                self._playwright_browser.close()
            if hasattr(self, "_playwright_instance") and self._playwright_instance:
                self._playwright_instance.stop()
        except Exception as e:
            logger.debug(f"Erro ao encerrar Playwright: {e}")
        finally:
            self._playwright_page = None
            self._playwright_context = None
            self._playwright_browser = None
            logger.info("Playwright desconectado.")

    # ------------------------------------------------------------------
    # Utilitários
    # ------------------------------------------------------------------

    @staticmethod
    def limpar_cnpj(cnpj_bruto: str) -> str:
        """Remove máscara do CNPJ e retorna 14 dígitos numéricos."""
        return re.sub(r"\D", "", cnpj_bruto)

    def __enter__(self) -> "ECacSession":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.encerrar_playwright()