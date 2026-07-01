# Hermes Unified

**Multi-agent LangGraph orchestrator** — 19 bridges, 3-tier memory, auto-evolution, and marketing causal inference.

Built on top of [Hermes Agent](https://github.com/HermesAgent/hermes) (160K+ GitHub stars), adapted for digital media analytics, data pipelines, causal marketing (MMM + Synthetic Control), and task automation.

---

## Architecture

```
Entry Points: Telegram | CLI (main.py) | Crons (3)
     |
LangGraph Orchestrator (core/graph.py — 1.9K lines)
  planner → 14+ agent nodes → router → integrator
  + Headroom compression (46-92%)
  + Cache diskcache (TTL 30min-24h)
  + Fallback cascade (primary → heuristic → message)
  + Guardrails + Query Rewriting + Hard cap 90 turns
     |
19 Bridges:
  MiMo Code | Hyper-Extract | Web Scraper | Scraper Fallback
  Viz (charts/pptx) | Observer (watchers) | Reporter (PDF/HTML)
  Sheets | DV360 | TikTok | Social (X) | Vision Scout
  Financial BR | MCP Brasil (307 tools) | Research | Causal (MMM)
  Memory (SQLite FTS5) | Notifier | Campaign
     |
Auto-Evolution:
  Skill Curator (Sun 3h) | Auto-Skill Creator | Memory Consolidator (12h)
```

## Bridges Overview

| Bridge | Status | Purpose |
|--------|--------|---------|
| **MiMo Code** | ✅ Live | Code generation & refactoring |
| **Hyper-Extract** | ✅ Live | PDF → knowledge graphs |
| **Web Scraper** | ✅ Live | Firecrawl web scraping |
| **Scraper Fallback** | ⚡ Tool | HTTP fallback (requests+BS4) |
| **Viz** | ✅ Live | matplotlib, plotly, PowerPoint |
| **Observer** | ✅ Live | Cron watchers (price, content, health) |
| **Reporter** | ✅ Live | Professional PDF reports |
| **Financial BR** | ✅ Live | BCB SGS, brapi.dev, Tesouro Direto |
| **Research** | ✅ Live | Deep web research with citations |
| **Causal (MMM)** | ⚡ Tool | Bayesian MMM + Synthetic Control |
| **DV360** | ✅ Live (mock) | Google Display & Video 360 |
| **TikTok** | ✅ Live (mock) | TikTok Ads |
| **MCP Brasil** | ⚡ Tool | 307 Brazilian public data tools |
| **Memory** | ✅ Live | SQLite FTS5 session search |

## Memory System (3 Tiers)

- **Tier 1** — Always in context: MEMORY.md (3.5K chars) + USER.md (2K chars), auto-consolidated every 12h
- **Tier 2** — Searchable: SQLite FTS5 across all sessions
- **Tier 3** — Procedural: 59 skills (40 bundled + 19 custom), 27 categories

## Auto-Evolution

- **Skill Curator** — Stale detection (30d), archive (90d), snapshots before changes. Runs Sunday 3h
- **Auto-Skill Creator** — Suggests skills after 5+ tool calls on same task
- **Memory Consolidator** — Merges related entries when memory >80% full
- **Hard Cap** — 90 turns max to prevent runaway costs

## Infrastructure

| Component | Detail |
|-----------|--------|
| **VPS** | Hostinger Ubuntu 22.04, 2 vCPUs, 4GB RAM |
| **Python** | 3.13 (main) + 3.11 (causal venv) |
| **LLM** | OpenRouter (Kimi K2.5, DeepSeek V4, GPT-4o-mini) |
| **Orchestration** | LangGraph StateGraph |
| **Storage** | SQLite FTS5 + JSON + Pickle |
| **Node.js** | v22.23.1 (Firecrawl CLI) |

## Quick Start

```bash
# Run the orchestrator
python main.py "Your objective" --files document.pdf

# Dry-run skill curator
python tools/skill_curator.py

# Consolidate memory
python tools/memory_consolidator.py

# Run MMM tutorial
python tools/causal_bridge.py tutorial
```

---

**Author:** Bruno Moura (42c) — bruno@42c.work  
**License:** MIT  
**Based on:** Hermes Agent (open-source, 160K+ GitHub stars)
