"""
Master Graph - Orquestrador LangGraph unificado
Integra MiMo (código), Hyper-Extract (conhecimento) e Web Tools
"""
import os

# Hard cap de turns para evitar loops infinitos e custos excessivos
MAX_TURNS = 90

import json
from typing import TypedDict, Dict, List, Optional, Any, Annotated, Literal
import operator

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from tools.mimo_bridge import MiMoBridge, get_mimo_bridge
from tools.he_bridge import HyperExtractBridge, get_he_bridge
from tools.scraper_bridge import ScraperBridge, get_scraper_bridge
from tools.scraper_fallback import ScraperFallback, get_scraper_fallback
from tools.viz_bridge import VizBridge, get_viz_bridge
from tools.observer_bridge import ObserverBridge, get_observer_bridge
from tools.vision_scout_bridge import VisionScoutBridge, get_vision_scout_bridge
from tools.sheets_bridge import SheetsBridge, get_sheets_bridge
from tools.reporter_bridge import ReporterBridge, get_reporter_bridge
from tools.dv360_bridge import DV360Bridge, get_dv360_bridge
from tools.tiktok_bridge import TikTokBridge, get_tiktok_bridge
from tools.research_bridge import ResearchBridge, get_research_bridge
from tools.financial_br_bridge import FinancialBridgeBR, get_financial_bridge
from tools.mcp_brasil_bridge import MCPBrasilDirectBridge, get_mcp_brasil_bridge
from tools.fallback import with_cascade_fallback, safe_execute
from tools.cache import web_get, web_set, bridge_get, bridge_set, llm_get, llm_set
from tools.telemetry import telemetry
from config import get_api_key, save_api_key
from core.ontology import get_ontology
from core.semantic_router import get_semantic_router

# =============================================
# CONFIGURACAO
# =============================================

DEEPSEEK_API_KEY = get_api_key("DEEPSEEK_API_KEY")
OPENROUTER_API_KEY = get_api_key("OPENROUTER_API_KEY")

HEADROOM_PROXY = os.environ.get("HEADROOM_PROXY_URL", "http://127.0.0.1:8787/v1")
HEADROOM_AVAILABLE = False
try:
    from headroom import compress as headroom_compress
    HEADROOM_AVAILABLE = True
except ImportError:
    headroom_compress = None

_llm = None

def get_llm():
    global _llm
    if _llm is not None:
        return _llm

    # Busca modelo configurado (env var ou default V4-Pro)
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")

    # Tenta DeepSeek direto primeiro
    if DEEPSEEK_API_KEY:
        _llm = ChatOpenAI(
            temperature=0.3,
            model=model,
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com/v1"
        )
        print("   LLM: DeepSeek " + model)
        return _llm

    # Fallback: OpenRouter gpt-4o-mini
    if OPENROUTER_API_KEY:
        _llm = ChatOpenAI(
            temperature=0.3,
            model="openai/gpt-4o-mini",
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        )
        print("   LLM: OpenRouter gpt-4o-mini")
        return _llm

    raise ValueError("Nenhuma chave de LLM configurada!")


def compress_context(context: dict) -> dict:
    """
    Comprime strings longas no contexto usando Headroom.
    Reduz 46-92% tokens mantendo acurácia.
    Usado no integrator_node antes de passar dados pro LLM.
    """
    if not HEADROOM_AVAILABLE or not context:
        return context

    import json
    compressed = {}

    for key, value in context.items():
        if isinstance(value, str) and len(value) > 2000:
            try:
                from headroom import compress
                # Headroom comprime tool_outputs no formato de mensagens
                msgs = [
                    {"role": "system", "content": "You are a data analyst assistant."},
                    {"role": "user", "content": "Analyze the tool data below."},
                    {"role": "tool", "tool_call_id": "ctx_001", "content": value},
                ]
                result = compress(msgs, optimize=True)
                # Pega o conteudo comprimido da mensagem tool
                for m in result.messages:
                    if m["role"] == "tool":
                        compressed[key] = m["content"]
                        break
                else:
                    compressed[key] = value
            except Exception as e:
                compressed[key] = value
        else:
            compressed[key] = value

    return compressed

# ESTADOS
# ==========================

class AgentState(TypedDict):
    """Estado global do sistema unificado."""
    task_id: str
    objective: str
    context: Dict[str, Any]
    current_agent: str
    artifacts: Annotated[List[str], operator.add]
    messages: Annotated[List[HumanMessage], operator.add]
    input_files: List[str]
    output_files: List[str]
    iteration: int
    max_iterations: int
    completed: bool
    success: bool
    error: Optional[str]
    next_action: Optional[str]
    turn_count: int  # Contador de turns para hard cap
    agent_sequence: List[str]  # Sequencia multi-passo de bridges
    sequence_index: int  # Indice atual na sequencia


# ==========================
# FALLBACK MAP — bridges com fallback runtime
# ==========================

FALLBACK_MAP = {
    "research": ["scraper", "web"],       # RESEARCH falhou -> tenta SCRAPE -> WEB
    "scraper": ["web"],                   # SCRAPE falhou -> tenta WEB
    "web": [],                            # WEB sem fallback
    "finance": [],                        # Finance sem fallback
    "codex": [],                          # Codex sem fallback
    "knowledge": [],                      # Knowledge sem fallback
    "viz": [],                            # Viz sem fallback
    "reporter": [],                       # Reporter sem fallback
    "observer": [],                       # Observer sem fallback
    "vision_scout": [],                   # Vision sem fallback
    "sheets": [],                         # Sheets sem fallback
    "dv360": [],                          # DV360 sem fallback
    "tiktok": [],                         # TikTok sem fallback
    "mcp_brasil": [],                     # MCP Brasil sem fallback
}

# Sequencias válidas: bridges que PODEM aparecer juntas numa multi-passo
# Bloqueia sequencias sem sentido como CODE-RESEARCH
VALID_SEQUENCES = {
    "research": {"viz", "reporter", "knowledge", "web", "scraper"},
    "scraper": {"viz", "reporter", "knowledge", "research", "web"},
    "web": {"viz", "reporter", "research", "scraper"},
    "finance": {"viz", "reporter"},
    "knowledge": {"viz", "reporter"},
    "codex": set(),         # Codex nunca combina com outras
    "viz": {"reporter"},    # Viz so combina com reporter
    "reporter": set(),      # Reporter nunca tem nada depois
    "dv360": {"viz", "reporter"},
    "tiktok": {"viz", "reporter"},
    "observer": set(),
    "vision_scout": set(),
    "sheets": set(),
    "mcp_brasil": set(),
}


# ==========================
# HELPER: Hard cap de turns
# ==========================

def _check_turn_limit(state: AgentState, node_name: str) -> Optional[dict]:
    """Verifica se o limite de turns foi atingido. Se sim, retorna um dict de erro."""
    turn_count = state.get("turn_count", 0)
    if turn_count >= MAX_TURNS:
        msg = f"Limite de {MAX_TURNS} turns atingido. Tarefa interrompida para evitar custos excessivos."
        print(f"   [{node_name}] {msg}")
        return {
            "error": msg,
            "completed": True,
            "success": False,
            "messages": [HumanMessage(content=f"TURN_LIMIT: {msg}")],
        }
    return None


def _increment_turn(state: AgentState) -> int:
    """Retorna o turn_count incrementado."""
    return state.get("turn_count", 0) + 1


# ==========================
# FERRAMENTAS LLM
# ==========================

def _check_guardrail(objective: str) -> tuple:
    """Guardrail: valida se a query está dentro do escopo do sistema.

    Bloqueia queries que são:
    - Conversacionais simples (oi, tudo bem?)
    - Spam ou conteúdo ofensivo
    - Fora do domínio de trabalho (mídia, dados, código, finanças, pesquisa)

    Returns: (mensagem, aprovado)
    """
    lower = objective.lower().strip()

    # Listas de rejeição
    greetings = ["oi", "ola", "olá", "hey", "hello", "hi", "bom dia", "boa tarde",
                 "boa noite", "tudo bem", "como vai", "td bem", "blz", "falae"]
    spam = ["ganhe dinheiro", "clique aqui", "promoção imperdível", "oferta"]
    too_short = len(objective) < 4

    if too_short:
        return "Query muito curta. Por favor, seja mais específico.", False

    if any(g in lower for g in greetings) and len(objective) < 20:
        return "Olá! Como posso ajudar? Por favor, me diga o que precisa.", False

    for s in spam:
        if s in lower:
            return "Query bloqueada pelo guardrail (conteúdo não permitido).", False

    return None, True


_REWRITE_PROMPT = """You are a query rewriter for a web search engine.
Given the user's question, rewrite it to be more effective for web search.

Rules:
1. Add relevant keywords that help find information
2. Remove conversational filler words
3. Keep the core intent
4. Output ONLY the rewritten query, nothing else

Original: {query}
Rewritten:"""


def _rewrite_query(query: str) -> str:
    """Reescreve query para melhorar resultados de busca.
    Usa o LLM para expandir/refinar a query.
    Fallback: retorna a query original.
    """
    if len(query) < 10:
        return query

    try:
        cached = llm_get(query, "rewrite_query")
        if cached:
            return cached

        llm = get_llm()
        prompt = _REWRITE_PROMPT.format(query=query)
        response = llm.invoke([HumanMessage(content=prompt)])
        rewritten = response.content.strip().strip('"\'')
        llm_set(query, rewritten, "rewrite_query")
        return rewritten if rewritten else query
    except Exception as e:
        print(f"   Query rewrite error: {e}")
        return query


