# README — sch\_ecac\_pro

Oct 6, 2026 · @Pedro

Sistema RPA de coleta automatica de documentos fiscais no portal eCAC da Receita Federal. Realiza autenticacao via certificado digital A3/A1, reutilizacao de sessao por cookies e oferece interface grafica para operar sem linha de comando.

## Visao Geral

O **sch\_ecac\_pro** e um sistema de automacao (RPA) que acessa o portal eCAC (Centro Virtual de Atendimento da Receita Federal) para baixar automaticamente documentos fiscais de um ou mais CNPJs. Opera em segundo plano, sem intervencao manual alem do disparo inicial.

**O que ele coleta:**

- **DARF** (Documentos de Arrecadacao de Receitas Federais) — comprovantes de pagamento
- **DCTFWeb** (Declaracao de Debitos e Creditos Tributarios Federais Web) — declaracoes completas em PDF
- **Fontes Pagadoras** — relatorio de rendimentos recebidos de pessoas juridicas

**Stack tecnologica:**

- `Python 3.10+` — linguagem principal
- `PyAutoGUI` — automacao de interface grafica (cliques, digitacao, busca por imagem na tela)
- `Playwright` — automacao de browser via protocolo CDP (Chrome DevTools Protocol), permite interagir com o DOM e capturar downloads
- `tkinter` — interface grafica nativa do Python (zero dependencias extras)
- `requests` — chamadas HTTP para API de resolucao de captcha
- `PIL / Pillow` — comparacao de imagens para deteccao de elementos na tela
- `pyperclip` — operacoes de clipboard para injecao de tokens de captcha

**Como funciona em alto nivel:**

1. O usuario inicia pelo `app.py` (interface) ou pelo `main.py` (CLI)
2. O sistema tenta reutilizar uma sessao anterior salva em JSON
3. Se nao houver sessao valida, faz login completo via certificado digital
4. Aguarda 5 segundos apos o login
5. Executa os fluxos de coleta selecionados
6. Salva os PDFs na estrutura de pastas `sch_ecac_pro/` dentro do destino configurado

## Estrutura de Pastas

### Pastas do projeto (codigo-fonte)

```
sch_ecac_pro/           <- pasta raiz do projeto
|-- app.py              <- interface grafica (tkinter)
|-- main.py             <- orquestrador (CLI + API)
|-- login_ecac.py       <- login completo via certificado
|-- login_session.py    <- reutilizacao de sessao salva
|-- darf.py             <- coleta de DARFs
|-- dctfweb.py          <- coleta de DCTFWeb
|-- fontes_pagadoras.py <- coleta de Fontes Pagadoras
|-- ecac_session.py     <- gerenciador de sessao ativa
|-- assets/             <- imagens de referencia (PyAutoGUI)
|   |-- hcaptcha_refs/          <- captchas detectados por imagem
|   |-- bloqueio_refs/          <- telas de bloqueio
|   |-- certificado_btn_refs/   <- botao de certificado digital
|   |-- ok_button_refs/         <- botao OK do dialogo nativo
|   |-- darf_menu_pagamentos.png
|   |-- darf_btn_consultar.png
|   |-- dctf_menu_declaracoes.png
|   |-- perfil_acesso.png
|   |-- campo_cnpj.png
|   |-- btn_home.png
|   `-- (demais PNGs de referencia)
`-- logs/               <- criada automaticamente em execucao
```

### Pastas geradas na execucao (pasta de destino)

O sistema cria automaticamente a seguinte estrutura dentro da pasta de destino configurada:

```
<destino>/
`-- sch_ecac_pro/
    |-- documentos/
    |   |-- darf/               <- PDFs dos DARFs coletados
    |   |-- dctf/               <- PDFs das declaracoes DCTFWeb
    |   `-- fontes_pagadoras/   <- PDFs de Fontes Pagadoras
    `-- storage/
        `-- session_<certificado>.json  <- sessao salva apos login
```

Exemplo com destino `\\192.168.1.100\temp`:

