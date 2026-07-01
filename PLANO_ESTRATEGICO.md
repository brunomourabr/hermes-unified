# Plano Estrategico - Hermes Unified

## Data: 29/06/2026
## Projeto: /opt/projetos/hermes-unified/
## Contexto: LangGraph multi-agent system integrado ao Hermes (Telegram AI)

---

## Sumario Executivo

O Hermes Unified e um orquestrador LangGraph funcional com 7 agentes (Planner, Codex, Knowledge, Web, Scraper, Viz, Observer) + Integrador. O sistema funciona e produz resultados, mas tem limitacoes significativas em confiabilidade, escopo e integracoes externas.

**O que funciona bem:** geracao de codigo via MiMo, charts matplotlib, criacao de watchers cron, scraping basico via Firecrawl CLI, pipeline de conhecimento via Hyper-Extract.

**O que e limitado:** scraping depende de Firecrawl CLI com SSL intermitente, viz depende de dados pre-estruturados (nao extrai dados automaticamente), observer nao notifica em real-time, knowledge depende do CLI `he` instalado.

**O que NAO existe:** integracao Google (Drive/Sheets/Docs/Slides/Gmail), visao computacional (nao conectada ao sistema), apresentacoes avancadas, agentes de midia social, automacao de email, pipeline de dados estruturados.

**Potencial imediato:** 3-5 novos agentes sao viaveis com dependencias ja instaladas (python-pptx, matplotlib, requests, httpx). Integracoes Google requerem pacotes novos mas sao viaveis. Visao ja existe no Hermes mas nao esta conectada a este sistema.

---

## Diagnostico Agente-por-Agente

### 1. Planner
| Aspecto | Status |
|---------|--------|
| **Status** | ⚠️ Funciona mas e simplistico |
| **Classificacao** | LLM-based com prompt simples, 7 categorias |
| **Roteamento** | Mapeia categoria -> unico agente, sem suporte a execucao paralela |
| **Plano** | Prompt gera 3-5 passos, mas o grafo NAO executa o plano passo-a-passo - so roteia para 1 agente |
| **Limites** | Nao suporta MULTI corretamente (rota direto pra codex sem envolver outros agentes). Nao tem memoria de planos anteriores. Nao valida se o agente escolhido faz sentido. |
| **O que falta** | Execucao multi-passo do plano, validacao pos-execucao, re-planejamento adaptativo, suporte a DAG (nao so sequencial) |

### 2. Codex (MiMo Bridge)
| Aspecto | Status |
|---------|--------|
| **Status** | ✅ Funcional |
| **Geracao** | Usa `mimo run` via subprocess, timeout 5min, modelo deepseek-chat |
| **Refatoracao** | Le codigo atual, faz backup, envia para MiMo re-gerar |
| **Validacao** | `py_compile` para Python, test_code tenta import |
| **Templates** | Suporta stack, style_guide, existing_files como contexto |
| **Limites** | Nao tem streaming de saida. Nao suporta outras linguagens alem de Python na validacao. `mimo` CLI precisa estar instalado. Nao tem controle fino de temperatura/tokens. |
| **O que falta** | Suporte a TypeScript/JavaScript/Go, cache de resultados, validacao com linters (ruff, mypy), geracao de testes |

### 3. Knowledge (Hyper-Extract Bridge)
| Aspecto | Status |
|---------|--------|
| **Status** | ⚠️ Funciona mas limitado |
| **Extracao** | `he parse` via subprocess, suporta PDF, texto puro, templates |
| **Busca** | `he search` e `he talk` para consultar grafos |
| **Projetos** | Lista projetos existentes, carrega grafos do disco |
| **Limites** | Depende do CLI `he` instalado (instalado, OK). So processa PDFs e texto. Nao tem OCR para imagens/scans. Nao suporta DOCX, HTML, ou URLs como entrada. `he` CLI pode ter versao incompativel. |
| **O que falta** | OCR (tesseract/pytesseract), suporte a mais formatos, chunking inteligente para PDFs grandes, visualizacao do grafo |

