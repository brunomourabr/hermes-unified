# DIAGNOSTICO COMPLETO - Hermes Unified

> Data: 29/06/2026
> Sistema: 12 agentes LangGraph + 16 bridges + 187KB Python
> Status geral: ✅ Operacional com limitacoes conhecidas

---

## SUMARIO EXECUTIVO

| Componente | Status | Modo | Dependencias Instaladas |
|---|---|---|---|
| MiMo Code Bridge | ✅ | Online | mimo CLI |
| Hyper-Extract Bridge | ✅ | Online | he CLI |
| Scraper Bridge (Firecrawl) | ✅ | Online | Firecrawl CLI, API key |
| Scraper Fallback (HTTP) | ✅ | Online | requests, beautifulsoup4 |
| Viz Bridge | ✅ | Online | matplotlib, plotly, python-pptx |
| Observer Bridge | ✅ | Online | Nenhuma extra |
| Vision Scout Bridge | ⚠️ | Online parcial | HermesBridge (OpenRouter) |
| Sheets Bridge | ⚠️ | Offline (local) | gspread, google-auth (instalados, sem creds) |
| Reporter Bridge | ✅ | Online | fpdf2, jinja2 |
| DV360 Bridge | ⚠️ | Offline (mock) | google-api-python-client (instalado, sem creds) |
| TikTok Bridge | ⚠️ | Offline (mock) | tiktok-business-api-sdk (instalado, sem token) |
| Social Bridge (X/Twitter) | ⚠️ | Offline (outbox) | tweepy (instalado, sem keys) |
| Hermes Bridge | ⚠️ | Online parcial | requests |
| Notifier Bridge | ✅ | Online (log local) | HermesBridge |
| Memory Bridge | ✅ | Online | SQLite (nativo) |
| Campaign Bridge | ❌ | Scaffold apenas | Nenhuma |

---

## 1. CORE: LangGraph Orchestrator

### graph.py

**Status:** ✅ Funcional

**O que faz:** Orquestrador mestre com 12 nos de agente + 1 no de planejamento + 1 integrador. Usa LangGraph StateGraph para rotear tarefas sequencialmente.

**Arquitetura:**
- `planner_node` -> LLM classifica tarefa (CODE, KNOWLEDGE, WEB, SCRAPE, VIZ, OBSERVER, VISION, SHEETS, REPORT, DV360, TIKTOK, MULTI)
- Roteamento condicional baseado na classificacao
- Cada no executa sua bridge e retorna estado
- `integrator_node` consolida resultados
- `router_node` decide o proximo passo (loop ou END)

**Dependencias instaladas:** LangGraph 1.2.6, langchain-openai, langchain-core

**API Keys necessarias:**
- DEEPSEEK_API_KEY (para LLM de classificacao)
- OPENROUTER_API_KEY (fallback)

**Limitacoes:**
- Maximo de 3 iteracoes (hardcoded)
- Roteamento linear: cada tarefa vai para UM agente, nao ha paralelismo
- Sem cache de plano entre sessoes
- O no `scraper_fallback` existe como no separado mas nunca e chamado diretamente pelo planner

**Para producao:**
- Adicionar paralelismo com `Send()` do LangGraph
- Persistencia de estado com checkpointing
- Max iterations configurável via env
- Implementar retry logic por no

---

## 2. MiMo Code Bridge

**Status:** ✅ Funcional

**O que faz:** Gera e refatora codigo usando MiMo CLI (`mimo run`). Suporta geracao, refatoracao com backup, validacao de sintaxe, e execucao de testes.

**Dependencias instaladas:** `mimo` CLI presente em /usr/local/bin

**API Keys necessarias:** DEEPSEEK_API_KEY

**Output:** Arquivos .py gerados em /tmp/mimo_work/

**Limitacoes:**
- Sempre gera em Python (nao detecta linguagem)
- Timeout de 5 minutos fixo
- Nao usa streaming (bloqueante)
- Work directory fixo em /tmp
- `refactor_code` usa `os.system()` para backup (inseguro)

**Para producao:**
- Timeout configurável
- Suporte a multiplas linguagens
- Streaming de output
- Sandbox para execucao de codigo gerado (Docker)