def classify_task(objective: str) -> str:
    """Classifica a tarefa para decidir qual agente acionar."""
    # Cache: mesma objective → mesma classificação
    cached = llm_get(objective, "classify_task")
    if cached:
        return cached

    llm = get_llm()
    prompt = f"""Classifique a tarefa abaixo em UMA das categorias principais.
Mas para cada categoria, pense: se essa bridge falhar, qual seria o fallback natural?

CATEGORIAS (com fallback):

RESEARCH (pesquisa aprofundada com citacoes)
  → Se falhar, tente SCRAPE (extrair de site especifico)
  → Se ainda falhar, tente WEB (busca simples na web)

SCRAPE (extrair conteudo de sites especificos)
  → Se falhar, tente WEB (busca simples na web)

KNOWLEDGE (extrair informacoes de PDFs/documentos)
  → Sem fallback direto (bridge unica)

CODE (gerar/modificar/refatorar codigo)
  → Sem fallback direto (bridge unica)

VIZ (graficos, dashboards, charts)
  → Sem fallback direto (bridge unica)

REPORT (relatorios PDF, documentacao estruturada)
  → Se vier de dados coletados, RODE RESEARCH/SCRAPE primeiro

OBSERVER (monitoramento continuo, watchers)
  → Sem fallback direto (bridge unica)

VISION (analise de imagens)
  → Sem fallback direto (bridge unica)

SHEETS (planilhas, tabelas organizadas)
  → Sem fallback direto (bridge unica)

DV360 (Google Display & Video 360)
  → Sem fallback direto (bridge unica)

TIKTOK (TikTok Ads)
  → Sem fallback direto (bridge unica)

FINANCE (dados financeiros, acoes, indicadores)
  → Sem fallback direto (bridge unica)

MCP_BRASIL (dados publicos brasileiros)
  → Sem fallback direto (bridge unica)

WEB (busca simples na internet)
  → Sem fallback direto (bridge unica)

MULTI (envolve multiplas categorias)
  → Liste as bridges em ordem: ex: RESEARCH-VIZ-REPORT

Tarefa: {objective}

Responda APENAS com o nome da categoria principal e, se for MULTI, a sequencia separada por virgula.
Exemplos:
  "Pesquise sobre IA" -> RESEARCH
  "Pesquise sobre IA e gere um grafico" -> RESEARCH-VIZ
  "Crie um relatorio com dados financeiros" -> FINANCE-REPORT
  "Pesquise MMM e crie um script" -> RESEARCH-CODE
  "Gere um grafico de vendas" -> VIZ
  "Crie uma API Flask" -> CODE"""

    response = llm.invoke([HumanMessage(content=prompt)])
    result = response.content.strip().upper()
    llm_set(objective, result, "classify_task")
    return result


def create_plan(objective: str, category: str, iteration: int = 0):
    """Cria um plano de execucao."""
    llm = get_llm()
    prompt = f"""Crie um plano de execucao para a tarefa abaixo.

Categoria: {category}
Objetivo: {objective}
Iteracao: {iteration + 1}

Responda com uma lista numerada de 3-5 passos. Cada passo deve ser uma acao concreta.
Exemplo:
1. Extrair documentacao do PDF
2. Gerar codigo baseado na documentacao
3. Validar o codigo gerado"""

    response = llm.invoke([HumanMessage(content=prompt)])
    steps = [s.strip() for s in response.content.split('\n') if s.strip() and s[0].isdigit()]
    return steps


# ==========================
# NOS DO GRAFO
# ==========================

def planner_node(state: AgentState) -> dict:
    """No de planejamento: analisa e decide o que fazer.
    Usa o Semantic Router para mapear a query para conceitos da ontologia,
    entao usa o LLM para classificar e planejar com esse contexto extra.
    Inclui guardrail para filtrar queries fora de escopo.
    """
    # Hard cap de turns
    turn_error = _check_turn_limit(state, "PLANNER")
    if turn_error:
        return {**turn_error, "turn_count": _increment_turn(state)}

    print(f"\n[PLANNER] Analisando: {state['objective'][:80]}...")

    # ====================================================================
    # GUARDRAIL — valida escopo da query antes de processar
    # ====================================================================
    guardrail_result, guardrail_ok = _check_guardrail(state["objective"])
    if not guardrail_ok:
        return {
            "context": {
                **state.get("context", {}),
                "guardrail_message": guardrail_result,
            },
            "current_agent": "integrator",
            "completed": False,
            "iteration": state.get("iteration", 0) + 1,
            "messages": [HumanMessage(content=f"GUARDRAIL: {guardrail_result}")],
            "last_agent": "planner",
            "error": guardrail_result,
            "turn_count": _increment_turn(state),
        }

    # ====================================================================
    # PASSO 1: Semantic Router — mapeia query para ontologia
    # ====================================================================
    router = get_semantic_router()
    semantic_analysis = router.analyze(state["objective"])
    semantic_context = semantic_analysis.get("semantic_context", {})
    semantic_annotations = semantic_context.get("semantic_annotations", [])

    print(f"   Router: intencao={semantic_analysis['primary_intent']}, "
          f"entidades={semantic_analysis['entities']}")

    if semantic_annotations:
        for ann in semantic_annotations[:3]:
            print(f"   [ONTOLOGIA] {ann}")

    # ====================================================================
    # PASSO 2: LLM classifica a tarefa (com contexto semântico extra)
    # ====================================================================
    category = classify_task(state["objective"])
    steps = create_plan(state["objective"], category, state.get("iteration", 0))

    print(f"   Categoria LLM: {category}")
    print(f"   Passos: {len(steps)}")

    # Parseia categoria: pode ser "RESEARCH" simples ou "RESEARCH-VIZ-REPORT" (multi-passo)
    category_parts = category.replace("-", ",").split(",")
    category_primary = category_parts[0].strip() if category_parts else "WEB"

    # Se tiver multiplas bridges separadas por virgula/hifen, monta sequencia
    agent_sequence = []
    for part in category_parts:
        part = part.strip()
        agent_map = {
            "CODE": "codex", "KNOWLEDGE": "knowledge", "WEB": "web",
            "SCRAPE": "scraper", "VIZ": "viz", "OBSERVER": "observer",
            "VISION": "vision_scout", "SHEETS": "sheets", "REPORT": "reporter",
            "DV360": "dv360", "TIKTOK": "tiktok", "RESEARCH": "research",
            "FINANCE": "finance", "MCP_BRASIL": "mcp_brasil",
        }
        mapped = agent_map.get(part)
        if mapped and mapped not in agent_sequence:
            agent_sequence.append(mapped)

    # VALIDAÇÃO DE SEQUENCIA — impede combinacoes invalidas
    if len(agent_sequence) > 1:
        validated = [agent_sequence[0]]
        for i in range(1, len(agent_sequence)):
            prev = validated[-1]
            next_br = agent_sequence[i]
            allowed = VALID_SEQUENCES.get(prev, set())
            if next_br in allowed:
                validated.append(next_br)
            else:
                print(f"   ⚠ Sequencia invalida: {prev} -> {next_br}. Removendo {next_br} da sequencia.")
        agent_sequence = validated

    print(f"   Sequencia bridges: {agent_sequence if agent_sequence else 'simples'}")

    # ====================================================================
    # PASSO 3: Decide o próximo agente
    # Usa semantic_router como primário, fallback para LLM
    # Se for multi-passo (agent_sequence), usa o primeiro da fila
    # ====================================================================
    semantic_agent = router.get_agent_for_query(state["objective"])

    # Mapa do semantic router para nomes do grafo
    semantic_to_graph = {
        "dv360": "dv360",
        "tiktok": "tiktok",
        "research": "research",
        "reporter": "reporter",
        "viz": "viz",
        "sheets": "sheets",
        "knowledge": "knowledge",
        "observer": "observer",
        "codex": "codex",
        "web": "web",
        "scraper": "scraper",
        "finance": "finance",
        "mcp_brasil": "mcp_brasil",
    }

    # Se tiver sequencia multi-passo, usa o primeiro da lista
    if agent_sequence:
        next_agent = agent_sequence[0]
        sequence_index = 0
        print(f"   Proximo agente (multi-passo seq 0/{len(agent_sequence)-1}): {next_agent}")
    elif semantic_agent != "web":
        next_agent = semantic_to_graph.get(semantic_agent, "web")
        agent_sequence = [next_agent]
        sequence_index = 0
        print(f"   Proximo agente (semantic router): {next_agent}")
    else:
        # Fallback para classificação LLM
        next_agent = "codex" if category_primary in ["CODE", "MULTI"] else (
            "knowledge" if category_primary == "KNOWLEDGE" else (
                "scraper" if category_primary == "SCRAPE" else (
                    "viz" if category_primary == "VIZ" else (
                        "observer" if category_primary == "OBSERVER" else (
                            "vision_scout" if category_primary == "VISION" else (
                                "sheets" if category_primary == "SHEETS" else (
                                    "reporter" if category_primary == "REPORT" else (
                                        "dv360" if category_primary == "DV360" else (
                                            "research" if category_primary == "RESEARCH" else
                                            "tiktok" if category_primary == "TIKTOK" else
                                            "finance" if category_primary == "FINANCE" else
                                            "mcp_brasil" if category_primary == "MCP_BRASIL" else "web"
                                        )
                                    )
                                )
                            )
                        )
                    )
                )
            )
        )
        agent_sequence = [next_agent]
        sequence_index = 0
        print(f"   Proximo agente (LLM fallback): {next_agent}")

    return {
        "context": {
            **state.get("context", {}),
            "category": category_primary,
            "plan": steps,
            "current_step": 0,
            "semantic_analysis": {
                "intent": semantic_analysis.get("primary_intent"),
                "entities": semantic_analysis.get("entities"),
                "bridges": semantic_analysis.get("bridges"),
                "disambiguations": semantic_analysis.get("disambiguations"),
                "constraints": semantic_analysis.get("constraints"),
                "annotations": semantic_annotations,
            }
        },
        "current_agent": next_agent,
        "agent_sequence": agent_sequence,
        "sequence_index": sequence_index,
        "messages": [HumanMessage(content=f"Plano criado: {len(steps)} passos, "
                                          f"sequencia={agent_sequence}, "
                                          f"entidades={semantic_analysis['entities']}")],
        "turn_count": _increment_turn(state),
    }


