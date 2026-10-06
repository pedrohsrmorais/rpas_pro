# Mapeamento de Fluxo — RPAs eCAC

> Documento de referência para a unificação dos três robôs de coleta do portal eCAC.
> Descreve, tela a tela e clique a clique, o que cada RPA faz hoje.

---

## Índice

1. [DCTFWeb](#1-dctfweb)
2. [DARF](#2-darf)
3. [Fontes Pagadoras](#3-fontes-pagadoras)
4. [Comparativo entre os três](#4-comparativo-entre-os-três)

---

## 1. DCTFWeb

**Arquivo:** `workflow_dctfweb.py`
**Tecnologia:** 100% PyAutoGUI (reconhecimento de imagem + teclado simulado)
**O que baixa:** PDF da "Declaração Completa" de cada competência do período solicitado

### 1.1 Entrada e parâmetros

```
cnpj_bruto       → CNPJ com ou sem máscara (limpo internamente)
data_inicio_str  → "ddmmaaaa" ex: "01012025"
data_fim_str     → "ddmmaaaa" ex: "31122026"
diretorio_base   → caminho onde cria a pasta do CNPJ
nome_certificado → chave do mapa: "agro", "varejo", "bank", etc.
callback_status  → função opcional chamada com int de status
```

### 1.2 Mapeamento de certificados

| Chave | Posição (setas ↓ a partir do topo da lista) |
|---|---|
| `operacional` | 0 (primeiro da lista, sem setas) |
| `agro` | 1 |
| `varejo` | 2 |
| `braga` | 3 |
| `spacew` | 4 |
| `bank` | 5 |
| `law` | 6 |
| `audit` | 7 |
| `store` | 8 |

> ⚠️ Bug conhecido: `"braga"` e `"spacew"` estão concatenados na lista `CERTIFICADOS_VALIDOS` (`"braga""spacew"` sem vírgula), mas o mapa está correto.

### 1.3 Fluxo passo a passo

```
PASSO 1 — Estrutura de pastas
  └── Cria {diretorio_base}/{cnpj}/
  └── Cria {diretorio_base}/{cnpj}/DCTF Web/
  └── Se a pasta já existe: limpa todos os PDFs anteriores (evita acúmulo de retries)
```

```
PASSO 2 — Login no eCAC
  TELA: Portal eCAC (já aberto no navegador)
  AÇÃO: Aguarda imagem "entrar_govbr.png" (timeout 30s)
        → Clica no botão "Entrar com gov.br"
        → Se não encontrar: pressiona Enter como fallback

  TELA: Tela de escolha de método de login
  AÇÃO: Aguarda imagem "btn_certificado.png" (timeout 40s, crítico)
        → Clica em "Seu Certificado Digital"
```

```
PASSO 3 — Seleção do certificado digital (diálogo nativo do Windows)
  TELA: Janela de seleção de certificado (diálogo do SO, não do browser)
  AÇÃO: Aguarda 40 segundos (tempo para o diálogo abrir)
        → Pressiona TAB 3x (foca na lista de certificados)
        → Pressiona seta ↓ N vezes (N = posição do certificado no mapa)
        → Pressiona Enter (confirma o certificado)
        → Aguarda 5 segundos
```

```
PASSO 4 — Troca de perfil para o CNPJ solicitado
  TELA: Home do eCAC
  AÇÃO: Aguarda imagem "perfil_acesso.png" (timeout 30s, crítico)
        → Clica no botão de alterar perfil

  TELA: Modal/campo de troca de perfil
  AÇÃO: Aguarda imagem "campo_cnpj.png" (timeout 15s, crítico)
        → Clica no campo
        → Digita o CNPJ (14 dígitos, sem máscara)
        → Pressiona TAB
        → Aguarda imagem "btn_alterar.png" (timeout 10s, crítico)
        → Clica em "Alterar"
        → Aguarda o botão "btn_alterar.png" sumir (confirma transição)

  VERIFICAÇÕES PÓS-TROCA:
        → Se aparecer "mensagem_cnpj.png": lança CNPJBlockedMessageError
        → Se aparecer "cnpj_invalido.png": lança InvalidCNPJError
```

```
PASSO 5 — Navegação até o DCTFWeb
  TELA: Home do eCAC (com perfil do CNPJ ativo)
  AÇÃO: Aguarda imagem "menu_declaracoes.png" (timeout 30s, crítico)
        → Clica em "Declarações e Demonstrativos"

  TELA: Submenu de declarações
  AÇÃO: Aguarda imagem "menu_dctfweb.png" (timeout 30s, crítico)
        → Clica em "DCTFWeb"
        → Aguarda 2 segundos
        → Chama callback_status(4) — "Processando Downloads"
```

```
PASSO 6 — Divisão do período em blocos anuais
  LÓGICA: Divide data_inicio → data_fim em blocos por ano
  EXEMPLO: "01012024" a "30062026" vira:
    Bloco 1: 01012024 → 31122024
    Bloco 2: 01012025 → 31122025
    Bloco 3: 01012026 → 30062026
```

```
PASSO 7 — Para cada bloco anual: configura filtros
  TELA: Lista de DCTFWeb
  AÇÃO: Pressiona Ctrl+Home (sobe ao topo)
        → Aguarda 2s
        → Scroll para baixo (200 unidades)
        → Aguarda imagem "apuracao_inicial.png" (timeout 50s, crítico)
        → Clica no campo de data inicial, offset Y +50px
        → Triplo clique (seleciona o conteúdo)
        → Digita data de início do bloco

        → Pressiona TAB 2x (vai para campo data fim)
        → Ctrl+A → Backspace (limpa)
        → Digita data de fim do bloco

  SE PRIMEIRO BLOCO (limpar_transmissao=True):
        → Pressiona TAB 2x → Ctrl+A → Backspace (limpa campo transmissão início)
        → Pressiona TAB 2x → Ctrl+A → Backspace (limpa campo transmissão fim)
        → Pressiona TAB 3x → Enter (confirma limpeza)
        → Aguarda 2s
        → Tenta clicar em "btn_em_andamento.png" (timeout 5s, não crítico)

  AÇÃO: Aguarda imagem "btn_pesquisar.png" (timeout 15s, crítico)
        → Clica em "Pesquisar"
        → Aguarda 5 segundos
        → Rola até o fim da página (tecla End + scroll -500)
```

```
PASSO 8 — Para cada item na lista: clica no ícone de visualização
  TELA: Lista de resultados do DCTFWeb
  AÇÃO: Localiza todas as ocorrências de "icone_visualizar.png" (confiança 0.9)
        → Ordena por posição Y (de cima para baixo)
        → Clica no primeiro ícone ainda não clicado (controle por conjunto de Y's)
        → Aguarda 2 segundos
```

```
PASSO 9 — Download do documento
  TELA: Tela de detalhe da apuração
  AÇÃO: Move o mouse para "menu_relatorios.png" (timeout 10s, crítico)
        → Aguarda 1 segundo (hover abre submenu)
        → Aguarda imagem "declaracao_completa.png" (timeout 10s, crítico)
        → Clica em "Declaração Completa"
        → Aguarda 4 segundos

  SE aparecer "sem_debitos.png":
        → Log de aviso "Nenhum débito encontrado"
        → Clica em "btn_voltar.png" (timeout 10s)
        → Aguarda 2s
        → Clica em "btn_voltar.png" novamente
        → Retorna False (sem download)

  SE download iniciou:
        → Aguarda PDF concluir em ~/Downloads (polling a cada 0.5s, timeout 40s):
            - Ignora arquivos .crdownload e .tmp
            - Confirma quando PDF mais recente tem tamanho > 0 e estável
        → Pressiona ESC (fecha diálogos)
        → Aguarda 1s
        → Clica em "btn_voltar.png" (timeout 15s)
        → Retorna True
```

```
PASSO 10 — Move o arquivo baixado para a pasta do CNPJ
  AÇÃO: mover_arquivos_recentes() move o PDF de ~/Downloads
        para {diretorio_base}/{cnpj}/DCTF Web/
        com prefixo: {cnpj}_{data_inicio}_{data_fim}_
```

```
PASSO 11 — Fim do bloco anual
  AÇÃO: Pressiona Ctrl+Home (sobe ao topo)
        → Aguarda 2s
        → Volta ao PASSO 7 para o próximo bloco
```

### 1.4 Saída

```
{diretorio_base}/
  {cnpj}/
    DCTF Web/
      {cnpj}_{data_inicio}_{data_fim}_{timestamp}.pdf
      {cnpj}_{data_inicio}_{data_fim}_{timestamp}.pdf
      ...
```

### 1.5 Tratamento de erros

| Situação | Comportamento |
|---|---|
| Imagem crítica não encontrada | Lança `CriticalImageNotFoundError` — encerra o fluxo |
| CNPJ com pendência no portal | Lança `CNPJBlockedMessageError` |
| CNPJ inválido no portal | Lança `InvalidCNPJError` |
| Competência sem débitos | Pula (volta 2x) e continua para o próximo ícone |
| Download não confirmado em 40s | Log de aviso, continua para o próximo |

---

## 2. DARF

**Arquivos:** `workflow_darf.py` + `playwright_darf_loop.py`
**Tecnologia:** PyAutoGUI para login/navegação inicial → Playwright (CDP) para o loop de paginação
**O que baixa:** PDF do comprovante de pagamento de cada DARF do período

### 2.1 Entrada e parâmetros

```
cnpj_bruto       → CNPJ com ou sem máscara
diretorio_base   → caminho base
nome_certificado → chave do mapa: "Studio Varejo", "Space W", etc.
callback_status  → função opcional
pagina_start     → página inicial (default 1, para retomada)
data_inicio      → "ddmmaaaa" ex: "01012025"
data_fim         → "ddmmaaaa" ou None (usa data atual)
```

### 2.2 Mapeamento de certificados

| Chave | Posição (setas ↓) |
|---|---|
| `Studio Agronegócios` | 0 |
| `Studio Varejo` | 1 |
| `Braga Monteiro` | 2 |
| `Space W` | 3 |
| `Studio Bank` | 4 |
| `Aliança Legal` | 5 |
| `Audit Tecnologia` | 6 |
| `Studio Store` | 7 |
| `Studio Operacional` | 8 |

### 2.3 Fluxo passo a passo — Fase PyAutoGUI

```
PASSO 1 — Estrutura de pastas
  └── Cria {diretorio_base}/{cnpj}/DARF/
```

```
PASSO 2 — Verificação de sessão existente
  AÇÃO: Verifica se "btn_home.png" está visível
        SE SIM: clica em Home (reaproveita sessão existente)
                → Aguarda 15 segundos
                → Pula login e troca de certificado
        SE NÃO: segue para login completo
```

```
PASSO 3 — Login no eCAC (se necessário)
  TELA: Portal eCAC
  AÇÃO: Aguarda "entrar_govbr.png" (timeout 20s)
        → Clica em "Entrar com gov.br"
        → Se não encontrar: F5 + aguarda 4-6s + tenta de novo (timeout 40s)
        → Se ainda não: pressiona Enter
```

```
PASSO 4 — Seleção do certificado
  TELA: Tela de escolha de método de login
  AÇÃO: Aguarda "btn_certificado.png" (timeout 20s)
        → Se não encontrar: F5 + aguarda 4-6s + tenta entrar_govbr de novo
        → Clica em "Seu Certificado Digital" (timeout 40s, crítico)

  TELA: Diálogo nativo do Windows (seleção de certificado)
  AÇÃO: Aguarda 20 segundos (abertura do diálogo)
        → Aguarda mais 20 segundos (tempo do colaborador)
        → Pressiona TAB 3x (foca na lista)
        → Pressiona seta ↓ N vezes (N = posição no mapa)
        → Pressiona Enter
        → Aguarda 4-6 segundos
```

```
PASSO 5 — Verificação pós-login
  AÇÃO: Aguarda 15 segundos
        → Verifica se "limite_dispositivo.png" está visível
        → SE SIM: loga erro e retorna False (limite de dispositivos atingido)
```

```
PASSO 6 — Troca de perfil para o CNPJ
  TELA: Home do eCAC
  AÇÃO: Tenta até 2x clicar em "alterar_perfil.png" (timeout 15s cada)
        → Se falhar na 1ª: aguarda 15s e tenta de novo
        → Se falhar nas 2: retorna False

        Após clicar:
        → Aguarda 10 segundos
        → Pressiona TAB 2x
        → Digita o CNPJ (14 dígitos)
        → Aguarda 2s
        → Pressiona TAB
        → Aguarda 2s
        → Pressiona Enter (confirma)
        → Aguarda 15 segundos

  VERIFICAÇÃO:
        → Se "sem_procuracao.png" visível: lança SemProcuracaoError (status 12)
```

```
PASSO 7 — Navegação até Consulta Comprovante
  TELA: Home do eCAC (com perfil do CNPJ)
  AÇÃO: Aguarda "menu_pagamentos.png" (timeout 30s, crítico)
        → Clica em "Pagamentos"

  TELA: Submenu de pagamentos
  AÇÃO: Aguarda "consulta_comprovante.png" (timeout 30s, crítico)
        → Clica em "Consulta de Comprovante de Pagamento"
```

```
PASSO 8 — Autenticação no serviço
  TELA: Página de autenticação do serviço
  AÇÃO: Aguarda "btn_autenticar.png" (timeout 30s, crítico)
        → Clica em "Autenticar"
        → Aguarda loading sumir (polling "loading.png", até 60s)
        → Aguarda 10 segundos
```

```
PASSO 9 — Seleção de perfil dentro do serviço
  TELA: Seleção de perfil de acesso ao serviço
  AÇÃO: Aguarda "selecionar_perfil.png" (timeout 15s, crítico)
        → Clica com offset X +80px (clica no botão ao lado do label)
```

```
PASSO 10 — Preenchimento do CNPJ no serviço
  TELA: Campo de busca por CNPJ dentro do serviço
  AÇÃO: Aguarda "cnpj_cliente.png" (timeout 15s, crítico)
        → Clica no campo
        → Digita o CNPJ
        → Aguarda 10 segundos
```

```
PASSO 11 — Seleção de tipo de perfil e procurador
  TELA: Opções de tipo de perfil
  AÇÃO: Aguarda "tipo_perfil.png" (timeout 15s, crítico)
        → Clica em "tipo_perfil"

  AÇÃO: Aguarda "tipo_procurador.png" (timeout 15s, crítico)
        → Clica em "tipo_procurador"
```

```
PASSO 12 — Botão representar
  TELA: Confirmação de representação
  AÇÃO: Aguarda "btn_representar.png" (timeout 15s, crítico)
        → Clica em "Representar"
        → Aguarda loading sumir

  VERIFICAÇÃO:
        → Se "sem_procuracao.png" visível: lança SemProcuracaoError (status 12)
```

```
PASSO 13 — Fechar modal de confirmação
  TELA: Modal pós-representação
  AÇÃO: Aguarda "btn_fechar.png" (timeout 15s, crítico)
        → Clica em "Fechar"
```

```
PASSO 14 — Filtro por tipo de documento
  TELA: Lista de comprovantes
  AÇÃO: Aguarda "tipo_doc.png" (timeout 15s, crítico)
        → Clica no seletor de tipo de documento
        → Aguarda 5 segundos

  AÇÃO: Aguarda "tipo_darf.png" (timeout 15s, crítico)
        → Clica em "DARF" na lista
        → Aguarda 10 segundos
```

```
PASSO 15 — Preenchimento das datas
  TELA: Filtros de período
  AÇÃO: Pressiona TAB 2x (vai para campo data início)
        → Digita data_inicio
        → Aguarda 10 segundos
        → Pressiona TAB 2x (vai para campo data fim)
        → Digita data_fim (ou data atual se None)
        → Aguarda 10 segundos
```

```
PASSO 16 — Filtrar resultados
  TELA: Filtros da consulta
  AÇÃO: Aguarda "btn_filtrar.png" (timeout 20s, crítico)
        → Clica em "Filtrar"
        → Aguarda loading sumir
```

```
PASSO 17 — Ajusta exibição para 50 itens/página
  TELA: Lista de resultados
  AÇÃO: Pressiona PageDown 3x + seta ↓ 10x (rola até o rodapé)
        → Aguarda "filtro_exibir.png" (timeout 10s, crítico)
        → Clica no seletor de exibição
        → Digita "50"
        → Pressiona Enter
        → Aguarda 2-4 segundos
```

```
PASSO 18 — Transfere controle para Playwright via CDP
  AÇÃO: Conecta ao Edge já aberto pela porta CDP
        → Identifica a aba ativa com a URL do serviço
        → Playwright assume o loop de paginação
```

### 2.4 Fluxo passo a passo — Fase Playwright (`playwright_darf_loop.py`)

```
PASSO 19 — Diagnóstico inicial
  AÇÃO: Loga URL e título da aba ativa
        → Inspeciona DOM: conta checkboxes, botões, tabelas
        → Diagnstica controles de paginação (loga HTML)
        → Garante "Exibir: 50" via ng-select Angular
          (se não confirmar: aviso, mas continua)
```

```
PASSO 20 — Posicionamento na página inicial (se pagina_start > 1)
  AÇÃO: Tenta ir direto via ng-select "Página:"
        SE falhar: avança uma a uma confirmando cada passo
```

```
LOOP PRINCIPAL — Para cada página da listagem:

  PASSO 21 — Selecionar todos os itens
    TELA: Lista de comprovantes de DARF
    AÇÃO: Executa JS para encontrar checkbox "Selecionar Todos" no thead
          → Desmarca se já marcado (garante estado limpo)
          → Clica para selecionar todos
          → Aguarda 1.5 segundos
          → SE não encontrar checkbox: encerra o loop (sem itens)

  PASSO 22 — Emitir comprovante e baixar PDF
    TELA: Lista com itens selecionados
    AÇÃO: Localiza botão "Emitir Comprovante"
          (tenta na página principal, depois nos iframes)
          → Scroll até ficar visível
          → Clica e aguarda nova aba abrir (timeout 15s)

    TELA: Nova aba — carregando PDF (about:blank → blob:)
    AÇÃO: Aguarda aba mudar de about:blank para blob: ou .pdf
          (poll a cada 0.5s, timeout 120s — não desiste antes!)
          → Enquanto aguarda: verifica mensagem de erro do eCAC a cada 3s

    DOWNLOAD DO BLOB:
    AÇÃO: Tenta fetch do blob na aba principal (mesmo origin)
          → Fallback: tenta na aba do documento
          → Decodifica base64 e salva como PDF em {diretorio}/DARF/
          → Nome: DARF_{cnpj}_pg{N}_{HHmmss}.pdf

    FALLBACK — Botão Baixar:
    AÇÃO: Se fetch falhou e há botão "Baixar" na aba do PDF
          → Clica e usa expect_download do Playwright

    FECHA abas de PDF (blob: e .pdf) — NUNCA fecha about:blank

  PASSO 23 — Verificação de duplicatas (após download bem-sucedido)
    AÇÃO: Calcula MD5 do PDF baixado
          → Se igual ao anterior: incrementa contador de duplicatas
          → Se 3 duplicatas consecutivas: encerra com erro (loop infinito detectado)

  PASSO 24 — Deselecionar todos e rolar
    TELA: Lista (foco voltou à aba principal)
    AÇÃO: bring_to_front() na aba principal
          → Executa JS para desmarcar todos os checkboxes
          → Aguarda 1 segundo

  PASSO 25 — Detectar fim das páginas
    MÉTODO 1 (mais confiável): Lê rótulo DOM ".indices"
      → Formato: "X-Y de N itens"
      → SE fim do intervalo (Y) >= total (N): última página → encerra

    MÉTODO 2: Botão "Página seguinte" desabilitado → encerra

    MÉTODO 3: Imagem "the_end.png" visível → encerra

    MÉTODO 4: Contagem de itens < 50 e índices ilegíveis → encerra

  PASSO 26 — Navegar para próxima página
    MÉTODO PREFERENCIAL: ng-select "Página:" no Angular
      → Abre dropdown → clica na opção N
      → Confirma pelo número real da página lida do DOM
      → Aguarda loading sumir + 5 segundos

    FALLBACK 1: Botão "#btn-next-page"
      → Clica UMA vez (nunca dois cliques — evita pular página)
      → Verifica se página mudou antes de tentar o segundo botão
      → Confirma pelo número real da página

    FALLBACK 2: Imagem "passar_pagina.png" com offset X +65px

    SE não confirmar após 5 tentativas:
      → Verifica índices: se há mais páginas, encerra com FALHA
      → Se índices ilegíveis: usa heurística de contagem de itens

  PASSO 27 — Tratamento de falhas por página
    SE timeout ou falha no download:
      → Retenta a mesma página (até 3x)
      → Se esgotou tentativas: pula a página, registra para relatório final
      → Incrementa contador de páginas improdutivas consecutivas
      → Se 5 páginas improdutivas seguidas: encerra o fluxo

  FIM DO LOOP — Relatório de páginas puladas
    → Loga quais páginas foram puladas e por qual motivo
```

### 2.5 Saída

```
{diretorio_base}/
  {cnpj}/
    DARF/
      DARF_{cnpj}_pg1_{HHmmss}.pdf
      DARF_{cnpj}_pg2_{HHmmss}.pdf
      ...
```

> Cada PDF contém todos os comprovantes da página (lote de até 50 DARFs por arquivo)

### 2.6 Tratamento de erros

| Situação | Comportamento |
|---|---|
| Imagem crítica não encontrada (PyAutoGUI) | Retorna False |
| Sem procuração para o CNPJ | Lança `SemProcuracaoError` (status 12) |
| Limite de dispositivos atingido | Retorna False com log de erro |
| Erro do eCAC ao emitir | Recarrega a página, reaplica filtros e reposiciona |
| Timeout no download do PDF (120s) | Pula a página sem reemitir (evita duplicata) |
| 3 PDFs idênticos consecutivos | Encerra — loop infinito detectado |
| 5 páginas improdutivas seguidas | Encerra o fluxo |
| 100 arquivos baixados | Encerra — limite de segurança |

---

## 3. Fontes Pagadoras

**Arquivos:** `main.py`, `ecac.py`, `coleta.py`, `execucao.py`, `painel.py`
**Tecnologia:** 100% Playwright via CDP (login assistido pelo colaborador)
**O que baixa:** TXT + PDF de rendimentos informados por fontes pagadoras, por ano-calendário

### 3.1 Entrada e parâmetros

```
cnpj                 → 14 dígitos limpos
url                  → URL do eCAC (do .env)
id_certificado       → int (para log e conferência)
cnpj_certificado     → CNPJ do certificado (confere quem logou)
nome_certificado     → nome da empresa do certificado (exibido no console)
razao_social_matriz  → razão social (usada na comparação com filiais)
coletar_filiais      → bool
ano_inicial          → ANO_INICIAL do .env (padrão 2021)
```

### 3.2 Fluxo passo a passo

```
FASE 1 — Consulta de filiais (ANTES do login, sem navegador)
  SE coletar_filiais = True:

  PASSO 1.1 — Gera candidatos de filial (offline, só aritmética)
    AÇÃO: Usa a raiz do CNPJ (8 primeiros dígitos)
          → Gera ordens 0002, 0003, 0004... até N_FILIAIS
          → Recalcula dígito verificador para cada candidato
          → Lista CNPJs candidatos (nenhum confirmado ainda)

  PASSO 1.2 — Confirma candidatos na API pública (com rede, sem eCAC)
    FONTE: BrasilAPI / MinhaReceita (configurável no .env)
    AÇÃO: Para cada candidato, consulta o cadastro público
          → Aplica TRAVA TRIPLA para confirmar como filial:
            ✓ Raiz igual à matriz (8 primeiros dígitos)
            ✓ Razão social parecida (fuzzy ≥ 0.95, sem acento/pontuação)
            ✓ Tag = FILIAL (descarta MATRIZ com mesma razão)
            ✓ Situação = ATIVA (ignora BAIXADA, SUSPENSA, etc.)
          → Grava evidência de cada consulta em logs/evidencias_filiais/

  PASSO 1.3 — Salva lista em disco
    AÇÃO: Grava {pasta_saida}/{cnpj}_filiais.txt
          (uma linha por filial confirmada: cnpj;ordem;razao_social;situacao;uf)
          → Grava CSV de auditoria com TODOS os candidatos (inclusive recusados)
    FALLBACK: Se a consulta falhar, a Fase 4 refaz a varredura sozinha

  PASSO 1.4 — Mostra resultado ao operador (painel)
    AÇÃO: Exibe janela "CONSULTA FILIAIS" com log linha a linha
          → Ao terminar: mostra filiais descobertas por N segundos
          → Só então o Edge abre para o login
```

```
FASE 2 — Abertura do navegador e login assistido
  PASSO 2.1 — Abre Edge em perfil temporário
    AÇÃO: Cria diretório temporário em %TEMP% (mkdtemp)
          → Grava Preferences: downloads → downloads/, impressão → PDF
          → Flags: --disable-extensions, --disable-sync, --no-experiments, etc.
          → Abre msedge.exe com --remote-debugging-port=9225
            e --user-data-dir={temp} direto na URL do eCAC

  PASSO 2.2 — Instrui o colaborador
    AÇÃO: Exibe no console:
          "1. Entrar com gov.br
           2. Seu certificado digital
           3. Escolha o certificado de {nome} (CNPJ {cnpj_certificado})"

  PASSO 2.3 — Aguarda login (polling CDP, não toca no navegador)
    AÇÃO: Poll a cada INTERVALO_ESPERA_LOGIN no endpoint /json/list da porta 9225
          → Verifica URLs abertas: aguarda caminho que indique home autenticada
          → Timeout: TIMEOUT_LOGIN_MANUAL (padrão 5 minutos)
          → Se a janela fechar antes: lança EntradaNaoConcluidaError
          → Exibe aviso a cada 30s enquanto aguarda

  PASSO 2.4 — Assume controle via Playwright/CDP
    AÇÃO: Aguarda ESPERA_ANTES_DO_CDP segundos (padrão configurável)
          → Conecta Playwright ao Edge pela porta CDP
          → Aguarda menu de serviços aparecer no DOM (confirma home)

  PASSO 2.5 — Confere certificado usado
    AÇÃO: Lê #informacao-perfil no DOM
          → Extrai CNPJ do titular autenticado
          → Compara com cnpj_certificado do job
          → SE diferente: lança CertificadoIncorretoError → job volta para fila
```

```
FASE 3 — Coleta da matriz
  PASSO 3.1 — Volta para a home (ponto de partida conhecido)
    TELA: Qualquer tela do eCAC
    AÇÃO: Navega para URL da home via Playwright
          → Aguarda #menu-servicos aparecer no DOM

  PASSO 3.2 — Troca de perfil para o CNPJ
    TELA: Home do eCAC
    AÇÃO: Clica em #btnPerfil (abre modal de perfil)
          → Aguarda #perfilAcesso ficar visível
          → Localiza campo #txtNIPapel2 (linha "Procurador de pessoa jurídica - CNPJ")
          → Preenche com o CNPJ (14 dígitos, caractere a caractere)
          → Clica no botão submit do formulário #formPJ

    AGUARDA CONFIRMAÇÃO (poll):
          → Verifica bloco .erro na modal:
            - "não possui procuração" / "vencida" → PerfilNaoPermitidoError (status 12)
            - "erro inesperado na validação" → ErroDoPortalError (reprocessa até 3x)
          → Verifica #informacao-perfil: quando mostra o CNPJ pedido → sucesso
          → hCaptcha visível → CaptchaError

  PASSO 3.3 — Navega até a consulta de rendimentos
    TELA: Home com perfil do CNPJ ativo
    AÇÃO: Clica em #btn214 (grupo "Declarações e Demonstrativos")
          → Aguarda painel #tabpanel214 abrir
          → Clica no link com href contendo "Aplicacao.aspx?id=21&"
            (Consulta Rendimentos Informados por Fontes Pagadoras)
          → FALLBACK: busca pelo texto exato se o id mudar

  PASSO 3.4 — Entra no iframe do serviço
    TELA: Página da aplicação 21
    NOTA: O serviço roda dentro de <iframe id="frmApp">
    AÇÃO: Obtém referência ao frame via web.quadro()
          → Todos os passos seguintes operam dentro deste frame
```

```
FASE 3 (continuação) — Loop de anos dentro do iframe

  PASSO 3.5 — Descobre anos disponíveis
    TELA: Iframe com select "Ano-Calendário"
    AÇÃO: Lê as opções do <select> de ano-calendário
          → Filtra: apenas anos >= ANO_INICIAL (padrão 2021)
          → Usa a intersecção (não pede ano que o portal não oferece)

  LOOP — Para cada ano disponível (do mais recente para o mais antigo):

    PASSO 3.6 — Seleciona o ano e consulta
      TELA: Iframe — lista de anos
      AÇÃO: Seleciona o ano no <select>
            → Clica em "Consultar"
            → AGUARDA (poll ativo — não sleep fixo):
              - Reobtém o frame a cada volta (handle pode mudar com AJAX)
              - Aguarda "Carregando..." sumir
              - Confirma uma das duas telas esperadas:
                ✓ Frase de ausência → ano sem dados
                ✓ Ícone de download visível → ano com dados

    PASSO 3.7 — SE ano sem dados:
      AÇÃO: Registra em anos_vazios
            → Captura print da tela (fontes_pagadoras_{cnpj}_{ano}.png)
            → Clica em Voltar (#btnVoltar_msg ou #btnVoltar, apenas o visível)
            → Confirma que a lista de anos voltou

    PASSO 3.8 — SE ano com dados — baixa TXT:
      TELA: Iframe — tela de resultado da consulta
      AÇÃO: Localiza ícone de download (lista de seletores, rejeita ícone de impressão)
            → Clica no ícone de download do TXT
            → AGUARDA o arquivo chegar:
              MODO A (Playwright intercepta): expect_download captura
              MODO B (Edge baixa sozinho): monitora pasta downloads/ pelo arquivo novo
              (Detecta qual modo funciona UMA vez por sessão)
            → Renomeia para fontes_pagadoras_{cnpj}_{ano}.txt

    PASSO 3.9 — SE ano com dados — salva PDF:
      TELA: Iframe — link "Preparar página para impressão"
      AÇÃO: Clica em "Preparar página para impressão" (img#imgImprimir com onclick)
            → Aguarda mini-janela abrir (window.open 800x300)
            → Maximiza a mini-janela
            → Marca checkbox "Detalhar por Código de Receita"
              (se não existir: aviso, PDF sai mesmo assim)
              (se existir mas não aceitar marcação: erro — PDF sairia diferente)
            → Executa Page.printToPDF via CDP
              (sem diálogo do sistema, sem depender de tema/idioma)
            → Salva como fontes_pagadoras_{cnpj}_{ano}.pdf
            → Fecha a mini-janela

    PASSO 3.10 — Volta para a lista de anos
      AÇÃO: Clica em Voltar
            → Confirma que a lista de anos reapareceu
            → SE não voltar: tenta de novo (1 retry)
            → SE ainda falhar: registra anos seguintes como "não tentados" e encerra o ano

    RESILIÊNCIA DO LOOP:
      → TXT que falha NÃO cancela o PDF (são independentes)
      → Ano que falha NÃO cancela os outros anos
      → Morte do navegador SIM encerra (é assim que a pausa chega)
      → Falha de Voltar: para aquele ano e tenta o próximo
```

```
FASE 4 — Coleta de filiais (SE coletar_filiais = True)
  PASSO 4.1 — Lê a lista do TXT gerado na Fase 1
    AÇÃO: Lê {pasta_saida}/{cnpj}_filiais.txt
          → Reaplica trava tripla na leitura (CNPJ com raiz diferente = recusado)
          → SE o TXT não existir: refaz a varredura (Fase 1) agora

  PARA CADA filial confirmada:

    PASSO 4.2 — Volta para a home
      AÇÃO: Navega para URL da home
            → Aguarda #menu-servicos

    PASSO 4.3 — Troca de perfil para a filial
      AÇÃO: Tenta linha 2 (#formPJ — "Procurador de pessoa jurídica - CNPJ")
            → SE recusar: tenta linha 3 (#formMatriz — "CNPJ matriz atuando como filial")
            → Registra qual linha funcionou

    PASSO 4.4 — Navega até a consulta e repete o loop de anos
      AÇÃO: Mesmo fluxo da Fase 3 (passos 3.3 a 3.10)
            → Saída em {pasta_saida}/{cnpj_filial}(FILIAL)/

    RESILIÊNCIA:
      → Filial que falha NÃO cancela as outras filiais
      → Morte do navegador CANCELA o lote (propaga exceção)
      → Falha total da etapa de filiais NÃO cancela a matriz (já está na pasta)
```

```
FASE 5 — Encerramento
  PASSO 5.1 — Fecha o Edge
    AÇÃO: Desconecta Playwright
          → Encerra processos com o perfil temporário
          → Apaga diretório temporário do %TEMP%

  PASSO 5.2 — Evidência quando não houve coleta
    SE falhou antes de chegar ao loop de anos:
    AÇÃO: Captura print da tela atual (fontes_pagadoras_{cnpj}_SEM_COLETA.png)
          → Grava TXT com motivo em português (fontes_pagadoras_{cnpj}_SEM_COLETA.txt)
          → Exceção continua subindo (evidência não disfarça o fracasso)
```

### 3.3 Saída

```
{pasta_saida}/                          ← {SAIDA_REDE}/{cnpj}/FONTES_PAGADORAS/
  fontes_pagadoras_{cnpj}_{ano}.txt     ← dados de rendimentos
  fontes_pagadoras_{cnpj}_{ano}.pdf     ← impressão detalhada
  fontes_pagadoras_{cnpj}_{ano}.png     ← print quando o ano não tem dados
  fontes_pagadoras_{cnpj}_SEM_COLETA.png   ← print quando nem chegou ao loop
  fontes_pagadoras_{cnpj}_SEM_COLETA.txt   ← motivo em texto
  {cnpj_filiais}.txt                   ← lista de filiais descobertas
  logs/filiais_{cnpj}_{carimbo}.csv    ← auditoria de todos os candidatos
  {cnpj_filial}(FILIAL)/
    fontes_pagadoras_{cnpj_filial}_{ano}.txt
    fontes_pagadoras_{cnpj_filial}_{ano}.pdf
```

### 3.4 Tratamento de erros

| Situação | Status | Comportamento |
|---|---|---|
| Login não concluído em 5 min | — | `EntradaNaoConcluidaError` → job volta para fila (status 1) |
| Certificado errado (CNPJ divergente) | — | `CertificadoIncorretoError` → job volta para fila |
| Sem procuração para o CNPJ | 12 | `PerfilNaoPermitidoError` → status "sem procuração" |
| Serviço ausente no menu do perfil | 6 | `ServicoIndisponivelError` → status erro |
| Erro do portal na troca de perfil | — | `ErroDoPortalError` → reprocessa até 3x, depois status 6 |
| Morte do navegador (pausa do operador) | 6 | Propaga exceção — próximos CNPJs do lote voltam para fila |
| Ano que falha | — | Registrado em `falhas`, continua para o próximo ano |
| Filial que falha | — | `FALHA_DOWNLOAD`, continua para a próxima filial |
| Nenhum documento em nenhum ano | 5 | Sucesso — prints arquivados como evidência |
| Coleta concluída na rede | 5 | Status sucesso |
| Coleta concluída só no disco local | 5 ou 21 | Depende de `EXIGIR_SAIDA_NA_REDE` |

---

## 4. Comparativo entre os três

### 4.1 Tecnologia e modo de login

| | DCTFWeb | DARF | Fontes Pagadoras |
|---|---|---|---|
| **Login** | Automático (PyAutoGUI) | Automático (PyAutoGUI) | Assistido (colaborador) |
| **Automação** | 100% PyAutoGUI | PyAutoGUI + Playwright | 100% Playwright/DOM |
| **Identificação de elementos** | Por imagem (screenshot) | Imagem → DOM (Playwright) | Por seletor CSS/DOM |
| **Fragilidade** | Alta (zoom, tema, resolução) | Média (só login é frágil) | Baixa |

### 4.2 Entrada e período

| | DCTFWeb | DARF | Fontes Pagadoras |
|---|---|---|---|
| **Input** | Parâmetros de função | Parâmetros de função | Banco de dados (fila) |
| **Período** | data_inicio / data_fim livre | data_inicio / data_fim livre | ANO_INICIAL do .env → atual |
| **Granularidade** | Por competência mensal | Por lote de página (até 50) | Por ano-calendário |
| **Filiais** | Não | Não | Sim (descoberta automática) |

### 4.3 Caminho no eCAC

| | Caminho |
|---|---|
| **DCTFWeb** | Home → Declarações e Demonstrativos → DCTFWeb → filtro por data → ícones de visualização → Relatórios → Declaração Completa |
| **DARF** | Home → Pagamentos → Consulta Comprovante → autenticar → selecionar perfil → filtrar DARF → emitir comprovante em lote |
| **Fontes Pagadoras** | Home → Declarações e Demonstrativos → Consulta Rendimentos Fontes Pagadoras → iframe → ano a ano → download TXT + printToPDF |

### 4.4 Formato de saída

| | DCTFWeb | DARF | Fontes Pagadoras |
|---|---|---|---|
| **Arquivo** | PDF | PDF | TXT + PDF por ano |
| **Quantidade** | 1 PDF por competência com débito | 1 PDF por página de 50 DARFs | 2 arquivos por ano por estabelecimento |
| **Pasta** | `{cnpj}/DCTF Web/` | `{cnpj}/DARF/` | `{cnpj}/FONTES_PAGADORAS/` |

### 4.5 Mapeamento de certificados — inconsistência a resolver

Os três usam nomes diferentes para o mesmo certificado:

| Certificado real | DCTFWeb | DARF | Fontes Pagadoras |
|---|---|---|---|
| Studio Agronegócios | `"agro"` | `"Studio Agronegócios"` | (nome do banco) |
| Studio Varejo | `"varejo"` | `"Studio Varejo"` | (nome do banco) |
| Space W | `"spacew"` | `"Space W"` | (nome do banco) |
| Studio Bank | `"bank"` | `"Studio Bank"` | (nome do banco) |
| Aliança Legal | `"law"` | `"Aliança Legal"` | (nome do banco) |
| Audit Tecnologia | `"audit"` | `"Audit Tecnologia"` | (nome do banco) |
| Studio Store | `"store"` | `"Studio Store"` | (nome do banco) |
| Studio Operacional | `"operacional"` | `"Studio Operacional"` | (nome do banco) |
| Braga Monteiro | `"braga"` | `"Braga Monteiro"` | (nome do banco) |

**Para a unificação:** adotar o nome completo (padrão DARF) como chave única e atualizar o mapeamento do DCTFWeb.
