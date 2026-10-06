#!/usr/bin/env python3
"""fontes_pagadoras.py — Coleta de Fontes Pagadoras no eCAC.

Pré-condição para uso integrado (main.py):
    - Chrome aberto com eCAC logado e perfil do CNPJ ativo.
    - ECacSession.conectar_playwright() já chamado (ou usar standalone).

Fluxo:
  1. (Opcional) Descobre filiais via cadastro público (antes do login)
  2. Navega: Declarações → Consulta Rendimentos Informados por Fontes Pagadoras
  3. Loop de anos: seleciona ano → consulta → baixa TXT → salva PDF
  4. Repete para filiais (se coletar_filiais=True)

Uso standalone (com Edge/Chrome já aberto e logado):
    python fontes_pagadoras.py --cnpj 12345678000199 --destino "\\\\192.168.1.100\\temp"

Uso como módulo (via main.py):
    from fontes_pagadoras import FontesPagadoras
    fp = FontesPagadoras(cnpj="12345678000199", ano_inicio=2024, ano_fim=2024)
    ok = fp.executar(porta_cdp=9222, diretorio_destino="C:/saida/fontes_pagadoras")
"""

from __future__ import annotations

import logging
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
    log_file = log_dir / f"fontes_pagadoras_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

    logger = logging.getLogger("fontes_pagadoras")
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


# ---------------------------------------------------------------------------
# Resultado simplificado (compatível com main.py)
# ---------------------------------------------------------------------------

class ResultadoColeta:
    def __init__(self) -> None:
        self.total: int = 0
        self.arquivos: list[str] = []

    def absorver(self, outro: "ResultadoColeta") -> None:
        self.total += outro.total
        self.arquivos.extend(outro.arquivos)


# ---------------------------------------------------------------------------
# Classe principal
# ---------------------------------------------------------------------------