def codex_node(state: AgentState) -> dict:
    """No de codigo: usa MiMo Bridge para gerar/refatorar codigo."""
    print(f"\n[CODEX] Executando tarefa de codigo...")

    mimo = get_mimo_bridge()
    objective = state["objective"]
    context = state.get("context", {})

    if state.get("input_files"):
        for f in state["input_files"]:
            if os.path.exists(f) and f.endswith('.py'):
                print(f"   Refatorando: {f}")
                content, success, msg = mimo.refactor_code(f, objective)
                if success:
                    state["output_files"].append(f)
                return {
                    "messages": [HumanMessage(content=f"CODEX: {msg}")],
                    "artifacts": [f"{f} (refatorado)" if success else f"{f} (falha)"]
                }

    spec = context.get("specification", objective)
    content, success, msg = mimo.generate_code(spec)

    print(f"   Resultado: {'OK' if success else 'FALHA'} {msg}")

    return {
        "messages": [HumanMessage(content=f"CODEX: {msg}")],
        "artifacts": [f"codigo_gerado ({msg})"] if success else [],
        "success": success,
        "error": None if success else msg,
        "last_agent": "codex"
    }


def knowledge_node(state: AgentState) -> dict:
    """No de conhecimento: usa Hyper-Extract Bridge."""
    print(f"\n[KNOWLEDGE] Processando documentos...")

    he = get_he_bridge()
    objective = state["objective"]

    if state.get("input_files"):
        for pdf_path in state["input_files"]:
            if os.path.exists(pdf_path) and pdf_path.endswith('.pdf'):
                project_id = state.get("task_id", "default")
                print(f"   Extraindo: {pdf_path}")

                graph, success, msg = he.extract_from_pdf(pdf_path, project_id)

                if success:
                    summary = he.graph_summary(project_id)
                    print(f"   Grafo: {summary.get('total_nodes', 0)} nos, {summary.get('total_edges', 0)} arestas")

                    return {
                        "context": {
                            **state.get("context", {}),
                            "knowledge_graph": graph,
                            "graph_summary": summary
                        },
                        "messages": [HumanMessage(content=f"KNOWLEDGE: {msg}")],
                        "artifacts": [f"grafo_{project_id} ({summary.get('total_nodes', 0)} nos)"],
                        "output_files": [f"{he.output_base}/{project_id}"],
                        "last_agent": "knowledge"
                    }

    projects = he.get_available_projects()
    if projects:
        results, success, msg = he.search_graph(projects[0], objective)
        return {
            "messages": [HumanMessage(content=f"KNOWLEDGE: {results}")],
            "artifacts": [f"consulta: {objective[:50]}..."]
        }

    return {
        "messages": [HumanMessage(content="KNOWLEDGE: Nenhum documento para processar")],
        "error": "Nenhum documento de entrada"
    }
def web_node(state: AgentState) -> dict:
    """No web: pesquisa na internet usando Scraper Bridge.
    Com cache de resultados (diskcache, TTL 1h).
    """
    print(f"\n[WEB] Pesquisando...")

    objective = state["objective"]

    # Cache check
    cached = web_get(f"web_search:{objective}")
    if cached is not None:
        print(f"   Cache hit: {len(cached)} resultados")
        return {
            "context": {
                **state.get("context", {}),
                "web_results": cached,
                "_cache_hit": True,
            },
            "messages": [HumanMessage(content=f"WEB: {len(cached)} resultados (cache)")],
            "artifacts": [f"web_search: {len(cached)} links (cache)"],
            "success": True,
            "last_agent": "web"
        }

    try:
        from tools.scraper_bridge import get_scraper_bridge
        scraper = get_scraper_bridge()
        results, success, msg = scraper.search_web(objective, max_results=5)

        if success and results:
            print(f"   {len(results)} resultados encontrados")
            web_set(f"web_search:{objective}", results)
            return {
                "context": {
                    **state.get("context", {}),
                    "web_results": results
                },
                "messages": [HumanMessage(content=f"WEB: {len(results)} resultados")],
                "artifacts": [f"web_search: encontrados {len(results)} links"],
                "success": True,
                "last_agent": "web"
            }

        # Query Rewriting — se busca falhou, tenta reescrever
        print(f"   Busca sem resultados, tentando query rewrite...")
        rewritten = _rewrite_query(objective)
        if rewritten and rewritten != objective:
            print(f"   Query reescrita: {rewritten[:80]}...")
            results, success, msg = scraper.search_web(rewritten, max_results=5)
            if success and results:
                print(f"   {len(results)} resultados com query reescrita")
                web_set(f"web_search:{objective}", results)
                return {
                    "context": {
                        **state.get("context", {}),
                        "web_results": results,
                        "rewritten_query": rewritten,
                    },
                    "messages": [HumanMessage(content=f"WEB: {len(results)} resultados (query reescrita)")],
                    "artifacts": [f"web_search: {len(results)} links (rewrite)"],
                    "success": True,
                    "last_agent": "web"
                }

    except Exception as e:
        return {
            "messages": [HumanMessage(content=f"WEB: Erro na pesquisa: {e}")],
            "error": str(e),
            "last_agent": "web"
        }

    return {
        "messages": [HumanMessage(content="WEB: Sem resultados")],
        "error": "Nenhum resultado encontrado",
        "last_agent": "web"
    }


def scraper_node(state: AgentState) -> dict:
    """No de scraping: usa Scraper Bridge para extrair conteudo de sites."""
    print(f"\n[SCRAPER] Executando web scraping...")

    scraper = get_scraper_bridge()
    objective = state["objective"]
    context = state.get("context", {})

    # Try to extract a URL from the objective or context
    import re
    url_match = re.search(r'https?://[^\s]+', objective)
    url = url_match.group(0) if url_match else None

    # Also check context for URLs
    if not url and context.get("web_results"):
        for r in context["web_results"]:
            if isinstance(r, dict) and r.get("url"):
                url = r["url"]
                break

    if url:
        print(f"   Scraping URL: {url}")
        content, success, msg = scraper.scrape_url(url)

        if success:
            # Extract links and title
            links = scraper.extract_links(content)
            title = scraper.get_page_title(content)

            print(f"   Conteudo obtido: {len(content)} chars, {len(links)} links")

            return {
                "context": {
                    **context,
                    "scraped_content": content,
                    "scraped_url": url,
                    "scraped_title": title,
                    "scraped_links": links
                },
                "messages": [HumanMessage(content=f"SCRAPER: {msg} ({len(content)} chars)")],
                "artifacts": [f"scrape_{url[:40]} ({len(content)} chars)"],
                "output_files": [],
                "last_agent": "scraper",
                "success": True
            }
        else:
            # Try fallback
            print(f"   Firecrawl falhou, tentando fallback...")
            script, success, msg = scraper.scrape_with_fallback(url)

            if not success:
                # Save fallback script as artifact
                script_path = f"/tmp/scraper_fallback_{state.get('task_id', 'default')}.py"
                with open(script_path, "w") as f:
                    f.write(script)
                return {
                    "messages": [HumanMessage(content=f"SCRAPER: {msg}")],
                    "artifacts": [f"fallback_script: {script_path}"],
                    "output_files": [script_path],
                    "last_agent": "scraper",
                    "success": False,
                    "error": msg
                }

    # If no URL found, try web search first
    print(f"   Nenhuma URL encontrada, fazendo busca...")
    results, success, msg = scraper.search_web(objective, max_results=3)

    if success and results:
        print(f"   {len(results)} resultados de busca")

        # Auto-scrape the first result
        first_url = results[0].get("url", "")
        if first_url:
            content, s_ok, s_msg = scraper.scrape_url(first_url)
            if s_ok:
                return {
                    "context": {
                        **context,
                        "search_results": results,
                        "scraped_content": content,
                        "scraped_url": first_url
                    },
                    "messages": [HumanMessage(content=f"SCRAPER: Busca + scrape do 1o resultado")],
                    "artifacts": [f"search_scrape: {len(results)} res, {len(content)} chars"],
                    "last_agent": "scraper",
                    "success": True
                }

        return {
            "context": {**context, "search_results": results},
            "messages": [HumanMessage(content=f"SCRAPER: {len(results)} resultados de busca")],
            "artifacts": [f"search_results: {len(results)} items"],
            "last_agent": "scraper",
            "success": True
        }

    return {
        "messages": [HumanMessage(content=f"SCRAPER: {msg}")],
        "error": msg,
        "last_agent": "scraper",
        "success": False
    }


def viz_node(state: AgentState) -> dict:
    """No de visualizacao: usa Viz Bridge para gerar graficos."""
    print(f"\n[VIZ] Gerando visualizacoes...")

    viz = get_viz_bridge()
    objective = state["objective"]
    context = state.get("context", {})

    # Check context for data to visualize
    scraped_data = context.get("scraped_content", "")
    search_results = context.get("search_results", [])
    knowledge_graph = context.get("knowledge_graph", {})
    web_results = context.get("web_results", [])

    artifacts = []

    # Determine chart type from objective
    chart_type = "bar"
    obj_lower = objective.lower()
    if any(w in obj_lower for w in ["pie", "proporcao", "percentual"]):
        chart_type = "pie"
    elif any(w in obj_lower for w in ["linha", "tendencia", "evolucao", "line"]):
        chart_type = "line"
    elif any(w in obj_lower for w in ["dispersao", "scatter", "correlacao"]):
        chart_type = "scatter"

    # Generate sample chart if we have numeric data context
    chart_paths = []
    saved_charts = []

    # Try to extract numeric data from context
    data = context.get("chart_data", None)
    if data and isinstance(data, dict):
        path, ok, msg = viz.generate_chart(data, chart_type, objective[:60])
        if ok:
            chart_paths.append(path)
            saved_charts.append(path)
            artifacts.append(f"chart_{os.path.basename(path)}")

    # If we have search results, create a summary chart
    if search_results and not data:
        labels = [r.get("title", f"Result {i}")[:20] for i, r in enumerate(search_results)]
        values = [len(r.get("description", "")) for r in search_results]
        sample_data = {"labels": labels, "values": values}
        path, ok, msg = viz.generate_chart(
            sample_data, "bar",
            "Search Results: Content Length Comparison",
            filename=f"search_summary_{state.get('task_id', 'default')}.png"
        )
        if ok:
            chart_paths.append(path)
            artifacts.append(f"chart_{os.path.basename(path)}")

    # Generate a comparison chart if we have multiple data sources
    comparison_data = context.get("comparison_data", None)
    if comparison_data and isinstance(comparison_data, list):
        path, ok, msg = viz.generate_comparison_chart(
            comparison_data,
            objective[:60],
            chart_type="bar"
        )
        if ok:
            chart_paths.append(path)
            artifacts.append(f"comparison_{os.path.basename(path)}")

    # Generate dashboard if multiple charts
    if len(chart_paths) > 1:
        dash_path, ok, msg = viz.generate_html_dashboard(
            chart_paths,
            f"Dashboard: {objective[:50]}"
        )
        if ok:
            artifacts.append(f"dashboard_{os.path.basename(dash_path)}")
            chart_paths.append(dash_path)

    if chart_paths:
        print(f"   {len(chart_paths)} visualizacoes geradas")
        return {
            "context": {
                **context,
                "generated_charts": chart_paths
            },
            "messages": [HumanMessage(content=f"VIZ: {len(chart_paths)} visualizacoes geradas")],
            "artifacts": artifacts,
            "output_files": chart_paths,
            "last_agent": "viz",
            "success": True
        }

    # If no data, generate a demo chart
    print(f"   Nenhum dado encontrado, gerando chart demo...")
    demo_data = {
        "labels": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
        "values": [23, 45, 56, 78, 44, 67]
    }
    path, ok, msg = viz.generate_chart(
        demo_data, chart_type,
        objective[:60],
        filename=f"demo_{state.get('task_id', 'default')}.png"
    )
    if ok:
        return {
            "context": {**context, "generated_charts": [path]},
            "messages": [HumanMessage(content=f"VIZ: Demo chart gerado - {msg}")],
            "artifacts": [f"chart_{os.path.basename(path)}"],
            "output_files": [path],
            "last_agent": "viz",
            "success": True
        }

    return {
        "messages": [HumanMessage(content=f"VIZ: {msg}")],
        "error": msg,
        "last_agent": "viz",
        "success": False
    }