### 4. Web
| Aspecto | Status |
|---------|--------|
| **Status** | ✅ Funcional (basico) |
| **Busca** | Usa ScraperBridge.search_web() -> Firecrawl CLI search |
| **Resultados** | Retorna lista de dicts com title, url, description |
| **Limites** | Mesmo que Scraper - depende de Firecrawl. Nao tem fallback para search engines alternativas. Resultados sao text-only, sem metadados. |
| **O que falta** | Fallback com duckduckgo ou google search, scraping de resultados enriquecidos (schema.org, open graph), cache de buscas frequentes |

### 5. Scraper
| Aspecto | Status |
|---------|--------|
| **Status** | ⚠️ Funciona mas instavel |
| **Firecrawl** | CLI em `~/.nvm/versions/node/v22.23.1/bin/firecrawl` - instalado e funcional |
| **SSL Issues** | Chamadas a api.firecrawl.ai tem problemas de SSL - CLI funciona para searches, scrape as vezes falha |
| **Resposta** | Parseia JSON do Firecrawl (markdown, content, text), fallback para texto puro |
| **Search** | Busca via `firecrawl search --limit N` com parse de saida textual |
| **Fallback** | Gera script Playwright quando Firecrawl falha (mas nao executa) |
| **Batch** | `batch_scrape()` que itera URLs sequencialmente |
| **Limites** | SSL intermitente. Nao usa a API HTTP diretamente (so CLI). Fallback nao e automatico - gera script mas nao executa. Nao tem rate limiting. Nao tem rendering JS. |
| **O que falta** | Fallback HTTP direto (requests + BeautifulSoup), browser headless (Playwright) integrado, respect a robots.txt, cache de scraping, parsing estruturado (JSON-LD, microdata) |

### 6. Viz
| Aspecto | Status |
|---------|--------|
| **Status** | ✅ Bom, com potencial |
| **Charts** | matplotlib: bar, line, pie, scatter. Tema limpo, 10 cores, resolucao 150dpi |
| **Comparacao** | `generate_comparison_chart()` - grupos de barras ou multiplas linhas |
| **Dashboard** | HTML com charts embutidos em base64, CSS bonito |
| **PPTX** | `generate_pptx()` - cria slides com titulo + chart. python-pptx 1.0.2 instalado ✅ |
| **Auto-deteccao** | Detecta tipo de chart por palavras-chave no objective (pie, line, etc) |
| **Dados** | So funciona com dados pre-estruturados no context (chart_data, comparison_data) |
| **Demo** | Gera chart demo com dados ficticios se nao achar dados reais |
| **Limites** | NAO extrai dados automaticamente de texto/scraping. NAO faz analise de dados. NAO tem suporte a histograma, boxplot, heatmap, 3D, ou graficos interativos (Plotly). PPTX e simples (slides com 1 chart cada, sem templates). |
| **O que falta** | Plotly para interatividade, Plotly-Resampler para series temporais grandes, extracao de dados de texto (NLP -> numeros), templates de dashboard, templates PPTX profissionais, exportacao PDF |

### 7. Observer
| Aspecto | Status |
|---------|--------|
| **Status** | ✅ Funcional |
| **Watchers** | 4 tipos: web_price, web_content, file_change, api_health |
| **Scripts** | Gera Python scripts standalone com urllib only (sem dependencias) |
| **Cron** | `install_to_crontab()` e `remove_from_crontab()` funcionam |
| **Registry** | JSON-based, persiste watchers criados |
| **Intervalos** | 5m, 15m, 30m, 1h, 2h, daily + suporte a cron expressions |
| **Dados** | Salva observacoes em JSON, mantem historico (ultimas 100) |
| **Limites** | Notificacao e so log (nao envia Telegram/Discord). Precos usam regex simples (funciona em sites com $/R$). Nao tem alertas por threshold. Nao tem dashboard de observacoes. |
| **O que falta** | Notificacoes via Hermes send_message, alerts configuráveis (ex: "avise se preco cair 10%"), dashboard web das observacoes, suporte a mais tipos (SSL expiry, disk usage, docker health) |