```
\\192.168.1.100\temp\sch_ecac_pro\documentos\darf\DARF_12345678000199_0001.pdf
\\192.168.1.100\temp\sch_ecac_pro\storage\session_studio_varejo.json
```

## Fluxo Geral de Execucao

### Diagrama do fluxo

```
[Usuario] --> [app.py ou main.py]
                     |
                     v
          [Cria estrutura de pastas]
                     |
                     v
          [login_session.py]
          Existe sessao valida?
          (JSON < 8h + Chrome na porta 9222)
               /         \
             SIM          NAO
              |            |
              |     [login_ecac.py]
              |     Abre Chrome + CDP
              |     Navega para gov.br
              |     Detecta hCaptcha?
              |          / \
              |        SIM  NAO
              |         |    |
              |    Resolve   |
              |    via API   |
              |         \   /
              |     Seleciona certificado
              |     (dialogo nativo Windows)
              |     Confirma login no eCAC
              |     Salva sessao JSON
              \           /
               \         /
         [Aguarda 5 segundos]
                     |
              ,------+------.
              |      |      |
           [DARF] [DCTFWeb] [Fontes]
              |      |      |
              `------+------'
                     |
          [PDFs salvos em documentos/]
```

### Descricao das etapas

**1. Verificacao de sessao (`login_session.py`)**

Antes de qualquer coisa, o sistema tenta reutilizar uma sessao anterior. Ele verifica se:

- Ha um arquivo `session_<certificado>.json` na pasta `storage/`
- O arquivo tem menos de 8 horas (parametro `SESSION_MAX_AGE_HORAS`)
- O Chrome esta rodando com CDP ativo na porta 9222

Se tudo estiver ok, os cookies sao injetados no contexto do Playwright e a sessao e validada navegando ate o eCAC. Se a URL resultante nao contiver `login`, a sessao e considerada valida.

**2. Login completo (`login_ecac.py`)**

Caso a sessao esteja expirada ou inexistente:

- Abre o Chrome com flag `--remote-debugging-port=9222` (ou conecta ao Chrome ja aberto)
- Navega para `https://acesso.gov.br`
- Usa PyAutoGUI com imagens de referencia (`assets/hcaptcha_refs/`) para detectar o hCaptcha
- Envia o `sitekey` e a URL para uma API externa de resolucao de captcha
- Injeta o token resolvido via JavaScript na barra de endereco
- Abre o dialogo nativo de selecao de certificado
- Seleciona o certificado correto pelo nome configurado em `CERTIFICADOS`
- Confirma o login no dialogo nativo (botao OK detectado por imagem)
- Extrai todos os cookies via CDP (incluindo HttpOnly) e salva em JSON

**3. Aguarda 5 segundos**

Apos o login (novo ou reutilizado), o sistema aguarda `time.sleep(5)` para garantir que a pagina do eCAC terminou de carregar completamente antes de iniciar a navegacao.

**4. Execucao dos fluxos de coleta**

Cada fluxo e independente e pode ser executado separadamente. Todos seguem a mesma estrutura:

- **Fase 1 (PyAutoGUI)**: navega pelo menu do eCAC, preenche filtros de data, clica em Consultar
- **Fase 2 (Playwright via CDP)**: percorre resultados, seleciona registros, captura downloads de PDF

### Formato do arquivo de sessao JSON

```json
{
  "login_at": "2026-10-06T09:15:30",
  "certificado_nome": "Studio Varejo",
  "porta_cdp": 9222,
  "cookies": [
    {
      "dominio": ".receita.fazenda.gov.br",
      "nome": "ASP.NET_SessionId",
      "valor": "abc123...",
      "path": "/",
      "http_only": true,
      "secure": true,
      "samesite": "None",
      "expira": 1728234930
    }
  ]
}
```

## login\_ecac.py — Login Completo

**Responsabilidade:** Realizar o login completo no eCAC via certificado digital A3/A1, resolver o hCaptcha automaticamente e salvar a sessao em JSON para reuso futuro.

### Como funciona internamente

**Certificados suportados** (dicionario `CERTIFICADOS`):