def observer_node(state: AgentState) -> dict:
    """No de observacao: usa Observer Bridge para criar watchers."""
    print(f"\n[OBSERVER] Configurando monitoramento...")

    observer = get_observer_bridge()
    objective = state["objective"]
    context = state.get("context", {})

    import re

    # Parse objective to determine watcher parameters
    obj_lower = objective.lower()

    # Detect check type
    check_type = "web_content"
    if any(w in obj_lower for w in ["preco", "price", "cotacao", "valor"]):
        check_type = "web_price"
    elif any(w in obj_lower for w in ["arquivo", "file", "modificado", "mudanca"]):
        check_type = "file_change"
    elif any(w in obj_lower for w in ["api", "health", "endpoint", "status"]):
        check_type = "api_health"

    # Extract target URL or file path
    url_match = re.search(r'https?://[^\s]+', objective)
    target = url_match.group(0) if url_match else "https://example.com"

    # Extract name from objective
    name_match = re.search(r'(?:chamado|chamada|named|called)\s+["\']?(\w+)["\']?', obj_lower)
    name = name_match.group(1) if name_match else f"watcher_{state.get('task_id', 'default')[:8]}"

    # Detect interval
    interval = "1h"
    if "daily" in obj_lower or "diario" in obj_lower:
        interval = "daily"
    elif "30m" in obj_lower or "30 min" in obj_lower:
        interval = "30m"
    elif "5m" in obj_lower or "5 min" in obj_lower:
        interval = "5m"

    # Create the watcher
    result = observer.create_watcher(
        name=name,
        target=target,
        check_type=check_type,
        interval=interval,
        notification="none"
    )

    if result.get("success"):
        print(f"   Watcher criado: {name} ({check_type} -> {target})")
        print(f"   Script: {result.get('script_path', 'N/A')}")
        print(f"   Cron: {result.get('cron_command', 'N/A')}")

        # List existing watchers
        all_watchers = observer.list_watchers()

        return {
            "context": {
                **context,
                "watcher": result,
                "all_watchers": all_watchers
            },
            "messages": [HumanMessage(
                content=f"OBSERVER: Watcher '{name}' criado ({check_type}, intervalo: {interval})"
            )],
            "artifacts": [
                f"watcher_{name}",
                f"script: {result.get('script_path', 'N/A')}",
                f"cron: {result.get('cron_command', 'N/A')}"
            ],
            "output_files": [result.get("script_path", "")],
            "last_agent": "observer",
            "success": True
        }

    return {
        "messages": [HumanMessage(content=f"OBSERVER: Falha ao criar watcher - {result.get('error', 'Erro desconhecido')}")],
        "error": result.get("error", "Unknown error"),
        "last_agent": "observer",
        "success": False
    }


def scraper_fallback_node(state: AgentState) -> dict:
    """No de fallback scraping: usa ScraperFallback (requests+BS4) quando Firecrawl falha."""
    print(f"\n[SCRAPER_FALLBACK] Executando fallback scraping...")

    fallback = get_scraper_fallback()
    objective = state["objective"]
    context = state.get("context", {})

    import re

    # Try to extract a URL from the objective or context
    url_match = re.search(r'https?://[^\s]+', objective)
    url = url_match.group(0) if url_match else None

    if not url and context.get("scraped_url"):
        url = context["scraped_url"]
    elif not url and context.get("web_results"):
        for r in context["web_results"]:
            if isinstance(r, dict) and r.get("url"):
                url = r["url"]
                break

    if url:
        print(f"   Scraping URL via fallback: {url}")
        content, success, msg = fallback.scrape_url(url)

        if success:
            print(f"   Conteudo obtido: {len(content)} chars")
            return {
                "context": {
                    **context,
                    "scraped_content": content,
                    "scraped_url": url,
                    "scraped_title": content.split("\n")[0] if content else "",
                    "scraper_method": "fallback_http"
                },
                "messages": [HumanMessage(content=f"SCRAPER_FALLBACK: {msg}")],
                "artifacts": [f"fallback_scrape_{url[:40]} ({len(content)} chars)"],
                "output_files": [],
                "last_agent": "scraper_fallback",
                "success": True
            }

        return {
            "messages": [HumanMessage(content=f"SCRAPER_FALLBACK: {msg}")],
            "error": msg,
            "last_agent": "scraper_fallback",
            "success": False
        }

    # If no URL found, try search via fallback
    print(f"   Nenhuma URL, buscando...")
    results, success, msg = fallback.search_google(objective, max_results=3)

    if success and results:
        first_url = results[0].get("url", "")
        if first_url:
            content, s_ok, s_msg = fallback.scrape_url(first_url)
            if s_ok:
                return {
                    "context": {
                        **context,
                        "search_results": results,
                        "scraped_content": content,
                        "scraped_url": first_url,
                        "scraper_method": "fallback_http"
                    },
                    "messages": [HumanMessage(content=f"SCRAPER_FALLBACK: Busca + scrape do 1o resultado")],
                    "artifacts": [f"fallback_search_scrape: {len(content)} chars"],
                    "last_agent": "scraper_fallback",
                    "success": True
                }

        return {
            "context": {**context, "search_results": results},
            "messages": [HumanMessage(content=f"SCRAPER_FALLBACK: {len(results)} resultados")],
            "artifacts": [f"fallback_search: {len(results)} items"],
            "last_agent": "scraper_fallback",
            "success": True
        }

    return {
        "messages": [HumanMessage(content=f"SCRAPER_FALLBACK: {msg}")],
        "error": msg,
        "last_agent": "scraper_fallback",
        "success": False
    }


def vision_scout_node(state: AgentState) -> dict:
    """No de visao computacional: usa VisionScoutBridge para analisar imagens."""
    print(f"\n[VISION_SCOUT] Analisando imagem...")

    vision = get_vision_scout_bridge()
    objective = state["objective"]
    context = state.get("context", {})
    input_files = state.get("input_files", [])

    import re

    obj_lower = objective.lower()

    # Determine the type of vision task
    is_comparison = any(w in obj_lower for w in ["compare", "comparar", "diferenca", "diferente"])
    is_text_extract = any(w in obj_lower for w in ["extrair texto", "ocr", "ler texto", "extract text", "leia"])
    is_screenshot = any(w in obj_lower for w in ["screenshot", "captura", "print", "tela"])
    is_analyze = not is_comparison and not is_text_extract and not is_screenshot

    # Find image files from input_files or extract path from objective
    image_path = None
    if input_files:
        for f in input_files:
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
                image_path = f
                break

    if not image_path:
        path_match = re.search(r'(/[^\s]+\.(?:png|jpg|jpeg|webp|gif))', objective)
        if path_match:
            image_path = path_match.group(1)

    if not image_path:
        return {
            "messages": [HumanMessage(content="VISION_SCOUT: Nenhuma imagem encontrada. Forneca um caminho de arquivo de imagem.")],
            "error": "No image file specified",
            "last_agent": "vision_scout",
            "success": False
        }

    print(f"   Imagem: {image_path}")

    if is_comparison and image_path:
        # Comparison requires two images - try to find a second one
        image2_path = None
        if len(input_files) >= 2:
            for f in input_files[1:]:
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
                    image2_path = f
                    break

        if image2_path:
            result, success, msg = vision.compare_images(image_path, image2_path)
        else:
            # Single image of comparison - just analyze
            result, success, msg = vision.analyze_image(image_path, "Descreva esta imagem em detalhes.")
    elif is_text_extract:
        result, success, msg = vision.extract_text_from_image(image_path)
    elif is_screenshot:
        # Extract elements of interest from objective
        elements = "textos, precos, botoes"
        elem_match = re.search(r'(?:elementos?|focus on|foco em)[s:]+(.+?)(?:\.|$)', obj_lower)
        if elem_match:
            elements = elem_match.group(1).strip()
        result, success, msg = vision.analyze_screenshot(image_path, elements)
    else:
        # Default: general analysis with custom question from objective
        question = "Descreva esta imagem em detalhes."
        if "?" in objective:
            q_part = objective.split("?")[0]
            question = q_part[-200:] if len(q_part) > 200 else q_part
        result, success, msg = vision.analyze_image(image_path, question)

    if success:
        print(f"   Analise concluida: {len(result)} chars")
        return {
            "context": {
                **context,
                "vision_result": result,
                "vision_image": image_path
            },
            "messages": [HumanMessage(content=f"VISION_SCOUT: {msg}")],
            "artifacts": [f"vision_analysis ({len(result)} chars)"],
            "output_files": [],
            "last_agent": "vision_scout",
            "success": True
        }

    return {
        "messages": [HumanMessage(content=f"VISION_SCOUT: {msg}")],
        "error": msg,
        "last_agent": "vision_scout",
        "success": False
    }


