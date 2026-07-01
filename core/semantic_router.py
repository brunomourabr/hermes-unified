"""
Semantic Router — Ponte entre planner (intenção crua) e bridges (execução).
Usa a ontologia para:
1. Mapear query do usuário para conceitos da ontologia
2. Selecionar bridge(s) correta(s) baseada no mapeamento
3. Anotar a query com contexto semântico antes de enviar pra bridge
4. Validar dados retornados contra constraints da ontologia
"""
import os
import json
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from core.ontology import get_ontology, OntologyEngine


class SemanticRouter:
    """
    Camada semântica entre o planner e as bridges.
    O LLM só escreve o texto final — o router garante que os dados são reais.
    """

    # Palavras-chave que mapeiam para entidades da ontologia
    INTENT_PATTERNS = {
        "campaign": {
            "entities": ["Campaign", "Metric", "AdSet"],
            "bridges": ["dv360_bridge", "tiktok_bridge"],
            "patterns": [
                r"\b(?:campanha|campaign|anuncio|ad|adset|roas|cpc|ctr|cpm|impressao|impression)\b",
                r"\b(?:performance|desempenho|resultado|relatorio|report|dashboard)\b",
            ]
        },
        "research": {
            "entities": ["ResearchTopic", "Claim", "Source", "Report"],
            "bridges": ["research_bridge"],
            "patterns": [
                r"\b(?:pesquisar?|research|pesquisa|estudo|artigo|topic|levantamento)\b",
                r"\b(?:cite|citação|referencia|fonte|source|claim|afirmacao)\b",
            ]
        },
        "report": {
            "entities": ["Report", "Visualization", "Claim", "Metric"],
            "bridges": ["reporter_bridge"],
            "patterns": [
                r"\b(?:relatorio|report|pdf|documento|docx|gerar.*(?:relatorio|report))\b",
            ]
        },
        "visualization": {
            "entities": ["Visualization", "Metric"],
            "bridges": ["viz_bridge"],
            "patterns": [
                r"\b(?:grafico|chart|viz|visualizac|dashboard|plot|graph|bar|pie|line|scatter|area)\b",
                r"\b(?:gerar.*(?:grafico|chart|viz|visualizac))\b",
            ]
        },
        "data": {
            "entities": ["Spreadsheet", "Metric"],
            "bridges": ["sheets_bridge"],
            "patterns": [
                r"\b(?:planilha|sheet|spreadsheet|tabela|excel|csv|json|dados?)\b",
            ]
        },
        "knowledge": {
            "entities": ["Document", "KnowledgeGraph"],
            "bridges": ["knowledge_bridge"],
            "patterns": [
                r"\b(?:documento|pdf|extrair|extract|conhecimento|knowledge|grafo|graph|processar.*pdf)\b",
            ]
        },
        "monitoring": {
            "entities": ["Observation", "Metric", "Campaign"],
            "bridges": ["observer_bridge"],
            "patterns": [
                r"\b(?:monitorar?|observar?|watcher|alerta|alert|notificacao|acompanhar?)\b",
            ]
        },
        "code": {
            "entities": [],
            "bridges": ["codex_bridge"],
            "patterns": [
                r"\b(?:codigo|código|programa|script|funcao|função|implementar|desenvolver)\b",
                r"\b(?:refatorar|refactor|bug|corrigir|deploy|terminal)\b",
            ]
        },
        "web_search": {
            "entities": ["Source"],
            "bridges": ["web_bridge", "scraper_bridge"],
            "patterns": [
                r"\b(?:pesquisar? na internet|buscar|search|web scrape|extrair.*site)\b",
            ]
        },
        "finance": {
            "entities": ["Metric"],
            "bridges": ["financial_br_bridge"],
            "patterns": [
                r"\b(?:selic|ipca|cdi|igpm|cambio|pib|desemprego|macro)\b",
                r"\b(?:acao|ação|fii|fundo imobiliario|tesouro|tesouro direto|bolsa|b3|petr4|vale3|itub4)\b",
                r"\b(?:investimento|financeiro|dividendo|provento|rentabilidade|retorno)\b",
            ]
        },
        "mcp_brasil": {
            "entities": ["GovernmentData", "Location", "PublicRecord"],
            "bridges": ["mcp_brasil_bridge"],
            "patterns": [
                r"\b(?:cnpj|cep|ibge|deputado|senador|camara|senado|tse|eleição|eleitoral)\b",
                r"\b(?:medicamento|anvisa|queimada|inpe|licitação|compras publicas|diario oficial|dou)\b",
                r"\b(?:dados públicos|dados abertos|brasil|município|estado|população)\b",
                r"\b(?:sus|saude pública|hospital|leito|doença|dengue|enem|ideb|educação)\b",
                r"\b(?:tcu|stf|stj|jurisprudência|acórdão)\b",
                r"\b(?:transferegov|emenda parlamentar|fnde|fundeb|merenda)\b",
            ]
        },
    }

    def __init__(self):
        self.ontology = get_ontology()

    def analyze(self, query: str) -> dict:
        """
        Analisa a query do usuário e retorna mapeamento semântico completo.

        Returns:
        {
            "intents": [...],        # Intenções detectadas (sorted by relevance)
            "entities": [...],       # Entidades da ontologia relevantes
            "bridges": [...],        # Bridges a serem chamadas
            "semantic_context": {...},  # Contexto anotado pra bridge
            "constraints": {...},    # Constraints a validar nos resultados
            "disambiguations": {...} # Termos desambiguados
        }
        """
        query_lower = query.lower()

        # 1. Detecta intenções
        intents = self._detect_intents(query_lower)
        primary_intent = intents[0] if intents else None

        # 2. Mapeia intenções para entidades e bridges
        entities = set()
        bridges = set()
        for intent_name, score in intents:
            intent_def = self.INTENT_PATTERNS.get(intent_name, {})
            for e in intent_def.get("entities", []):
                entities.add(e)
            for b in intent_def.get("bridges", []):
                bridges.add(b)

        # 3. Search na ontologia por contexto adicional
        search_results = self.ontology.search_entities(query_lower)
        for result in search_results:
            if result["type"] == "entity":
                entities.add(result["name"])
                # Adiciona bridges que operam essa entidade
                for b in self.ontology.get_bridge_for_entity(result["name"]):
                    bridges.add(b)

        # 4. Desambigua termos
        disambiguations = {}
        for term in self._extract_terms(query_lower):
            ctx = primary_intent[0] if primary_intent else None
            info = self.ontology.disambiguate(term, ctx)
            if not info.get("_unknown"):
                disambiguations[term] = info

        # 5. Extrai constraints
        constraints = self._extract_constraints(query_lower)

        # 6. Constrói contexto semântico
        semantic_context = self._build_semantic_context(
            query, primary_intent, list(entities), disambiguations, constraints
        )

        return {
            "intents": intents,
            "entities": sorted(entities),
            "bridges": sorted(bridges),
            "primary_bridge": list(bridges)[0] if bridges else "web_bridge",
            "semantic_context": semantic_context,
            "disambiguations": disambiguations,
            "constraints": constraints,
            "primary_intent": primary_intent[0] if primary_intent else "unknown"
        }

    def _detect_intents(self, query_lower: str) -> List[Tuple[str, float]]:
        """Detecta intenções na query baseado em padrões de palavras-chave."""
        intents = []
        for intent_name, intent_def in self.INTENT_PATTERNS.items():
            score = 0.0
            for pattern in intent_def.get("patterns", []):
                if re.search(pattern, query_lower):
                    score += 0.4
            # Bônus: palavra completa match no nome da intenção
            if intent_name in query_lower:
                score += 0.3
            # Bônus extra para palavras-chave específicas
            entity_names = intent_def.get("entities", [])
            for en in entity_names:
                if en.lower() in query_lower:
                    score += 0.2
            if score > 0:
                intents.append((intent_name, min(score, 1.0)))

        intents.sort(key=lambda x: x[1], reverse=True)

        # Se nenhuma intenção detectada, fallback para web_search
        if not intents:
            intents.append(("web_search", 0.5))

        return intents

    def _extract_terms(self, query_lower: str) -> List[str]:
        """Extrai termos candidatos a desambiguação da query."""
        disamb_terms = self.ontology.constraints.get("disambiguation", [])
        terms = []
        for entry in disamb_terms:
            term = entry.get("term", "").lower()
            if term in query_lower:
                terms.append(term)
        return terms

    def _extract_constraints(self, query_lower: str) -> dict:
        """Extrai constraints da query (datas, valores, etc)."""
        constraints = {}

        # Datas
        date_patterns = [
            (r"\b(janeiro|jan)\b", "01"),
            (r"\b(fevereiro|fev)\b", "02"),
            (r"\b(março|marco|mar)\b", "03"),
            (r"\b(abril|abr)\b", "04"),
            (r"\b(maio)\b", "05"),
            (r"\b(junho|jun)\b", "06"),
            (r"\b(julho|jul)\b", "07"),
            (r"\b(agosto|ago)\b", "08"),
            (r"\b(setembro|set)\b", "09"),
            (r"\b(outubro|out)\b", "10"),
            (r"\b(novembro|nov)\b", "11"),
            (r"\b(dezembro|dez)\b", "12"),
        ]
        for pattern, month_num in date_patterns:
            if re.search(pattern, query_lower):
                year = "2026"
                if re.search(r"\b2025\b", query_lower):
                    year = "2025"
                constraints.setdefault("periods", []).append(f"{year}-{month_num}")

        # Métricas
        if re.search(r"\b(roas|return on ad spend)\b", query_lower):
            constraints["metrics"] = constraints.get("metrics", []) + ["ROAS"]
        if re.search(r"\b(cpc|custo por clique)\b", query_lower):
            constraints["metrics"] = constraints.get("metrics", []) + ["CPC"]
        if re.search(r"\b(ctr|taxa de clique|click.?through)\b", query_lower):
            constraints["metrics"] = constraints.get("metrics", []) + ["CTR"]
        if re.search(r"\b(impressão|impressao|impression)\b", query_lower):
            constraints["metrics"] = constraints.get("metrics", []) + ["impressions"]
        if re.search(r"\b(conversão|conversao|conversion)\b", query_lower):
            constraints["metrics"] = constraints.get("metrics", []) + ["conversions"]

        # Comparações
        if re.search(r"\b(comparado|comparar|vs|versus|diferença|delta)\b", query_lower):
            constraints["comparison"] = True

        return constraints

    def _build_semantic_context(self, query: str, primary_intent: Tuple[str, float],
                                 entities: List[str], disambiguations: dict,
                                 constraints: dict) -> dict:
        """Constrói contexto semântico anotado para a bridge."""
        context = {
            "query": query,
            "intent": primary_intent[0] if primary_intent else "unknown",
            "entities": entities,
            "disambiguations": disambiguations,
            "constraints": constraints,
            "semantic_annotations": [],
        }

        # Anotações semânticas
        for ent in entities:
            ent_def = self.ontology.get_entity(ent)
            if ent_def:
                context["semantic_annotations"].append(
                    f"A query refere-se à entidade '{ent}': {ent_def.get('description', '')}"
                )

        for term, info in disambiguations.items():
            context["semantic_annotations"].append(
                f"'{term}' no contexto {primary_intent[0] if primary_intent else 'default'} "
                f"significa: {info.get('meaning', term)}"
            )

        if "periods" in constraints:
            context["semantic_annotations"].append(
                f"Períodos mencionados: {', '.join(constraints['periods'])}"
            )

        if "metrics" in constraints:
            context["semantic_annotations"].append(
                f"Métricas mencionadas: {', '.join(constraints['metrics'])}"
            )

        if constraints.get("comparison"):
            context["semantic_annotations"].append(
                "Query solicita comparação entre períodos ou entidades"
            )

        return context

    def validate_bridge_output(self, bridge_name: str, data: Any) -> Tuple[bool, str]:
        """
        Valida a saída de uma bridge contra a ontologia.
        Usado ANTES de enviar dados para o LLM.
        """
        bridge_info = self.ontology.get_bridge_info(bridge_name)
        produces = bridge_info.get("produces", [])

        if isinstance(data, dict):
            # Verifica cada entidade que a bridge produz
            for entity_name in produces:
                if entity_name == "Metric":
                    ok, msg = self.ontology.validate_metric(data)
                    if not ok:
                        return False, f"Metric inválida: {msg}"
                elif entity_name == "Claim":
                    ok, msg = self.ontology.validate_claim(data)
                    if not ok:
                        return False, f"Claim inválido: {msg}"

        return True, "ok"

    def get_agent_for_query(self, query: str) -> str:
        """
        Método de compatibilidade: retorna o nome do agente (no grafo)
        baseado na análise semântica da query.
        """
        analysis = self.analyze(query)
        primary = analysis.get("primary_intent", "unknown")
        query_lower = query.lower()

        # Mapa intenção -> agente do grafo
        intent_to_agent = {
            "campaign": "dv360",       # padrão, tiktok se mencionar tiktok
            "research": "research",
            "report": "reporter",
            "visualization": "viz",
            "data": "sheets",
            "knowledge": "knowledge",
            "monitoring": "observer",
            "code": "codex",
            "web_search": "web",
            "mcp_brasil": "mcp_brasil",
        }

        # Sobrescritas baseadas em palavras-chave específicas (mais forte que intenção)
        if "tiktok" in query_lower:
            return "tiktok"
        if "dv360" in query_lower or "display & video" in query_lower:
            return "dv360"
        if "scrape" in query_lower or "extrair" in query_lower:
            return "scraper"
        if "grafico" in query_lower or "gráfico" in query_lower or "chart" in query_lower:
            return "viz"
        if "planilha" in query_lower or "sheet" in query_lower:
            return "sheets"
        if "monitor" in query_lower:
            return "observer"
        if "codigo" in query_lower or "código" in query_lower or "implement" in query_lower:
            return "codex"
        # MCP-Brasil: palavras-chave de dados públicos brasileiros
        if any(w in query_lower for w in ["cnpj", "cep", "ibge", "deputado", "senador",
                                           "camara", "senado", "tse", "eleição", "eleitoral",
                                           "anvisa", "medicamento", "queimada", "inpe",
                                           "licitação", "comprasnet", "diario oficial", "dou",
                                           "sus", "leito", "dengue", "enem", "ideb",
                                           "transferegov", "emenda parlamentar", "fnde",
                                           "jurisprudência", "acórdão"]):
            return "mcp_brasil"

        # Finance
        if any(w in query_lower for w in ["selic", "ipca", "cdi", "macro", "pib", "cambio",
                                            "fii", "fundo imobiliario", "tesouro", "bolsa",
                                            "b3", "investimento", "dividendo", "provento",
                                            "petr4", "vale3", "itub4", "bbas3", "mglu3"]):
            return "finance"

        # Se detectou campanha + comparação, vai pra dv360
        if primary == "campaign":
            if "compare" in query_lower or "compar" in query_lower or "vs" in query_lower:
                return "dv360"
            if "maio" in query_lower or "abril" in query_lower:
                return "dv360"
            return "dv360"

        return intent_to_agent.get(primary, "web")

    def routing_summary(self, query: str) -> str:
        """Resumo legível do roteamento semântico."""
        analysis = self.analyze(query)
        agent = self.get_agent_for_query(query)

        lines = [
            f"🔍 Análise semântica da query",
            f"Query: {query[:80]}...",
            f"Intenção primária: {analysis['primary_intent']}",
            f"Entidades detectadas: {', '.join(analysis['entities']) or 'nenhuma'}",
            f"Bridge(s) selecionada(s): {', '.join(analysis['bridges']) or 'web_bridge'}",
            f"Agente no grafo: {agent}",
        ]

        if analysis["disambiguations"]:
            lines.append("Desambiguações:")
            for term, info in analysis["disambiguations"].items():
                lines.append(f"  • {term} → {info.get('meaning')} ({info.get('unit', '')})")

        if analysis["constraints"].get("periods"):
            lines.append(f"Períodos: {', '.join(analysis['constraints']['periods'])}")

        if analysis["constraints"].get("metrics"):
            lines.append(f"Métricas: {', '.join(analysis['constraints']['metrics'])}")

        return "\n".join(lines)


# =====================================================================
# SINGLETON
# =====================================================================
_semantic_router = None


def get_semantic_router() -> SemanticRouter:
    global _semantic_router
    if _semantic_router is None:
        _semantic_router = SemanticRouter()
    return _semantic_router


# =====================================================================
# CLI DE TESTE
# =====================================================================
if __name__ == "__main__":
    router = get_semantic_router()

    test_queries = [
        "Qual o ROAS da campanha de maio?",
        "Pesquise sobre impacto da IA no marketing digital 2026",
        "Gere um relatório em PDF sobre os resultados",
        "Crie um gráfico de barras com as impressões",
        "Monitore a campanha de display e me avise se o CPC subir",
        "Extraia os dados desse PDF",
        "Crie uma planilha com os dados de CPC e CPM",
        "Compare as campanhas de abril e maio no DV360",
        "Como está a campanha do TikTok?",
    ]

    for q in test_queries:
        print("\n" + "=" * 60)
        print(router.routing_summary(q))
        print("=" * 60)