| Nome de exibicao | Chave interna | Posicao no dialogo |
| --- | --- | --- |
| Studio Varejo | STUDIO VAREJO | 1 |
| Studio Operacional | STUDIO OPERACIONAL | 7 |
| Studio Brokers | STUDIO BROKERS | 2 |
| Studio Store | STUDIO STORE | 6 |
| Studio Agronegócios | STUDIO AGRONEGOCIOS | 9 |
| Space W | SPACE W | (posicao manual) |
| Alianca Legal | ALIANCA LEGAL | 4 |
| Studio Fiscal | STUDIO FISCAL | 8 |
| Studio Bank | STUDIO BANK | 3 |
| Audit Tecnologia | AUDIT TECNOLOGIA | 5 |

A "posicao" representa quantas vezes a seta PARA BAIXO e pressionada no dialogo nativo do Windows para selecionar o certificado correto.

**Resolucao de captcha:**

1. PyAutoGUI compara a tela com imagens em `assets/hcaptcha_refs/` para detectar o captcha
2. Extrai o `sitekey` da pagina via Playwright
3. Envia `sitekey` + URL para a API configurada em `CAPTCHA_API_URL`
4. Recebe o token de resposta
5. Injeta o token via JavaScript na barra de endereco do Chrome

**Extracao de cookies (via CDP):**

Usa Playwright conectado via CDP para extrair todos os cookies do contexto, incluindo os marcados como `HttpOnly` (inacessiveis por `document.cookie`). Os cookies sao serializados em formato compativel com o Playwright para reinjeccao posterior.

### Funcao principal

```python
from login_ecac import executar_login

ok = executar_login(
    certificado_nome="Studio Varejo",
    pasta_storage="C:/RPA/sch_ecac_pro/storage",
    abrir_chrome=True   # False = assume Chrome ja aberto
)
```

**Parametros:**

- `certificado_nome` — nome do certificado (ex: `"Studio Varejo"`). Aceita acento ou sem acento.
- `pasta_storage` — caminho onde o arquivo `session_<slug>.json` sera salvo
- `abrir_chrome` — se `True`, abre um novo processo do Chrome; se `False`, conecta ao Chrome ja aberto na porta 9222

**Retorna:** `True` se o login foi concluido e a sessao foi salva; `False` em caso de falha.

### Uso standalone (linha de comando)

```bash
# Login com certificado padrao (Studio Varejo)
python login_ecac.py

# Especificando certificado e pasta de storage
python login_ecac.py --certificado "Studio Varejo" --storage "C:/RPA/sch_ecac_pro/storage"

# Usando Chrome ja aberto (sem abrir novo)
python login_ecac.py --certificado "Studio Varejo" --storage "C:/saida/storage" --sem-chrome
```

**Pre-condicao para `--sem-chrome`:** Chrome/Edge deve estar aberto com a flag `--remote-debugging-port=9222`.

### Sessao salva

Apos login bem-sucedido, salva `storage/session_studio_varejo.json` (slug gerado a partir do nome do certificado, normalizado e sem acentos). O arquivo e lido por `login_session.py` na proxima execucao.

## login\_session.py — Reutilizacao de Sessao

**Responsabilidade:** Tentar restaurar uma sessao anterior sem realizar novo login. Verifica se o arquivo JSON de sessao existe, esta dentro do prazo de validade e se os cookies ainda dao acesso ao eCAC.

### Logica de validacao

1. **Verifica porta CDP** — checa se ha um Chrome em `http://127.0.0.1:9222/json/version`. Se nao houver, retorna `False` imediatamente (nao ha browser para injetar os cookies)
2. **Localiza o arquivo de sessao** — busca `storage/session_<slug>.json` pelo nome do certificado. Se nao encontrar pelo slug exato, usa o arquivo mais recente na pasta
3. **Valida a idade** — le o campo `login_at` do JSON e verifica se o login foi ha menos de `SESSION_MAX_AGE_HORAS = 8` horas
4. **Injeta cookies** — conecta ao Chrome via CDP (Playwright), injeta os cookies no contexto
5. **Navega para o eCAC** — abre `https://cav.receita.fazenda.gov.br/eCAC/publico/login.aspx`
6. **Verifica autenticacao** — se a URL resultante contem o dominio eCAC mas NAO contem `login`, a sessao e valida. Tambem verifica o conteudo da pagina por palavras como `sair`, `encerrar sessao`, `minha conta`