def sheets_node(state: AgentState) -> dict:
    """No de planilhas: usa Sheets Bridge para operacoes com sheets."""
    print(f"\n[SHEETS] Executando operacao com planilhas...")

    sheets = get_sheets_bridge()
    objective = state["objective"]
    context = state.get("context", {})

    obj_lower = objective.lower()

    # Detect operation type
    if any(w in obj_lower for w in ["listar", "list sheets", "listar planilhas", "list"]):
        results, success, msg = sheets.list_sheets()
        if success:
            return {
                "context": {**context, "sheets_list": results},
                "messages": [HumanMessage(content=f"SHEETS: {msg}")],
                "artifacts": [f"sheets_list ({len(results)} sheets)"],
                "success": True,
                "last_agent": "sheets"
            }

    elif any(w in obj_lower for w in ["criar", "create", "nova", "new sheet", "nova planilha"]):
        # Try to extract title and headers from objective
        import re
        title = "New Sheet"
        title_match = re.search(r'(?:chamado["\']?|called["\']?|titulo["\']?|title["\']?)[:\s]+["\']?([^"\'\n]+)["\']?', objective)
        if title_match:
            title = title_match.group(1).strip()

        headers = ["Coluna A", "Coluna B", "Coluna C"]
        headers_match = re.search(r'(?:colunas?:|headers?:|cabecalhos?:)\s*(.+?)(?:\.|$)', obj_lower)
        if headers_match:
            raw = headers_match.group(1)
            headers = [h.strip().strip('"').strip("'") for h in raw.split(",")]

        result, success, msg = sheets.create_sheet(title, headers)
        return {
            "context": {**context, "sheet_result": result},
            "messages": [HumanMessage(content=f"SHEETS: {msg}")],
            "artifacts": [f"sheet_created: {title}"],
            "output_files": [result] if isinstance(result, str) and os.path.exists(result) else [],
            "success": success,
            "last_agent": "sheets"
        }

    elif any(w in obj_lower for w in ["ler", "read", "abrir", "open"]):
        # Try to find a sheet ID or path
        import re
        path_match = re.search(r'(?:sheet|planilha|arquivo|file)[:\s]+["\']?([^"\'\n]+)["\']?', objective)
        sheet_ref = path_match.group(1).strip() if path_match else ""

        if not sheet_ref:
            # Use the first available sheet
            all_sheets, ok, _ = sheets.list_sheets()
            if ok and all_sheets:
                sheet_ref = all_sheets[0].get("path") or all_sheets[0].get("filename", "")

        if sheet_ref:
            data, success, msg = sheets.read_sheet(sheet_ref)
            return {
                "context": {**context, "sheet_data": data},
                "messages": [HumanMessage(content=f"SHEETS: {msg}")],
                "artifacts": [f"sheet_read: {len(data) if isinstance(data, list) else 1} rows"],
                "success": success,
                "last_agent": "sheets"
            }

        return {
            "messages": [HumanMessage(content="SHEETS: Nenhuma sheet especificada")],
            "error": "No sheet reference found",
            "last_agent": "sheets",
            "success": False
        }

    # Default: create a demo sheet
    print(f"   Operacao nao especificada, criando demo...")
    result, success, msg = sheets.create_sheet(
        f"auto_{objective[:30]}",
        ["Item", "Valor", "Data"],
        [["Exemplo 1", "100", "2024-01-01"], ["Exemplo 2", "200", "2024-01-02"]]
    )

    return {
        "context": {**context, "sheet_result": result},
        "messages": [HumanMessage(content=f"SHEETS: {msg}")],
        "artifacts": [f"sheet_demo: {msg[:50]}"] if success else [],
        "success": success,
        "error": None if success else msg,
        "last_agent": "sheets"
    }


def reporter_node(state: AgentState) -> dict:
    """No de relatorios: usa Reporter Bridge para gerar PDF/HTML reports."""
    print(f"\n[REPORTER] Gerando relatorio...")

    reporter = get_reporter_bridge()
    objective = state["objective"]
    context = state.get("context", {})

    # Build sections from context if available
    sections = []

    # Check for web/scraper data
    scraped_content = context.get("scraped_content", "")
    if scraped_content:
        sections.append({
            "heading": "Dados Coletados da Web",
            "content": scraped_content[:3000]
        })

    # Check for search results
    search_results = context.get("search_results", context.get("web_results", []))
    if search_results:
        content_lines = []
        for i, r in enumerate(search_results[:15]):
            if isinstance(r, dict):
                title = r.get("title", r.get("name", f"Resultado {i+1}"))
                desc = r.get("description", r.get("snippet", ""))
                url = r.get("url", r.get("link", ""))
                content_lines.append(f"- {title}")
                if desc:
                    content_lines.append(f"  {desc}")
                if url:
                    content_lines.append(f"  URL: {url}")
                content_lines.append("")
        sections.append({
            "heading": "Resultados de Pesquisa",
            "content": "\n".join(content_lines)
        })

    # Check for vision analysis
    vision_result = context.get("vision_result", "")
    if vision_result:
        sections.append({
            "heading": "Analise de Imagem",
            "content": vision_result[:2000]
        })

    # Check for knowledge graph
    graph_summary = context.get("graph_summary", {})
    if graph_summary:
        sections.append({
            "heading": "Grafo de Conhecimento",
            "content": json.dumps(graph_summary, indent=2, ensure_ascii=False)[:2000]
        })

    # Add a section from the objective itself
    sections.insert(0, {
        "heading": "Resumo",
        "content": f"Objetivo: {objective}\n\nRelatorio gerado automaticamente pelo Hermes-Unified Reporter Agent."
    })

    # If no context data, generate a report from the objective
    if len(sections) <= 1:
        sections = [
            {"heading": "Resumo", "content": f"Objetivo: {objective}"},
            {"heading": "Detalhes", "content": "Relatorio gerado automaticamente. Sentencas e analises serao processadas conforme dados disponiveis."},
            {"heading": "Proximos Passos", "content": "- Revisar dados gerados\n- Validar informacoes\n- Exportar resultados"}
        ]

    # Check for charts to include
    charts = context.get("generated_charts", [])

    # Generate full report (PDF + HTML)
    title = objective[:80]
    results, success, msg = reporter.generate_full_report(title, sections, charts)

    if success:
        print(f"   Report gerado: PDF={results.get('pdf_path', 'N/A')}, HTML={results.get('html_path', 'N/A')}")
        return {
            "context": {**context, "report_results": results},
            "messages": [HumanMessage(content=f"REPORTER: {msg}")],
            "artifacts": [f"report: {os.path.basename(results.get('pdf_path', ''))}"],
            "output_files": [v for v in results.values() if isinstance(v, str) and os.path.exists(v)],
            "success": True,
            "last_agent": "reporter"
        }

    return {
        "messages": [HumanMessage(content=f"REPORTER: {msg}")],
        "error": msg,
        "last_agent": "reporter",
        "success": False
    }


def dv360_node(state: AgentState) -> dict:
    """No de DV360: usa DV360 Bridge para analisar campanhas de Display & Video 360."""
    print(f"\n[DV360] Analisando dados de Display & Video 360...")

    dv360 = get_dv360_bridge()
    objective = state["objective"]
    context = state.get("context", {})

    obj_lower = objective.lower()

    # Detect operation type
    if any(w in obj_lower for w in ["advertiser", "anunciante", "list advertiser", "listar"]):
        partner_id = context.get("partner_id", None)
        results, success, msg = dv360.list_advertisers(partner_id)
        return {
            "context": {**context, "dv360_advertisers": results},
            "messages": [HumanMessage(content=f"DV360: {msg}")],
            "artifacts": [f"dv360_advertisers ({len(results)} found)"],
            "success": success,
            "last_agent": "dv360"
        }

    elif any(w in obj_lower for w in ["performance", "desempenho", "metrics", "metricas"]):
        # Try to extract advertiser ID
        import re
        adv_match = re.search(r'(?:advertiser[_\s]?id|adv[_\s]?id)[:\s]+(\d+)', obj_lower)
        advertiser_id = adv_match.group(1) if adv_match else context.get("advertiser_id", "SAMPLE_ADVERTISER")

        # Extract dates
        date_match = re.findall(r'(\d{4}-\d{2}-\d{2})', objective)
        start_date = date_match[0] if len(date_match) > 0 else "2024-01-01"
        end_date = date_match[1] if len(date_match) > 1 else "2024-12-31"

        if any(w in obj_lower for w in ["compare", "comparar", "vs", "period"]):
            # Comparison between periods
            p2_start = date_match[2] if len(date_match) > 2 else "2023-01-01"
            p2_end = date_match[3] if len(date_match) > 3 else "2023-12-31"
            path, success, msg = dv360.compare_periods(advertiser_id, start_date, end_date, p2_start, p2_end)
        else:
            path, success, msg = dv360.generate_report(advertiser_id, start_date, end_date)

        return {
            "context": {**context, "dv360_report": path if success else None},
            "messages": [HumanMessage(content=f"DV360: {msg}")],
            "artifacts": [f"dv360_report: {os.path.basename(path) if path else 'N/A'}"],
            "output_files": [path] if success and path else [],
            "success": success,
            "error": None if success else msg,
            "last_agent": "dv360"
        }

    # Default: show status and available operations
    status = dv360.status()
    return {
        "context": {**context, "dv360_status": status},
        "messages": [HumanMessage(content=f"DV360: Modo {'online' if status['online'] else 'offline'}. Use 'performance', 'advertisers', ou 'compare'.")],
        "artifacts": [f"dv360_status: {'online' if status['online'] else 'offline'}"],
        "success": True,
        "last_agent": "dv360"
    }


