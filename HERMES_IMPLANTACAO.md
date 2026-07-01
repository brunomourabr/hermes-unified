# Hermes Agent — Implantação e Arquitetura

**Autor:** Bruno Moura (42c)
**Data:** Julho 2026
**Base:** Hermes Agent (open-source, 160K+ GitHub stars) adaptado para análise de dados, marketing causal e automação de mídia digital.

---

## 1. Filosofia de Design

O Hermes foi implantado seguindo três princípios fundamentais:

**Composição sobre monólito.** Em vez de um único agente que faz tudo, usamos um **orquestrador LangGraph** que roteia tarefas para bridges especializadas (código, conhecimento, scraping, finanças, marketing causal). Cada bridge é independente, testável e substituível.

**Memória e skills que evoluem.** O Hermes não é um sistema estático — ele acumula conhecimento entre sessões (memória persistente) e cria/refina procedimentos reutilizáveis (skills). Quanto mais você usa, melhor ele fica.

**Offline-first.** Todas as bridges funcionam sem API keys. Dados sintéticos são gerados localmente quando não há dados reais. Isso garante que o sistema nunca fique bloqueado por dependências externas.

---

## 2. Stack Tecnológica

```
┌─────────────────────────────────────────────────────────┐
│                    ENTRY POINTS                          │
│            Telegram  │  CLI  │  Cron Jobs                │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│              LANGGRAPH ORCHESTRATOR                      │
│           (core/graph.py — ~1900 linhas)                 │
│                                                          │
│  planner → [codex│knowledge│web│finance|causal] → router │
│                                                          │
│  + Headroom compression (46-92% token reduction)         │
│  + Cache diskcache (TTL 30min-24h)                       │
│  + Fallback cascata (primário → heurística → msg)        │
│  + Hard cap 90 turns (MAX_TURNS = 90)                    │
│  + Auto-skill suggestion hook (5+ tool calls)            │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                    BRIDGES                                │
│                                                          │
│  📊 Financeiro   → financial_br_bridge.py                │
│  🔬 Causal       → causal_bridge.py (PyMC + CausalPy)   │
│  🌐 Web          → scraper_bridge.py (Firecrawl)         │
│  📄 Relatórios   → reporter_bridge.py (PDF)              │
│  📈 Campanhas    → campaign_bridge.py                    │
│  📱 Mídia Social → tiktok_bridge.py, dv360_bridge.py     │
│  🧠 Conhecimento → he_bridge.py (Hyper-Extract)          │
│  💻 Código       → mimo_bridge.py (DeepSeek)             │
│  🇧🇷 Dados BR    → mcp_brasil_bridge.py                   │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│              AUTO-EVOLUÇÃO                               │
│                                                          │
│  🧹 Curador de Skills    → cron semanal (dom 3h)        │
│  🤖 Auto-Skill Creator   → hook no LangGraph            │
│  🧠 Memory Consolidator  → cron a cada 12h              │
│  📸 Snapshots            → antes de cada curadoria      │
└─────────────────────────────────────────────────────────┘
```

### Infraestrutura

- **VPS:** Hostinger (Ubuntu 22.04, 2 vCPUs, 4GB RAM)
- **Python:** 3.13 (venv principal) + 3.11 (venv causal para PyMC)
- **LLM Provider:** OpenRouter (Kimi K2.5, DeepSeek V4, GPT-4o-mini)
- **Cache:** Diskcache (TTL configurável por tipo de dado)
- **Orquestração:** LangGraph (StateGraph com ~20 nodes)
- **Armazenamento:** SQLite (memória) + JSON (configuração)

---

## 3. Sistema de Memória (Três Níveis)

Inspirado no Hermes oficial, implementamos três tiers de memória:

### Tier 1: Sempre em Contexto (MEMORY.md + USER.md)

- **Limite:** 3.500 caracteres (MEMORY) + 2.000 (USER)
- **Injeção:** Snapshot congelado no início de cada sessão
- **Persistência:** Imediata (via `memory` tool), visível na próxima sessão
- **Consolidação automática:** Script `memory_consolidator.py` roda a cada 12h via cron. Quando uso atinge 80%+, faz merge de entradas relacionadas

**Escolha de design:** Optamos por limites menores que o Hermes oficial (2.200 + 1.375) porque nossas sessões tendem a ser mais longas e densas em contexto técnico. O consolidador roda com mais frequência (12h vs 7d).

### Tier 2: Buscável (Session Search)

- **Engine:** SQLite com FTS5 (full-text search)
- **Trigger:** Busca explícita via `session_search(query)` ou referência a conversas passadas
- **Cobertura:** Todas as sessões, sem limite de tamanho

### Tier 3: Skills (Memória Procedural)