### 8. Integrator
| Aspecto | Status |
|---------|--------|
| **Status** | ⚠️ Funciona mas nao integra de verdade |
| **Funcao** | Consolida mensagens, decide se continua ou termina |
| **Logica** | Se tem artifacts ou messages > 1 ou iteration >= 1, marca como completo |
| **Memoria** | Salva sessao no Memory Bridge (SQLite) apos execucao |
| **Limites** | Nao faz sumarizacao inteligente. Nao combina resultados de multiplos agentes. Nao gera relatorio final formatado. A logica de "completo" e muito simples - qualquer artifact ja finaliza. |
| **O que falta** | Sumarizador LLM, formatador de output (markdown, texto), combinador de resultados multi-agente, geracao de relatorio executivo |

---

## Respostas as Perguntas Especificas do Bruno

### 1. Visao Computacional (Computer Vision)

**Disponivel no Hermes:** SIM, no nivel do Hermes (nao do Hermes Unified)

O Hermes (sistema Telegram) tem `vision_tools.py` com `vision_analyze_tool()` que:
- Faz download de imagens de URLs
- Detecta MIME type (JPEG, PNG, WebP, GIF)
- Redimensiona se necessario
- Envia para modelo de visao LLM (GPT-4o, Claude, etc)
- Retorna analise textual

**Mas:** O Hermes Unified (LangGraph) NAO tem acesso a isso atualmente. O sistema foi construido como orquestrador standalone que nao importa os tools do Hermes.

**O que fazer:**
- **Facil:** Criar um Vision Bridge que chama `vision_analyze_tool()` via import direto (se o path estiver acessivel) ou via subprocess/API
- **Medio:** Usar browser_tool screenshot + vision_analyze para "ver" paginas web
- **Dificil:** Treinar/afinar modelo de visao proprio

**Recomendacao:** Conectar o Hermes Unified ao vision_analyze do Hermes via import. Implementar agente Vision que: analisa imagens enviadas no Telegram, extrai texto de imagens (OCR via vision + validation), analisa screenshots de paginas web.

### 2. Apresentacoes (Presentations)

**python-pptx:** INSTALADO (versao 1.0.2) e FUNCIONAL ✅

O Viz Bridge ja tem `generate_pptx()` que:
- Cria slide de titulo (fonte 40pt, centralizado)
- Adiciona slides com chart PNG para cada chart gerado
- Usa layout widescreen (13.333 x 7.5 polegadas)

**Capacidades atuais do python-pptx 1.0.2:**
- Criar/modificar apresentacoes do zero
- Adicionar slides com layouts pre-definidos ou blank
- Inserir imagens, textos, tabelas, graficos
- Formatacao: fontes, cores, alinhamento, bullets
- Funciona sem Microsoft Office

**Limitacoes atuais:**
- So cria slides de chart - sem texto, tabelas, graficos editaveis (so PNG)
- Sem templates profissionais
- Sem suporte a graficos do Excel incorporados
- Sem animacoes ou transicoes

**O que implementar:**
1. **Agente SlideDeck:** Cria apresentacoes completas com titulo, agenda, secoes de texto, charts, conclusao
2. **Templates 42c:** Tema com cores da marca, logo, fontes padrao
3. **Exportacao PDF:** Converter PPTX -> PDF via LibreOffice (headless)
4. **Importacao:** Ler PPTX existente e modificar

### 3. Integracao Google (Drive, Sheets, Slides, Docs, Gmail)

**google-api-python-client:** NAO INSTALADO ❌
**google-auth, google-oauth2:** NAO INSTALADOS ❌
**gspread (Google Sheets):** NAO INSTALADO ❌

**O que precisa ser instalado:**
```
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
pip install gspread  (opcional, mais facil que API raw)
```

**Nivel de esforco e complexidade:**

| Servico | Dependencias | Dificuldade | Prioridade |
|---------|-------------|-------------|------------|
| **Google Drive** | google-api-python-client | Media | Alta - para armazenar outputs |
| **Google Sheets** | gspread ou API Sheets | Baixa-Media | Alta - para dados de clientes |
| **Google Docs** | google-api-python-client | Media | Media - para relatorios |
| **Google Slides** | google-api-python-client | Media-Alta | Media - templates de apresentacao |
| **Gmail** | google-api-python-client | Media (OAuth) | Alta - email marketing |