def tiktok_node(state: AgentState) -> dict:
    """No de TikTok Ads: usa TikTok Bridge para analisar campanhas de anuncios."""
    print(f"\n[TIKTOK] Analisando dados de TikTok Ads...")

    tiktok = get_tiktok_bridge()
    objective = state["objective"]
    context = state.get("context", {})

    obj_lower = objective.lower()

    # Detect operation type
    if any(w in obj_lower for w in ["advertiser", "anunciante", "list advertiser", "listar", "conta", "account"]):
        results, success, msg = tiktok.list_advertisers()
        return {
            "context": {**context, "tiktok_advertisers": results},
            "messages": [HumanMessage(content=f"TIKTOK: {msg}")],
            "artifacts": [f"tiktok_advertisers ({len(results)} found)"],
            "success": success,
            "last_agent": "tiktok"
        }

    elif any(w in obj_lower for w in ["campaign", "campanha", "performance", "desempenho"]):
        import re
        adv_match = re.search(r'(?:advertiser[_\s]?id|adv[_\s]?id)[:\s]+(\d+)', obj_lower)
        advertiser_id = adv_match.group(1) if adv_match else context.get("advertiser_id", "SAMPLE_ADVERTISER")

        date_match = re.findall(r'(\d{4}-\d{2}-\d{2})', objective)
        start_date = date_match[0] if len(date_match) > 0 else "2024-01-01"
        end_date = date_match[1] if len(date_match) > 1 else "2024-12-31"

        if any(w in obj_lower for w in ["adgroup", "grupo de anuncio", "ad group"]):
            results, success, msg = tiktok.get_adgroup_stats(advertiser_id, start_date, end_date)
        elif any(w in obj_lower for w in ["compare", "comparar", "vs", "period"]):
            p2_start = date_match[2] if len(date_match) > 2 else "2023-01-01"
            p2_end = date_match[3] if len(date_match) > 3 else "2023-12-31"
            path, success, msg = tiktok.compare_periods(advertiser_id, start_date, end_date, p2_start, p2_end)
            return {
                "context": {**context, "tiktok_comparison": path if success else None},
                "messages": [HumanMessage(content=f"TIKTOK: {msg}")],
                "artifacts": [f"tiktok_comparison: {os.path.basename(path) if path else 'N/A'}"],
                "output_files": [path] if success and path else [],
                "success": success,
                "last_agent": "tiktok"
            }
        else:
            results, success, msg = tiktok.get_campaign_performance(advertiser_id, start_date, end_date)

        return {
            "context": {**context, "tiktok_campaigns": results},
            "messages": [HumanMessage(content=f"TIKTOK: {msg}")],
            "artifacts": [f"tiktok_campaigns ({len(results.get('campaigns', []))} campaigns)"],
            "success": success,
            "last_agent": "tiktok"
        }

    elif any(w in obj_lower for w in ["report", "relatorio", "reportar"]):
        import re
        adv_match = re.search(r'(?:advertiser[_\s]?id|adv[_\s]?id)[:\s]+(\d+)', obj_lower)
        advertiser_id = adv_match.group(1) if adv_match else context.get("advertiser_id", "SAMPLE_ADVERTISER")

        date_match = re.findall(r'(\d{4}-\d{2}-\d{2})', objective)
        start_date = date_match[0] if len(date_match) > 0 else "2024-01-01"
        end_date = date_match[1] if len(date_match) > 1 else "2024-12-31"

        path, success, msg = tiktok.generate_report(advertiser_id, start_date, end_date)
        return {
            "context": {**context, "tiktok_report": path if success else None},
            "messages": [HumanMessage(content=f"TIKTOK: {msg}")],
            "artifacts": [f"tiktok_report: {os.path.basename(path) if path else 'N/A'}"],
            "output_files": [path] if success and path else [],
            "success": success,
            "last_agent": "tiktok"
        }

    # Default: show status
    status = tiktok.status()
    return {
        "context": {**context, "tiktok_status": status},
        "messages": [HumanMessage(content=f"TIKTOK: Modo {'online' if status['online'] else 'offline'}. Use 'campaigns', 'adgroups', 'advertisers', 'report', ou 'compare'.")],
        "artifacts": [f"tiktok_status: {'online' if status['online'] else 'offline'}"],
        "success": True,
        "last_agent": "tiktok"
    }


def research_node(state: AgentState) -> dict:
    """No de pesquisa: usa Research Bridge estilo STORM para pesquisar topicos."""
    print(f"\n[RESEARCH] Iniciando pesquisa...")

    objective = state["objective"]
    context = state.get("context", {})

    research = get_research_bridge()
    obj_lower = objective.lower()

    # Detecta profundidade
    depth = "medium"
    if any(w in obj_lower for w in ["profundo", "detalhado", "deep", "completo"]):
        depth = "deep"
    elif any(w in obj_lower for w in ["rapido", "quick", "resumo"]):
        depth = "quick"

    # Extrai o topico (remove palavras de comando)
    topic = objective
    for prefix in ["pesquise sobre", "pesquise", "pesquisa sobre", "pesquisa",
                    "artigo sobre", "artigo", "escreva sobre", "gere artigo",
                    "research", "write about", "generate article"]:
        if obj_lower.startswith(prefix):
            topic = objective[len(prefix):].strip().strip(":,.;!?")

    print(f"   Topico: {topic[:80]}...")
    print(f"   Profundidade: {depth}")

    # Verifica status primeiro
    status = research.status()
    if not status["storm_installed"]:
        print(f"   knowledge-storm nao disponivel, usando modo offline")

    path, success, msg = research.research_topic(topic, depth)

    # Le o artigo se foi gerado
    article_preview = ""
    if success and path:
        try:
            with open(path) as f:
                content = f.read()
            article_preview = content[:500]
        except:
            pass

    return {
        "context": {
            **context,
            "research_topic": topic,
            "research_depth": depth,
            "research_article": article_preview,
            "article_path": path if success else None,
        },
        "messages": [HumanMessage(content=f"RESEARCH: {msg}")],
        "artifacts": [f"research_article: {os.path.basename(path) if path else 'N/A'} ({depth})"],
        "output_files": [path] if success and path else [],
        "success": success,
        "last_agent": "research"
    }


def finance_node(state: AgentState) -> dict:
    """No de finanças: usa FinancialBridgeBR para dados de investimentos Brasil."""
    print(f"\n[FINANCE] Processando dados financeiros...")

    fb = get_financial_bridge()
    objective = state["objective"]
    context = state.get("context", {})
    obj_lower = objective.lower()

    # Detecta intenção
    if any(w in obj_lower for w in ["panorama", "sintese", "resumo", "mercado"]):
        result = fb.sintese_mercado()
        return {
            "context": {**context, "finance_sintese": result},
            "messages": [HumanMessage(content=f"FINANCE: Síntese de mercado gerada")],
            "artifacts": ["finance_sintese_mercado"],
            "success": True,
            "last_agent": "finance"
        }

    if any(w in obj_lower for w in ["selic", "ipca", "cdi", "macro", "pib", "cambio", "câmbio", "desemprego"]):
        # Detecta indicadores específicos na query
        indicadores = []
        for ind in ["selic", "ipca", "cdi", "igpm", "cambio_usd", "pib_mensal", "desemprego"]:
            nome_clean = ind.replace("_", "")
            if ind in obj_lower or nome_clean in obj_lower:
                indicadores.append(ind)
        if not indicadores:
            indicadores = ["selic", "ipca", "cdi", "cambio_usd", "pib_mensal", "desemprego"]

        result = fb.get_multi_macro(indicadores) if len(indicadores) > 1 else fb.get_macro(indicadores[0])
        return {
            "context": {**context, "finance_macro": result},
            "messages": [HumanMessage(content=f"FINANCE: Dados macro: {', '.join(indicadores)}")],
            "artifacts": [f"macro_{'_'.join(indicadores)}"],
            "success": True,
            "last_agent": "finance"
        }

    if any(w in obj_lower for w in ["fii", "fundo imobiliario", "fundo imobiliário"]):
        # Tenta detectar ticker específico
        import re
        tickers = re.findall(r'\b[A-Z]{4}11\b', objective.upper())
        if tickers:
            result = {t: fb.get_fii(t) for t in tickers[:5]}
        else:
            result = {"ranking": fb.get_fiis_ranking()}

        return {
            "context": {**context, "finance_fiis": result},
            "messages": [HumanMessage(content=f"FINANCE: Dados de FIIs")],
            "artifacts": [f"fiis_{'_'.join(tickers) if tickers else 'ranking'}"],
            "success": True,
            "last_agent": "finance"
        }

    if any(w in obj_lower for w in ["tesouro", "titulo", "título", "tesouro direto"]):
        result = fb.get_tesouro()
        return {
            "context": {**context, "finance_tesouro": result},
            "messages": [HumanMessage(content=f"FINANCE: Tesouro Direto — {result.get('total_titulos', 0)} títulos")],
            "artifacts": ["tesouro_direto"],
            "success": True,
            "last_agent": "finance"
        }

    if any(w in obj_lower for w in ["dividend", "provento"]):
        import re
        tickers = re.findall(r'\b[A-Z]{4}\b', objective.upper())
        if tickers:
            result = {t: fb.get_dividendos(t) for t in tickers[:5]}
        else:
            result = {"error": "Informe o ticker (ex: PETR4)"}
        return {
            "context": {**context, "finance_dividendos": result},
            "messages": [HumanMessage(content=f"FINANCE: Dividendos")],
            "artifacts": [f"dividendos_{'_'.join(tickers[:2]) if tickers else 'none'}"],
            "success": True,
            "last_agent": "finance"
        }

    if any(w in obj_lower for w in ["comparar", "comparação", "vs", "versus"]):
        import re
        tickers = re.findall(r'\b[A-Z]{4}\b', objective.upper())
        if len(tickers) >= 2:
            result = fb.comparar_ativos(tickers[:5])
            return {
                "context": {**context, "finance_comparacao": result},
                "messages": [HumanMessage(content=f"FINANCE: Comparação de {len(tickers)} ativos")],
                "artifacts": [f"comparacao_{'_'.join(tickers[:3])}"],
                "success": True,
                "last_agent": "finance"
            }

    # Default: cotação
    import re
    tickers = re.findall(r'\b[A-Z]{4}\b', objective.upper())
    if tickers:
        result = fb.get_multiplas_cotacoes(tickers[:5])
    else:
        # Ranking como fallback
        result = {"ranking_volume": fb.get_ranking("volume")[:5]}

    return {
        "context": {**context, "finance_data": result},
        "messages": [HumanMessage(content=f"FINANCE: Dados financeiros processados")],
        "artifacts": [f"finance_data"],
        "success": True,
        "last_agent": "finance"
    }