- **Formato:** SKILL.md com YAML frontmatter (nome, descrição, versão, tags)
- **Disclosure progressiva:** Nível 0 (nomes+descrições) → Nível 1 (corpo completo) → Nível 2 (arquivos de referência)
- **Catálogo atual:** 59 skills em 15 categorias
- **Auto-criação:** Sugerida após 5+ tool calls na mesma tarefa

**Por que não implementar memória Tier 3 externa (knowledge graph)?** O custo de manutenção de um knowledge graph supera o benefício para um time de 1-2 pessoas. A busca FTS5 sobre sessões cobre 95% dos casos de "lembra daquela conversa sobre X?".

---

## 4. Sistema de Skills e Curadoria

### Estrutura de uma Skill

```yaml
---
name: k8s-pod-debug
description: Ativar para pods crashando, CrashLoopBackOff
version: 1.2.0
author: agent
platforms: [linux, macos]
---

## Procedimento
1. Get pod status → check events → pull logs
2. Look for OOMKilled, ImagePullBackOff

## Pitfalls
- Esquecer a flag --previous em containers reiniciados

## Verificação
- Pod stays Running with 0 restarts for 5+ minutes
```

### Curador Automático (skill_curator.py)

**Agendamento:** Todo domingo às 3h (cron job)

**Fase 1 — Determinística (sem custo de LLM):**
- Skills não usadas por 30+ dias → marcadas como `stale` (SKILL.stale.md + .stale_info)
- Skills não usadas por 90+ dias → movidas para `.archive/`
- Skills com arquivo de proteção (`.hermes_curator_pin`) → nunca tocadas
- Skills em categorias protegidas (`software-development`, `devops`, `github`) → nunca arquivadas

**Fase 2 — Com LLM (opcional, ativável via flag):**
- Skills quebradas (YAML frontmatter inválido) → detectadas e reportadas
- Skills duplicadas → sugeridas para merge

**Segurança:**
- Snapshot tar.gz completo antes de qualquer alteração (`/opt/data/skills/.snapshots/`)
- Skills bundled (instaladas com o Hermes) — NUNCA tocadas
- Reversível: extraia o snapshot para restaurar

### Auto-Skill Creator (auto_skill_creator.py)

- **Trigger:** 5+ tool calls na mesma sequência de tarefa
- **Mecanismo:** Hook no `integrator_node` do `core/graph.py`
- **Extração:** Nome, descrição, categoria, procedimento inferidos do contexto
- **Decisão:** Apenas SUGERE — nunca cria automaticamente
- **Armazenamento:** Sugestão em JSON (`/opt/projetos/hermes-unified/.session_skill_suggestions/`)

**Escolha de design:** Não criar automaticamente evita poluir o catálogo com skills de baixa qualidade. O usuário decide o que merece virar skill.

---

## 5. Hard Cap de Turns

**Problema resolvido:** Agentes LLM podem entrar em loops infinitos, queimando créditos da API do OpenRouter sem produzir resultado.

**Implementação:**
- `MAX_TURNS = 90` constante no topo do `core/graph.py`
- `turn_count: int` no `AgentState` — incrementado a cada node
- `_check_turn_limit()` no início do `planner_node` — se >= 90, interrompe com mensagem clara
- Estado inicial `turn_count: 0`

**Por que 90?** O Hermes oficial usa 90. Nossas tarefas típicas (análise de dados, pesquisa web) consomem 15-30 turns. 90 é seguro mesmo para tarefas complexas com múltiplos subagentes, sem ser frouxo a ponto de permitir runaway.

---

## 6. Marketing Causal (MMM + Causal Inference)

### Stack

| Componente | Versão | Função |
|-----------|--------|--------|
| PyMC | 5.28.5 | Amostragem MCMC Bayesiana |
| PyMC-Marketing | 0.19.4 | MMM multidimensional (adstock + saturação) |
| CausalPy | 0.8.1 | Synthetic Control para quasi-experimentos |
| ArviZ | 0.x | Diagnóstico de convergência (R-hat, ESS) |

### Bridge: `tools/causal_bridge.py`

Venv isolado em `/opt/venvs/causal/` para não conflitar com dependências do Hermes.

**Métodos:**
- `mmm_train()` — Treina MMM com dados reais (CSV) ou sintéticos
- `mmm_analyze()` — Contribuições, saturação, parâmetros, ROAS
- `budget_optimize()` — Alocação ótima de budget entre canais
- `causal_analyze()` — Synthetic Control com Ridge regression

**Bug conhecido:** `cores=0` no PyMC (detecção de BLAS falha em VPS single-core). Contornado com `cores=1` no sampler_config.

### Datasets Públicos (5 preparados)