---

## 3. Hyper-Extract Bridge

**Status:** ✅ Funcional

**O que faz:** Extrai conhecimento de PDFs usando `he` CLI. Converte documentos em grafos de conhecimento (JSON) com nos e arestas. Suporta busca semantica e chat com o grafo.

**Dependencias instaladas:** `he` CLI presente em /usr/local/bin

**API Keys necessarias:** Nenhuma (modelo local)

**Output:** JSON em /opt/data/knowledge_graphs/

**Metricas:** `graph_summary()` retorna total_nodes, total_edges, node_types

**Limitacoes:**
- Apenas PDF como entrada (texto puro e convertido para PDF temporario)
- Timeout de 2 minutos na extracao
- Output base hardcoded (/opt/data/knowledge_graphs)
- `talk_to_graph` nunca e chamado pelo grafo principal
- Sem validacao de template antes de executar

**Para producao:**
- Suporte a DOCX, TXT, HTML direto
- Output dir configurável
- Cache de templates descobertos
- Integrar `talk_to_graph` como no LangGraph

---

## 4. Scraper Bridge (Firecrawl)

**Status:** ✅ Funcional (online)

**O que faz:** Web scraping e busca via Firecrawl CLI. Scrape de URLs (markdown/html/text), busca web, extracao de links e titulos.

**Dependencias instaladas:** Firecrawl CLI em ~/.nvm/versions/node/v22.23.1/bin/firecrawl

**API Keys necessarias:** FIRECRAWL_API_KEY

**Output:** Texto markdown, JSON de resultados de busca

**Limitacoes:**
- Path do Firecrawl hardcoded
- Parse de resultados de busca e frágil (regex em texto plano)
- `batch_scrape` e sequencial (N chamadas)
- Timeout de 120s

**Para producao:**
- Path do firecrawl via config/env
- Usar SDK do Firecrawl em vez de CLI
- Rate limiting
- Rotacao de User-Agent

---

## 5. Scraper Fallback (HTTP)

**Status:** ✅ Funcional

**O que faz:** Fallback HTTP usando requests + BeautifulSoup. Scrape de URLs, extracao de tabelas HTML, extracao de links, busca no Google.

**Dependencias instaladas:** requests 2.34.2, beautifulsoup4 4.15.0

**API Keys necessarias:** Nenhuma

**Output:** Texto limpo, listas de dicts

**Limitacoes:**
- Google pode bloquear apos N requisicoes
- Usa unico User-Agent fixo
- Timeout de 30s
- Navegacao JavaScript nao funciona

**Para producao:**
- Rotacao de User-Agent
- Suporte a proxies
- Cache de resultados
- Integrar Playwright como segundo fallback

---

## 6. Viz Bridge

**Status:** ✅ Funcional

**O que faz:** Gera graficos matplotlib (bar, line, pie, scatter), graficos interativos Plotly, HTML dashboards, apresentacoes PowerPoint (com template 42c). Suporta comparacao de datasets e exportacao PNG/HTML/PPTX.

**Dependencias instaladas:** matplotlib 3.11.0, plotly 6.8.0, python-pptx 1.0.2

**API Keys necessarias:** Nenhuma

**Output:** PNG em /opt/projetos/hermes-unified/output/viz/

**Limitacoes:**
- Nao usa dados reais do usuario (gera dados demo quando sem contexto)
- Plotly PNG export requer Chrome/Playwright (falha silenciosa)
- Template 42c e PPTX tem cores fixas no codigo
- Dashboard HTML nao tem suporte a JavaScript interativo

**Para producao:**
- Kaggle/seaborn para dados estatisticos
- Exportacao PDF dos graficos (em vez de PNG)
- Templates customizaveis via JSON
- Temas dark mode

---

## 7. Observer Bridge

**Status:** ✅ Funcional

**O que faz:** Sistema de monitoramento cron-based. Cria watchers Python que monitoram precos web, conteudo, arquivos, e health de APIs. Registra watchers e gera comandos crontab.

**Dependencias instaladas:** Nenhuma extra (stdlib puro)

**API Keys necessarias:** Nenhuma

