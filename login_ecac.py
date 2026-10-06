#!/usr/bin/env python3
"""login_ecac.py — Login completo no eCAC via certificado digital.

Adaptado de reinf_login_standalone.py. Executa o fluxo de autenticação
completo: abre Chrome, navega para gov.br, resolve hCaptcha via API externa,
seleciona o certificado digital e confirma o login no eCAC.

Após login bem-sucedido, salva a sessão em JSON na pasta storage/.

Uso standalone (com Edge/Chrome já aberto e logado, ou do zero):
    python login_ecac.py --certificado "Studio Varejo"
    python login_ecac.py  # usa certificado padrão

Uso como módulo:
    from login_ecac import executar_login
    ok = executar_login("Studio Varejo", pasta_storage="C:/RPA/sch_ecac_pro/storage")
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Optional

import pyautogui
import pyperclip
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

def _setup_logger() -> logging.Logger:
    base_dir = Path(__file__).resolve().parent
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"login_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

    logger = logging.getLogger("login_ecac")
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
# Pasta base dos assets (imagens de referência)
# ---------------------------------------------------------------------------
_BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = _BASE_DIR / "assets"

# ---------------------------------------------------------------------------
# Mapeamento de certificados: nome → posição no diálogo nativo do Windows
# ---------------------------------------------------------------------------
CERTIFICADOS: dict[str, dict] = {
    "STUDIO OPERACIONAL":  {"pos": 7},
    "STUDIO BROKERS":      {"pos": 2},
    "STUDIO STORE":        {"pos": 6},
    "STUDIO VAREJO":       {"pos": 1},
    "STUDIO AGRONEGOCIOS": {"pos": 9},
    "SPACE W":             {"pos": None},
    "ALIANCA LEGAL":       {"pos": 4},
    "STUDIO FISCAL":       {"pos": 8},
    "STUDIO BANK":         {"pos": 3},
    "AUDIT TECNOLOGIA":    {"pos": 5},
}

# Mapa de exibição → chave interna normalizada
NOMES_DISPLAY: dict[str, str] = {
    "Studio Operacional":  "STUDIO OPERACIONAL",
    "Studio Brokers":      "STUDIO BROKERS",
    "Studio Store":        "STUDIO STORE",
    "Studio Varejo":       "STUDIO VAREJO",
    "Studio Agronegócios": "STUDIO AGRONEGOCIOS",
    "Space W":             "SPACE W",
    "Aliança Legal":       "ALIANCA LEGAL",
    "Studio Fiscal":       "STUDIO FISCAL",
    "Studio Bank":         "STUDIO BANK",
    "Audit Tecnologia":    "AUDIT TECNOLOGIA",
}

# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------
URL_ECAC = "https://cav.receita.fazenda.gov.br/autenticacao/login"
DEFAULT_CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
REMOTE_DEBUGGING_PORT = int(os.getenv("REMOTE_DEBUGGING_PORT", "9222"))

CAPTCHA_API_URL = os.getenv(
    "CAPTCHA_API_URL",
    "http://cs4wwkcksg40ww0g0oosg08s.72.62.104.140.sslip.io/api/captcha",
)
CAPTCHA_API_KEY = os.getenv("CAPTCHA_API_KEY", "apt_b44e49e9ed16f5e9bf2cc57f92fd2157")
USER_AGENT = os.getenv(
    "ECAC_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)

MAX_TENTATIVAS_FLUXO = int(os.getenv("MAX_TENTATIVAS_FLUXO", "5"))
RETRY_COOLDOWN_S = float(os.getenv("RETRY_COOLDOWN_S", "20"))
CHROME_CLOSE_WAIT_S = float(os.getenv("CHROME_CLOSE_WAIT_S", "5"))

AUTO_DELAY_S = 5
JAVA_WRITE_INTERVAL_S = 0.02

HCAPTCHA_REF_DIR = str(ASSETS_DIR / "hcaptcha_refs")
BLOQUEIO_REF_DIR = str(ASSETS_DIR / "bloqueio_refs")
CERTIFICADO_BTN_REF_DIR = str(ASSETS_DIR / "certificado_btn_refs")
OK_BUTTON_REF_DIR = str(ASSETS_DIR / "ok_button_refs")

HCAPTCHA_MATCH_CONFIDENCE = float(os.getenv("HCAPTCHA_MATCH_CONFIDENCE", "0.7"))
HCAPTCHA_MATCH_SCALES = [
    float(s) for s in os.getenv(
        "HCAPTCHA_MATCH_SCALES", "0.85,0.9,0.95,1.0,1.05,1.1,1.15"
    ).split(",")
]
HCAPTCHA_WAIT_TIMEOUT_S = float(os.getenv("HCAPTCHA_WAIT_TIMEOUT_S", "10"))
HCAPTCHA_WAIT_TIMEOUT_POS_CERTIFICADO_S = float(
    os.getenv("HCAPTCHA_WAIT_TIMEOUT_POS_CERTIFICADO_S", "40")
)
CAPTCHA_POLL_INTERVAL_S = 5
CAPTCHA_TIMEOUT_S = 120
CAPTCHA_VERIFICACAO_POS_SUBMIT_S = float(os.getenv("CAPTCHA_VERIFICACAO_POS_SUBMIT_S", "5"))
CAPTCHA_DELAY_ANTES_VERIFICACAO_POS_SUBMIT_S = float(
    os.getenv("CAPTCHA_DELAY_ANTES_VERIFICACAO_POS_SUBMIT_S", "10")
)

BLOQUEIO_WAIT_TIMEOUT_S = float(os.getenv("BLOQUEIO_WAIT_TIMEOUT_S", "3"))
CERTIFICADO_BTN_WAIT_TIMEOUT_S = float(os.getenv("CERTIFICADO_BTN_WAIT_TIMEOUT_S", "15"))
OK_BUTTON_WAIT_TIMEOUT_S = float(os.getenv("OK_BUTTON_WAIT_TIMEOUT_S", "20"))
MOUSE_MOVE_DURATION_S = float(os.getenv("MOUSE_MOVE_DURATION_S", "0.35"))
MAX_TENTATIVAS_CLIQUE_CERTIFICADO_RECUPERACAO = int(
    os.getenv("MAX_TENTATIVAS_CLIQUE_CERTIFICADO_RECUPERACAO", "3")
)
DELAY_VERIFICACAO_POS_CLIQUE_RECUPERACAO_S = float(
    os.getenv("DELAY_VERIFICACAO_POS_CLIQUE_RECUPERACAO_S", "8")
)
TEMPO_ABRIR_JANELA_CERTIFICADO = 12
CERTIFICADO_PRIMEIRO_ITEM_X = 250
CERTIFICADO_PRIMEIRO_ITEM_Y = 145
CERTIFICADO_ITEM_DOWN_DELAY = 0.6
CERTIFICADO_PRE_SEL_DELAY = 5.0

_TEXTOS_BLOQUEIO_AUTOMACAO = (
    "acesso foi bloqueado por possuir atributos",
    "caracteriza como um acesso automatizado",
    "bloqueado por possuir atributos",
)
_TEXTOS_ERRO_CAPTCHA = ("captcha inv", "tente novamente", "captcha expirou", "captcha expirado")
_URL_ECAC_LOGIN_MARCADOR = "cav.receita.fazenda.gov.br/autenticacao/login"
_DOMINIO_ECAC = "cav.receita.fazenda.gov.br"
_DOMINIOS_SSO_GOVBR = ("sso.acesso.gov.br", "acesso.gov.br", "certificado.acesso.gov.br")

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.4

# Processo Chrome atual
_chrome_process: Optional[subprocess.Popen] = None
_chrome_profile_dir: Optional[str] = None

# Cache de referências visuais
_referencias_cache: dict[str, list] = {}

# ---------------------------------------------------------------------------
# Utilitários internos
# ---------------------------------------------------------------------------

def _normalizar_nome(valor: str) -> str:
    texto = (valor or "").replace("\xa0", " ").strip().upper()
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


def _resolver_chave_certificado(nome: str) -> str:
    """Resolve o nome de exibição ou chave interna para a chave normalizada."""
    normalizado = _normalizar_nome(nome)
    # Busca direta
    if normalizado in CERTIFICADOS:
        return normalizado
    # Busca via mapa de exibição
    for display, chave in NOMES_DISPLAY.items():
        if _normalizar_nome(display) == normalizado:
            return chave
    # Busca parcial
    for chave in CERTIFICADOS:
        if normalizado in chave or chave in normalizado:
            return chave
    raise ValueError(
        f"Certificado '{nome}' não encontrado. Disponíveis: {list(CERTIFICADOS.keys())}"
    )


def _colar_texto(texto: str) -> None:
    pyperclip.copy(texto)
    pyautogui.hotkey("ctrl", "v")


def _carregar_referencias_com_escalas(pasta_dir: str) -> list:
    if pasta_dir in _referencias_cache:
        return _referencias_cache[pasta_dir]
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow não instalado — comparação visual desativada.")
        _referencias_cache[pasta_dir] = []
        return []

    pasta = Path(pasta_dir)
    arquivos = sorted(pasta.glob("*.png")) if pasta.is_dir() else []
    if not arquivos:
        logger.warning(f"Nenhuma imagem de referência em '{pasta_dir}'.")
        _referencias_cache[pasta_dir] = []
        return []

    variacoes = []
    for arq in arquivos:
        try:
            img = Image.open(arq).convert("RGB")
        except Exception as e:
            logger.warning(f"Não consegui abrir '{arq}': {e}")
            continue
        w, h = img.size
        for escala in HCAPTCHA_MATCH_SCALES:
            if escala == 1.0:
                variacoes.append(img)
            else:
                variacoes.append(img.resize((max(1, round(w * escala)), max(1, round(h * escala)))))

    logger.info(f"Referências '{pasta_dir}': {len(arquivos)} img(s) × {len(HCAPTCHA_MATCH_SCALES)} escalas")
    _referencias_cache[pasta_dir] = variacoes
    return variacoes


def _aguardar_padrao_visivel(
    pasta_dir: str,
    timeout_s: float,
    intervalo_s: float = 1.0,
    rotulo: str = "padrão",
) -> bool:
    refs = _carregar_referencias_com_escalas(pasta_dir)
    if not refs:
        return False

    fim = time.time() + timeout_s
    t = 0
    while time.time() < fim:
        t += 1
        try:
            captura = pyautogui.screenshot()
        except Exception as e:
            logger.warning(f"Print falhou (tentativa {t}): {e}")
            time.sleep(intervalo_s)
            continue
        for needle in refs:
            try:
                loc = pyautogui.locate(needle, captura, confidence=HCAPTCHA_MATCH_CONFIDENCE, grayscale=True)
            except Exception:
                continue
            if loc is not None:
                logger.info(f"'{rotulo}' detectado na tela (tentativa {t}).")
                return True
        time.sleep(intervalo_s)
    return False


def _localizar_e_clicar_via_imagem(pasta_dir: str, rotulo: str, timeout_s: float) -> bool:
    refs = _carregar_referencias_com_escalas(pasta_dir)
    if not refs:
        return False

    fim = time.time() + timeout_s
    t = 0
    while time.time() < fim:
        t += 1
        try:
            captura = pyautogui.screenshot()
        except Exception as e:
            logger.warning(f"Print falhou (tentativa {t}): {e}")
            time.sleep(1)
            continue
        for needle in refs:
            try:
                loc = pyautogui.locate(needle, captura, confidence=HCAPTCHA_MATCH_CONFIDENCE, grayscale=True)
            except Exception:
                continue
            if loc is not None:
                left, top, larg, alt = loc
                cx, cy = left + larg / 2, top + alt / 2
                logger.info(f"'{rotulo}' encontrado em ({cx:.0f}, {cy:.0f}) — clicando.")
                pyautogui.moveTo(cx, cy, duration=MOUSE_MOVE_DURATION_S)
                time.sleep(0.15)
                pyautogui.click()
                return True
        time.sleep(1)
    logger.warning(f"'{rotulo}' não encontrado em {timeout_s}s.")
    return False


def _capturar_url_atual() -> str:
    anterior = pyperclip.paste()
    try:
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.2)
        url = (pyperclip.paste() or "").strip()
        pyautogui.press("esc")
        return url
    finally:
        pyperclip.copy(anterior)


def _ler_estado_pagina() -> Optional[tuple[str, str]]:
    js = (
        "script:(()=>{"
        "const url=window.location.href;"
        "let texto='';"
        "try{texto=(document.body?document.body.innerText:'').toLowerCase();}catch(e){}"
        "const payload=url+'||'+texto.slice(0,800);"
        "const ta=document.createElement('textarea');"
        "ta.value=payload;ta.style.position='fixed';ta.style.opacity='0';"
        "document.body.appendChild(ta);ta.focus();ta.select();"
        "document.execCommand('copy');"
        "document.body.removeChild(ta);"
        "})()"
    )
    try:
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.2)
        pyautogui.write("java", interval=JAVA_WRITE_INTERVAL_S)
        _colar_texto(js)
        pyautogui.press("enter")
        time.sleep(1)
        conteudo = pyperclip.paste() or ""
    except Exception as e:
        logger.warning(f"Não foi possível ler estado da página: {e}")
        return None

    if "||" not in conteudo:
        return None
    url, _, texto = conteudo.partition("||")
    return url, texto


def _bloqueio_no_dom(texto: str) -> bool:
    t = texto.lower()
    return any(m in t for m in _TEXTOS_BLOQUEIO_AUTOMACAO)


def _login_concluido(url: str) -> bool:
    u = url.lower()
    return _DOMINIO_ECAC in u and "login" not in u


def _pos_submit_falhou(url: str, texto: str) -> bool:
    if _URL_ECAC_LOGIN_MARCADOR in url:
        return True
    if _bloqueio_no_dom(texto):
        return True
    for m in _TEXTOS_ERRO_CAPTCHA:
        if m in texto:
            return True
    return False


# ---------------------------------------------------------------------------
# Chrome
# ---------------------------------------------------------------------------

def _abrir_chrome() -> None:
    global _chrome_process, _chrome_profile_dir
    import tempfile

    chrome_exe = os.path.expandvars(
        os.getenv("CHROME_EXECUTABLE_PATH", DEFAULT_CHROME_PATH)
    )
    perfil_temp = _chrome_profile_dir or os.path.join(
        tempfile.gettempdir(), f"Chrome_eCAC_{REMOTE_DEBUGGING_PORT}"
    )
    os.makedirs(perfil_temp, exist_ok=True)
    _chrome_profile_dir = perfil_temp

    cmd = [
        chrome_exe,
        f"--remote-debugging-port={REMOTE_DEBUGGING_PORT}",
        "--remote-allow-origins=*",
        "--new-window",
        "--start-maximized",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        f"--user-data-dir={perfil_temp}",
        URL_ECAC,
    ]
    _chrome_process = subprocess.Popen(cmd)
    time.sleep(AUTO_DELAY_S)
    pyautogui.hotkey("alt", "space")
    time.sleep(0.3)
    pyautogui.press("x")
    time.sleep(1)


def _fechar_navegador() -> None:
    try:
        pyautogui.hotkey("alt", "F4")
        time.sleep(CHROME_CLOSE_WAIT_S)
    except Exception as e:
        logger.warning(f"Falha ao fechar navegador: {e}")


def _fechar_e_reabrir_navegador() -> None:
    logger.warning(f"Bloqueio detectado — reiniciando navegador em {RETRY_COOLDOWN_S}s...")
    time.sleep(RETRY_COOLDOWN_S)
    _fechar_navegador()
    try:
        _abrir_chrome()
    except Exception as e:
        logger.warning(f"Falha ao reabrir Chrome: {e}")


def _abrir_nova_aba_e_reiniciar() -> None:
    logger.warning(f"Captcha não resolvido — aguardando {RETRY_COOLDOWN_S}s antes de reiniciar em nova aba...")
    time.sleep(RETRY_COOLDOWN_S)
    try:
        pyautogui.hotkey("ctrl", "t")
        time.sleep(1)
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.2)
        pyautogui.write("https://www.google.com", interval=JAVA_WRITE_INTERVAL_S)
        pyautogui.press("enter")
        time.sleep(2)
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.2)
        pyautogui.write(URL_ECAC, interval=JAVA_WRITE_INTERVAL_S)
        pyautogui.press("enter")
        time.sleep(AUTO_DELAY_S)
        pyautogui.hotkey("ctrl", "shift", "tab")
        time.sleep(0.5)
        pyautogui.hotkey("ctrl", "w")
        time.sleep(0.5)
    except Exception as e:
        logger.warning(f"Falha ao reiniciar em nova aba: {e}")


# ---------------------------------------------------------------------------
# Captcha
# ---------------------------------------------------------------------------

def _extrair_sitekey() -> Optional[tuple[str, str, str, str]]:
    js = (
        "script:(()=>{"
        "function buscar(doc,prof){"
        "if(prof>5)return null;"
        "try{"
        "const el=doc.querySelector('[data-sitekey]');"
        "if(el){const sk=el.getAttribute('data-sitekey')||'';"
        "const cls=(el.className||'')+'';"
        "const t=cls.includes('g-recaptcha')?'recaptcha':'hcaptcha';"
        "if(sk)return{sitekey:sk,tipo:t};}"
        "}catch(e){}"
        "let iframes=[];"
        "try{iframes=Array.from(doc.querySelectorAll('iframe'));}catch(e){}"
        "for(const f of iframes){"
        "const src=f.src||'';"
        "if(src.includes('hcaptcha')){const m=src.match(/sitekey=([^&]+)/);if(m)return{sitekey:m[1],tipo:'hcaptcha'};}"
        "if(src.includes('recaptcha')){const m=src.match(/[?&]k=([^&]+)/);if(m)return{sitekey:m[1],tipo:'recaptcha'};}"
        "}"
        "for(const f of iframes){"
        "try{const d=f.contentDocument;if(d){const r=buscar(d,prof+1);if(r)return r;}}catch(e){}"
        "}"
        "return null;"
        "}"
        "const r=buscar(document,0)||{sitekey:'',tipo:''};"
        "const payload=r.tipo+'||'+r.sitekey+'||'+window.location.href+'||'+navigator.userAgent;"
        "const ta=document.createElement('textarea');"
        "ta.value=payload;ta.style.position='fixed';ta.style.opacity='0';"
        "document.body.appendChild(ta);ta.focus();ta.select();"
        "document.execCommand('copy');"
        "document.body.removeChild(ta);"
        "})()"
    )
    try:
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.2)
        pyautogui.write("java", interval=JAVA_WRITE_INTERVAL_S)
        _colar_texto(js)
        pyautogui.press("enter")
        time.sleep(1)
        conteudo = pyperclip.paste()
    except Exception as e:
        logger.warning(f"Falha ao extrair sitekey: {e}")
        return None

    partes = (conteudo or "").split("||")
    if len(partes) != 4 or not partes[1]:
        return None
    tipo, sitekey, url, ua = partes
    return tipo or "hcaptcha", sitekey, url, ua or USER_AGENT


def _resolver_captcha_api(sitekey: str, page_url: str, tipo: str, user_agent: str) -> Optional[str]:
    try:
        resp = requests.post(
            CAPTCHA_API_URL,
            json={"type": tipo, "sitekey": sitekey, "pageUrl": page_url, "userAgent": user_agent, "useProxy": True},
            headers={"x-api-key": CAPTCHA_API_KEY},
            timeout=10,
            verify=False,
        )
        resp.raise_for_status()
        job_id = resp.json().get("jobId")
        if not job_id:
            return None

        logger.info(f"Captcha na fila | jobId={job_id}")
        fim = time.time() + CAPTCHA_TIMEOUT_S
        while time.time() < fim:
            time.sleep(CAPTCHA_POLL_INTERVAL_S)
            data = requests.get(
                f"{CAPTCHA_API_URL}/{job_id}",
                headers={"x-api-key": CAPTCHA_API_KEY},
                timeout=10,
                verify=False,
            ).json()
            estado = data.get("status")
            logger.info(f"Status captcha: {estado}")
            if estado == "completed":
                return data.get("token")
            if estado == "failed":
                return None
        return None
    except Exception as e:
        logger.warning(f"Erro API captcha: {e}")
        return None


def _injetar_token(token: str) -> None:
    token_js = json.dumps(token)
    js = (
        "script:(()=>{"
        f"const t={token_js};"
        "function tentarLoginCertificado(doc){"
        "try{"
        "const host=(doc.defaultView.location.hostname||'');"
        "if(!host.endsWith('acesso.gov.br'))return false;"
        "const csrfEl=doc.querySelector('[name=\"_csrf\"]');"
        "const captchaEl=doc.querySelector('[name=\"h-captcha-response\"]');"
        "if(!csrfEl||!captchaEl)return false;"
        "const params=new URLSearchParams(doc.defaultView.location.search);"
        "const clientId=params.get('client_id')||'';"
        "const authId=params.get('authorization_id')||'';"
        "if(!clientId||!authId)return false;"
        "const hostSemSub=host.replace(/^certificado\\./,'');"
        "const url='https://certificado.'+hostSemSub+'/login?client_id='+encodeURIComponent(clientId)+'&authorization_id='+encodeURIComponent(authId);"
        "const form=doc.createElement('form');"
        "form.method='POST';form.action=url;form.style.display='none';"
        "const campos={accountId:'',_csrf:csrfEl.value||'',operation:'login-certificate','h-captcha-response':t};"
        "Object.keys(campos).forEach(n=>{const i=doc.createElement('input');i.type='hidden';i.name=n;i.value=campos[n];form.appendChild(i);});"
        "doc.body.appendChild(form);form.submit();return true;"
        "}catch(e){return false;}"
        "}"
        "function processar(doc,prof){"
        "if(prof>5)return false;"
        "try{"
        "if(tentarLoginCertificado(doc))return true;"
        "const campos=doc.querySelectorAll('[name=\"h-captcha-response\"],[name=\"g-recaptcha-response\"]');"
        "if(campos.length){"
        "let form=null;"
        "campos.forEach(el=>{el.value=t;if(!form){form=el.closest('form');}});"
        "if(!form){form=doc.querySelector('form');}"
        "const widget=doc.querySelector('.h-captcha,[data-sitekey],.g-recaptcha');"
        "const cb=widget?widget.getAttribute('data-callback'):null;"
        "if(cb&&typeof doc.defaultView[cb]==='function'){doc.defaultView[cb](t);}"
        "else if(form){const btn=form.querySelector('button[type=\"submit\"],input[type=\"submit\"],button:not([type])');if(btn){btn.click();}else{form.submit();}}"
        "return true;"
        "}"
        "}catch(e){}"
        "let iframes=[];try{iframes=Array.from(doc.querySelectorAll('iframe'));}catch(e){}"
        "for(const f of iframes){try{const d=f.contentDocument;if(d&&processar(d,prof+1))return true;}catch(e){}}"
        "return false;"
        "}"
        "processar(document,0);"
        "})()"
    )
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.2)
    pyautogui.write("java", interval=JAVA_WRITE_INTERVAL_S)
    _colar_texto(js)
    pyautogui.press("enter")
    time.sleep(1)


def _resolver_captcha_automatico(
    timeout_espera_s: float = HCAPTCHA_WAIT_TIMEOUT_S,
    verificar_pos_submit: bool = True,
) -> bool:
    # 1) Bloqueio via imagem
    if _aguardar_padrao_visivel(BLOQUEIO_REF_DIR, BLOQUEIO_WAIT_TIMEOUT_S, rotulo="bloqueio"):
        return False

    # 2) Bloqueio via DOM
    estado = _ler_estado_pagina()
    if estado and _bloqueio_no_dom(estado[1]):
        return False

    # 3) Existe captcha?
    if not _aguardar_padrao_visivel(HCAPTCHA_REF_DIR, timeout_espera_s, rotulo="hCaptcha"):
        logger.info("Nenhum captcha na tela — seguindo.")
        return True

    # 4) Resolver via API
    dados = _extrair_sitekey()
    if not dados:
        return False
    tipo, sitekey, url, ua = dados
    token = _resolver_captcha_api(sitekey, url, tipo, ua)
    if not token:
        return False

    _injetar_token(token)

    if not verificar_pos_submit:
        time.sleep(AUTO_DELAY_S)
        return True

    time.sleep(CAPTCHA_DELAY_ANTES_VERIFICACAO_POS_SUBMIT_S)
    estado_pos = _ler_estado_pagina()
    if estado_pos:
        url_pos, texto_pos = estado_pos
        if _bloqueio_no_dom(texto_pos) or _pos_submit_falhou(url_pos, texto_pos):
            return False

    if _aguardar_padrao_visivel(HCAPTCHA_REF_DIR, CAPTCHA_VERIFICACAO_POS_SUBMIT_S, rotulo="hCaptcha"):
        logger.warning("Captcha ainda visível após submissão.")
        return False

    logger.info("Captcha resolvido com sucesso.")
    return True


# ---------------------------------------------------------------------------
# Navegação / interação
# ---------------------------------------------------------------------------

def _clicar_entrar_govbr() -> None:
    larg, alt = pyautogui.size()
    x = int(larg * 0.646)
    y = int(alt * 0.509)
    pyautogui.moveTo(x, y, duration=0.5)
    pyautogui.click()
    logger.info("Cliquei em 'Entrar com gov.br'")


def _clicar_certificado_digital() -> None:
    time.sleep(AUTO_DELAY_S)
    clicou = _localizar_e_clicar_via_imagem(
        CERTIFICADO_BTN_REF_DIR,
        "botão 'Seu certificado digital'",
        CERTIFICADO_BTN_WAIT_TIMEOUT_S,
    )
    if clicou:
        time.sleep(AUTO_DELAY_S)
        return

    # Fallback via JavaScript
    logger.warning("Botão de certificado não encontrado via imagem — usando JS fallback.")
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.2)
    pyautogui.write("java", interval=JAVA_WRITE_INTERVAL_S)
    js = """script:(()=>{const c=()=>{const b=document.getElementById('login-certificate');if(b){b.scrollIntoView({block:'center'});b.click();return true;}return false;};if(!c()){let t=0;const i=setInterval(()=>{t++;if(c()||t>40){clearInterval(i);}},500);}})()"""
    _colar_texto(js)
    pyautogui.press("enter")
    time.sleep(AUTO_DELAY_S)


def _selecionar_certificado_via_mouse() -> bool:
    """Clica em OK no diálogo nativo do Windows."""
    time.sleep(TEMPO_ABRIR_JANELA_CERTIFICADO)
    clicou = _localizar_e_clicar_via_imagem(
        OK_BUTTON_REF_DIR,
        "botão 'OK' do diálogo de certificado",
        OK_BUTTON_WAIT_TIMEOUT_S,
    )
    if clicou:
        time.sleep(AUTO_DELAY_S)
        return True

    # Fallback: navegar pelo diálogo nativo com teclado
    logger.warning("Botão OK não encontrado via imagem — tentando seleção por teclado.")
    return False


def _selecionar_certificado_por_posicao(chave: str) -> None:
    """Fallback: seleciona certificado no diálogo nativo por posição (tecla down)."""
    info = CERTIFICADOS.get(chave, {})
    pos = info.get("pos")
    if not pos:
        logger.warning(f"Posição não configurada para '{chave}'.")
        return

    time.sleep(CERTIFICADO_PRE_SEL_DELAY)
    pyautogui.click(CERTIFICADO_PRIMEIRO_ITEM_X, CERTIFICADO_PRIMEIRO_ITEM_Y)
    time.sleep(0.6)
    pyautogui.press("home")
    time.sleep(0.5)

    for i in range(pos - 1):
        pyautogui.press("down")
        time.sleep(CERTIFICADO_ITEM_DOWN_DELAY)

    pyautogui.press("enter")
    time.sleep(1.5)
    logger.info(f"Certificado selecionado por posição: {pos}")


def _tentar_clique_certificado_recuperacao() -> bool:
    for i in range(1, MAX_TENTATIVAS_CLIQUE_CERTIFICADO_RECUPERACAO + 1):
        logger.info(f"Recuperação: clique {i}/{MAX_TENTATIVAS_CLIQUE_CERTIFICADO_RECUPERACAO} em 'Seu certificado digital'...")
        _clicar_certificado_digital()
        time.sleep(DELAY_VERIFICACAO_POS_CLIQUE_RECUPERACAO_S)

        estado = _ler_estado_pagina()
        if not estado:
            _selecionar_certificado_via_mouse()
            time.sleep(DELAY_VERIFICACAO_POS_CLIQUE_RECUPERACAO_S)
            estado = _ler_estado_pagina()

        if not estado:
            continue

        url, texto = estado
        if _bloqueio_no_dom(texto):
            return False
        if _login_concluido(url):
            logger.info(f"Login concluído na recuperação tentativa {i}.")
            return True

    return False


# ---------------------------------------------------------------------------
# Extração de cookies e gravação de sessão
# ---------------------------------------------------------------------------

def _extrair_cookies_cdp(porta: int = REMOTE_DEBUGGING_PORT) -> list[dict]:
    """Extrai todos os cookies (incluindo HttpOnly) via Playwright CDP."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright não instalado — cookies não serão extraídos.")
        return []

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}")
            try:
                contexto = browser.contexts[0]
                cookies_raw = contexto.cookies()
                cookies = []
                for c in cookies_raw:
                    cookies.append({
                        "dominio":   c.get("domain", ""),
                        "nome":      c.get("name", ""),
                        "valor":     c.get("value", ""),
                        "path":      c.get("path", "/"),
                        "http_only": c.get("httpOnly", False),
                        "secure":    c.get("secure", False),
                        "samesite":  c.get("sameSite", ""),
                        "expira":    c.get("expires", -1),
                    })
                logger.info(f"{len(cookies)} cookie(s) extraído(s) via CDP.")
                return cookies
            finally:
                browser.close()
    except Exception as e:
        logger.warning(f"Falha ao extrair cookies via CDP: {e}")
        return []