### Funcao principal

```python
from login_session import tentar_sessao

ok = tentar_sessao(
    certificado_nome="Studio Varejo",
    pasta_storage="C:/RPA/sch_ecac_pro/storage",
    porta_cdp=9222
)
```

**Retorna:** `True` se a sessao foi restaurada com sucesso; `False` caso contrario.

### Uso standalone

```bash
python login_session.py --certificado "Studio Varejo" --storage "C:/RPA/sch_ecac_pro/storage"
python login_session.py --certificado "Studio Varejo" --storage "C:/storage" --porta 9222
```

### Integracao com login\_ecac.py

Este arquivo e sempre chamado ANTES do `login_ecac.py`. O `main.py` implementa o seguinte fluxo:

```python
if tentar_sessao(...):
    pass  # sessao ok, continua
else:
    executar_login(...)  # login completo
```

Nunca se deve chamar `login_ecac.py` diretamente sem antes tentar `login_session.py`, pois o login completo abre o dialogo de certificado digital, o que pode ser desnecessario se a sessao ainda e valida.

## Arquivos de Coleta

Todos os tres arquivos de coleta seguem a mesma arquitetura de duas fases e sao **100% independentes**: podem ser executados standalone se o Chrome ja estiver aberto e logado no eCAC, ou acionados pelo `main.py` como modulos.

---

### darf.py — Coleta de DARFs

**O que coleta:** Documentos de Arrecadacao de Receitas Federais (comprovantes de pagamento de tributos federais).

**Classe:** `DARF(cnpj, diretorio_destino, porta_cdp=9222)`

**Metodo principal:** `executar(data_inicio, data_fim, pagina_start=1) -> bool`

**Fase 1 — Navegacao (PyAutoGUI):**

1. Clica em "Pagamentos e Parcelamentos" no menu do eCAC (`assets/darf_menu_pagamentos.png`)
2. Clica em "Consulta de Pagamentos / DARF" (`assets/darf_menu_consulta.png`)
3. Preenche os campos de data inicio e fim (`assets/darf_campo_data_inicio.png`, `darf_campo_data_fim.png`)
4. Clica em Consultar (`assets/darf_btn_consultar.png`)

**Fase 2 — Download (Playwright via CDP):**

1. Conecta ao Chrome na porta 9222 via `playwright.chromium.connect_over_cdp()`
2. Marca o checkbox "Selecionar todos" da pagina atual
3. Clica em cada link de PDF e captura o download com `page.expect_download()`
4. Salva o arquivo em `documentos/darf/`
5. Avanca para a proxima pagina ate nao haver mais

**Nomenclatura dos arquivos:** `DARF_<cnpj>_<indice_4_digitos>.pdf`

**Uso standalone:**

```bash
# Chrome ja aberto e logado
python darf.py --cnpj 12345678000199 --destino "\\\\192.168.1.100\\temp" --inicio 01012024 --fim 31122024

# Com login automatico
python darf.py --cnpj 12345678000199 --destino "C:/saida" --login auto --certificado "Studio Varejo"
```

---

### dctfweb.py — Coleta de DCTFWeb

**O que coleta:** Declaracoes de Debitos e Creditos Tributarios Federais Web (declaracoes completas de contribuicoes previdenciarias).

**Classe:** `DCTFWeb(cnpj, diretorio_destino)`

**Metodo principal:** `executar(data_inicio_str, data_fim_str) -> tuple[bool, list[str]]`

**Logica de blocos anuais:**

O portal DCTFWeb so permite consultar um ano por vez. O metodo `_calcular_blocos_anuais()` divide automaticamente o periodo informado em blocos anuais. Por exemplo, o periodo `01012023` a `31052025` vira:

- `(2023, "01012023", "31122023")`
- `(2024, "01012024", "31122024")`
- `(2025, "01012025", "31052025")`

