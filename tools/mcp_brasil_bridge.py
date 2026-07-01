"""
MCP-Brasil Bridge — 307+ ferramentas de dados públicos brasileiros
Features: BCB, IBGE, IPEA, BNDES, BrasilAPI, Câmara, Senado, TSE,
ANVISA, INPE, ComprasNet, Diário Oficial, SUS, INEP, TCEs, e mais.

Acesso direto via batch._dispatch (async → sync com asyncio.run()).
"""
import asyncio
import inspect
import json
import re
from typing import Dict, List, Optional, Any
from pathlib import Path

# Import da infra do MCP-Brasil (import server primeiro para trigger build_dispatch)
import mcp_brasil.server  # noqa: F401 — garante que o server inicialize o dispatch
from mcp_brasil._shared.batch import _dispatch


class MCPBrasilDirectBridge:
    """Bridge direta para o MCP-Brasil via batch dispatch."""

    def __init__(self):
        self.output_dir = "/opt/projetos/hermes-unified/output/mcp_brasil/"
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        self._dispatch = _dispatch
        self._features = self._build_feature_map()

    def _build_feature_map(self) -> dict:
        """Constrói mapa feature → [tool_names] a partir do _dispatch."""
        features = {}
        for tool_key in self._dispatch:
            parts = tool_key.split("_", 1)
            feat = parts[0] if len(parts) > 1 else "geral"
            features.setdefault(feat, []).append(tool_key)
        return features

    def status(self) -> dict:
        total_tools = len(self._dispatch)
        features = self._features
        return {
            "online": True,
            "total_features": len(features),
            "features": list(features.keys()),
            "total_tools": total_tools,
        }

    def list_features(self) -> dict:
        """Lista features com suas tools."""
        return self._features

    def call_tool(self, tool_name: str, **kwargs) -> dict:
        """
        Chama uma ferramenta diretamente pelo nome do dispatch.
        Ex: 'brasilapi_consultar_cep', 'camara_listar_deputados'
        """
        fn = self._dispatch.get(tool_name)
        if fn is None:
            return {"success": False, "message": f"Tool '{tool_name}' não encontrada. Disponíveis: {len(self._dispatch)} tools"}

        try:
            # Verifica se a função precisa de 'ctx'
            sig = inspect.signature(fn)
            call_kwargs = dict(kwargs)
            if "ctx" in sig.parameters:
                # Cria um contexto mock com métodos async
                class _MockCtx:
                    async def info(self, msg): pass
                    async def debug(self, msg): pass
                    async def error(self, msg): pass
                    async def warning(self, msg): pass
                call_kwargs["ctx"] = _MockCtx()

            result = asyncio.run(fn(**call_kwargs))

            return {
                "success": True,
                "tool": tool_name,
                "result": result,
            }
        except Exception as e:
            return {"success": False, "message": f"Erro em {tool_name}: {e}"}

    def call_feature(self, feature: str, **kwargs) -> dict:
        """
        Chama a primeira ferramenta de uma feature.
        """
        tools = self._features.get(feature, [])
        if not tools:
            return {"success": False, "message": f"Feature '{feature}' sem tools"}
        return self.call_tool(tools[0], **kwargs)

    # ==================================================================
    # ACESSO RÁPIDO — features mais usadas
    # ==================================================================

    def bacen_get(self, codigo: int = 11) -> dict:
        """Série do BCB pelo código SGS."""
        return self.call_feature("bacen", codigo=codigo)

    def brasilapi_cep(self, cep: str) -> dict:
        """Busca CEP via BrasilAPI."""
        return self.call_feature("brasilapi", cep=cep)

    def brasilapi_cnpj(self, cnpj: str) -> dict:
        """Busca CNPJ via BrasilAPI."""
        return self.call_feature("brasilapi", cnpj=cnpj)

    # ==================================================================
    # BUSCA INTELIGENTE
    # ==================================================================

    def buscar(self, query: str) -> List[dict]:
        """
        Busca inteligente — detecta feature pela query e chama a tool.
        Usa call_tool com nome específico da ferramenta.
        """
        query_lower = query.lower()

        # Mapeamento: palavra-chave → (tool_name, kwargs)
        intent_map = {
            "brasilapi": {"tool": "brasilapi_consultar_cep", "kwarg": "cep", "keywords": ["cep"]},
            "cnpj": {"tool": "brasilapi_consultar_cnpj", "kwarg": "cnpj", "keywords": ["cnpj"]},
            "bacen_selic": {"tool": "bacen_indicadores_atuais", "keywords": ["selic", "juros"]},
            "bacen_ipca": {"tool": "bacen_indicadores_atuais", "keywords": ["ipca", "inflação"]},
            "bacen_cambio": {"tool": "bacen_indicadores_atuais", "keywords": ["câmbio", "dólar"]},
            "bacen_pib": {"tool": "bacen_indicadores_atuais", "keywords": ["pib"]},
            "camara_deputados": {"tool": "camara_listar_deputados", "keywords": ["deputado", "câmara", "câmara"]},
            "senado_senadores": {"tool": "senado_listar_senadores", "keywords": ["senador", "senado"]},
            "tse_eleicoes": {"tool": "tse_listar_eleicoes", "keywords": ["eleição", "candidato", "urna", "tse"]},
            "ibge_populacao": {"tool": "ibge_obter_populacao", "keywords": ["população", "ibge", "censo"]},
            "inpe_queimadas": {"tool": "inpe_listar_queimadas", "keywords": ["queimada", "desmatamento"]},
            "anvisa_medicamento": {"tool": "anvisa_buscar_medicamento", "keywords": ["medicamento", "remédio", "bula", "anvisa"]},
            "compras_licitacoes": {"tool": "compras_listar_licitacoes", "keywords": ["licitação", "contrato", "compras pública", "pregão"]},
            "diario_oficial": {"tool": "diario_oficial_buscar", "keywords": ["diário oficial", "dou", "nomeação", "portaria"]},
            "transferegov": {"tool": "transferegov_listar_emendas", "keywords": ["emenda", "transferência", "pix"]},
            "saude_dengue": {"tool": "saude_alertas_dengue", "keywords": ["dengue", "chikungunya", "zika"]},
            "inep_ideb": {"tool": "inep_consultar_ideb", "keywords": ["ideb", "enem", "educação", "escola"]},
            "bndes": {"tool": "bndes_listar_operacoes", "keywords": ["bndes", "financiamento"]},
            "tcu": {"tool": "tcu_consultar_acordao", "keywords": ["tcu", "acórdão"]},
            "jurisprudencia": {"tool": "jurisprudencia_buscar", "keywords": ["stf", "stj", "jurisprudência"]},
            "fnde": {"tool": "fnde_consultar_fundeb", "keywords": ["fundeb", "merenda", "livro didático"]},
            "atlas_violencia": {"tool": "atlas_violencia_consultar", "keywords": ["violência", "homicídio", "segurança"]},
            "saude_hospital": {"tool": "saude_listar_estabelecimentos", "keywords": ["hospital", "leito", "sus", "saúde", "doença"]},
        }

        results = []
        for key, config in intent_map.items():
            keywords = config["keywords"]
            if any(kw in query_lower for kw in keywords):
                tool_name = config["tool"]
                # Extrai valor do argumento se for uma keyword como cep/cnpj
                if "kwarg" in config and "value" in config:
                    kwargs = {config["kwarg"]: config["value"]}
                elif "kwarg" in config and config["kwarg"] in ["cep", "cnpj"]:
                    # Tenta extrair o valor numérico da query
                    import re
                    match = re.search(r'\b(\d{8})\b', query) if config["kwarg"] == "cep" else re.search(r'\b(\d{14})\b', query)
                    if match:
                        kwargs = {config["kwarg"]: match.group(1)}
                    else:
                        kwargs = {}
                else:
                    kwargs = {}

                result = self.call_tool(tool_name, **kwargs)
                results.append({
                    "feature": key,
                    "query": query,
                    "result": result,
                })

        if not results:
            # Fallback: lista status
            results.append({
                "feature": "status",
                "query": query,
                "result": {"success": True, "message": f"{len(self._dispatch)} tools disponíveis em {len(self._features)} features"}
            })

        return results[:5]


# =====================================================================
# SINGLETON
# =====================================================================
_mcp_brasil_bridge = None


def get_mcp_brasil_bridge() -> MCPBrasilDirectBridge:
    global _mcp_brasil_bridge
    if _mcp_brasil_bridge is None:
        _mcp_brasil_bridge = MCPBrasilDirectBridge()
    return _mcp_brasil_bridge
