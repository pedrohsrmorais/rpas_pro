#!/usr/bin/env python3
"""main.py — Orquestrador principal do sch_ecac_pro.

Fluxo de login:
  1. Tenta reutilizar sessão via login_session.py
  2. Se não conseguir, executa login completo via login_ecac.py
  3. Aguarda 5 segundos após o login
  4. Executa os fluxos solicitados (DARF, DCTFWeb, Fontes Pagadoras)

Estrutura de pastas criada automaticamente:
  <destino>/
  └── sch_ecac_pro/
      ├── documentos/
      │   ├── darf/
      │   ├── dctf/
      │   └── fontes_pagadoras/
      └── storage/

Uso:
    python main.py --cnpj 12345678000199 --destino "\\\\192.168.1.100\\temp"
    python main.py --ajuda
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

def _setup_logger() -> logging.Logger:
    base_dir = Path(__file__).resolve().parent
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"main_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

    logger = logging.getLogger("main")
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
# Estrutura de pastas
# ---------------------------------------------------------------------------

def criar_estrutura_pastas(destino_base: str | Path) -> dict[str, Path]:
    """Cria e retorna a estrutura de pastas sch_ecac_pro.

    Args:
        destino_base: Pasta raiz informada pelo usuário (ex: \\\\192.168.1.100\\temp).

    Returns:
        Dicionário com os caminhos de cada subpasta.
    """
    raiz = Path(destino_base) / "sch_ecac_pro"
    pastas = {
        "raiz": raiz,
        "darf": raiz / "documentos" / "darf",
        "dctf": raiz / "documentos" / "dctf",
        "fontes_pagadoras": raiz / "documentos" / "fontes_pagadoras",
        "storage": raiz / "storage",
    }
    for pasta in pastas.values():
        pasta.mkdir(parents=True, exist_ok=True)

    logger.info(f"Estrutura criada em: {raiz}")
    return pastas


# ---------------------------------------------------------------------------
# Fluxo de login unificado
# ---------------------------------------------------------------------------

def executar_login_unificado(
    certificado_nome: str,
    pasta_storage: str | Path,
    porta_cdp: int = 9222,
    abrir_chrome: bool = True,
) -> bool:
    """Tenta sessão salva; se expirada/inválida, faz login completo.

    Args:
        certificado_nome: Ex: "Studio Varejo".
        pasta_storage:    Pasta storage/ onde os JSONs de sessão ficam.
        porta_cdp:        Porta CDP do Chrome.
        abrir_chrome:     Se True, abre Chrome novo se necessário.

    Returns:
        True se o login (via sessão ou completo) foi bem-sucedido.
    """
    logger.info(f"=== Login — certificado: '{certificado_nome}' ===")

    # 1) Tenta reutilizar sessão
    try:
        from login_session import tentar_sessao
        logger.info("Verificando sessão existente...")
        if tentar_sessao(certificado_nome, pasta_storage=pasta_storage, porta_cdp=porta_cdp):
            logger.info("✔ Sessão reutilizada com sucesso.")
            return True
        logger.info("Sessão inválida ou expirada — iniciando login completo...")
    except ImportError:
        logger.warning("login_session.py não disponível — pulando verificação de sessão.")

    # 2) Login completo
    try:
        from login_ecac import executar_login
        logger.info("Executando login completo via login_ecac.py...")
        ok = executar_login(
            certificado_nome=certificado_nome,
            pasta_storage=str(pasta_storage),
            abrir_chrome=abrir_chrome,
        )
        if ok:
            logger.info("✔ Login completo realizado com sucesso.")
        else:
            logger.error("✘ Login completo falhou.")
        return ok
    except ImportError:
        logger.error("login_ecac.py não disponível. Certifique-se de que está na mesma pasta.")
        return False
    except Exception as e:
        logger.error(f"Exceção durante login completo: {e}")
        return False


# ---------------------------------------------------------------------------
# Execução dos fluxos
# ---------------------------------------------------------------------------

def executar_darf(
    cnpj: str,
    pasta_darf: Path,
    data_inicio: str,
    data_fim: str,
    porta_cdp: int = 9222,
) -> bool:
    """Executa o fluxo de coleta de DARFs."""
    logger.info(f"[DARF] Iniciando — período: {data_inicio} → {data_fim}")
    try:
        from darf import DARF
        fluxo = DARF(cnpj=cnpj, diretorio_destino=pasta_darf, porta_cdp=porta_cdp)
        return fluxo.executar(data_inicio=data_inicio, data_fim=data_fim)
    except ImportError:
        logger.error("darf.py não encontrado.")
        return False
    except Exception as e:
        logger.error(f"[DARF] Exceção: {e}")
        return False


def executar_dctfweb(
    cnpj: str,
    pasta_dctf: Path,
    data_inicio: str,
    data_fim: str,
) -> bool:
    """Executa o fluxo de coleta de DCTFWeb."""
    logger.info(f"[DCTFWeb] Iniciando — período: {data_inicio} → {data_fim}")
    try:
        from dctfweb import DCTFWeb
        fluxo = DCTFWeb(cnpj=cnpj, diretorio_destino=pasta_dctf)
        ok, arquivos = fluxo.executar(data_inicio_str=data_inicio, data_fim_str=data_fim)
        logger.info(f"[DCTFWeb] {len(arquivos)} arquivo(s) coletado(s).")
        return ok
    except ImportError:
        logger.error("dctfweb.py não encontrado.")
        return False
    except Exception as e:
        logger.error(f"[DCTFWeb] Exceção: {e}")
        return False


def executar_fontes_pagadoras(
    cnpj: str,
    razao_social: str,
    pasta_fontes: Path,
    ano_inicio: int,
    ano_fim: int,
    coletar_filiais: bool = False,
    porta_cdp: int = 9222,
) -> bool:
    """Executa o fluxo de coleta de Fontes Pagadoras."""
    logger.info(f"[FontesPagadoras] Iniciando — período: {ano_inicio} → {ano_fim}")
    try:
        from fontes_pagadoras import FontesPagadoras
        fluxo = FontesPagadoras(
            cnpj=cnpj,
            razao_social=razao_social,
            coletar_filiais=coletar_filiais,
            ano_inicio=ano_inicio,
            ano_fim=ano_fim,
        )
        ok, resultado = fluxo.executar(porta_cdp=porta_cdp, diretorio_destino=pasta_fontes)
        logger.info(f"[FontesPagadoras] {resultado.total} arquivo(s) coletado(s).")
        return ok
    except ImportError:
        logger.error("fontes_pagadoras.py não encontrado.")
        return False
    except Exception as e:
        logger.error(f"[FontesPagadoras] Exceção: {e}")
        return False


# ---------------------------------------------------------------------------
# Ponto de entrada público (para app.py e uso programático)
# ---------------------------------------------------------------------------

def executar(
    cnpj: str,
    razao_social: str,
    certificado_nome: str,
    destino_base: str | Path,
    data_inicio: str,
    data_fim: str,
    fluxos: list[str],
    ano_inicio: Optional[int] = None,
    ano_fim: Optional[int] = None,
    coletar_filiais: bool = False,
    porta_cdp: int = 9222,
    abrir_chrome: bool = True,
) -> dict[str, bool]:
    """Ponto de entrada principal. Usado pelo app.py.

    Args:
        cnpj:             CNPJ sem máscara (14 dígitos).
        razao_social:     Razão social (para Fontes Pagadoras).
        certificado_nome: Nome do certificado (ex: "Studio Varejo").
        destino_base:     Pasta raiz (ex: \\\\192.168.1.100\\temp).
        data_inicio:      Formato ddmmaaaa.
        data_fim:         Formato ddmmaaaa.
        fluxos:           Lista de fluxos: ["darf", "dctf", "fontes"].
        ano_inicio:       Ano inicial para Fontes Pagadoras.
        ano_fim:          Ano final para Fontes Pagadoras.
        coletar_filiais:  Se True, coleta filiais em Fontes Pagadoras.
        porta_cdp:        Porta CDP do Chrome.
        abrir_chrome:     Se True, abre Chrome novo se necessário.

    Returns:
        Dicionário {fluxo: sucesso} para cada fluxo executado.
    """
    resultados: dict[str, bool] = {}

    # Cria estrutura de pastas
    pastas = criar_estrutura_pastas(destino_base)

    # Login
    login_ok = executar_login_unificado(
        certificado_nome=certificado_nome,
        pasta_storage=pastas["storage"],
        porta_cdp=porta_cdp,
        abrir_chrome=abrir_chrome,
    )
    if not login_ok:
        logger.error("Login falhou. Abortando fluxos.")
        for f in fluxos:
            resultados[f] = False
        return resultados

    logger.info("Aguardando 5 segundos após login...")
    time.sleep(5)

    # Calcula anos para Fontes Pagadoras se não informados
    ano_ini = ano_inicio or int(data_inicio[4:])
    ano_fim_calc = ano_fim or int(data_fim[4:])

    # Executa fluxos selecionados
    for fluxo in fluxos:
        if fluxo == "darf":
            resultados["darf"] = executar_darf(cnpj, pastas["darf"], data_inicio, data_fim, porta_cdp)

        elif fluxo in ("dctf", "dctfweb"):
            resultados["dctf"] = executar_dctfweb(cnpj, pastas["dctf"], data_inicio, data_fim)

        elif fluxo in ("fontes", "fontes_pagadoras"):
            resultados["fontes"] = executar_fontes_pagadoras(
                cnpj=cnpj,
                razao_social=razao_social,
                pasta_fontes=pastas["fontes_pagadoras"],
                ano_inicio=ano_ini,
                ano_fim=ano_fim_calc,
                coletar_filiais=coletar_filiais,
                porta_cdp=porta_cdp,
            )
        else:
            logger.warning(f"Fluxo desconhecido: '{fluxo}' — ignorado.")

    # Resumo
    logger.info("=== Resumo da execução ===")
    for nome, ok in resultados.items():
        status = "✔ OK" if ok else "✘ FALHOU"
        logger.info(f"  {nome:20s}: {status}")

    return resultados


def apenas_login(
    certificado_nome: str,
    destino_base: str | Path,
    porta_cdp: int = 9222,
    abrir_chrome: bool = True,
) -> bool:
    """Executa apenas o login e salva a sessão. Sem executar nenhum fluxo.

    Args:
        certificado_nome: Ex: "Studio Varejo".
        destino_base:     Pasta raiz (para criar storage/ dentro de sch_ecac_pro/).
        porta_cdp:        Porta CDP do Chrome.
        abrir_chrome:     Se True, abre Chrome novo se necessário.

    Returns:
        True se o login foi bem-sucedido.
    """
    pastas = criar_estrutura_pastas(destino_base)
    return executar_login_unificado(
        certificado_nome=certificado_nome,
        pasta_storage=pastas["storage"],
        porta_cdp=porta_cdp,
        abrir_chrome=abrir_chrome,
    )


# ---------------------------------------------------------------------------
# Execução standalone (linha de comando)
# ---------------------------------------------------------------------------

def _standalone_run() -> None:
    hoje = date.today()
    ano_anterior = hoje.year - 1

    parser = argparse.ArgumentParser(
        description="Orquestrador eCAC — DARF / DCTFWeb / Fontes Pagadoras",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python main.py --cnpj 12345678000199 --destino "\\\\192.168.1.100\\temp" --fluxos darf dctf fontes
  python main.py --cnpj 12345678000199 --destino "C:\\saida" --fluxos darf --inicio 01012023 --fim 31122024
  python main.py --so-login --certificado "Studio Varejo" --destino "C:\\saida"
        """,
    )

    parser.add_argument("--cnpj", help="CNPJ sem máscara (14 dígitos)")
    parser.add_argument("--razao-social", default="Empresa", help="Razão social (para Fontes Pagadoras)")
    parser.add_argument(
        "--certificado",
        default="Studio Varejo",
        help="Nome do certificado digital (padrão: Studio Varejo)",
    )
    parser.add_argument(
        "--destino",
        default=r"\\192.168.1.100\temp",
        help=r"Pasta de destino (padrão: \\192.168.1.100\temp)",
    )
    parser.add_argument("--inicio", default=None, help="Data início ddmmaaaa (padrão: 01/01/ano anterior)")
    parser.add_argument("--fim", default=None, help="Data fim ddmmaaaa (padrão: hoje)")
    parser.add_argument(
        "--fluxos",
        nargs="+",
        choices=["darf", "dctf", "dctfweb", "fontes", "fontes_pagadoras"],
        default=["darf", "dctf", "fontes"],
        help="Fluxos a executar (padrão: darf dctf fontes)",
    )
    parser.add_argument("--ano-inicio", type=int, default=None, help="Ano inicial (Fontes Pagadoras)")
    parser.add_argument("--ano-fim", type=int, default=None, help="Ano final (Fontes Pagadoras)")
    parser.add_argument("--filiais", action="store_true", help="Coletar filiais em Fontes Pagadoras")
    parser.add_argument("--porta", type=int, default=9222, help="Porta CDP do Chrome (padrão: 9222)")
    parser.add_argument("--sem-chrome", action="store_true", help="Não abre Chrome novo (assume já aberto)")
    parser.add_argument(
        "--so-login",
        action="store_true",
        help="Executa apenas o login e salva sessão, sem rodar fluxos",
    )
    args = parser.parse_args()

    data_inicio = args.inicio or f"0101{ano_anterior}"
    data_fim = args.fim or hoje.strftime("%d%m%Y")

    if args.so_login:
        ok = apenas_login(
            certificado_nome=args.certificado,
            destino_base=args.destino,
            porta_cdp=args.porta,
            abrir_chrome=not args.sem_chrome,
        )
        print(f"\n{'✔ Login realizado com sucesso' if ok else '✘ Login falhou'}")
        sys.exit(0 if ok else 1)

    if not args.cnpj:
        parser.error("--cnpj é obrigatório quando não usar --so-login")

    resultados = executar(
        cnpj=args.cnpj,
        razao_social=args.razao_social,
        certificado_nome=args.certificado,
        destino_base=args.destino,
        data_inicio=data_inicio,
        data_fim=data_fim,
        fluxos=args.fluxos,
        ano_inicio=args.ano_inicio,
        ano_fim=args.ano_fim,
        coletar_filiais=args.filiais,
        porta_cdp=args.porta,
        abrir_chrome=not args.sem_chrome,
    )

    sucessos = sum(1 for v in resultados.values() if v)
    total = len(resultados)
    print(f"\n=== Resultado: {sucessos}/{total} fluxo(s) concluído(s) ===")
    for nome, ok in resultados.items():
        print(f"  {'✔' if ok else '✘'} {nome}")
    sys.exit(0 if all(resultados.values()) else 1)


if __name__ == "__main__":
    _standalone_run()