**Requisitos comuns:**
1. Google Cloud Project com APIs habilitadas
2. Credenciais OAuth 2.0 (client_secret.json)
3. Token de refresh para acesso persistente
4. Escopos definidos por servico

**Recomendacao:** Comecar por **Google Sheets** (mais facil, mais util para agencia de midia) e **Google Drive** (para armazenar outputs de charts/PDFs). Usar **gspread** que abstrai complexidade da API Sheets. Gmail requer OAuth completo e e mais complexo.

---

## Propostas de Novos Agentes

### 1. **Reporter** -- Geracao de Relatorios
- **Funcao:** Combina resultados de outros agentes em relatorios formatados (PDF, HTML, Markdown)
- **Como:** Usa Jinja2 templates + fpdf2 ou weasyprint para gerar PDFs profissionais
- **Trigger:** Task completa com artifacts -> Reporter gera relatorio final
- **Dependencias:** fpdf2/jinja2 (INSTALADO: Jinja2 OK, fpdf2 needs install)
- **Facilidade:** FACIL (Jinja2 ja instalado)
- **Valor:** Alto - clareza e profissionalismo para clientes

### 2. **Mailroom** -- Automacao de Email
- **Funcao:** Envia emails com resultados, relatorios, e notificacoes
- **Como:** SMTP (simples) ou Gmail API (mais robusto)
- **Trigger:** Agendado ou pos-execucao de tarefa
- **Dependencias:** smtplib (built-in), google-api-python-client (Opcional)
- **Facilidade:** FACIL (SMTP) / MEDIA (Gmail API)
- **Valor:** Alto - comunicacao com clientes automatizada

### 3. **Archivist** -- Arquivamento e Organizacao
- **Funcao:** Salva outputs em locais estruturados, faz backup, organiza por cliente/projeto
- **Como:** Google Drive API + sistema de arquivos local
- **Trigger:** Sempre que artifacts sao gerados
- **Dependencias:** google-api-python-client, google-auth
- **Facilidade:** MEDIA
- **Valor:** Medio-Alto - organizacao para agencia com varios clientes

### 4. **Vision Scout** -- Analise de Imagens e Screenshots
- **Funcao:** Analisa imagens, extrai texto, identifica objetos/graficos em screenshots
- **Como:** Conecta ao `vision_analyze_tool()` do Hermes (ja existe!)
- **Trigger:** Input de imagem ou screenshot de pagina web
- **Dependencias:** Nenhuma nova (usa Hermes existente)
- **Facilidade:** FACIL (bridge para tool existente)
- **Valor:** Alto - expande capacidades drasticamente

### 5. **Social Publisher** -- Publicacao em Redes Sociais
- **Funcao:** Publica resultados em X/Twitter, LinkedIn, Instagram
- **Como:** APIs das plataformas + cron scheduling
- **Trigger:** Agendado ou manual
- **Dependencias:** xitter CLI ou tweepy, linkedin-api, instagram-basic-display
- **Facilidade:** MEDIA (cada API tem sua complexidade)
- **Valor:** Alto - agencia de midia precisa disso

### 6. **Data Miner** -- Extracao de Dados Estruturados
- **Funcao:** Extrai tabelas, precos, metricas de paginas web e PDFs
- **Como:** BeautifulSoup + pandas + regex avançado
- **Trigger:** Output do Scraper ou Knowledge
- **Dependencias:** beautifulsoup4, lxml (INSTALADO: lxml OK), pandas
- **Facilidade:** FACIL-MEDIA
- **Valor:** Alto - transforma texto solto em dados acionaveis

### 7. **Notifier** -- Sistema de Notificacoes Multi-canal
- **Funcao:** Envia notificacoes via Telegram, email, webhook
- **Como:** Conecta ao `send_message_tool()` do Hermes
- **Trigger:** Watchers do Observer, conclusao de tarefas, alerts
- **Dependencias:** Nenhuma nova (usa Hermes send_message)
- **Facilidade:** FACIL (bridge para tool existente)
- **Valor:** Alto - fecha o loop do Observer