def mcp_brasil_node(state: AgentState) -> dict:
    """No MCP-Brasil: acessa 307+ ferramentas de dados públicos brasileiros.
    Features: BCB, IBGE, IPEA, BNDES, BrasilAPI, Câmara, Senado, TSE,
    ANVISA, INPE, ComprasNet, Diário Oficial, SUS, INEP, e mais.
    """
    print(f"\n[MCP_BRASIL] Acessando dados públicos brasileiros...")

    bridge = get_mcp_brasil_bridge()
    objective = state["objective"]
    context = state.get("context", {})
    obj_lower = objective.lower()

    # Tenta busca inteligente primeiro
    result = bridge.buscar(objective)

    # Se a busca inteligente retornou resultados, usa o primeiro
    if result and result[0].get("result", {}).get("success", False):
        feature_results = result[0]
        print(f"   Feature acionada: {feature_results['feature']}")

        return {
            "context": {
                **context,
                "mcp_brasil_data": feature_results["result"],
                "mcp_brasil_feature": feature_results["feature"],
            },
            "messages": [HumanMessage(
                content=f"MCP_BRASIL: Dados obtidos via feature '{feature_results['feature']}'"
            )],
            "artifacts": [f"mcp_brasil_{feature_results['feature']}"],
            "success": True,
            "last_agent": "mcp_brasil"
        }

    # Fallback: retorna lista de features disponíveis
    status = bridge.status()
    return {
        "context": {**context, "mcp_brasil_status": status},
        "messages": [HumanMessage(
            content=f"MCP_BRASIL: {status['total_features']} features disponíveis com {status['total_tools']} ferramentas. "
                    f"Não encontrei correspondência para '{objective[:80]}'."
        )],
        "artifacts": [f"mcp_brasil_status: {status['total_features']} features"],
        "success": True,
        "last_agent": "mcp_brasil"
    }


def integrator_node(state: AgentState) -> dict:
    """No de integracao: consolida resultados e decide proximos passos.
    Valida dados contra a ontologia antes de declarar conclusao.
    """
    print(f"\n[INTEGRATOR] Consolidando resultados...")

    messages = state.get("messages", [])
    artifacts = state.get("artifacts", [])
    has_artifacts = len(artifacts) > 0
    has_messages = len(messages) > 1
    iteration = state.get("iteration", 0)
    last_agent = state.get("last_agent", "")

    # ====================================================================
    # VALIDAÇÃO ONTOLÓGICA — verifica dados antes de passar pro LLM
    # ====================================================================
    ontology = get_ontology()
    validation_errors = []

    # Tenta validar saídas da última bridge contra a ontologia
    context = state.get("context", {})
    for key, value in context.items():
        if isinstance(value, dict):
            # Verifica se parece uma Metric
            if "name" in value and "value" in value:
                ok, msg = ontology.validate_metric(value)
                if not ok:
                    validation_errors.append(f"[ONTOLOGIA] Metric inválida: {msg}")
            # Verifica se parece um Claim
            if "text" in value and "confidence" in value:
                ok, msg = ontology.validate_claim(value)
                if not ok:
                    validation_errors.append(f"[ONTOLOGIA] Claim inválido: {msg}")
        elif isinstance(value, list):
            for item in value[:5]:  # Limita a 5 itens
                if isinstance(item, dict):
                    if "name" in item and "value" in item:
                        ok, msg = ontology.validate_metric(item)
                        if not ok:
                            validation_errors.append(f"[ONTOLOGIA] Metric '{item.get('name')}' inválida: {msg}")
                    if "text" in item and "confidence" in item:
                        ok, msg = ontology.validate_claim(item)
                        if not ok:
                            validation_errors.append(f"[ONTOLOGIA] Claim inválido: {msg}")

    if validation_errors:
        print(f"   ⚠ {len(validation_errors)} validação(ões) ontológica(s) falharam:")
        for err in validation_errors:
            print(f"      {err}")
    else:
        print(f"   ✓ Dados validados contra ontologia")

    if has_artifacts or has_messages or iteration >= 1 or state.get("error"):
        # ====================================================================
        # VERIFICA SE TEM PROXIMO PASSO NA SEQUENCIA MULTI-PASSO
        # ====================================================================
        agent_sequence = state.get("agent_sequence", [])
        sequence_index = state.get("sequence_index", 0)
        next_seq_index = sequence_index + 1

        last_error = state.get("error")
        bridge_falhou = bool(last_error) or not state.get("success", True)

        if agent_sequence and next_seq_index < len(agent_sequence):
            # Ainda tem bridges para executar na sequencia
            next_agent = agent_sequence[next_seq_index]

            if bridge_falhou:
                print(f"   [MULTI-PASSO] Bridge {last_agent} FALHOU. Pulando para {next_agent} "
                      f"({next_seq_index+1}/{len(agent_sequence)})")
                # Limpa o erro ao pular
                error_msg = f"Bridge {last_agent} falhou: {last_error}. Pulando para {next_agent}."
            else:
                print(f"   [MULTI-PASSO] Avancando para bridge {next_seq_index+1}/{len(agent_sequence)}: {next_agent}")
                error_msg = None

            print(f"   Artifacts ate agora: {len(artifacts)}")

            # Auto-skill hook (parcial)
            try:
                from tools.auto_skill_creator import skill_suggestion_hook
                objective = state.get("objective", "")
                suggestion = skill_suggestion_hook(
                    last_agent=last_agent,
                    messages=messages,
                    objective=objective,
                    tool_calls_count=1,
                )
                if suggestion and suggestion.get("suggested"):
                    print(f"   [SKILL HOOK] {suggestion['message']}")
                    context["_skill_suggestion"] = suggestion
            except ImportError:
                pass
            except Exception as e:
                print(f"   [SKILL HOOK] Erro: {e}")

            return {
                "completed": False,
                "success": not bridge_falhou,
                "current_agent": next_agent,
                "sequence_index": next_seq_index,
                "error": error_msg,  # None se OK, mensagem se pulou falha
                "iteration": iteration + 1,
                "context": {
                    **context,
                    "summary": f"Bridge {last_agent} {'FALHOU' if bridge_falhou else 'OK'}. Proximo: {next_agent}",
                    "validation_errors": validation_errors if validation_errors else None,
                },
                "messages": [HumanMessage(content=f"INTEGRATOR: Bridge {last_agent} {'FALHOU' if bridge_falhou else 'OK'}. Proximo: {next_agent}")]
            }

        # ====================================================================
        # FIM DA SEQUENCIA — finaliza a tarefa
        # ====================================================================
        print(f"   Tarefa concluida (artifacts={has_artifacts}, msgs={has_messages}, iter={iteration})\n")

        # ====================================================================
        # AUTO-SKILL HOOK — verifica se devemos sugerir criar uma skill
        # ====================================================================
        try:
            from tools.auto_skill_creator import skill_suggestion_hook
            objective = state.get("objective", "")
            suggestion = skill_suggestion_hook(
                last_agent=last_agent,
                messages=messages,
                objective=objective,
                tool_calls_count=1,
            )
            if suggestion and suggestion.get("suggested"):
                skill_msg = (
                    f"\n[DICA] Detectei {suggestion['message']} "
                    f"Use 'skill_manage action=create' com os parametros "
                    f"name={suggestion['skill_name']} "
                    f"description=... para salvar esta skill."
                )
                print(f"   {skill_msg}")
                # Anexa a dica ao contexto para o usuario ver
                context["_skill_suggestion"] = suggestion
        except ImportError:
            pass  # auto_skill_creator nao disponivel
        except Exception as e:
            print(f"   [SKILL HOOK] Erro: {e}")

        # Comprime contexto com Headroom antes de enviar pro LLM
        compressed_context = compress_context(context)
        if compressed_context != context:
            print(f"   ✓ Contexto comprimido com Headroom ({len(str(context))} -> {len(str(compressed_context))} chars)\n")

        return {
            "completed": True,
            "success": True,
            "iteration": iteration + 1,
            "context": {
                **compressed_context,
                "summary": "Tarefa executada com sucesso",
                "validation_errors": validation_errors if validation_errors else None,
                "_headroom_compressed": compressed_context != context
            },
            "messages": [HumanMessage(content="INTEGRATOR: Tarefa completa.")]
        }

    print(f"   Primeira execucao, continuando...")
    return {
        "current_agent": "codex",
        "last_agent": "integrator",
        "iteration": iteration + 1,
        "messages": [HumanMessage(content="INTEGRATOR: Primeira execucao, continuando...")]
    }


