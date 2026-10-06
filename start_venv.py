"""start_venv.py — Cria e prepara o ambiente virtual para os RPAs eCAC.

Execute este script UMA VEZ, no diretório raiz do projeto:
    python start_venv.py

O que ele faz:
  1. Cria o venv em .venv/ no diretório atual
  2. Instala todas as dependências de requirements.txt
  3. Instala o navegador Edge gerenciado pelo Playwright
  4. Exibe o comando de ativação para a sessão do terminal
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# O script sempre opera no diretório onde ELE está salvo,
# independente de onde o terminal está.
# ---------------------------------------------------------------------------
RAIZ = Path(__file__).parent.resolve()
VENV_DIR = RAIZ / ".venv"
REQUIREMENTS = RAIZ / "requirements.txt"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cor(codigo: str, texto: str) -> str:
    return f"\033[{codigo}m{texto}\033[0m"

def ok(msg: str)     -> None: print(_cor("32",   f"  ✔  {msg}"))
def info(msg: str)   -> None: print(_cor("36",   f"  →  {msg}"))
def erro(msg: str)   -> None: print(_cor("31",   f"  ✘  {msg}"))
def titulo(msg: str) -> None: print("\n" + _cor("1;34", f"  {msg}"))


def _executar(cmd: list[str], descricao: str) -> None:
    info(descricao)
    resultado = subprocess.run(cmd, check=False)
    if resultado.returncode != 0:
        erro(f"Falhou: {' '.join(str(c) for c in cmd)}")
        sys.exit(resultado.returncode)


# ---------------------------------------------------------------------------
# Script principal
# ---------------------------------------------------------------------------

def main() -> None:
    os.system("")  # habilita ANSI no Windows

    print()
    print(_cor("1;37", "=" * 56))
    print(_cor("1;37", "   Setup — RPAs eCAC Unificados"))
    print(_cor("1;37", "=" * 56))
    info(f"Diretório do projeto: {RAIZ}")

    # 1. Python
    titulo("Verificando Python...")
    v = sys.version_info
    if v < (3, 10):
        erro(f"Python 3.10+ é obrigatório. Atual: {sys.version}")
        sys.exit(1)
    ok(f"Python {v.major}.{v.minor}.{v.micro}")

    # 2. requirements.txt
    titulo("Verificando requirements.txt...")
    if not REQUIREMENTS.exists():
        erro(f"Não encontrado: {REQUIREMENTS}")
        sys.exit(1)
    ok(f"requirements.txt em {REQUIREMENTS}")

    # 3. Cria venv
    titulo("Criando ambiente virtual em .venv/ ...")
    if VENV_DIR.exists():
        info(".venv/ já existe — pulando criação.")
    else:
        _executar([sys.executable, "-m", "venv", str(VENV_DIR)], "python -m venv .venv")
        ok(".venv/ criado.")

    # 4. Localiza executáveis do venv
    if sys.platform == "win32":
        scripts  = VENV_DIR / "Scripts"
        pip_exe  = scripts / "pip.exe"
        py_exe   = scripts / "python.exe"
        pw_exe   = scripts / "playwright.exe"
        ativar   = rf".venv\Scripts\activate"
        ativar_ps = r".venv\Scripts\Activate.ps1"
    else:
        scripts  = VENV_DIR / "bin"
        pip_exe  = scripts / "pip"
        py_exe   = scripts / "python"
        pw_exe   = scripts / "playwright"
        ativar   = "source .venv/bin/activate"
        ativar_ps = ativar

    # Valida que o venv foi criado corretamente
    if not pip_exe.exists():
        erro(f"pip não encontrado em {pip_exe} — o venv pode estar corrompido.")
        erro("Apague a pasta .venv/ e rode este script novamente.")
        sys.exit(1)

    # 5. Atualiza pip
    titulo("Atualizando pip...")
    _executar([str(py_exe), "-m", "pip", "install", "--upgrade", "pip"],
              "pip install --upgrade pip")
    ok("pip atualizado.")

    # 6. Instala dependências
    titulo("Instalando dependências (requirements.txt)...")
    _executar([str(pip_exe), "install", "-r", str(REQUIREMENTS)],
              "pip install -r requirements.txt")
    ok("Dependências instaladas.")

    # 7. Playwright Edge
    titulo("Instalando Microsoft Edge via Playwright...")
    _executar([str(pw_exe), "install", "msedge"], "playwright install msedge")
    ok("Microsoft Edge (Playwright) instalado.")

    # 8. Instruções finais
    print()
    print(_cor("1;37", "=" * 56))
    print(_cor("1;32", "  Setup concluído!"))
    print(_cor("1;37", "=" * 56))
    print()
    print("  Para ativar o ambiente nesta sessão do terminal:")
    print()
    if sys.platform == "win32":
        print(_cor("33", f"    CMD:        {ativar}"))
        print(_cor("33", f"    PowerShell: {ativar_ps}"))
    else:
        print(_cor("33", f"    {ativar}"))
    print()
    print("  Após ativar, abra a interface com:")
    print(_cor("33", "    python app.py"))
    print()


if __name__ == "__main__":
    main()