class FontesPagadoras:
    """Coleta TXT + PDF de Fontes Pagadoras do eCAC para um CNPJ.

    Args:
        cnpj:              CNPJ da matriz (14 dígitos, sem máscara).
        razao_social:      Razão social (usada na comparação com filiais).
        coletar_filiais:   Se True, coleta filiais após a matriz.
        ano_inicio:        Primeiro ano-calendário (ex: 2024).
        ano_fim:           Último ano-calendário (ex: 2024). None = ano atual.
    """

    def __init__(
        self,
        cnpj: str,
        razao_social: Optional[str] = None,
        coletar_filiais: bool = False,
        ano_inicio: int = 2024,
        ano_fim: Optional[int] = None,
    ) -> None:
        self.cnpj = cnpj
        self.razao_social = razao_social
        self.coletar_filiais = coletar_filiais
        self.ano_inicio = ano_inicio
        self.ano_fim = ano_fim or datetime.now().year

    def executar(
        self,
        porta_cdp: int = 9222,
        diretorio_destino: Optional[str | Path] = None,
    ) -> tuple[bool, ResultadoColeta]:
        """Executa a coleta de Fontes Pagadoras.

        Args:
            porta_cdp:           Porta do Chrome com depuração remota.
            diretorio_destino:   Pasta de destino (opcional, usa pasta padrão se None).

        Returns:
            Tupla (sucesso: bool, resultado: ResultadoColeta).
        """
        coleta = ResultadoColeta()

        if diretorio_destino:
            destino = Path(diretorio_destino)
            destino.mkdir(parents=True, exist_ok=True)
        else:
            destino = None

        logger.info(
            f"[FP] Iniciando — CNPJ: {self.cnpj} | "
            f"Anos: {self.ano_inicio}→{self.ano_fim} | "
            f"Filiais: {self.coletar_filiais}"
        )

        try:
            # Tenta usar os módulos do projeto original Fontes Pagadoras
            result = self._executar_via_modulos_originais(porta_cdp, destino)
            if result is not None:
                return True, result

            # Fallback: fluxo próprio via PyAutoGUI + Playwright
            return self._executar_fluxo_proprio(porta_cdp, destino, coleta)

        except Exception as e:
            logger.error(f"[FP] Exceção: {e}\n{traceback.format_exc()}")
            return False, coleta

    def _executar_via_modulos_originais(
        self,
        porta_cdp: int,
        destino: Optional[Path],
    ) -> Optional[ResultadoColeta]:
        """Tenta usar os módulos originais do projeto Fontes Pagadoras."""
        try:
            from core.ecac import ECac
            from core.navegador import Navegador
            from core.execucao import registrar_execucao
            from core.coleta import coletar_estabelecimento, ResultadoColeta as RC_orig
            from core.saida import pasta_de_saida, reiniciar_deteccao
        except ImportError:
            return None  # módulos não disponíveis — usa fluxo próprio

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return None

        logger.info("[FP] Usando módulos originais do projeto Fontes Pagadoras.")

        try:
            reiniciar_deteccao()
            pasta = destino or pasta_de_saida(self.cnpj)

            registro = registrar_execucao(f"fp_{self.cnpj}")

            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{porta_cdp}")
                try:
                    contexto = browser.contexts[0]
                    page = contexto.pages[0]

                    from core.web import SessaoWeb
                    web = SessaoWeb()
                    web._page = page
                    web._context = contexto

                    navegador = Navegador()
                    ecac = ECac(navegador, cnpj_certificado=None, nome_certificado=None)
                    ecac.web = web

                    from fontes_pagadoras_wrapper import FontesPagadoras as FP_orig
                    fluxo = FP_orig(
                        ecac=ecac,
                        cnpj=self.cnpj,
                        razao_social=self.razao_social,
                        coletar_filiais=self.coletar_filiais,
                        ano_inicio=self.ano_inicio,
                        ano_fim=self.ano_fim,
                    )
                    coleta_orig = fluxo.executar(registro=registro)
                    registro.finalizar("SUCESSO")

                    # Converte para ResultadoColeta simplificado
                    resultado = ResultadoColeta()
                    resultado.total = getattr(coleta_orig, "total", 0)
                    resultado.arquivos = getattr(coleta_orig, "arquivos", [])
                    return resultado

                finally:
                    browser.close()

        except Exception as e:
            logger.warning(f"[FP] Módulos originais falharam: {e} — usando fluxo próprio.")
            return None

    def _executar_fluxo_proprio(
        self,
        porta_cdp: int,
        destino: Optional[Path],
        coleta: ResultadoColeta,
    ) -> tuple[bool, ResultadoColeta]:
        """Fluxo próprio via PyAutoGUI + Playwright (sem dependência dos módulos originais)."""
        logger.info("[FP] Usando fluxo próprio (PyAutoGUI + Playwright).")

        if not destino:
            destino = Path(__file__).resolve().parent / "saida" / self.cnpj / "fontes_pagadoras"
            destino.mkdir(parents=True, exist_ok=True)

        try:
            self._navegar_para_fontes_pagadoras()
        except Exception as e:
            logger.error(f"[FP] Falha ao navegar: {e}")
            return False, coleta

        for ano in range(self.ano_inicio, self.ano_fim + 1):
            try:
                arquivos_ano = self._coletar_ano(ano, porta_cdp, destino)
                coleta.total += len(arquivos_ano)
                coleta.arquivos.extend(arquivos_ano)
                logger.info(f"[FP] Ano {ano}: {len(arquivos_ano)} arquivo(s).")
            except Exception as e:
                logger.error(f"[FP] Falha no ano {ano}: {e}")

        logger.info(f"[FP] Coleta concluída: {coleta.total} arquivo(s).")
        return True, coleta

    def _navegar_para_fontes_pagadoras(self) -> None:
        logger.info("[FP] Navegando para Fontes Pagadoras via menu...")

        # Menu Declarações
        if not _esperar_e_clicar(_img("fp_menu_declaracoes.png"), timeout=20, critical=True):
            raise RuntimeError("Menu 'Declarações' não encontrado.")
        time.sleep(1)

        # Submenu Fontes Pagadoras
        if not _esperar_e_clicar(_img("fp_menu_fontes_pagadoras.png"), timeout=15, critical=True):
            raise RuntimeError("Submenu Fontes Pagadoras não encontrado.")
        time.sleep(2)

        # Entra no iframe do serviço
        logger.info("[FP] Aguardando carregamento do iframe...")
        time.sleep(3)

    def _coletar_ano(self, ano: int, porta_cdp: int, destino: Path) -> list[str]:
        """Coleta os arquivos de um ano-calendário específico."""
        logger.info(f"[FP] Coletando ano {ano}...")
        arquivos = []

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("[FP] Playwright não instalado.")
            return arquivos

        try:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{porta_cdp}")
                try:
                    contexto = browser.contexts[0]
                    page = contexto.pages[0]

                    # Seleciona o ano no formulário
                    try:
                        select_ano = page.locator(f"select option[value='{ano}']").first
                        if select_ano.is_visible(timeout=3000):
                            page.select_option("select", str(ano))
                            time.sleep(1)
                    except Exception:
                        logger.warning(f"[FP] Não foi possível selecionar o ano {ano} via select.")

                    # Clica em Consultar
                    try:
                        btn = page.locator("button:has-text('Consultar'), input[value='Consultar']").first
                        if btn.is_visible(timeout=5000):
                            btn.click()
                            time.sleep(3)
                    except Exception:
                        logger.warning(f"[FP] Botão Consultar não encontrado para o ano {ano}.")

                    # Baixa TXT e PDF
                    arqs_txt = self._baixar_arquivo(page, "txt", ano, destino)
                    arqs_pdf = self._baixar_arquivo(page, "pdf", ano, destino)
                    arquivos.extend(arqs_txt)
                    arquivos.extend(arqs_pdf)

                finally:
                    browser.close()

        except Exception as e:
            logger.error(f"[FP] Erro ao coletar ano {ano}: {e}")

        return arquivos

    def _baixar_arquivo(
        self,
        page,
        tipo: str,
        ano: int,
        destino: Path,
    ) -> list[str]:
        """Baixa arquivos de um tipo específico (txt ou pdf) da página atual."""
        seletores = {
            "txt": ["a:has-text('.txt'), a[href*='.txt'], a[onclick*='txt']"],
            "pdf": ["a:has-text('.pdf'), a[href*='.pdf'], a[onclick*='pdf']"],
        }
        arquivos = []

        for seletor in seletores.get(tipo, []):
            try:
                links = page.locator(seletor).all()
                for i, link in enumerate(links):
                    try:
                        with page.expect_download(timeout=30000) as dl_info:
                            link.click()
                        download = dl_info.value
                        nome = download.suggested_filename or f"FP_{self.cnpj}_{ano}_{tipo}_{i+1:04d}.{tipo}"
                        caminho = destino / nome
                        download.save_as(str(caminho))
                        arquivos.append(str(caminho))
                        logger.info(f"[FP] Salvo: {nome}")
                        time.sleep(0.5)
                    except Exception as e:
                        logger.warning(f"[FP] Falha ao baixar {tipo} link {i+1}: {e}")
            except Exception:
                pass

        return arquivos