### 8. **Transcriber** -- Audio para Texto
- **Funcao:** Transcreve audio (reunioes, podcasts, voicenotes)
- **Como:** Whisper (local ou API OpenAI), ou `transcription_tools.py` do Hermes
- **Trigger:** Upload de arquivo de audio
- **Dependencias:** openai-whisper (local) ou API externa
- **Facilidade:** MEDIA
- **Valor:** Medio - util para agencia com reunioes de cliente

### 9. **Campaign Tracker** -- Monitoramento de Campanhas
- **Funcao:** Rastreia metricas de campanhas de marketing (anuncios, social media)
- **Como:** APIs de ads (Google Ads, Meta Ads) + scraping de dashboards
- **Trigger:** Agendado (daily/weekly)
- **Dependencias:** APIs especificas de cada plataforma
- **Facilidade:** DIFICIL (cada plataforma tem API diferente)
- **Valor:** Alto - essencial para agencia de midia

### 10. **Scheduler** -- Agendamento Inteligente
- **Funcao:** Agenda tarefas recorrentes (relatorios, scraping, monitoring)
- **Como:** Cron + banco de schedule + LLM para decidir quando executar
- **Trigger:** Configuracao do usuario
- **Dependencias:** cron (built-in), SQLite (ja existe)
- **Facilidade:** FACIL
- **Valor:** Medio - automatiza operacoes recorrentes

---

## Roadmap de Evolucao

### Fase 1: "Consolidacao" (Agora -- 2 semanas)

**Objetivo:** Estabilizar o que existe, conectar ao Hermes, adicionar agentes faceis de alto valor.

| Tarefa | Agentes Afetados | Esforco |
|--------|-----------------|---------|
| **Corrigir SSL do Firecrawl** -- Adicionar `--no-check` ou configurar CA certs no Scraper Bridge | Scraper, Web | 1 dia |
| **Bridge para Hermes Tools** -- Importar vision_analyze_tool e send_message_tool no sistema | Vision Scout, Notifier | 2 dias |
| **Agente Notifier** -- Notificacoes Telegram quando watchers detectarem mudancas | Observer, Notifier | 1 dia |
| **Agente Reporter** -- Jinja2 template para relatorio Markdown/HTML dos resultados | Integrator, Reporter | 2 dias |
| **Viz: Chart auto-data-extraction** -- Extrair numeros de texto/scraping com regex + LLM | Viz | 2 dias |
| **Viz: Plotly support** -- Adicionar Plotly para graficos interativos | Viz | 3 dias |
| **PPTX Templates 42c** -- Tema profissional com logo, cores, fontes | Viz | 2 dias |
| **Memory Bridge: search improvement** -- Busca full-text, RAG sobre sessoes anteriores | Todos | 3 dias |

**Dependencias tecnicas:**
- Plotly: `pip install plotly kaleido`
- Nou: `pip install fpdf2`
- Nenhuma dependencia externa de API

**Entregaveis:** Sistema + estavel, notificacoes reais, relatorios basicos, graficos interativos.

### Fase 2: "Integracao" (Proximo mes)

**Objetivo:** Google integrado, pipeline de dados, automacao de midia.

| Tarefa | Agentes Afetados | Esforco |
|--------|-----------------|---------|
| **Google Sheets Agent** -- Ler/escrever dados de planilhas, criar dashboards | Data Miner, Viz | 1 semana |
| **Google Drive Agent** -- Salvar outputs, organizar por cliente | Archivist | 3 dias |
| **Agente Data Miner** -- Extrair tabelas de paginas web com BS4 + pandas | Scraper, Data Miner | 1 semana |
| **Browser Fallback Real** -- Playwright integrado para JS rendering | Scraper | 1 semana |
| **Vision Scout** -- Analisar imagens, extrair texto de screenshots | Vision Scout | 3 dias |
| **Agente Social Publisher** -- Postar em X/Twitter | Social Publisher | 1 semana |
| **Planner Multi-passo** -- Executar plano passo-a-passo, nao so 1 agente | Planner | 1 semana |
| **Planner Improvements** -- Re-planejamento, validacao de rota | Planner | 3 dias |

**Dependencias tecnicas:**
- Google: `pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib gspread`
- Playwright: `pip install playwright && playwright install chromium`
- BS4 ja disponivel? `pip install beautifulsoup4`
- Social: `x` CLI ou tweepy
- Credenciais OAuth para Google

