# Hermes — Implantação Completa

**Autor:** Bruno Moura (42c)
**Data:** Julho 2026
**Sistema:** Agente autônomo LangGraph + Telegram + CLI + Crons
**Base:** Hermes Agent (open-source, 160K+ GitHub stars) adaptado para mídia digital, dados, marketing causal e automação

---

## 1. Visão Geral da Arquitetura

O Hermes é um **orquestrador multi-agente** baseado em LangGraph. Ele roteia tarefas do usuário para **bridges especializadas**, cada uma responsável por um domínio. O sistema acumula conhecimento entre sessões (memória persistente), cria procedimentos reutilizáveis (skills), e evolui automaticamente (curadoria).

```
┌─────────────────────────────────────────────────────────────┐
│                     ENTRY POINTS                             │
│         Telegram (DM)  │  CLI (main.py)  │  Crons (3)       │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│               LANGGRAPH ORCHESTRATOR                         │
│        core/graph.py — ~1.900 linhas, 12-14 agent nodes      │
│                                                              │
│  planner → [codex│knowledge│web│scrape│viz│observer|report   │
│            │sheets│dv360│tiktok│social│vision|research|multi] │
│          → router → integrator → (loop até 90 turns)        │
│                                                              │
│  + Headroom compression (46-92% token reduction)             │
│  + Cache diskcache (TTL 30min-24h)                           │
│  + Fallback cascata (primário → heurística → msg amigável)   │
│  + Guardrails (bloqueia saudações, spam, queries curtas)     │
│  + Query Rewriting (re-escrita inteligente se busca falhar)  │
│  + Hard cap 90 turns                                         │
│  + Auto-skill suggestion (5+ tool calls → sugere skill)      │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    CAMADA DE BRIDGES                          │
│                                                              │
│  1. MiMo Code     → tools/mimo_bridge.py       Geração/refat.│
│  2. Hyper-Extract → tools/he_bridge.py         Grafos PDF    │
│  3. Web Scraper   → tools/scraper_bridge.py     Firecrawl CLI │
│  4. Scraper Fallb.→ tools/scraper_fallback.py   requests+BS4  │
│  5. Viz           → tools/viz_bridge.py         matplotlib/pptx│
│  6. Observer      → tools/observer_bridge.py    Watchers cron │
│  7. Reporter      → tools/reporter_bridge.py    PDF/HTML      │
│  8. Sheets        → tools/sheets_bridge.py      JSON/CSV/GSht│
│  9. DV360         → tools/dv360_bridge.py        Mídia program│
│ 10. TikTok        → tools/tiktok_bridge.py       TikTok Ads   │
│ 11. Social        → tools/twitter_bridge.py      X/Twitter   │
│ 12. Vision Scout  → tools/vision_scout_bridge.py Imagens      │
│ 13. Financial BR  → tools/financial_br_bridge.py  BCB/indices │
│ 14. MCP Brasil    → tools/mcp_brasil_bridge.py   307 tools BR │
│ 15. Research      → tools/research_bridge.py      Pesquisa    │
│ 16. Causal (MMM)  → tools/causal_bridge.py        PyMC/Causal │
│ 17. Memory        → tools/memory_bridge.py        SQLite FTS5 │
│ 18. Notifier      → tools/notifier_bridge.py       Notificações│
│ 19. Campo         → tools/campaign_bridge.py       Campanhas  │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    AUTO-EVOLUÇÃO                              │
│                                                              │
│  Curador de Skills    → dom 3h  (skill_curator.py)           │
│  Auto-Skill Creator   → hook no LangGraph                    │
│  Memory Consolidator  → 12h     (memory_consolidator.py)     │
│  Snapshots            → antes de cada curadoria              │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Infraestrutura

| Componente | Detalhe |
|-----------|---------|
| **VPS** | Hostinger (Ubuntu 22.04, 2 vCPUs, 4GB RAM) |
| **Python** | 3.13 (venv principal) + 3.11 (venv causal PyMC) |
| **LLM Provider** | OpenRouter (Kimi K2.5, DeepSeek V4, GPT-4o-mini) |
| **Cache** | Diskcache (TTL configurável por tipo) |
| **Orquestração** | LangGraph StateGraph (~1.900 linhas) |
| **Armazenamento** | SQLite (memória FTS5) + JSON (config) + Pickle (modelos) |
| **Node.js** | v22.23.1 (Firecrawl CLI, localtunnel) |
| **Domínios** | estante.42c.ia.br (automação) |

---

## 3. Bridges — Detalhamento Completo

### 3.1 MiMo Code Bridge (`tools/mimo_bridge.py` — 6.1KB)

Gera e refatora código usando MiMo CLI (`mimo run -m deepseek/deepseek-chat`).

**Funcionalidades:**
- Geração de Python a partir de descrição textual
- Refatoração com backup automático
- Validação de sintaxe (`py_compile`)
- Templates com stack, style_guide, existing_files

**Limitações:** Sempre gera Python, timeout fixo 5min, sem streaming.

---

### 3.2 Hyper-Extract Bridge (`tools/he_bridge.py` — 7.9KB)

Extrai conhecimento de PDFs usando Hyper-Extract CLI (`he parse`).

**Funcionalidades:**
- Converte PDFs em **grafos de conhecimento** (JSON com nós + arestas)
- Busca semântica no grafo (`he search`)
- Chat com o documento (`he talk`)
- Templates customizáveis

**Exemplo de uso:** Extrair conceitos de whitepapers, artigos, documentação técnica.

---

### 3.3 Web Scraper Bridge (`tools/scraper_bridge.py` — 7.7KB)

Scraping via Firecrawl CLI.

**Funcionalidades:**
- Busca na web (`firecrawl search --limit N`)
- Extração de conteúdo de URL (`firecrawl scrape`)
- Batch scraping (sequencial)
- Auto-detecção de formato

**Limitação:** SSL intermitente com api.firecrawl.ai. Fallback via `scraper_fallback.py`.

---

### 3.4 Scraper Fallback (`tools/scraper_fallback.py` — 10.4KB)

Alternativa quando Firecrawl falha.

**Funcionalidades:**
- HTTP direto com `requests` + `BeautifulSoup`
- Extração de tabelas HTML
- Extração de links
- Fallback automático

---

### 3.5 Viz Bridge (`tools/viz_bridge.py` — 24.3KB)

Geração de gráficos e apresentações.

**Funcionalidades:**
- matplotlib: bar, line, pie, scatter, area, comparação
- Dashboard HTML com múltiplos gráficos (base64 embed)
- PowerPoint (.pptx) com branding 42c
- Gráficos interativos Plotly

---

### 3.6 Observer Bridge (`tools/observer_bridge.py` — 24KB)

Criação de watchers automatizados.

**Funcionalidades:**
- Watcher de preço web
- Watcher de conteúdo web (hash MD5)
- Watcher de arquivo local
- Watcher de health check de API
- Instalação/remoção de cron jobs
- Registry JSON-based

---

### 3.7 Reporter Bridge (`tools/reporter_bridge.py` — 16.7KB)

Geração de relatórios profissionais.

**Funcionalidades:**
- PDF com capa escura + sumário + seções numeradas
- HTML interativo responsivo
- Planilhas JSON + CSV

---

### 3.8 Sheets Bridge (`tools/sheets_bridge.py` — 12.5KB)

Manipulação de planilhas.

**Funcionalidades:**
- Planilhas locais (JSON + CSV)
- Google Sheets (requer service account)
- Exportação CSV

---

### 3.9 DV360 Bridge (`tools/dv360_bridge.py` — 22.2KB)

Integração com Google Display & Video 360.

**Funcionalidades:**
- Listar anunciantes
- Performance de campanhas (impressões, clicks, gasto, conversões)
- Comparação de períodos com delta percentual
- **Status:** Mock offline (sem credenciais). Funciona com dados de demonstração.

---

### 3.10 TikTok Bridge (`tools/tiktok_bridge.py` — 22.7KB)

Integração com TikTok Ads.

**Funcionalidades:**
- Listar anunciantes
- Performance de campanhas
- Estatísticas de Ad Groups
- Relatório completo com recomendações
- **Status:** Mock offline (sem token de API)

---

### 3.11 Financial BR Bridge (`tools/financial_br_bridge.py` — 22.8KB)

Dados financeiros brasileiros.

**Funcionalidades:**
- BCB SGS (Selic, CDI, câmbio, TR, IPCA)
- brapi.dev (ações: PETR4, MGLU3, VALE3, ITUB4)
- Tesouro Direto
- Yahoo Finance (câmbio)
- Fallback offline com dados realistas
- Cache diskcache (TTL 30min)

---

### 3.12 MCP Brasil Bridge (`tools/mcp_brasil_bridge.py` — 8.9KB)

307 ferramentas de dados públicos brasileiros.

**Funcionalidades:**
- Acesso batch direto ao MCP-Brasil
- CNPJ, CEP, legislação, dados abertos
- Integração via dispatch interno

---

### 3.13 Research Bridge (`tools/research_bridge.py` — 16.4KB)

Pesquisa aprofundada com múltiplas fontes.

**Funcionalidades:**
- Pesquisa web com síntese
- Múltiplas queries paralelas
- Citação de fontes
- Relatório estruturado

---

### 3.14 Causal Bridge (`tools/causal_bridge.py` — 19.2KB)

Marketing Causal — MMM + Synthetic Control.

**Stack:**
- PyMC 5.28.5 (MCMC Bayesiano)
- PyMC-Marketing 0.19.4 (MMM: adstock + saturação)
- CausalPy 0.8.1 (Synthetic Control)
- ArviZ (diagnóstico R-hat, ESS)

**Funcionalidades:**
- `mmm_train()` — Treina MMM com dados reais ou sintéticos
- `mmm_analyze()` — Contribuições, saturação, ROAS por canal
- `budget_optimize()` — Alocação ótima entre canais
- `causal_analyze()` — Synthetic Control (Ridge)

**Bug conhecido:** `cores=0` falha em VPS — contornado com `cores=1`.

**5 datasets públicos preparados:**
| Dataset | Fonte | Linhas | Canais |
|---------|-------|--------|--------|
| Shenzhen MMM | Dados reais (China) | 374 sem. | 5 mídia + econômicos |
| Observed MMM | deejayrusso | 156 sem. | TV + Search |
| Meridian Style | Google Meridian | 104 sem. | 4 canais |
| PyMC Tutorial | Tutorial oficial | 179 sem. | 2 canais |
| CausalPy SC | Sintético | 150 per. | 10 controles |

---

### 3.15 Memory Bridge / Session Search

Memória persistente baseada em SQLite com FTS5 (full-text search).

**Funcionalidades:**
- Todas as sessões indexadas e buscáveis
- Recall automático via `session_search(query)`

---

## 4. Camada de Orquestração

### 4.1 LangGraph (`core/graph.py` — 76.6KB, ~1.900 linhas)

O cérebro do sistema. StateGraph com 14+ nodes.

**Nodes:**
- `planner_node` — Classifica tarefa com LLM (CODE, KNOWLEDGE, WEB, SCRAPE, VIZ, OBSERVER, VISION, SHEETS, REPORT, DV360, TIKTOK, SOCIAL, RESEARCH, MULTI)
- Nodes de execução — Cada agente executa sua bridge
- `router_node` — Decide loop ou END
- `integrator_node` — Consolida resultados

**Funcionalidades transversais:**
- **Headroom compression** — Reduz tokens em 46-92% via proxy
- **Cache diskcache** — web TTL 1h, bridge TTL 30min, LLM TTL 24h
- **Fallback cascata** — Bridge primária → heurística → mensagem amigável
- **Guardrails** — Bloqueia saudações, spam, queries muito curtas
- **Query Rewriting** — Se busca falha, LLM reescreve e tenta de novo
- **Hard cap 90 turns** — Evita loops infinitos

### 4.2 Ontology Engine (`core/ontology.py` — 11.9KB)

Camada semântica compartilhada — define o que cada conceito significa.

**Entidades definidas:** Campaign, Metric, AdSet, ResearchTopic, Claim, Source, Report, Spreadsheet, Visualization, etc.

### 4.3 Semantic Router (`core/semantic_router.py` — 19KB)

Ponte entre planner e bridges. Usa a ontologia para:
- Mapear query do usuário para conceitos
- Selecionar bridge(s) correta(s)
- Anotar com contexto semântico
- Validar dados contra constraints

**9 intents mapeadas:** campaign, research, report, visualization, data, social, code, monitor, general.

---

## 5. Sistema de Memória (3 Tiers)

### Tier 1: Sempre em Contexto (MEMORY.md + USER.md)

| Limite MEMORY | Limite USER | Persistência |
|:---:|:---:|:---|
| 3.500 chars | 2.000 chars | Imediata via `memory` tool |

- Snapshot congelado no início de cada sessão
- Visível na sessão seguinte
- Consolidação automática a cada 12h via cron

### Tier 2: Buscável (Session Search)

- SQLite com FTS5 (full-text search)
- Busca explícita via `session_search(query)`
- Cobertura: todas as sessões, sem limite

### Tier 3: Skills (Memória Procedural)

59 skills em 27 categorias:
- 40 skills bundled (instaladas com o Hermes — protegidas)
- 19 skills criadas por usuário/agente
- 15 categorias: ai-ml, creative, data-science, devops, github, mcp, media, productivity, research, social-media, software-development, e mais

**Disclosure progressiva:** Nível 0 (nomes + descrições) → Nível 1 (corpo completo) → Nível 2 (arquivos de referência)

---

## 6. Sistema de Skills e Curadoria

### Curador Automático (`tools/skill_curator.py` — 19.8KB)

| Aspecto | Detalhe |
|---------|---------|
| **Agendamento** | Domingo 3h (cron job) |
| **Fase 1** | Determinística: stale 30+ dias, archive 90+ dias |
| **Fase 2** | LLM (opcional): detecta quebradas, sugere merge |
| **Proteção** | Skills bundled NUNCA tocadas. Snapshot antes de alterar |
| **Snapshot** | `/opt/data/skills/.snapshots/curation_*.tar.gz` |

### Auto-Skill Creator (`tools/auto_skill_creator.py` — 23.7KB)

| Aspecto | Detalhe |
|---------|---------|
| **Trigger** | 5+ tool calls na mesma sequência |
| **Hook** | `integrator_node` no LangGraph |
| **Extração** | Nome, descrição, categoria, procedimento inferidos |
| **Decisão** | Apenas SUGERE — nunca cria automaticamente |
| **Storage** | `/opt/projetos/hermes-unified/.session_skill_suggestions/` |

**Exemplo real:** Durante testes da bridge causal (6 tool calls), sugeriu skill `dados-campanha-marketing-mmm`.

---

## 7. Hard Cap de Turns

| Parâmetro | Valor |
|-----------|-------|
| MAX_TURNS | 90 |
| Implementação | `planner_node` → `_check_turn_limit()` |
| State | `turn_count: int` no `AgentState` |
| Típico | 15-30 turns por tarefa |

**Por que 90:** Igual ao Hermes oficial. Suficiente para tarefas complexas com subagentes, sem permitir runaway.

---

## 8. Crons Ativos

| Nome | Agenda | Função | Entrega |
|------|--------|--------|---------|
| Panorama Financeiro | Seg-Sex 19h | Selic, CDI, câmbio, ações | Telegram |
| Curador de Skills | Dom 3h | Stale/archive/merge | Relatório interno |
| Memory Consolidator | Cada 12h | Merge de entradas >80% | Relatório interno |

---

## 9. Documentação Produzida

| Documento | Tamanho | Conteúdo |
|-----------|---------|----------|
| `CATALOGO_FUNCIONALIDADES.md` | 18.1KB | 557 linhas — catálogo completo de funcionalidades |
| `DIAGNOSTICO_COMPLETO.md` | 17.4KB | 561 linhas — diagnóstico bridge por bridge |
| `PLANO_ESTRATEGICO.md` | 21.9KB | 413 linhas — plano de evolução agente por agente |
| `HERMES_IMPLANTACAO.md` | 14.6KB | 300 linhas — resumo técnico da implantação |
| `docs/MCP_COMPENDIO.md` | 10.2KB | 202 linhas — 400+ MCP servers catalogados |

---

## 10. Métricas de Operação

| Métrica | Valor | Nota |
|---------|-------|------|
| **Skills no catálogo** | 59 | 40 bundled + 19 user |
| **Bridges implementadas** | 19 | 8 live no grafo, 11 como tool |
| **Código total** | ~187KB Python | core + tools + bridges |
| **Memória usada** | 88% | Consolidado a cada 12h |
| **Custo médio/sessão** | ~$0.05-0.20 | OpenRouter (gpt-4o-mini + Kimi) |
| **Tempo médio resposta** | 15-30s | Varia com complexidade |
| **Tarefas/semana** | ~15-25 | Estimativa |
| **Crons ativos** | 3 | Financeiro, Curador, Memória |
| **Snapshots** | 2 | Curadoria manual + automática |

---

## 11. Decisões de Arquitetura Comentadas

### LangGraph vs ReAct puro
**Escolha:** LangGraph com state graph. O Hermes oficial usa ReAct. Para pipelines de dados multi-etapa, grafo é mais natural.

### Venv isolado para PyMC
**Escolha:** Venv separado (/opt/venvs/causal/). PyMC-Marketing tem dependências conflitantes (pytensor).

### Headroom compression
**Escolha:** Proxy mode. Reduz tokens em 46-92%, essencial para sessões longas.

### Curador determinístico vs LLM
**Escolha:** Fase 1 (sempre) + Fase 2 (opcional). Decisão temporal não precisa de LLM.

### 90 turns como hard cap
**Escolha:** Igual Hermes oficial. Tarefas típicas: 15-30 turns. Seguro.

### Não implementar GEPA
**Motivo:** $2-10/rodada para evolução offline de prompts. Só compensa com uso intensivo ou multi-agente.

### Não implementar knowledge graph externo
**Motivo:** Busca FTS5 sobre sessões cobre 95% dos casos. KG só vale a pena em 1.000+ sessões.

---

## 12. Status das Bridges

| Bridge | Status | Modo | Dependências |
|--------|--------|------|-------------|
| MiMo Code | ✅ Live | Online | mimo CLI, DEEPSEEK_API_KEY |
| Hyper-Extract | ✅ Live | Online | he CLI |
| Web Scraper | ✅ Live | Online | Firecrawl CLI |
| Scraper Fallback | ⚡ Tool | Online | requests, bs4 |
| Viz | ✅ Live | Online | matplotlib, plotly, python-pptx |
| Observer | ✅ Live | Online | Nenhuma |
| Reporter | ✅ Live | Online | fpdf2 |
| Sheets | ⚡ Tool | Local OK / Google offline | gspread (sem creds) |
| DV360 | ✅ Live | Mock offline | google-api-client (sem creds) |
| TikTok | ✅ Live | Mock offline | tiktok-business-api (sem token) |
| Social (X) | ⚡ Tool | Outbox local | tweepy (sem keys) |
| Vision Scout | ⚠️ | Parcial | OpenRouter |
| Financial BR | ✅ Live | Online | BCB SGS, brapi.dev |
| MCP Brasil | ⚡ Tool | Online | MCP-Brasil dispatch |
| Research | ✅ Live | Online | web_search |
| Causal (MMM) | ⚡ Tool | Online | PyMC 5.28, venv isolado |
| Memory | ✅ Live | Online | SQLite FTS5 |
| Notifier | ⚡ Tool | Log local | Hermes Bridge |
| Campaign | ❌ | Scaffold | Nenhuma |

---

## 13. Roadmap

### Prioridade alta
- Integrar bridge causal no LangGraph (node `causal` no graph.py)
- Adicionar experimentos controlados com geo-lift
- Métricas de desempenho das skills

### Prioridade média
- Dashboard web com status dos crons e bridges
- Testes automatizados (pytest + CI)
- Cache de respostas do LLM para queries frequentes

### Prioridade baixa
- GEPA (evolução offline de prompts)
- Knowledge graph como Tier 3 de memória
- Multi-agent paralelo

---

## 14. Comandos Úteis

```bash
# Executar orquestrador
python main.py "Seu objetivo aqui" --files documento.pdf

# Rodar curador de skills
python tools/skill_curator.py              # dry-run
python tools/skill_curator.py --no-dry-run  # real

# Consolidar memória
python tools/memory_consolidator.py

# Rodar MMM
python tools/causal_bridge.py tutorial

# Ver skills
hermes skills list

# Ver crons
hermes cron list
```

---

*Este documento descreve a implantação completa do Hermes Agent na 42c em julho de 2026. Baseado no código aberto Hermes Agent (160K+ GitHub stars). Bruno Moura — bruno@42c.work*