**Fluxo por ano:**

1. Navega para o servico DCTFWeb (`assets/dctf_menu_declaracoes.png`, `dctf_menu_dctfweb.png`)
2. Seleciona o periodo com os campos de data
3. Clica em Consultar
4. Verifica se ha registros (`assets/dctf_sem_registros.png`)
5. Localiza icones de visualizacao/download (`assets/dctf_icone_visualizar.png` ou `dctf_icone_pdf.png`)
6. Clica em cada icone, aguarda o PDF aparecer na pasta de destino
7. Volta para a lista (`Alt + Left`) e continua

**Nomenclatura dos arquivos:** `DCTFWeb_<cnpj>_<ano>_<indice_4_digitos>.pdf`

**Uso standalone:**

```bash
python dctfweb.py --cnpj 12345678000199 --destino "\\\\192.168.1.100\\temp"
python dctfweb.py --cnpj 12345678000199 --destino "C:/saida" --inicio 01012023 --fim 31052025 --login auto
```

---

### fontes\_pagadoras.py — Coleta de Fontes Pagadoras

**O que coleta:** Relatorio de rendimentos recebidos de pessoas juridicas (Fontes Pagadoras) para o CNPJ informado.

**Classe:** `FontesPagadoras(cnpj, razao_social, coletar_filiais, ano_inicio, ano_fim)`

**Metodo principal:** `executar(porta_cdp, diretorio_destino) -> tuple[bool, ResultadoColeta]`

**ResultadoColeta:** Objeto simples com atributos `total: int` e `arquivos: list[str]`.

**Estrategia de execucao:**

O arquivo tenta primeiro usar os modulos do projeto original (`from src.fontes_pagadoras import ...`). Se nao estiverem disponiveis, executa seu proprio fluxo interno (`_executar_fluxo_proprio()`), garantindo que funcione de forma totalmente autonoma.

**Uso standalone:**

```bash
python fontes_pagadoras.py --cnpj 12345678000199 --razao "Empresa XYZ" --destino "C:/saida"
python fontes_pagadoras.py --cnpj 12345678000199 --razao "Empresa" --destino "C:/saida" --ano-inicio 2022 --ano-fim 2024 --filiais
```

## main.py — Orquestrador

**Responsabilidade:** Ponto de entrada principal do sistema. Orquestra o fluxo completo: cria as pastas, executa o login (sessao ou completo), aguarda 5 segundos e dispara os fluxos de coleta selecionados.

### API publica (uso como modulo)

**`executar()` — executa login + fluxos:**

```python
from main import executar

resultados = executar(
    cnpj="12345678000199",
    razao_social="Empresa XYZ Ltda",
    certificado_nome="Studio Varejo",
    destino_base=r"\\192.168.1.100\temp",
    data_inicio="01012024",
    data_fim="31122024",
    fluxos=["darf", "dctf", "fontes"],
    ano_inicio=2024,          # opcional; deduz do data_inicio
    ano_fim=2024,             # opcional; deduz do data_fim
    coletar_filiais=False,    # True = inclui filiais em Fontes Pagadoras
    porta_cdp=9222,
    abrir_chrome=True,
)
# resultados = {"darf": True, "dctf": True, "fontes": True}
```

**`apenas_login()` — so faz o login corretamente, salva a sessao:**

```python
from main import apenas_login

ok = apenas_login(
    certificado_nome="Studio Varejo",
    destino_base=r"\\192.168.1.100\temp",
    porta_cdp=9222,
    abrir_chrome=True,
)
```

**`criar_estrutura_pastas()` — garante que as pastas existam:**

```python
from main import criar_estrutura_pastas

pastas = criar_estrutura_pastas(r"\\192.168.1.100\temp")
# pastas = {"raiz": ..., "darf": ..., "dctf": ..., "fontes_pagadoras": ..., "storage": ...}
```

### Uso via linha de comando