**Output:** Scripts Python em output/observations/scripts/

**Limitacoes:**
- Apenas 4 tipos de check (web_price, web_content, file_change, api_health)
- Notificacao via log apenas (modo "none" por padrao)
- Sem dashboard de observacoes
- `install_to_crontab` funcional mas requer acesso ao crontab do usuario
- Watchers nao sao automaticamente ativados no grafo

**Para producao:**
- Dashboard web para visualizar observacoes
- Suporte a webhooks
- Metricas com Prometheus
- Sistema de alertas com escalonamento

---

## 8. Vision Scout Bridge

**Status:** ⚠️ Online parcial

**O que faz:** Analisa imagens usando HermesBridge (OpenRouter). Suporta analise geral, extracao de texto (OCR via modelo), comparacao de imagens, e analise de screenshots.

**Dependencias instaladas:** requests (via HermesBridge)

**API Keys necessarias:** OPENROUTER_API_KEY

**Output:** Texto em output/vision/

**Limitacoes:**
- Nao e OCR real: usa modelo de visao (Gemini) para "ler" texto
- Comparacao de imagens e feita descrevendo cada imagem separadamente (nao compara pixel a pixel)
- Requer OpenRouter para funcionar (DeepSeek nao tem visao)
- Sem suporte a video
- Nao faz deteccao de objetos

**Para producao:**
- Usar OCR dedicado (Tesseract, EasyOCR)
- Comparacao real com SSIM/histograma
- Deteccao de objetos (YOLO)
- Cache de analises

---

## 9. Sheets Bridge

**Status:** ⚠️ Offline (modo local)

**O que faz:** Criar, ler, e modificar planilhas. Online (Google Sheets API) se configurado, offline (JSON + CSV) caso contrario.

**Dependencias instaladas:** gspread 6.2.1, google-auth

**API Keys necessarias:** google-service-account.json em config/

**Output:** JSON + CSV em output/sheets/

**Limitacoes:**
- Modo online requer configuracao manual de service account
- Google Sheets URL/ID retornado apenas se online
- `append_row` offline funciona mas e frágil (busca por nome de arquivo)
- Sem suporte a Google Sheets formatting (cores, formulas)

**Para producao:**
- Setup automatizado de service account
- Suporte a formulas e formatacao
- Cache local + sync
- Multiple worksheets

---

## 10. Reporter Bridge

**Status:** ✅ Funcional

**O que faz:** Gera relatorios profissionais em PDF e HTML com branding 42c. Inclui capa, sumario, secoes numeradas, e suporte a graficos.

**Dependencias instaladas:** fpdf2 2.8.7, Jinja2 3.1.6

**API Keys necessarias:** Nenhuma

**Output:** PDF + HTML em output/reports/

**Limitacoes:**
- Nao insere graficos no PDF (apenas menciona)
- PDF e gerado com fpdf2 (sem suporte a Unicode completo)
- HTML report tem CSS inline no codigo
- `generate_full_report` gera PDF+HTML mas nao acopla graficos

**Para producao:**
- Inserir graficos no PDF
- Suporte a WeasyPrint para PDF de alta qualidade
- Templates externos (nao inline)
- Exportacao DOCX

---

## 11. DV360 Bridge

**Status:** ⚠️ Offline (dados mock)

**O que faz:** Integracao com Google Display & Video 360 API. Lista anunciantes, metricas de performance, comparacao entre periodos.

**Dependencias instaladas:** google-api-python-client 2.198.0

**API Keys necessarias:** google-credentials.json (OAuth) em config/

**Output:** JSON em output/dv360/

**Limitacoes:**
- Modo offline retorna dados mock (amostra)
- Agregacao de metricas online e frágil (soma heuristicamente)
- `get_performance` tenta somar line items mas metricas sao placeholders
- Comparacao entre periodos so funciona com dados mock

**Para producao:**
- Implementar Google Ads Reporting API de verdade
- Usar queries de relatorio pre-definidas
- Dashboard de performance
- Alertas de anomalias

---

## 12. TikTok Bridge

**Status:** ⚠️ Offline (dados mock)

**O que faz:** Integracao com TikTok Ads Business API. Lista anunciantes, metricas de campanhas e ad groups, comparacao entre periodos.

