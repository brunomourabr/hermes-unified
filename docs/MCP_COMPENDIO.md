# MCP Servers Compendium — Hermes Unified

**Data:** Junho 2026  
**Fontes:** awesome-mcp-servers (90k★), best-of-mcp-servers (400 servers), mcpservers.org, mcp.directory (2k+ servers), glama.ai, pulsemcp.com (20k+ servers)  
**Total identificado:** 400+ servidores curados, 20k+ em agregadores

---

## 1. CLOUD & INFRA

| MCP | Instalação | Tools | Custo | Descrição |
|-----|-----------|-------|-------|-----------|
| **AWS (awslabs)** | `uvx mcp-proxy-for-aws@latest` | 15+ servers | Grátis | IaC, EKS, ECS, Lambda, DynamoDB, Bedrock, Athena, S3 |
| **Cloudflare** | Remote HTTP | 13 servers | Free tier | Workers, KV, R2, D1, AI Gateway |
| **Google Cloud (genai-toolbox)** | `docker pull` | Multi-DB | Grátis | Cloud SQL, Spanner, AlloyDB (13.3k★) |
| **Google Maps** | `npx` | Directions, places | Grátis | Oficial Google (3.4k★) |
| **Azure All** | Remote HTTP | API Management | Preview | Oficial Microsoft (1.2k★) |
| **Kubernetes (containers)** | `docker pull` | kubectl, helm | Grátis | K8s + OpenShift (1.7k★) |
| **Docker** | `npx` | 50+ tools | Grátis | Containers, images, volumes |
| **Terraform (Hashicorp)** | `npx` | Docs, modules | Grátis | Oficial (1.4k★) |
| **Railway** | Remote HTTP | Deploy | Grátis | Oficial (1k★) |
| **Netlify** | Remote HTTP | Deploy | Grátis | Oficial (1.1k★) |
| **Firebase** | Remote HTTP | Firebase | Grátis | Oficial (4.4k★) |
| **Modal** | Remote HTTP | GPU serverless | Grátis | Serverless GPU (2.6k★) |

## 2. BANCOS DE DADOS

| MCP | Instalação | Tools | Custo |
|-----|-----------|-------|-------|
| **PostgreSQL (official)** | `npx @modelcontextprotocol/server-postgres` | Schema, queries | Grátis |
| **Postgres (crystaldba)** | `npx` | Performance, dev/ops (3k★) | Grátis |
| **SQLite (official)** | `npx @modelcontextprotocol/server-sqlite` | Full SQLite | Grátis |
| **MySQL (benborla)** | `npm install` | MySQL (1.9k★) | Grátis |
| **GenAI Toolbox (Google)** | `docker pull` | Multi-DB (13.3k★) | Grátis |
| **Redis (official)** | Remote HTTP | Key-value (540★) | Grátis |
| **Neo4j** | Remote HTTP | Graph queries (970★) | Grátis |
| **MongoDB Lens** | Remote HTTP | Read operations | Grátis |
| **Supabase** | Remote HTTP | SQL, auth, storage (2.7k★) | Grátis |
| **Snowflake** | Remote HTTP | SQL, Cortex (official) | Grátis |
| **ClickHouse** | Remote HTTP | Official ClickHouse | Grátis |
| **Qdrant** | Remote HTTP | Vector search | Grátis |
| **Chroma** | Remote HTTP | Vector database | Grátis |

## 3. DESENVOLVIMENTO

| MCP | Instalação | Tools | Custo |
|-----|-----------|-------|-------|
| **GitHub (official)** | `npx @github/github-mcp-server` | 54+ tools | Grátis |
| **Git (official)** | `uvx mcp-server-git` | Git ops | Grátis |
| **GitLab (official)** | Remote HTTP | GitLab | Grátis |
| **Linear (official)** | Remote HTTP (OAuth) | Issues, projects | Grátis |
| **Jira + Confluence (Atlassian)** | Remote HTTP (SSE) | 25 tools | Grátis |
| **Notion (official v2)** | `npx` ou remote HTTP | Full Notion | Free tier |
| **Context7 (upstash)** | Remote HTTP | Docs em prompts (58k★) | Grátis |
| **Codebase Memory (DeusData)** | Remote HTTP | 159 linguagens (13k★) | Grátis |
| **Magic MCP (21st-dev)** | Remote HTTP | UI components (5.2k★) | Grátis |
| **Figma Context** | Remote HTTP | Figma data (15k★) | Grátis |
| **JetBrains mcpProxy** | Remote HTTP | IDE integration | Grátis |