```bash
# Executa todos os tres fluxos
python main.py --cnpj 12345678000199 --destino "\\\\192.168.1.100\\temp" --fluxos darf dctf fontes

# Apenas DARF com periodo customizado
python main.py --cnpj 12345678000199 --destino "C:/saida" --fluxos darf --inicio 01012023 --fim 31122024

# Apenas login (sem rodar coleta)
python main.py --so-login --certificado "Studio Varejo" --destino "C:/saida"

# Chrome ja aberto
python main.py --cnpj 12345678000199 --destino "C:/saida" --fluxos darf --sem-chrome
```

### Fluxo interno de `executar()`

```
1. criar_estrutura_pastas(destino_base)
2. executar_login_unificado():
   a. tentar_sessao()  -->  se ok: continua
   b. executar_login() -->  se ok: continua
   c. se ambos falharem: marca todos os fluxos como False e retorna
3. time.sleep(5)
4. para cada fluxo em ["darf", "dctf", "fontes"]:
   - chama o modulo correspondente
   - registra sucesso/falha no dict resultados
5. retorna resultados
```

## app.py — Interface Grafica

**Responsabilidade:** Fornecer uma interface visual (tkinter) para operar o sistema sem precisar usar o terminal.

**Executar:** `python app.py`

### Tela principal

A janela e dividida em secoes:

**Configuracoes:**

- **Certificado** — dropdown com os 10 certificados suportados. Padrao: `Studio Varejo`.
- **Pasta de destino** — campo de texto editavel. Padrao: `\\192.168.1.100\temp`. Ha um botao `...` para abrir o explorador de arquivos e escolher qualquer pasta local ou de rede.
- **Porta CDP** — porta do Chrome com depuracao remota. Padrao: `9222`.

**Empresa:**

- **CNPJ** — 14 digitos sem mascara
- **Razao Social** — nome da empresa (usado por Fontes Pagadoras)

**Periodo:**

- **Data inicio** — formato `ddmmaaaa`. Padrao: `0101<ano_anterior>`
- **Data fim** — formato `ddmmaaaa`. Padrao: data de hoje

**Fluxos a executar:**

- Checkbox `DARF`
- Checkbox `DCTFWeb`
- Checkbox `Fontes Pagadoras`
- Checkbox `Incluir filiais (Fontes Pagadoras)`

**Botoes:**

| Botao | Cor | Funcao |
| --- | --- | --- |
| Fazer apenas o login | Laranja | Executa so o login e salva sessao. Util para "reaquecer" a sessao antes de rodar os fluxos depois. |
| Executar fluxos | Verde | Tentativa de sessao -> login se necessario -> aguarda 5s -> coleta selecionada |
| Limpar log | Cinza | Limpa o painel de log da interface |

**Log de execucao:**

O painel inferior exibe todas as mensagens em tempo real, com timestamp. As acoes do `main.py`, `login_ecac.py`, `darf.py`, etc. aparecem aqui durante a execucao.

### Threading

Todas as operacoes de execucao rodam em uma `Thread` separada (daemon thread) para nao travar a interface grafica durante a coleta. Os botoes ficam desativados enquanto uma operacao esta em andamento, impedindo cliques duplos.

### Validacoes

Antes de qualquer execucao, a interface verifica:

- Certificado selecionado
- Pasta de destino preenchida
- CNPJ preenchido (apenas para execucao de fluxos)
- Ao menos um fluxo selecionado
- Datas no formato correto (8 digitos)

Erros de validacao exibem uma caixa de dialogo (`messagebox.showwarning`) sem iniciar a operacao.

## ecac\_session.py — Gerenciador de Sessao Ativa

**Responsabilidade:** Classe `ECacSession` que representa uma sessao autenticada no eCAC. Centraliza operacoes comuns a todos os fluxos: troca de perfil de CNPJ, retorno para a home e conexao com o Playwright.

### Classe ECacSession

```python
from ecac_session import ECacSession

sessao = ECacSession(porta_cdp=9222)
sessao.trocar_perfil("12345678000199")
context, page = sessao.conectar_playwright()
# ... usa page para navegar ...
sessao.encerrar_playwright()

# Ou como context manager:
with ECacSession() as sessao:
    sessao.trocar_perfil("12345678000199")
    context, page = sessao.conectar_playwright()
```