**Dependencias instaladas:** tiktok-business-api-sdk-official 1.1.3

**API Keys necessarias:** TIKTOK_ACCESS_TOKEN

**Output:** JSON em output/tiktok/

**Limitacoes:**
- Modo offline retorna dados mock
- SDK instalado mas API online nunca testada (sem token)
- `get_campaign_performance` e `get_adgroup_stats` nao chamam endpoints de stats reais
- Stats das campanhas online sao zero (placeholders)

**Para producao:**
- Configurar OAuth flow para TikTok Ads
- Implementar chamadas reais de stats
- Dashboard de performance TikTok
- Integrar com Viz Bridge para graficos

---

## 13. Social Bridge (X/Twitter)

**Status:** ⚠️ Offline (modo outbox)

**O que faz:** Publica posts no X/Twitter (texto, midia, threads). Modo offline salva em "outbox" local para publicacao posterior.

**Dependencias instaladas:** tweepy 4.16.0

**API Keys necessarias:** TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET (ou BEARER_TOKEN)

**Output:** JSON em output/social/outbox/

**Limitacoes:**
- Modo offline nunca e "despachado" automaticamente
- Thread posting tem OAuth1UserHandler com `...` (codigo incompleto)
- Limite de 280 chars fixo (X/Twitter agora permite ate 4000)
- Media upload depende de API v1.1 (v2 mais recente usa media_ids)

**Para producao:**
- Implementar "flush" do outbox
- Suporte a agendamento de posts
- Suporte a multiplas plataformas (LinkedIn, Instagram)
- Analise de engajamento

---

## 14. Hermes Bridge

**Status:** ⚠️ Online parcial

**O que faz:** Ponte para servicos externos. Analise de imagem via OpenRouter/Gemini, envio de notificacoes Telegram, fallback para log local.

**Dependencias instaladas:** requests 2.34.2

**API Keys necessarias:** OPENROUTER_API_KEY (visao), TELEGRAM_BOT_TOKEN + TELEGRAM_HOME_CHANNEL (notificacoes)

**Output:** Texto de analise, arquivos de log em output/notifications/

**Limitacoes:**
- Vision analyze funciona apenas com OpenRouter (nao fallback para outro provider)
- Telegram notification usa env vars (nao usa config/secrets.json)
- Sem suporte a envio de midia pelo Telegram
- Sem validacao de modelo de visao antes de chamar

**Para producao:**
- Suporte a Anthropic Claude Vision
- Upload de midia Telegram
- Templates de mensagem configuráveis
- Rate limiting nas chamadas API

---

## 15. Notifier Bridge

**Status:** ✅ Funcional (log local)

**O que faz:** Sistema de notificacoes multicanal. Conecta watchers, tarefas, e erros ao Hermes Bridge para envio.

**Dependencias instaladas:** HermesBridge (nativo)

**API Keys necessarias:** TELEGRAM_BOT_TOKEN (opcional, para Telegram)

**Output:** Arquivos .txt em output/notifications/

**Limitacoes:**
- Apenas notifica se Hermes Bridge conseguir enviar
- Sem suporte a email/SMS
- Sem templates de notificacao
- Nao ha fila de notificacoes (perde se falhar)

**Para producao:**
- Fila de notificacoes com retry
- Suporte a Email (SMTP)
- Suporte a Webhook
- Dashboard de notificacoes

---

## 16. Memory Bridge

**Status:** ✅ Funcional

**O que faz:** Memoria persistente via SQLite. Salva sessoes, artefatos, observacoes de watchers, e cache de conhecimento com TTL.

**Dependencias instaladas:** SQLite3 (stdlib)

**API Keys necessarias:** Nenhuma

**Output:** data/memory.db (32768 bytes atual)

**Metricas:** 4 tabelas (sessions, artifacts, observations, knowledge_cache)

**Limitacoes:**
- `search_sessions` usa LIKE (case-sensitive, sem full-text search)
- Cache com TTL simples (nao expira em tempo real)
- Sem compressao de dados
- Sem migracoes de schema