## 4. MÍDIA & CONTEÚDO

| MCP | Instalação | Tools | Custo |
|-----|-----------|-------|-------|
| **YouTube (anaisbetts)** | `npm install` | Transcripts (490★) | Grátis |
| **YouTube Transcript (jkawamoto)** | `pip install` | Pagination 50k+ chars | Grátis |
| **Apify MCP** | Remote HTTP | 2k+ Actors (1.4k★) | Free tier |
| **Firecrawl MCP** | `npx` | 13+ tools (6.5k★) | Free tier |
| **Browserbase** | Remote HTTP | Cloud browser (3.4k★) | Pago |
| **Bright Data** | Remote HTTP | Enterprise scraping | Pago |

## 5. COMUNICAÇÃO

| MCP | Instalação | Tools | Custo |
|-----|-----------|-------|-------|
| **Slack (official)** | Remote HTTP (OAuth) | Messages, threads (1.7k★) | Grátis |
| **Discord (Omnicord)** | Remote HTTP | 148 tools | Grátis |
| **Telegram (chigwell)** | Remote HTTP | Messages, bots (1.2k★) | Grátis |
| **Email (codefuturist)** | Remote HTTP | 42 tools, IMAP/SMTP | Grátis |
| **Nylas CLI** | Remote HTTP | 16 tools, multi-account | Grátis |
| **Spix (voice)** | Remote HTTP | 26 tools, phone number | Pago |
| **Infobip** | Remote HTTP | SMS, voice, email, WhatsApp | Pago |
| **MS 365 (Softeria)** | Remote HTTP | 24 tools, Graph API (790★) | Grátis |

## 6. IA / ML

| MCP | Instalação | Tools | Custo |
|-----|-----------|-------|-------|
| **HuggingFace (official)** | `pip install huggingface-mcp-server` | Models, datasets, Spaces | Grátis |
| **OpenAI** | Nativo ChatGPT (Set/2025) | Remote | Pago |
| **Anthropic** | Nativo Claude | Remote | Pago |
| **Google Gemini** | Via GenAI Toolbox | Remote | Grátis |
| **Blockrun** | Remote HTTP | 30+ models, x402 | Micro-pagamento |

## 7. DADOS & ANALYTICS

| MCP | Instalação | Tools | Custo |
|-----|-----------|-------|-------|
| **Metabase (official)** | Remote HTTP | Search, query, semantic layer | Grátis |
| **Superset (official)** | Remote HTTP | 20 tools | Grátis |
| **Grafana (official)** | Remote HTTP | Dashboards, metrics | Grátis |
| **Sentry (official)** | Remote HTTP | Errors, stack traces | Grátis |

## 8. PRODUTIVIDADE

| MCP | Instalação | Tools | Custo |
|-----|-----------|-------|-------|
| **Google Workspace (official)** | `npx` ou remote HTTP | Gmail, Calendar, Drive, Docs, Sheets | Grátis |
| **MS 365 Graph API** | Remote HTTP | Outlook, Calendar, Teams, Planner | Grátis |
| **Obsidian** | Plugin community | Local knowledge base | Grátis |
| **Notion (official)** | Remote HTTP | Full Notion API | Free tier |
| **Cal.com (official)** | Remote HTTP | Scheduling | Grátis |

## 9. FINANÇAS & PAGAMENTOS

| MCP | Instalação | Tools | Custo |
|-----|-----------|-------|-------|
| **Stripe (official)** | Remote HTTP (mcp.stripe.com) | 27 tools | Pay-per-call |
| **Mercado Pago (official)** | Remote HTTP | Payments, refunds | Grátis |
| **Polygon.io** | Remote HTTP | Stock market data | Pago |
| **Alpha Vantage** | Remote HTTP | Stocks, forex, crypto | Free tier |
| **Base (Coinbase)** | Remote HTTP | Wallet, DeFi, smart contracts | Grátis |
| **Alchemy** | Remote HTTP | Blockchain APIs | Free tier |

## 10. PESQUISA & CONHECIMENTO