def salvar_sessao(
    certificado_nome: str,
    pasta_storage: str | Path,
    porta: int = REMOTE_DEBUGGING_PORT,
) -> Optional[Path]:
    """Extrai cookies e salva sessão JSON em pasta_storage/session_{cnpj_ou_cert}.json."""
    pasta = Path(pasta_storage)
    pasta.mkdir(parents=True, exist_ok=True)

    cookies = _extrair_cookies_cdp(porta)

    # Nome do arquivo baseado no certificado (normalizado)
    slug = _normalizar_nome(certificado_nome).replace(" ", "_").lower()
    arquivo = pasta / f"session_{slug}.json"

    sessao = {
        "login_at":          datetime.now().isoformat(),
        "certificado_nome":  certificado_nome,
        "porta_cdp":         porta,
        "cookies":           cookies,
    }

    try:
        arquivo.write_text(json.dumps(sessao, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Sessão salva em: {arquivo}")
        return arquivo
    except Exception as e:
        logger.error(f"Falha ao salvar sessão: {e}")
        return None


# ---------------------------------------------------------------------------
# Ponto de entrada público
# ---------------------------------------------------------------------------

def executar_login(
    certificado_nome: str = "Studio Varejo",
    pasta_storage: Optional[str | Path] = None,
    abrir_chrome: bool = True,
) -> bool:
    """Executa o fluxo completo de login no eCAC.

    Args:
        certificado_nome: Nome do certificado (ex: "Studio Varejo").
        pasta_storage:    Caminho da pasta storage/ onde o JSON será salvo.
                          Se None, não salva sessão.
        abrir_chrome:     Se True, abre um novo Chrome. Se False, assume que
                          o Chrome já está aberto na home do eCAC.

    Returns:
        True se login foi concluído com sucesso.
    """
    try:
        chave = _resolver_chave_certificado(certificado_nome)
    except ValueError as e:
        logger.error(str(e))
        return False

    logger.info(f"=== Iniciando login com certificado: {chave} ===")

    if abrir_chrome:
        _abrir_chrome()

    for tentativa in range(1, MAX_TENTATIVAS_FLUXO + 1):
        logger.info(f"=== Tentativa {tentativa}/{MAX_TENTATIVAS_FLUXO} ===")
        try:
            # Etapa 1: Captcha inicial
            _clicar_entrar_govbr()
            ok = _resolver_captcha_automatico()
            if not ok:
                logger.error(f"Tentativa {tentativa}: captcha inicial falhou.")
                if tentativa < MAX_TENTATIVAS_FLUXO:
                    _abrir_nova_aba_e_reiniciar()
                    continue
                return False

            # Etapa 2: Clique em "Seu certificado digital"
            _clicar_certificado_digital()
            ok = _resolver_captcha_automatico(
                timeout_espera_s=HCAPTCHA_WAIT_TIMEOUT_POS_CERTIFICADO_S,
                verificar_pos_submit=False,
            )
            if not ok:
                logger.error(f"Tentativa {tentativa}: captcha pós-clique em certificado falhou.")
                if tentativa < MAX_TENTATIVAS_FLUXO:
                    _abrir_nova_aba_e_reiniciar()
                    continue
                return False

            # Etapa 3: Diálogo nativo de seleção de certificado
            _selecionar_certificado_via_mouse()

            # Etapa 4: Verificação pós-seleção
            time.sleep(3)
            estado = _ler_estado_pagina()

            if estado:
                url, texto = estado
                logger.info(f"Estado pós-certificado: {url}")

                if _bloqueio_no_dom(texto):
                    logger.warning(f"Tentativa {tentativa}: bloqueio detectado pós-certificado.")
                    if tentativa < MAX_TENTATIVAS_FLUXO:
                        _fechar_e_reabrir_navegador()
                        continue
                    return False

                if _login_concluido(url):
                    logger.info(f"Login concluído! Página: {url}")
                    if pasta_storage:
                        salvar_sessao(certificado_nome, pasta_storage)
                    return True
            else:
                logger.warning("DOM inacessível pós-seleção — tentando recuperação.")

            # Etapa 5: Clique de recuperação
            if _tentar_clique_certificado_recuperacao():
                logger.info("Login concluído via recuperação.")
                if pasta_storage:
                    salvar_sessao(certificado_nome, pasta_storage)
                return True

            logger.warning(f"Tentativa {tentativa}: recuperação falhou.")
            if tentativa < MAX_TENTATIVAS_FLUXO:
                _fechar_e_reabrir_navegador()
                continue

            return False

        except Exception as e:
            logger.warning(f"Erro inesperado na tentativa {tentativa}: {e}")
            if tentativa < MAX_TENTATIVAS_FLUXO:
                _abrir_nova_aba_e_reiniciar()
                continue
            return False

    return False


# ---------------------------------------------------------------------------
# Execução standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Login eCAC via certificado digital")
    parser.add_argument(
        "--certificado",
        default="Studio Varejo",
        help="Nome do certificado (ex: 'Studio Varejo')",
    )
    parser.add_argument(
        "--storage",
        default=None,
        help="Pasta para salvar o JSON de sessão (ex: C:\\RPA\\sch_ecac_pro\\storage)",
    )
    parser.add_argument(
        "--sem-chrome",
        action="store_true",
        help="Não abre o Chrome (assume que já está aberto)",
    )
    args = parser.parse_args()

    ok = executar_login(
        certificado_nome=args.certificado,
        pasta_storage=args.storage,
        abrir_chrome=not args.sem_chrome,
    )
    print(f"\n{'✔ Login concluído' if ok else '✘ Login falhou'}")
    sys.exit(0 if ok else 1)