#!/usr/bin/env python3
"""dctfweb.py — Coleta de declarações DCTFWeb no eCAC.

100% PyAutoGUI — navega pelo menu do eCAC, processa períodos anuais
e baixa os PDFs de Declaração Completa.

Pré-condição para uso integrado (main.py):
    - Chrome aberto com eCAC logado e perfil do CNPJ ativo.

Uso standalone (com Edge/Chrome já aberto e logado):
    python dctfweb.py --cnpj 12345678000199 --destino "\\\\192.168.1.100\\temp"

Uso como módulo:
    from dctfweb import DCTFWeb
    fluxo = DCTFWeb(cnpj="12345678000199", diretorio_destino="C:/saida/dctf")
    ok, arquivos = fluxo.executar("01012024", "31122024")
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
    log_file = log_dir / f"dctfweb_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

    logger = logging.getLogger("dctfweb")
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
# Classe principal
# ---------------------------------------------------------------------------

class DCTFWeb:
    """Coleta PDFs de DCTFWeb do eCAC para um CNPJ.

    Args:
        cnpj:               CNPJ sem máscara (14 dígitos).
        diretorio_destino:  Pasta onde os PDFs serão salvos.
    """

    def __init__(self, cnpj: str, diretorio_destino: str | Path) -> None:
        self.cnpj = cnpj
        self.diretorio_destino = Path(diretorio_destino)

    def executar(
        self,
        data_inicio_str: str,
        data_fim_str: str,
    ) -> tuple[bool, list[str]]:
        """Executa a coleta de DCTFWeb.

        Args:
            data_inicio_str: Data início no formato ddmmaaaa (ex: "01012024").
            data_fim_str:    Data fim no formato ddmmaaaa (ex: "31122024").

        Returns:
            Tupla (sucesso: bool, arquivos: list[str]).
        """
        logger.info(f"[DCTFWeb] Iniciando — CNPJ: {self.cnpj} | Período: {data_inicio_str} → {data_fim_str}")
        self.diretorio_destino.mkdir(parents=True, exist_ok=True)

        arquivos_baixados: list[str] = []

        try:
            # Navega para o serviço DCTFWeb
            self._navegar_para_dctfweb()

            # Calcula blocos anuais dentro do período
            blocos = self._calcular_blocos_anuais(data_inicio_str, data_fim_str)
            logger.info(f"[DCTFWeb] Blocos anuais: {blocos}")

            for ano, inicio, fim in blocos:
                arqs = self._processar_ano(ano, inicio, fim)
                arquivos_baixados.extend(arqs)

            logger.info(f"[DCTFWeb] Coleta concluída: {len(arquivos_baixados)} arquivo(s).")
            return True, arquivos_baixados

        except Exception as e:
            logger.error(f"[DCTFWeb] Exceção: {e}\n{traceback.format_exc()}")
            return False, arquivos_baixados

    # ------------------------------------------------------------------
    # Navegação
    # ------------------------------------------------------------------

    def _navegar_para_dctfweb(self) -> None:
        logger.info("[DCTFWeb] Navegando para DCTFWeb via menu...")

        # Menu principal: Declarações
        if not _esperar_e_clicar(_img("dctf_menu_declaracoes.png"), timeout=20, critical=True):
            raise RuntimeError("Menu 'Declarações' não encontrado.")
        time.sleep(1)

        # Submenu: DCTFWeb
        if not _esperar_e_clicar(_img("dctf_menu_dctfweb.png"), timeout=15, critical=True):
            raise RuntimeError("Submenu DCTFWeb não encontrado.")
        time.sleep(2)

    # ------------------------------------------------------------------
    # Cálculo de blocos anuais
    # ------------------------------------------------------------------

    @staticmethod
    def _calcular_blocos_anuais(
        data_inicio: str,
        data_fim: str,
    ) -> list[tuple[int, str, str]]:
        """Divide o período em blocos anuais para a consulta.

        O DCTFWeb consulta um ano por vez.

        Args:
            data_inicio: ddmmaaaa (ex: "01012023")
            data_fim:    ddmmaaaa (ex: "31052025")

        Returns:
            Lista de (ano, inicio_str, fim_str) para cada ano no período.
        """
        ano_inicio = int(data_inicio[4:])
        ano_fim = int(data_fim[4:])
        blocos = []

        for ano in range(ano_inicio, ano_fim + 1):
            if ano == ano_inicio:
                inicio = data_inicio
            else:
                inicio = f"0101{ano}"

            if ano == ano_fim:
                fim = data_fim
            else:
                fim = f"3112{ano}"

            blocos.append((ano, inicio, fim))

        return blocos

    # ------------------------------------------------------------------
    # Processamento por ano
    # ------------------------------------------------------------------

    def _processar_ano(self, ano: int, data_inicio: str, data_fim: str) -> list[str]:
        logger.info(f"[DCTFWeb] Processando ano {ano}: {data_inicio} → {data_fim}")
        arquivos = []

        try:
            # Seleciona o ano no campo de período
            self._selecionar_periodo(data_inicio, data_fim)

            # Clica em Consultar
            if not _esperar_e_clicar(_img("dctf_btn_consultar.png"), timeout=15):
                logger.warning(f"[DCTFWeb] Botão Consultar não encontrado para ano {ano}.")
                return arquivos
            time.sleep(3)

            # Verifica se há declarações listadas
            if _imagem_existe(_img("dctf_sem_registros.png"), confianca=0.85):
                logger.info(f"[DCTFWeb] Nenhum registro para o ano {ano}.")
                return arquivos

            # Percorre declarações e baixa PDFs
            arquivos = self._baixar_declaracoes(ano)

        except Exception as e:
            logger.error(f"[DCTFWeb] Erro no ano {ano}: {e}")

        return arquivos

    def _selecionar_periodo(self, data_inicio: str, data_fim: str) -> None:
        """Preenche os campos de período no formulário de consulta."""
        # Campo data início
        if _esperar_e_clicar(_img("dctf_campo_data_inicio.png"), timeout=10):
            pyautogui.hotkey("ctrl", "a")
            pyautogui.typewrite(data_inicio, interval=0.05)
            time.sleep(0.3)
        else:
            logger.warning("[DCTFWeb] Campo data início não encontrado — tentando Tab.")
            pyautogui.press("tab")
            pyautogui.typewrite(data_inicio, interval=0.05)

        # Campo data fim
        if _esperar_e_clicar(_img("dctf_campo_data_fim.png"), timeout=10):
            pyautogui.hotkey("ctrl", "a")
            pyautogui.typewrite(data_fim, interval=0.05)
            time.sleep(0.3)

    def _baixar_declaracoes(self, ano: int) -> list[str]:
        """Itera pelos ícones de visualização/download e salva os PDFs."""
        arquivos = []
        idx = 0

        while True:
            # Procura ícone de "visualizar declaração completa" ou PDF
            icone = _img("dctf_icone_visualizar.png")
            try:
                loc = pyautogui.locateOnScreen(icone, confidence=0.85)
            except Exception:
                loc = None

            if not loc:
                # Tenta ícone alternativo de download
                icone_alt = _img("dctf_icone_pdf.png")
                try:
                    loc = pyautogui.locateOnScreen(icone_alt, confidence=0.85)
                except Exception:
                    loc = None

            if not loc:
                logger.info(f"[DCTFWeb] Nenhum ícone de declaração encontrado para ano {ano}.")
                break

            idx += 1
            pyautogui.click(pyautogui.center(loc))
            time.sleep(2)

            # Aguarda PDF abrir/baixar
            nome_arquivo = f"DCTFWeb_{self.cnpj}_{ano}_{idx:04d}.pdf"
            caminho = self.diretorio_destino / nome_arquivo

            # Aguarda o arquivo aparecer (download automático) ou copia o PDF aberto
            arquivo_baixado = self._aguardar_download_pdf(nome_arquivo, timeout=30)
            if arquivo_baixado:
                arquivos.append(str(arquivo_baixado))
                logger.info(f"[DCTFWeb] Salvo: {arquivo_baixado.name}")
            else:
                logger.warning(f"[DCTFWeb] Arquivo não localizado após clique {idx}.")

            # Volta para a lista
            pyautogui.hotkey("alt", "left")
            time.sleep(2)

            # Verifica se ainda há mais ícones (evita loop infinito)
            if idx > 50:
                logger.warning("[DCTFWeb] Limite de 50 declarações atingido — abortando loop.")
                break

        return arquivos

    def _aguardar_download_pdf(self, nome_sugerido: str, timeout: int = 30) -> Optional[Path]:
        """Aguarda o PDF aparecer na pasta de destino."""
        fim = time.time() + timeout
        while time.time() < fim:
            # Procura arquivos PDF na pasta destino modificados recentemente
            for pdf in self.diretorio_destino.glob("*.pdf"):
                mtime = pdf.stat().st_mtime
                if time.time() - mtime < timeout:
                    return pdf
            time.sleep(1)
        return None


# ---------------------------------------------------------------------------
# Execução standalone
# ---------------------------------------------------------------------------

def _standalone_run() -> None:
    import argparse
    from datetime import date

    parser = argparse.ArgumentParser(description="Coleta declarações DCTFWeb do eCAC")
    parser.add_argument("--cnpj", required=True, help="CNPJ (14 dígitos, sem máscara)")
    parser.add_argument("--destino", required=True, help="Pasta de destino para os PDFs")
    parser.add_argument("--inicio", default=None, help="Data início ddmmaaaa (padrão: 01/01/ano anterior)")
    parser.add_argument("--fim", default=None, help="Data fim ddmmaaaa (padrão: hoje)")
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

    if args.login == "auto":
        logger.info("[DCTFWeb] Tentando reutilizar sessão...")
        from login_session import tentar_sessao
        from login_ecac import executar_login

        sessao_ok = tentar_sessao(args.certificado, args.storage)
        if not sessao_ok:
            logger.info("[DCTFWeb] Sessão inválida — fazendo login completo...")
            pasta_storage_calc = args.storage or str(Path(args.destino).parent.parent / "sch_ecac_pro" / "storage")
            login_ok = executar_login(args.certificado, pasta_storage=pasta_storage_calc)
            if not login_ok:
                print("✘ Falha no login. Abortando.")
                sys.exit(1)
            logger.info("[DCTFWeb] Aguardando 5 segundos após login...")
            time.sleep(5)
        else:
            logger.info("[DCTFWeb] Sessão reutilizada.")

    fluxo = DCTFWeb(cnpj=args.cnpj, diretorio_destino=args.destino)
    ok, arquivos = fluxo.executar(data_inicio_str=data_inicio, data_fim_str=data_fim)
    print(f"\n{'✔ DCTFWeb concluído' if ok else '✘ DCTFWeb falhou'}: {len(arquivos)} arquivo(s)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    _standalone_run()