**Metodos:**

| Metodo | Descricao |
| --- | --- |
| `trocar_perfil(cnpj)` | Clica no botao de perfil, preenche o CNPJ, confirma. Verifica bloqueios apos a troca. |
| `voltar_home()` | Clica em `btn_home.png`; fallback: pressiona F5 |
| `conectar_playwright()` | Conecta ao Chrome via CDP; retorna `(context, page)` |
| `encerrar_playwright()` | Desconecta o Playwright sem fechar o Chrome |
| `limpar_cnpj(cnpj)` | Remove mascara do CNPJ (estatico) |

### Excecoes

Todas estendem `ECacSessionError`:

| Excecao | Quando e lancada |
| --- | --- |
| `CriticalImageNotFoundError` | Imagem critica nao encontrada na tela no timeout |
| `SemProcuracaoError` | eCAC exibe tela de "sem procuracao" para o CNPJ |
| `CNPJBlockedMessageError` | eCAC exibe mensagem de pendencia/bloqueio |
| `InvalidCNPJError` | CNPJ foi recusado como invalido pelo portal |

### Helpers de visao (funcoes globais)

Disponiveis para uso direto nos outros modulos:

```python
from ecac_session import esperar_e_clicar, imagem_existe, esperar_sumir

# Aguarda a imagem aparecer e clica
esperar_e_clicar("darf_btn_consultar.png", timeout=15, critical=True)

# Verifica se a imagem esta na tela
if imagem_existe("dctf_sem_registros.png", confianca=0.9):
    print("Sem registros")

# Aguarda a imagem desaparecer
esperar_sumir("btn_alterar.png", timeout=15)
```

Todas as imagens sao buscadas em `assets/` (relativo ao diretorio do arquivo).

---

## Pre-requisitos e Configuracao

### Dependencias Python

```bash
pip install pyautogui playwright requests pillow pyperclip urllib3
python -m playwright install chromium
```

Ou via `requirements.txt`:

```
pyautogui
playwright
requests
Pillow
pyperclip
urllib3
```

### Configuracao do Chrome (para CDP)

O Chrome precisa ser iniciado com a flag de depuracao remota:

```bash
chrome.exe --remote-debugging-port=9222 --user-data-dir="C:/chrome-cdp-profile"
```

Ou o `login_ecac.py` abre o Chrome automaticamente com essa flag quando `abrir_chrome=True`.

### Pasta assets/

Todas as imagens de referencia usadas pelo PyAutoGUI devem estar em `assets/`. Sao capturas de tela (.png) dos elementos visuais que o sistema precisa localizar. Subpastas obrigatorias:

- `assets/hcaptcha_refs/` — amostras do captcha para deteccao
- `assets/bloqueio_refs/` — telas de bloqueio do eCAC
- `assets/certificado_btn_refs/` — botao de certificado digital no dialogo nativo
- `assets/ok_button_refs/` — botao OK do dialogo nativo do Windows

**Como capturar imagens de referencia:** Use o `print screen` ou uma ferramenta de captura parcial (como o Snipping Tool do Windows) e salve o PNG na pasta `assets/` com o nome esperado pelo modulo.

### Variavel de ambiente — API de captcha

O `login_ecac.py` usa uma API externa para resolver o hCaptcha. Configure a URL no arquivo ou como variavel de ambiente:

```python
# Em login_ecac.py
CAPTCHA_API_URL = os.environ.get("CAPTCHA_API_URL", "http://seu-servidor/resolve")
```

A API deve aceitar um POST com `{"sitekey": "...", "url": "..."}` e retornar `{"token": "..."}`.

### Compatibilidade

- **Sistema operacional:** Windows (PyAutoGUI com captura de tela requer ambiente grafico Windows)
- **Python:** 3.10 ou superior
- **Browser:** Google Chrome ou Microsoft Edge com CDP ativo na porta 9222
- **Rede:** Acesso ao portal `https://cav.receita.fazenda.gov.br` e a API de captcha