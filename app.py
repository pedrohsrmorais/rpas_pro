#!/usr/bin/env python3
"""app.py — Interface gráfica (tkinter) do sch_ecac_pro.

Funcionalidades:
  - Seleção de certificado digital (dropdown)
  - Configuração de pasta de destino (editável)
  - Seleção de CNPJ e Razão Social
  - Período de datas
  - Checkboxes para cada fluxo (DARF, DCTFWeb, Fontes Pagadoras)
  - Botão "Fazer apenas o login" — executa somente o login e salva sessão
  - Botão "Executar" — tenta reutilizar sessão, faz login se necessário, roda fluxos
  - Log em tempo real na interface

Uso:
    python app.py
"""

from __future__ import annotations

import logging
import sys
import threading
from datetime import date, datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# ---------------------------------------------------------------------------
# Certificados disponíveis (mesmos de login_ecac.py)
# ---------------------------------------------------------------------------

CERTIFICADOS_LISTA = [
    "Studio Varejo",
    "Studio Operacional",
    "Studio Brokers",
    "Studio Store",
    "Studio Agronegócios",
    "Space W",
    "Aliança Legal",
    "Studio Fiscal",
    "Studio Bank",
    "Audit Tecnologia",
]

# ---------------------------------------------------------------------------
# Logger que também escreve na caixa de texto da UI
# ---------------------------------------------------------------------------

class TextHandler(logging.Handler):
    """Handler que redireciona logs para um widget ScrolledText."""

    def __init__(self, widget: scrolledtext.ScrolledText) -> None:
        super().__init__()
        self.widget = widget

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record) + "\n"
        try:
            self.widget.configure(state="normal")
            self.widget.insert(tk.END, msg)
            self.widget.see(tk.END)
            self.widget.configure(state="disabled")
        except Exception:
            pass


def _setup_ui_logger(widget: scrolledtext.ScrolledText) -> logging.Logger:
    logger = logging.getLogger("app_ui")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger
    fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
    handler = TextHandler(widget)
    handler.setLevel(logging.INFO)
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


# ---------------------------------------------------------------------------
# Aplicação principal
# ---------------------------------------------------------------------------