**Para producao:**
- Full-text search (FTS5)
- Compressao de artefatos grandes
- Backup automatico
- API REST para consulta externa

---

## 17. Campaign Bridge

**Status:** ❌ Scaffold apenas

**O que faz:** Placeholder para integracao com Google Ads e Meta Ads. Nao faz nada alem de verificar status de configuracao.

**Dependencias instaladas:** Nenhuma

**API Keys necessarias:** GOOGLE_ADS_*, META_* (documentadas apenas)

**Output:** Nenhum

**Limitacoes:**
- Nenhuma implementacao real
- Google Ads requer `google-ads` lib (nao instalada)
- Meta Ads requer `facebook-business` lib (nao instalada)
- Nao integrado ao grafo principal

**Para producao:**
- Implementar track_google_ads() com google-ads API
- Implementar track_meta_ads() com facebook-business SDK
- Integrar como nos no LangGraph
- Dashboard de campanhas

---

## 18. Config Management

**Status:** ✅ Funcional

**O que faz:** Config/__init__.py carrega chaves de secrets.json com fallback para env vars. Protege arquivo com chmod 600.

**Arquivo:** config/secrets.json (criado automaticamente)

**Limitacoes:**
- Sem encryptacao do arquivo de secrets (apenas permissoes de arquivo)
- Sem suporte a AWS Secrets Manager ou Vault
- Sem refresh automatico de chaves expiradas

**Para producao:**
- Criptografia do secrets.json
- Provider externo (AWS Secrets Manager, HashiCorp Vault)
- Rotacao automatica de chaves

---

## 19. Output Organization

**Status:** ✅ Funcional

**Diretorios de output:**
- output/viz/ - Graficos PNG, HTML, PPTX
- output/reports/ - Relatorios PDF, HTML
- output/sheets/ - Planilhas JSON, CSV
- output/social/outbox/ - Posts pendentes
- output/social/sent/ - Posts enviados
- output/dv360/ - Dados DV360
- output/tiktok/ - Dados TikTok
- output/campaigns/ - Dados de campanhas (vazio)
- output/vision/ - Analises de imagem
- output/observations/scripts/ - Scripts de watcher
- output/observations/data/ - Dados de watcher
- output/notifications/ - Logs de notificacao

---

## MATRIZ DE DEPENDENCIAS

| Bridge | Dependencias | API Keys | Online sem config |
|---|---|---|---|
| MiMo | mimo CLI | DEEPSEEK_API_KEY | Sim |
| Hyper-Extract | he CLI | - | Sim |
| Scraper | Firecrawl CLI, node | FIRECRAWL_API_KEY | Nao |
| ScraperFallback | requests, bs4 | - | Sim |
| Viz | matplotlib, plotly, pptx | - | Sim |
| Observer | stdlib | - | Sim |
| VisionScout | requests | OPENROUTER_API_KEY | Nao |
| Sheets | gspread, google-auth | google-service-account.json | Sim (offline) |
| Reporter | fpdf2, jinja2 | - | Sim |
| DV360 | google-api-python-client | google-credentials.json | Sim (mock) |
| TikTok | tiktok-business-api-sdk | TIKTOK_ACCESS_TOKEN | Sim (mock) |
| Social | tweepy | TWITTER_* keys | Sim (outbox) |
| Hermes | requests | OPENROUTER_API_KEY, TELEGRAM_* | Parcial |
| Notifier | HermesBridge | TELEGRAM_BOT_TOKEN | Sim (log) |
| Memory | sqlite3 | - | Sim |
| Campaign | - | GOOGLE_ADS_*, META_* | Sim (vazio) |

---

## RECOMENDACOES PRIORITARIAS

1. **CRITICO:** Configurar FIRECRAWL_API_KEY e OPENROUTER_API_KEY (2 bridges offline)
2. **ALTO:** Ativar TikTok e DV360 com credenciais reais (substituir dados mock)
3. **MEDIO:** Integrar Campaign Bridge ao grafo principal
4. **MEDIO:** Adicionar persistencia de estado no LangGraph
5. **BAIXO:** Implementar "flush" do outbox do Social Bridge
6. **BAIXO:** Substituir OCR via modelo de visao por Tesseract/EasyOCR