| MCP | Instalação | Tools | Custo |
|-----|-----------|-------|-------|
| **Exa Search** | Remote HTTP (mcp.exa.ai) | Web + code search (4.6k★) | Free tier |
| **Brave Search (official)** | `npx @modelcontextprotocol/server-brave-search` | Privacy search | Free tier |
| **Perplexity** | Remote HTTP | Web + academic research | Pago |
| **DuckDuckGo** | Remote HTTP | No-auth search | Grátis |
| **arXiv** | `pip install arxiv-mcp-server` | Academic papers | Grátis |
| **Wikipedia** | Remote HTTP | Articles, summaries | Grátis |
| **PubMed** | Remote HTTP | Medical research | Grátis |
| **Memory (official)** | `npx @modelcontextprotocol/server-memory` | Knowledge graph | Grátis |
| **Cognee** | Remote HTTP | 30+ data sources (20k★) | Grátis |
| **Fetch (official)** | `npx @modelcontextprotocol/server-fetch` | Web content | Grátis |
| **Filesystem (official)** | `npx @modelcontextprotocol/server-filesystem` | File ops | Grátis |

## 11. MCPs NACIONAIS (BRASIL)

| MCP | Instalação | Tools | Custo |
|-----|-----------|-------|-------|
| **MCP-Brasil** | `pip install mcp-brasil` | 533 tools, 70 fontes | Grátis |
| **bcb-br-mcp** | `npx -y bcb-br-mcp` | 8 tools (BCB) | Grátis |
| **Tesouro Direto MCP** | `npx -y tesouro-direto-mcp` | 3 tools | Grátis |
| **brapi.dev MCP** | URL direta | 56 tools | Free tier |
| **Mercado Pago (official)** | Remote HTTP | Pix, payments | Grátis |
| **MCP Dev Latam** | Remote HTTP | Pix, NF-e, banking | Grátis |

## 12. REFERÊNCIS (Official modelcontextprotocol)

| Server | Instalação | Descrição |
|--------|-----------|-----------|
| **Everything** | `npx @modelcontextprotocol/server-everything` | Test server |
| **Fetch** | `npx @modelcontextprotocol/server-fetch` | Web content |
| **Filesystem** | `npx @modelcontextprotocol/server-filesystem` | File ops |
| **Git** | `uvx mcp-server-git` | Git |
| **Memory** | `npx @modelcontextprotocol/server-memory` | Knowledge graph |
| **Sequential Thinking** | `npx @modelcontextprotocol/server-sequential-thinking` | Problem-solving |
| **Time** | `npx @modelcontextprotocol/server-time` | Time/timezone |
| **PostgreSQL** | `npx @modelcontextprotocol/server-postgres` | Postgres |
| **SQLite** | `npx @modelcontextprotocol/server-sqlite` | SQLite |
| **Brave Search** | `npx @modelcontextprotocol/server-brave-search` | Search |

## 13. LISTAS CURADAS (Fontes primárias)

1. **punkpeye/awesome-mcp-servers** — 90k★, 49+ categorias, 2k+ contribuidores
2. **tolkonepiu/best-of-mcp-servers** — 400 servers, 34 categorias, scoring semanal
3. **mcpservers.org** — Diretório curado com featured/official
4. **mcp.directory** — 2k+ servidores, 14+ categorias
5. **glama.ai/mcp/servers** — Marketplace buscável
6. **pulsemcp.com** — 20k+ servidores atualizados diariamente
7. **mcp.so** — Coleção massiva
8. **Docker MCP Catalog** — 270+ MCPs containerizados no hub.docker.com

---

## Como Integrar no Hermes Unified

### Método 1: Config no graph.py (recomendado para MCPs locais)
```python
from core.mcp_bridge import MCPBridge
mcp = MCPBridge()
tools = mcp.get_tools("github", "postgres", "slack")
```

### Método 2: MCP Proxy (recomendado para MCPs remotos)
```bash
headroom proxy --mcp-server postgres://localhost:5432/db
headroom proxy --mcp-server https://mcp.github.com
```

### Método 3: Bridge específica (para MCPs nacionais)
Cada MCP vira uma bridge no Hermes, seguindo o padrão existente:
```python
# tools/mcp_brasil_bridge.py
class MCPBrasilBridge:
    def get_selic(self): ...
    def get_ipca(self): ...
    def get_cotacao(self, ticker): ...
```