def router_node(state: AgentState):
    """Roteia para o proximo no baseado no estado.
    Implementa:
    1. Fallback cascade runtime: se bridge falhou, tenta fallback automaticamente
    2. Skip de bridge falha: se nao tem fallback, pula e continua sequencia
    3. Sequencia multi-passo avanca ate o fim normalmente
    """
    last = state.get("last_agent", "")
    error = state.get("error")
    success = state.get("success", True)
    has_failed = bool(error) or not success
    agent_sequence = state.get("agent_sequence", [])
    sequence_index = state.get("sequence_index", 0)
    iteration = state.get("iteration", 0)
    completed = state.get("completed", False)

    print(f"   [ROUTER] completed={completed} last={last} iter={iteration} "
          f"error={bool(error)} seq={sequence_index}/{len(agent_sequence)}")

    # ============================================================
    # CONDIÇÕES DE PARADA
    # ============================================================
    if completed:
        print("   [ROUTER] -> END (completed)")
        return "end"

    if iteration >= state.get("max_iterations", 3):
        print(f"   [ROUTER] -> END (max iter {iteration})")
        return "end"

    # ============================================================
    # FALLBACK CASCADE EM RUNTIME
    # Se a bridge falhou E tem fallback configurado, tenta fallback
    # ============================================================
    if has_failed and last in FALLBACK_MAP and FALLBACK_MAP[last]:
        fallbacks = FALLBACK_MAP[last]
        print(f"   [ROUTER] Bridge {last} falhou. Tentando fallback: {fallbacks}")

        # Tenta o primeiro fallback disponivel que nao esta na sequencia
        for fb in fallbacks:
            if fb not in agent_sequence:
                print(f"   [ROUTER] Fallback: {last} -> {fb}")
                # Nao incrementa sequence_index — o fallback substitui a bridge atual
                return {
                    "current_agent": fb,
                    "last_agent": "router",
                    "error": None,  # Limpa erro — vamos tentar de novo
                    "success": True,
                    "sequence_index": sequence_index,  # Mesmo indice
                    "agent_sequence": agent_sequence,
                    "iteration": iteration + 1,
                    "messages": state.get("messages", []) + [
                        HumanMessage(content=f"ROUTER: {last} falhou. Tentando fallback {fb}.")
                    ],
                }

        # Esgotou fallbacks — segue adiante sem esta bridge
        print(f"   [ROUTER] Fallbacks esgotados para {last}. Seguindo sem ela.")

    # ============================================================
    # SKIP DE BRIDGE FALHA NA SEQUENCIA
    # Se a bridge falhou e estamos em multi-passo, pula e vai pro integrator
    # O integrator decide se avanca ou encerra
    # ============================================================
    if has_failed and agent_sequence and (sequence_index + 1) < len(agent_sequence):
        print(f"   [ROUTER] Bridge {last} falhou em multi-passo. Pulando para proxima...")
        # Router retorna routing string — integrator vai tratar o skip
        return "integrator"

    # ============================================================
    # SEQUENCIA PENDENTE — nao encerra mesmo com artifacts
    # ============================================================
    if agent_sequence and (sequence_index + 1) < len(agent_sequence):
        print(f"   [ROUTER] Sequencia pendente: {sequence_index+1}/{len(agent_sequence)} - continuando...")
    elif len(state.get("artifacts", [])) > 0 and not has_failed:
        print("   [ROUTER] -> END (has artifacts)")
        return "end"

    # ============================================================
    # ROTEAMENTO PADRAO
    # ============================================================
    if last in ["codex", "knowledge", "web", "scraper", "viz", "observer",
                "scraper_fallback", "vision_scout", "sheets", "reporter",
                "dv360", "tiktok", "research", "finance", "mcp_brasil"]:
        print(f"   [ROUTER] -> integrator (from {last})")
        return "integrator"

    if last == "integrator":
        current = state.get("current_agent", "codex")
        if current in ["codex", "knowledge", "web", "scraper", "viz", "observer",
                        "scraper_fallback", "vision_scout", "sheets", "reporter",
                        "dv360", "tiktok", "research", "finance", "mcp_brasil"]:
            print(f"   [ROUTER] -> {current} (from integrator)")
            return current
        print("   [ROUTER] -> integrator (fallback)")
        return "integrator"

    print(f"   [ROUTER] -> codex (fallback, last={last})")
    return "codex"


# ==========================
# CONSTRUCAO DO GRAFO
# ==========================

def build_master_graph() -> StateGraph:
    """Constroi o grafo mestre de orquestracao."""
    print("=" * 60)
    print("CONSTRUINDO GRAFO MESTRE UNIFICADO")
    print("=" * 60)

    workflow = StateGraph(AgentState)

    # Mapa de bridge -> operação para telemetria
    _TELEMETRY_OPS = {
        "codex": "codex_node",
        "knowledge": "knowledge_node",
        "web": "web_node",
        "scraper": "scraper_node",
        "viz": "viz_node",
        "observer": "observer_node",
        "scraper_fallback": "scraper_fallback_node",
        "vision_scout": "vision_scout_node",
        "sheets": "sheets_node",
        "reporter": "reporter_node",
        "dv360": "dv360_node",
        "tiktok": "tiktok_node",
        "research": "research_node",
        "finance": "finance_node",
        "mcp_brasil": "mcp_brasil_node",
    }

    # Wrapper de telemetria para nodes de bridge
    def _wrap_node(node_fn, bridge_name):
        def wrapped(state):
            with telemetry.span(bridge_name, _TELEMETRY_OPS.get(bridge_name, f"{bridge_name}_node")):
                return node_fn(state)
        wrapped.__name__ = node_fn.__name__
        return wrapped

    # Adiciona nodes com telemetria
    workflow.add_node("planner", planner_node)
    workflow.add_node("integrator", integrator_node)
    for name, fn in [
        ("codex", codex_node), ("knowledge", knowledge_node),
        ("web", web_node), ("scraper", scraper_node),
        ("viz", viz_node), ("observer", observer_node),
        ("scraper_fallback", scraper_fallback_node),
        ("vision_scout", vision_scout_node),
        ("sheets", sheets_node), ("reporter", reporter_node),
        ("dv360", dv360_node), ("tiktok", tiktok_node),
        ("research", research_node), ("finance", finance_node),
        ("mcp_brasil", mcp_brasil_node),
    ]:
        workflow.add_node(name, _wrap_node(fn, name))

    workflow.set_entry_point("planner")
    # Roteamento pos-planner: segue o current_agent definido pelo planner
    def planner_route(state):
        agent = state.get("current_agent", "codex")
        print(f"   [PLANNER] Roteando para: {agent}")
        return agent

    workflow.add_conditional_edges(
        "planner",
        planner_route,
        {
            "codex": "codex",
            "knowledge": "knowledge",
            "web": "web",
            "scraper": "scraper",
            "viz": "viz",
            "observer": "observer",
            "vision_scout": "vision_scout",
            "sheets": "sheets",
            "reporter": "reporter",
            "dv360": "dv360",
            "tiktok": "tiktok",
            "research": "research",
            "finance": "finance",
            "mcp_brasil": "mcp_brasil",
            "integrator": "integrator",
        }
    )

    for agent in ["codex", "knowledge", "web", "scraper", "viz", "observer", "scraper_fallback", "vision_scout", "sheets", "reporter", "dv360", "tiktok", "research", "finance", "mcp_brasil"]:
        workflow.add_conditional_edges(
            agent,
            router_node,
            {
                "codex": "codex",
                "knowledge": "knowledge",
                "web": "web",
                "scraper": "scraper",
                "viz": "viz",
                "observer": "observer",
                "scraper_fallback": "scraper_fallback",
                "vision_scout": "vision_scout",
                "sheets": "sheets",
                "reporter": "reporter",
                "dv360": "dv360",
                "tiktok": "tiktok",
                "finance": "finance",
                "mcp_brasil": "mcp_brasil",
                "integrator": "integrator",
                "end": END
            }
        )

    workflow.add_conditional_edges(
        "integrator",
        router_node,
        {
            "codex": "codex",
            "knowledge": "knowledge",
            "web": "web",
            "scraper": "scraper",
            "viz": "viz",
            "observer": "observer",
            "scraper_fallback": "scraper_fallback",
            "vision_scout": "vision_scout",
            "sheets": "sheets",
            "reporter": "reporter",
            "dv360": "dv360",
            "tiktok": "tiktok",
            "research": "research",
            "finance": "finance",
            "mcp_brasil": "mcp_brasil",
            "planner": "planner",
            "integrator": "integrator",
            "end": END
        }
    )

    app = workflow.compile()
    print("Grafo mestre compilado!")
    print("   Nos: planner -> {codex, knowledge, web, scraper, viz, observer, scraper_fallback, vision_scout, sheets, reporter, dv360, tiktok, research, finance, mcp_brasil} -> integrator -> (loop)")
    return app


# ==========================
# FUNCAO PRINCIPAL
# ==========================

def run_agent(objective: str, input_files: list = None, max_iterations: int = 3) -> dict:
    """Executa o agente orquestrado para uma tarefa."""
    import uuid

    graph = build_master_graph()

    initial_state = {
        "task_id": str(uuid.uuid4())[:8],
        "objective": objective,
        "context": {},
        "current_agent": "planner",
        "artifacts": [],
        "messages": [],
        "input_files": input_files or [],
        "output_files": [],
        "iteration": 0,
        "max_iterations": max_iterations,
        "completed": False,
        "success": False,
        "error": None,
        "next_action": None,
        "turn_count": 0
    }

    print("INICIANDO EXECUCAO")
    print(f"   Task ID: {initial_state['task_id']}")
    print(f"   Objetivo: {objective[:100]}...")
    if input_files:
        print(f"   Inputs: {', '.join(input_files)}")
    print()

    final_state = graph.invoke(initial_state)

    # Salva na memória persistente
    try:
        from tools.memory_bridge import get_memory_bridge
        mem = get_memory_bridge()
        category = final_state.get("context", {}).get("category", "unknown")
        mem.save_session(
            objective=objective,
            category=category,
            success=final_state.get("success", False),
            artifacts=final_state.get("artifacts", []),
            summary=final_state.get("context", {}).get("summary", "")
        )
    except Exception as e:
        print(f"   [MEMORY] Erro ao salvar: {e}")

    print("\n" + "=" * 60)
    print("RESULTADO FINAL")
    print("=" * 60)
    print(f"Successo: {final_state.get('success', False)}")
    print(f"Iteracoes: {final_state.get('iteration', 0)}")
    print(f"Artefatos: {len(final_state.get('artifacts', []))}")
    print(f"Resumo: {final_state.get('context', {}).get('summary', 'N/A')}")

    return final_state


# ==========================
# EXEMPLO DE USO
# ==========================

if __name__ == "__main__":
    print("\n\nTESTE 1: Geracao de codigo")
    print("-" * 40)
    result1 = run_agent(
        "Crie um script Python que le um arquivo CSV e calcula a media de uma coluna"
    )