# ---------------------------------------------------------------------------
# Execução standalone
# ---------------------------------------------------------------------------

def _standalone_run() -> None:
    import argparse
    from datetime import date

    parser = argparse.ArgumentParser(description="Coleta Fontes Pagadoras do eCAC")
    parser.add_argument("--cnpj", required=True, help="CNPJ (14 dígitos, sem máscara)")
    parser.add_argument("--destino", required=True, help="Pasta de destino para os arquivos")
    parser.add_argument("--razao-social", default=None, help="Razão social (opcional)")
    parser.add_argument("--ano-inicio", type=int, default=None, help="Ano início (padrão: ano anterior)")
    parser.add_argument("--ano-fim", type=int, default=None, help="Ano fim (padrão: ano anterior)")
    parser.add_argument("--filiais", action="store_true", help="Coletar também filiais")
    parser.add_argument("--porta", type=int, default=9222, help="Porta CDP do Chrome")
    parser.add_argument(
        "--login",
        choices=["auto", "nenhum"],
        default="nenhum",
        help="'auto': tenta sessão/login; 'nenhum': assume Chrome já logado (padrão)",
    )
    parser.add_argument("--certificado", default="Studio Varejo", help="Certificado para login")
    parser.add_argument("--storage", default=None, help="Pasta storage/ para sessão")
    args = parser.parse_args()

    hoje = date.today()
    ano_anterior = hoje.year - 1
    ano_inicio = args.ano_inicio or ano_anterior
    ano_fim = args.ano_fim or ano_anterior

    if args.login == "auto":
        logger.info("[FP] Tentando reutilizar sessão...")
        from login_session import tentar_sessao
        from login_ecac import executar_login

        sessao_ok = tentar_sessao(args.certificado, args.storage)
        if not sessao_ok:
            logger.info("[FP] Sessão inválida — fazendo login completo...")
            pasta_storage_calc = args.storage or str(Path(args.destino).parent.parent / "sch_ecac_pro" / "storage")
            login_ok = executar_login(args.certificado, pasta_storage=pasta_storage_calc)
            if not login_ok:
                print("✘ Falha no login. Abortando.")
                sys.exit(1)
            logger.info("[FP] Aguardando 5 segundos após login...")
            time.sleep(5)
        else:
            logger.info("[FP] Sessão reutilizada.")

    fluxo = FontesPagadoras(
        cnpj=args.cnpj,
        razao_social=args.razao_social,
        coletar_filiais=args.filiais,
        ano_inicio=ano_inicio,
        ano_fim=ano_fim,
    )
    ok, coleta = fluxo.executar(porta_cdp=args.porta, diretorio_destino=args.destino)
    print(f"\n{'✔ Fontes Pagadoras concluído' if ok else '✘ Fontes Pagadoras falhou'}: {coleta.total} arquivo(s)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    _standalone_run()