class App(tk.Tk):
    """Janela principal do sch_ecac_pro."""

    DEFAULT_DESTINO = r"\\192.168.1.100\temp"
    DEFAULT_PORTA = 9222

    def __init__(self) -> None:
        super().__init__()
        self.title("sch_ecac_pro — Coleta eCAC")
        self.resizable(False, False)
        self._executando = False
        self._criar_widgets()
        self.ui_logger = _setup_ui_logger(self.txt_log)

    # ------------------------------------------------------------------
    # Construção da interface
    # ------------------------------------------------------------------

    def _criar_widgets(self) -> None:
        pad = {"padx": 8, "pady": 4}

        # ── Cabeçalho ─────────────────────────────────────────────────
        frm_cabecalho = tk.Frame(self, bg="#1e3a5f")
        frm_cabecalho.pack(fill="x")
        tk.Label(
            frm_cabecalho,
            text="sch_ecac_pro",
            font=("Segoe UI", 16, "bold"),
            bg="#1e3a5f",
            fg="white",
        ).pack(pady=8, padx=12, anchor="w")

        # ── Configurações ─────────────────────────────────────────────
        frm_config = tk.LabelFrame(self, text="Configurações", **pad)
        frm_config.pack(fill="x", **pad)

        # Certificado
        tk.Label(frm_config, text="Certificado:").grid(row=0, column=0, sticky="w", **pad)
        self.var_certificado = tk.StringVar(value="Studio Varejo")
        self.cmb_certificado = ttk.Combobox(
            frm_config,
            textvariable=self.var_certificado,
            values=CERTIFICADOS_LISTA,
            state="readonly",
            width=30,
        )
        self.cmb_certificado.grid(row=0, column=1, columnspan=2, sticky="w", **pad)

        # Destino
        tk.Label(frm_config, text="Pasta de destino:").grid(row=1, column=0, sticky="w", **pad)
        self.var_destino = tk.StringVar(value=self.DEFAULT_DESTINO)
        ent_destino = tk.Entry(frm_config, textvariable=self.var_destino, width=40)
        ent_destino.grid(row=1, column=1, sticky="we", **pad)
        tk.Button(
            frm_config,
            text="...",
            width=3,
            command=self._selecionar_pasta,
        ).grid(row=1, column=2, **pad)

        # Porta CDP
        tk.Label(frm_config, text="Porta CDP:").grid(row=2, column=0, sticky="w", **pad)
        self.var_porta = tk.IntVar(value=self.DEFAULT_PORTA)
        tk.Entry(frm_config, textvariable=self.var_porta, width=8).grid(row=2, column=1, sticky="w", **pad)

        # ── CNPJ / Razão Social ────────────────────────────────────────
        frm_empresa = tk.LabelFrame(self, text="Empresa", **pad)
        frm_empresa.pack(fill="x", **pad)

        tk.Label(frm_empresa, text="CNPJ (sem máscara):").grid(row=0, column=0, sticky="w", **pad)
        self.var_cnpj = tk.StringVar()
        tk.Entry(frm_empresa, textvariable=self.var_cnpj, width=20).grid(row=0, column=1, sticky="w", **pad)

        tk.Label(frm_empresa, text="Razão Social:").grid(row=1, column=0, sticky="w", **pad)
        self.var_razao = tk.StringVar()
        tk.Entry(frm_empresa, textvariable=self.var_razao, width=40).grid(row=1, column=1, sticky="w", **pad)

        # ── Período ────────────────────────────────────────────────────
        frm_periodo = tk.LabelFrame(self, text="Período", **pad)
        frm_periodo.pack(fill="x", **pad)

        hoje = date.today()
        ano_anterior = hoje.year - 1
        anos_disponiveis = [str(a) for a in range(2018, hoje.year + 1)]
        meses_disponiveis = [f"{m:02d}" for m in range(1, 13)]

        # Início
        tk.Label(frm_periodo, text="De:").grid(row=0, column=0, sticky="w", **pad)
        self.var_inicio_mes = tk.StringVar(value="01")
        self.var_inicio_ano = tk.StringVar(value=str(ano_anterior))
        ttk.Combobox(
            frm_periodo, textvariable=self.var_inicio_mes,
            values=meses_disponiveis, state="readonly", width=4,
        ).grid(row=0, column=1, sticky="w", padx=(8, 2), pady=4)
        tk.Label(frm_periodo, text="/").grid(row=0, column=2, padx=0)
        ttk.Combobox(
            frm_periodo, textvariable=self.var_inicio_ano,
            values=anos_disponiveis, state="readonly", width=6,
        ).grid(row=0, column=3, sticky="w", padx=(2, 8), pady=4)

        # Fim
        tk.Label(frm_periodo, text="Até:").grid(row=0, column=4, sticky="w", **pad)
        self.var_fim_mes = tk.StringVar(value=hoje.strftime("%m"))
        self.var_fim_ano = tk.StringVar(value=str(hoje.year))
        ttk.Combobox(
            frm_periodo, textvariable=self.var_fim_mes,
            values=meses_disponiveis, state="readonly", width=4,
        ).grid(row=0, column=5, sticky="w", padx=(8, 2), pady=4)
        tk.Label(frm_periodo, text="/").grid(row=0, column=6, padx=0)
        ttk.Combobox(
            frm_periodo, textvariable=self.var_fim_ano,
            values=anos_disponiveis, state="readonly", width=6,
        ).grid(row=0, column=7, sticky="w", padx=(2, 8), pady=4)

        # ── Fluxos ─────────────────────────────────────────────────────
        frm_fluxos = tk.LabelFrame(self, text="Fluxos a executar", **pad)
        frm_fluxos.pack(fill="x", **pad)

        self.var_darf = tk.BooleanVar(value=True)
        self.var_dctf = tk.BooleanVar(value=True)
        self.var_fontes = tk.BooleanVar(value=True)
        self.var_filiais = tk.BooleanVar(value=False)

        tk.Checkbutton(frm_fluxos, text="DARF", variable=self.var_darf).grid(
            row=0, column=0, sticky="w", **pad
        )
        tk.Checkbutton(frm_fluxos, text="DCTFWeb", variable=self.var_dctf).grid(
            row=0, column=1, sticky="w", **pad
        )
        tk.Checkbutton(frm_fluxos, text="Fontes Pagadoras", variable=self.var_fontes).grid(
            row=0, column=2, sticky="w", **pad
        )
        tk.Checkbutton(
            frm_fluxos,
            text="Incluir filiais (Fontes Pagadoras)",
            variable=self.var_filiais,
        ).grid(row=1, column=0, columnspan=3, sticky="w", **pad)

        # ── Botões ─────────────────────────────────────────────────────
        frm_botoes = tk.Frame(self)
        frm_botoes.pack(fill="x", **pad)

        self.btn_so_login = tk.Button(
            frm_botoes,
            text="🔑  Fazer apenas o login",
            width=24,
            bg="#f0a500",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            command=self._so_login,
        )
        self.btn_so_login.pack(side="left", padx=8, pady=6)

        self.btn_executar = tk.Button(
            frm_botoes,
            text="▶  Executar fluxos",
            width=20,
            bg="#1e7e34",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            command=self._executar,
        )
        self.btn_executar.pack(side="left", padx=4, pady=6)

        self.btn_limpar = tk.Button(
            frm_botoes,
            text="🗑  Limpar log",
            width=14,
            command=self._limpar_log,
        )
        self.btn_limpar.pack(side="right", padx=8, pady=6)

        # ── Log ────────────────────────────────────────────────────────
        frm_log = tk.LabelFrame(self, text="Log de execução", **pad)
        frm_log.pack(fill="both", expand=True, **pad)

        self.txt_log = scrolledtext.ScrolledText(
            frm_log, state="disabled", height=18, font=("Consolas", 9)
        )
        self.txt_log.pack(fill="both", expand=True, padx=4, pady=4)

        # Barra de status
        self.var_status = tk.StringVar(value="Pronto.")
        tk.Label(self, textvariable=self.var_status, relief="sunken", anchor="w").pack(
            fill="x", side="bottom", padx=2, pady=2
        )

    # ------------------------------------------------------------------
    # Ações dos botões
    # ------------------------------------------------------------------

    def _selecionar_pasta(self) -> None:
        pasta = filedialog.askdirectory(title="Selecione a pasta de destino")
        if pasta:
            self.var_destino.set(pasta)

    def _limpar_log(self) -> None:
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", tk.END)
        self.txt_log.configure(state="disabled")

    def _validar_campos_login(self) -> bool:
        if not self.var_certificado.get().strip():
            messagebox.showwarning("Atenção", "Selecione um certificado.")
            return False
        if not self.var_destino.get().strip():
            messagebox.showwarning("Atenção", "Informe a pasta de destino.")
            return False
        return True

    def _validar_campos_fluxos(self) -> bool:
        if not self._validar_campos_login():
            return False
        if not self.var_cnpj.get().strip():
            messagebox.showwarning("Atenção", "Informe o CNPJ.")
            return False
        if not (self.var_darf.get() or self.var_dctf.get() or self.var_fontes.get()):
            messagebox.showwarning("Atenção", "Selecione ao menos um fluxo para executar.")
            return False
        try:
            mi = int(self.var_inicio_mes.get())
            ai = int(self.var_inicio_ano.get())
            mf = int(self.var_fim_mes.get())
            af = int(self.var_fim_ano.get())
        except ValueError:
            messagebox.showwarning("Atenção", "Selecione mês e ano de início e fim.")
            return False
        if (ai, mi) > (af, mf):
            messagebox.showwarning("Atenção", "O período de início não pode ser posterior ao fim.")
            return False
        return True

    def _bloquear_botoes(self) -> None:
        self._executando = True
        self.btn_executar.configure(state="disabled", text="⏳ Executando...")
        self.btn_so_login.configure(state="disabled")

    def _desbloquear_botoes(self) -> None:
        self._executando = False
        self.btn_executar.configure(state="normal", text="▶  Executar fluxos")
        self.btn_so_login.configure(state="normal")

    def _set_status(self, texto: str) -> None:
        self.var_status.set(texto)

    # ------------------------------------------------------------------
    # "Fazer apenas o login"
    # ------------------------------------------------------------------

    def _so_login(self) -> None:
        if self._executando:
            return
        if not self._validar_campos_login():
            return

        self._bloquear_botoes()
        self._set_status("Fazendo login...")

        def _run() -> None:
            try:
                self.ui_logger.info("=== Iniciando login ===")
                try:
                    from main import apenas_login
                    ok = apenas_login(
                        certificado_nome=self.var_certificado.get().strip(),
                        destino_base=self.var_destino.get().strip(),
                        porta_cdp=int(self.var_porta.get()),
                        abrir_chrome=True,
                    )
                except ImportError:
                    self.ui_logger.error("main.py não encontrado.")
                    ok = False

                if ok:
                    self.ui_logger.info("✔ Login realizado e sessão salva com sucesso.")
                    self.after(0, lambda: messagebox.showinfo("Sucesso", "Login realizado e sessão salva!"))
                else:
                    self.ui_logger.error("✘ Login falhou.")
                    self.after(0, lambda: messagebox.showerror("Erro", "Login falhou. Verifique o log."))

            except Exception as e:
                self.ui_logger.error(f"Exceção inesperada: {e}")
            finally:
                self.after(0, self._desbloquear_botoes)
                self.after(0, lambda: self._set_status("Pronto."))

        threading.Thread(target=_run, daemon=True).start()

    # ------------------------------------------------------------------
    # "Executar fluxos"
    # ------------------------------------------------------------------

    def _executar(self) -> None:
        if self._executando:
            return
        if not self._validar_campos_fluxos():
            return

        self._bloquear_botoes()
        self._set_status("Executando fluxos...")

        # Coleta parâmetros da UI
        import calendar
        certificado = self.var_certificado.get().strip()
        destino = self.var_destino.get().strip()
        cnpj = self.var_cnpj.get().strip()
        razao = self.var_razao.get().strip() or "Empresa"
        porta = int(self.var_porta.get())
        filiais = self.var_filiais.get()

        mes_ini = int(self.var_inicio_mes.get())
        ano_inicio = int(self.var_inicio_ano.get())
        mes_fim = int(self.var_fim_mes.get())
        ano_fim = int(self.var_fim_ano.get())

        # Primeiro dia do mês inicial, último dia do mês final
        inicio = f"01{mes_ini:02d}{ano_inicio}"
        ultimo_dia = calendar.monthrange(ano_fim, mes_fim)[1]
        fim = f"{ultimo_dia:02d}{mes_fim:02d}{ano_fim}"

        fluxos: list[str] = []
        if self.var_darf.get():
            fluxos.append("darf")
        if self.var_dctf.get():
            fluxos.append("dctf")
        if self.var_fontes.get():
            fluxos.append("fontes")

        def _run() -> None:
            try:
                self.ui_logger.info("=== Iniciando execução ===")
                self.ui_logger.info(f"Certificado: {certificado}")
                self.ui_logger.info(f"CNPJ: {cnpj} | Razão: {razao}")
                self.ui_logger.info(f"Período: {mes_ini:02d}/{ano_inicio} → {mes_fim:02d}/{ano_fim}  ({inicio} → {fim})")
                self.ui_logger.info(f"Fluxos: {', '.join(fluxos)}")
                self.ui_logger.info(f"Destino: {destino}")

                try:
                    from main import executar
                    resultados = executar(
                        cnpj=cnpj,
                        razao_social=razao,
                        certificado_nome=certificado,
                        destino_base=destino,
                        data_inicio=inicio,
                        data_fim=fim,
                        fluxos=fluxos,
                        ano_inicio=ano_inicio,
                        ano_fim=ano_fim,
                        coletar_filiais=filiais,
                        porta_cdp=porta,
                        abrir_chrome=True,
                    )
                except ImportError:
                    self.ui_logger.error("main.py não encontrado.")
                    resultados = {}

                if resultados:
                    sucessos = sum(1 for v in resultados.values() if v)
                    total = len(resultados)
                    resumo = f"{sucessos}/{total} fluxo(s) concluído(s)"
                    self.ui_logger.info(f"=== {resumo} ===")
                    for nome, ok in resultados.items():
                        self.ui_logger.info(f"  {'✔' if ok else '✘'} {nome}")

                    if all(resultados.values()):
                        self.after(0, lambda: messagebox.showinfo("Concluído", resumo))
                    else:
                        self.after(0, lambda: messagebox.showwarning("Parcial", f"{resumo}\nVerifique o log."))

            except Exception as e:
                self.ui_logger.error(f"Exceção inesperada: {e}")
                self.after(0, lambda: messagebox.showerror("Erro", f"Exceção: {e}"))
            finally:
                self.after(0, self._desbloquear_botoes)
                self.after(0, lambda: self._set_status("Pronto."))

        threading.Thread(target=_run, daemon=True).start()


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()