**Entregaveis:** Planilhas de clientes automaticas, scraping robusto, publicacao social, visao funcional.

### Fase 3: "Escalabilidade" (Futuro -- 2-3 meses)

**Objetivo:** Automacao de campanhas, inteligencia multi-canal, dashboard executivo.

| Tarefa | Agentes Afetados | Esforco |
|--------|-----------------|---------|
| **Campaign Tracker** -- Google Ads + Meta Ads integrados | Campaign Tracker | 2-3 semanas |
| **Gmail Agent** -- Ler/responder emails, triagem automatica | Mailroom | 1 semana |
| **Agente Transcriber** -- Audio -> texto para reunioes | Transcriber | 1 semana |
| **Dashboard Executivo Web** -- Flask dashboard com todas as metricas | Todos | 2 semanas |
| **Agente Scheduler** -- Agendamento inteligente com LLM | Scheduler | 1 semana |
| **RAG sobre conhecimento** -- Busca semântica nos knowledge graphs | Knowledge, Memory | 2 semanas |
| **Parallel Agent Execution** -- DAG de agentes executando em paralelo | Core | 3 semanas |
| **Integracao WhatsApp** -- Canal de comunicacao com clientes | Mailroom | 1-2 semanas |

**Dependencias tecnicas:**
- Flask: `pip install flask`
- Google Ads API: SDK especifico
- Meta Ads API: SDK especifico
- Whisper: `pip install openai-whisper` (requer GPU idealmente)
- WhatsApp Business API: requer aprovacao do Meta

**Entregaveis:** Automacao de campanhas, comunicacao multi-canal, dashboard executivo.

---

## Tabela de Dependencias Tecnicas por Fase

### Fase 1 -- Instalacoes
```
pip install plotly kaleido fpdf2
```

### Fase 2 -- Instalacoes
```
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib gspread
pip install playwright beautifulsoup4
playwright install chromium
```

### Fase 3 -- Instalacoes
```
pip install flask openai-whisper
# Google Ads API:
pip install google-ads
# Meta Ads: python-social-auth ou SDK direto
```

---

## Riscos e Mitigacoes

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|--------------|---------|-----------|
| Firecrawl SSL nunca resolve | Media | Alto | Migrar para API HTTP direta (requests + BeautifulSoup) como fallback padrao |
| Google OAuth expira | Alta | Medio | Implementar refresh token automatico, notificar quando expirar |
| `mimo` CLI quebra | Baixa | Alto | Criar fallback usando LLM direto (ChatOpenAI) |
| `he` CLI incompativel | Baixa | Medio | Versionar requirement, fallback para extracao basica com PyMuPDF |
| VPS sem recursos para Playwright | Media | Medio | Usar API de scraping externa (ScrapingBee, ScraperAPI) |
| Hermes tools mudam de API | Media | Alto | Versionar bridge, testar na integracao continua |

---

## Metricas de Sucesso

1. **Confiabilidade:** Scraper com taxa de sucesso > 90% (hoje ~60-70%)
2. **Velocidade:** Pipeline completo < 2 min para tarefas simples
3. **Cobertura:** 5+ novas capacidades (Google, vision, notificacao, relatorios, social)
4. **Adocao:** Bruno usa o sistema para tarefas reais de agencia
5. **Extensibilidade:** Adicionar novo agente leva < 1 dia de trabalho

---

## Conclusao

O Hermes Unified tem uma base solida com LangGraph, 7 agentes funcionais, e ferramentas como MiMo, Hyper-Extract, e Firecrawl integradas. O potencial imediato esta em:

1. **Conectar ao Hermes** -- vision_analyze e send_message sao tools prontas que so precisam de uma bridge
2. **Reforzar o Viz** -- Plotly + templates PPTX profissionais sao instalacao simples
3. **Adicionar Google Sheets** -- maior valor para agencia, dependencia viavel
4. **Estabilizar Scraper** -- fallback HTTP + Playwright resolve 90% dos problemas

A Fase 1 pode ser entregue em 2 semanas com esforco focado. A Fase 2 requer dependencias externas (OAuth Google) mas e viavel.