| Dataset | Fonte | Linhas | Canais | Uso |
|---------|-------|--------|--------|-----|
| Shenzhen MMM | Dados reais (China) | 374 sem. | 5 mídia + econômicos | Benchmark real |
| Observed MMM | deejayrusso | 156 sem. | TV + Search | Segundo benchmark |
| Meridian Style | Google Meridian (replicado) | 104 sem. | 4 canais | Tutorial |
| PyMC Tutorial | Tutorial oficial | 179 sem. | 2 canais | Validação (parâmetros conhecidos) |
| CausalPy SC | Sintético | 150 per. | 10 controles | Teste de Synthetic Control |

### Tutorial Interativo

`tutorial_causal.py` — guia passo a passo que:
1. Explica conceitos (adstock, saturação, R-hat)
2. Treina MMM e compara parâmetros recuperados vs verdadeiros
3. Mostra diagnóstico (R², resíduos)
4. Calcula ROAS por canal
5. Otimiza budget
6. Roda Synthetic Control
7. Propõe 5 desafios práticos

---

## 7. Crons Ativos

| Nome | Agenda | Função | Entrega |
|------|--------|--------|---------|
| Panorama Financeiro | Seg-Sex 19h | Relatório de indicadores financeiros (Selic, CDI, câmbio, ações) | Telegram |
| Curador de Skills | Dom 3h | Marca skills não usadas como stale, arquiva antigas, sugere merge | Relatório interno |
| Memory Consolidator | A cada 12h | Se memória >80%, faz merge de entradas relacionadas | Relatório interno |

---

## 8. Decisões de Arquitetura Comentadas

### LangGraph vs ReAct puro

**Escolha:** LangGraph com state graph.

**Por quê:** O Hermes oficial usa ReAct (think → act → observe). Para pipelines de dados (ex: "baixa dados → processa → treina modelo → gera relatório → envia"), um grafo de estados é mais natural. Cada node pode ser uma etapa distinta com seu próprio contexto, tratamento de erro e retry.

**Trade-off:** Mais complexidade de implementação. Para tarefas simples (ex: "pesquisa X na web"), ReAct é mais direto.

### Venv isolado para PyMC vs tudo no mesmo ambiente

**Escolha:** Venv separado (`/opt/venvs/causal/`).

**Por quê:** PyMC-Marketing 0.19.4+ tem dependências conflitantes com as bibliotecas do Hermes (especialmente `pytensor`). Manter isolado evita "dependency hell" e permite atualizar cada stack independentemente.

**Trade-off:** Overhead de ~1-2s por chamada (subprocess). Aceitável para tarefas que já levam minutos (treino MMM).

### Persistência de modelo em disco vs em memória

**Escolha:** Pickle em disco + metadados JSON.

**Por quê:** O modelo MMM treinado (~32MB) precisa sobreviver a restarts do Hermes. Salvar em disco permite carregar sob demanda (lazy loading) e compartilhar entre sessões.

**Trade-off:** Serialização/desserialização adiciona ~500ms. Modelos muito grandes (>100MB) exigiriam formato mais eficiente (Parquet + pesos separados).

### Curador determinístico vs com LLM

**Escolha:** Fase 1 determinística (sempre), Fase 2 com LLM (opcional).

**Por quê:** A decisão de "essa skill está velha?" é puramente temporal — não precisa de LLM. Já "essas duas skills são equivalentes?" exige compreensão semântica. Separar as fases minimiza custos de API.

**Trade-off:** Skills similares com nomes diferentes não são detectadas automaticamente. A Fase 2 (LLM) pode ser ativada manualmente quando necessário.

---

## 9. Métricas de Operação

| Métrica | Valor | Nota |
|---------|-------|------|
| Skills no catálogo | 59 | 15 categorias, 40 bundled |
| Memória usada (MEMORY.md) | 88% (3.107/3.500) | Consolidado manualmente |
| Tempo médio de resposta | 15-30s | Varia com complexidade |
| Custo médio por sessão | ~$0.05-0.20 | OpenRouter (gpt-4o-mini + Kimi) |
| Tarefas concluídas/semana | ~15-25 | Estimativa |
| Crons ativos | 3 | Financeiro, Curador, Memória |

---

## 10. Roadmap — Próximas Evoluções

**Prioridade alta:**
- Integrar bridge causal no LangGraph (node `causal` no `graph.py`)
- Adicionar experimentos controlados com geo-lift (expansão do CausalPy)
- Métricas de desempenho das skills (qual está sendo mais usada?)

**Prioridade média:**
- Dashboard web com status dos crons e bridges
- Testes automatizados para todas as bridges (pytest + CI)
- Cache de respostas do LLM para queries frequentes

**Prioridade baixa:**
- GEPA (evolução offline de prompts) — $2-10/rodada, só compensa com uso intensivo
- Knowledge graph como Tier 3 de memória
- Multi-agent paralelo para tarefas independentes

---

*Este documento descreve a implantação do Hermes Agent na 42c em julho de 2026. Para dúvidas ou sugestões, Bruno Moura — bruno@42c.work.*
