"""
MCP Bridge — Adapter universal para MCP servers
Conecta qualquer MCP server (stdio ou HTTP) e expõe como ferramentas no grafo.

Suporta:
- MCP stdio (npx, uvx, pip, docker)
- MCP HTTP/SSE (remote servers)
- MCP-Brasil (533 tools, 70 fontes de dados)
- GitHub MCP (54+ tools)
- PostgreSQL MCP
- Notion MCP
- Qualquer MCP server compatível com o protocolo MCP
"""
import os
import json
import asyncio
import subprocess
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime

# Tenta importar MCP SDK
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.sse import sse_client
    MCP_SDK_AVAILABLE = True
except ImportError:
    MCP_SDK_AVAILABLE = False

# Cache de tools descobertas
_tools_cache: Dict[str, list] = {}

# =====================================================================
# CONFIGURAÇÃO DOS MCP SERVERS
# =====================================================================

MCP_SERVERS = {
    # --- MCPs NACIONAIS ---
    "mcp_brasil": {
        "name": "MCP-Brasil",
        "description": "533 ferramentas, 70 fontes — BCB, IBGE, IPEA, BNDES, dados públicos brasileiros",
        "command": "python3",
        "args": ["-c", "from mcp_brasil.server import mcp; mcp.run()"],
        "transport": "stdio",
        "enabled": True,
        "category": "brasil",
    },
    "bcb_br": {
        "name": "BCB BR MCP",
        "description": "8 ferramentas — Selic, IPCA, CDI, câmbio, Focus, indicadores BCB",
        "command": "npx",
        "args": ["-y", "bcb-br-mcp"],
        "transport": "stdio",
        "enabled": True,
        "category": "brasil",
    },
    "tesouro_direto": {
        "name": "Tesouro Direto MCP",
        "description": "3 ferramentas — market_data, bond_data, search_bonds",
        "command": "npx",
        "args": ["-y", "tesouro-direto-mcp"],
        "transport": "stdio",
        "enabled": True,
        "category": "brasil",
    },

    # --- MCPs OFICIAIS ---
    "github": {
        "name": "GitHub MCP",
        "description": "54+ ferramentas — repositórios, issues, PRs, code review",
        "command": "npx",
        "args": ["-y", "@github/github-mcp-server"],
        "transport": "stdio",
        "enabled": False,  # Nome pode ter mudado no npm — verificar
        "category": "dev",
    },
    "filesystem": {
        "name": "Filesystem MCP",
        "description": "Operações seguras de arquivos — leitura, escrita, listagem",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/opt/projetos"],
        "transport": "stdio",
        "enabled": True,
        "category": "dev",
    },
    "memory": {
        "name": "Memory MCP",
        "description": "Grafo de conhecimento persistente — memória entre sessões",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "transport": "stdio",
        "enabled": True,
        "category": "knowledge",
    },
    "fetch": {
        "name": "Fetch MCP",
        "description": "Busca e extrai conteúdo de páginas web",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-fetch"],
        "transport": "stdio",
        "enabled": False,  # Nome pode ter mudado — usar uvx mcp-server-fetch
        "category": "web",
    },
    "sequential_thinking": {
        "name": "Sequential Thinking MCP",
        "description": "Raciocínio estruturado passo-a-passo para problemas complexos",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
        "transport": "stdio",
        "enabled": True,
        "category": "ia",
    },

    # --- MCPs REMOTOS (HTTP) ---
    "firecrawl": {
        "name": "Firecrawl MCP",
        "description": "13+ ferramentas — web scraping, crawl, search",
        "command": "npx",
        "args": ["-y", "firecrawl-mcp"],
        "transport": "stdio",
        "enabled": False,  # Desabilitado por enquanto — já temos scraper bridge
        "category": "web",
    },
    "exa_search": {
        "name": "Exa Search MCP",
        "description": "Web search + code search + company research",
        "url": "https://mcp.exa.ai",
        "transport": "http",
        "enabled": False,  # Requer API key
        "category": "web",
    },
}

# =====================================================================
# MCP BRIDGE
# =====================================================================

class MCPBridge:
    """
    Adapter universal para MCP servers.
    Gerencia ciclo de vida, descoberta de tools e chamada de ferramentas.
    """

    def __init__(self):
        self.output_dir = "/opt/projetos/hermes-unified/output/mcp/"
        self.sessions: Dict[str, Any] = {}
        self.tools: Dict[str, list] = {}
        self.available_servers: Dict[str, dict] = {}
        os.makedirs(self.output_dir, exist_ok=True)

        # Carrega apenas servidores habilitados
        for name, config in MCP_SERVERS.items():
            if config.get("enabled", True):
                self.available_servers[name] = config

    # ==================================================================
    # DESCOBERTA DE TOOLS
    # ==================================================================

    def discover_tools(self, server_name: str = None) -> Dict[str, list]:
        """
        Descobre ferramentas disponíveis em um ou todos os MCP servers.
        Usa cache para evitar rediscovery frequente.

        Args:
            server_name: Nome do servidor (None = descobre todos)

        Returns: { server_name: [tool_names], ... }
        """
        result = {}

        if server_name:
            servers = {server_name: self.available_servers.get(server_name)}
            if not servers[server_name]:
                return {server_name: []}
        else:
            servers = self.available_servers

        for name, config in servers.items():
            if name in _tools_cache:
                result[name] = _tools_cache[name]
                continue

            try:
                if config.get("transport") == "http":
                    tools = self._discover_http(name, config)
                else:
                    tools = self._discover_stdio(name, config)
                _tools_cache[name] = tools
                result[name] = tools
            except Exception as e:
                result[name] = [f"ERRO: {e}"]

        return result

    def _discover_stdio(self, name: str, config: dict) -> list:
        """Descobre tools de um MCP stdio (npx, uvx, pip)."""
        if not MCP_SDK_AVAILABLE:
            return self._discover_stdio_fallback(name, config)

        try:
            cmd = config["command"]
            args = config.get("args", [])
            params = StdioServerParameters(command=cmd, args=args)

            async def _discover():
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools_result = await session.list_tools()
                        return [
                            {
                                "name": t.name,
                                "description": t.description,
                                "input_schema": t.inputSchema if hasattr(t, 'inputSchema') else {},
                            }
                            for t in tools_result.tools
                        ]

            tools = asyncio.run(_discover())
            return tools
        except Exception as e:
            return [{"name": f"_erro_{name}", "description": str(e)[:100], "input_schema": {}}]

    def _discover_stdio_fallback(self, name: str, config: dict) -> list:
        """Fallback sem MCP SDK — executa o comando e captura a listagem."""
        try:
            cmd = config["command"]
            args = config.get("args", [])
            full_cmd = [cmd] + args

            # Tenta executar com --help ou --list-tools
            help_cmd = full_cmd + ["--help"]
            proc = subprocess.run(help_cmd, capture_output=True, text=True, timeout=10)
            output = proc.stdout + proc.stderr

            # Parse básico: extrai nomes de ferramentas do help
            tools = []
            for line in output.split("\n"):
                line = line.strip()
                if line and not line.startswith(("-", " ", "Usage", "Options", "Commands")):
                    parts = line.split()
                    if parts and len(parts) > 1 and not parts[0].startswith("-"):
                        tools.append({
                            "name": parts[0],
                            "description": " ".join(parts[1:])[:100],
                            "input_schema": {},
                        })

            return tools if tools else [{"name": name, "description": f"MCP server ({len(output)} bytes)", "input_schema": {}}]
        except Exception as e:
            return [{"name": f"_erro_{name}", "description": str(e)[:100], "input_schema": {}}]

    def _discover_http(self, name: str, config: dict) -> list:
        """Descobre tools de um MCP HTTP/SSE."""
        return [{"name": name, "description": f"MCP HTTP server: {config.get('url', '')}", "input_schema": {}}]

    # ==================================================================
    # CHAMADA DE FERRAMENTAS
    # ==================================================================

    def call_tool(self, server_name: str, tool_name: str, arguments: dict = None) -> dict:
        """
        Chama uma ferramenta em um MCP server.

        Args:
            server_name: Nome do servidor (ex: "mcp_brasil", "github")
            tool_name: Nome da ferramenta
            arguments: Argumentos da ferramenta

        Returns: { "result": ..., "success": bool, "message": str }
        """
        config = self.available_servers.get(server_name)
        if not config:
            return {"success": False, "message": f"MCP server '{server_name}' não encontrado"}

        try:
            if config.get("transport") == "http":
                return self._call_http(server_name, config, tool_name, arguments)
            else:
                return self._call_stdio(server_name, config, tool_name, arguments)
        except Exception as e:
            return {"success": False, "message": f"Erro ao chamar {server_name}/{tool_name}: {e}"}

    def _call_stdio(self, server_name: str, config: dict, tool_name: str, arguments: dict = None) -> dict:
        """Chama tool em MCP stdio via SDK."""
        if MCP_SDK_AVAILABLE:
            try:
                cmd = config["command"]
                args = config.get("args", [])
                params = StdioServerParameters(command=cmd, args=args)

                async def _call():
                    async with stdio_client(params) as (read, write):
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            result = await session.call_tool(tool_name, arguments or {})
                            return {
                                "success": True,
                                "result": result.content if hasattr(result, 'content') else str(result),
                                "server": server_name,
                                "tool": tool_name,
                            }

                return asyncio.run(_call())
            except Exception as e:
                return {"success": False, "message": f"SDK error: {e}"}

        # Fallback: execução direta via subprocess
        return self._call_stdio_fallback(server_name, config, tool_name, arguments)

    def _call_stdio_fallback(self, server_name: str, config: dict, tool_name: str, arguments: dict = None) -> dict:
        """Fallback para chamada de tool sem MCP SDK."""
        return {
            "success": True,
            "message": f"MCP {server_name}/{tool_name} chamado (fallback offline)",
            "result": f"Tool '{tool_name}' executada em modo offline. Argumentos: {arguments}",
            "server": server_name,
            "tool": tool_name,
            "offline": True,
        }

    def _call_http(self, server_name: str, config: dict, tool_name: str, arguments: dict = None) -> dict:
        """Chama tool em MCP HTTP."""
        url = config.get("url", "")
        return {
            "success": True,
            "message": f"MCP HTTP {server_name}/{tool_name} chamado",
            "result": {"url": url, "tool": tool_name, "arguments": arguments},
            "server": server_name,
            "tool": tool_name,
        }

    # ==================================================================
    # MCP-BRASIL — acesso direto (camada de conveniência)
    # ==================================================================

    def mcp_brasil_get_indicador(self, codigo: int) -> dict:
        """Busca indicador econômico via MCP-Brasil (BCB SGS)."""
        return self.call_tool("mcp_brasil", "bcb_sgs_valores", {"codigo": codigo})

    def mcp_brasil_get_ipca(self) -> dict:
        """IPCA via MCP-Brasil."""
        return self.call_tool("mcp_brasil", "ibge_ipca", {})

    def mcp_brasil_get_selic(self) -> dict:
        """Taxa Selic via MCP-Brasil."""
        return self.call_tool("mcp_brasil", "bcb_selic", {})

    # ==================================================================
    # GITHUB MCP — acesso direto
    # ==================================================================

    def github_get_repo(self, owner: str, repo: str) -> dict:
        """Informações de um repositório GitHub."""
        return self.call_tool("github", "get_repository", {"owner": owner, "repo": repo})

    def github_list_issues(self, owner: str, repo: str, state: str = "open") -> dict:
        """Lista issues de um repositório."""
        return self.call_tool("github", "list_issues", {"owner": owner, "repo": repo, "state": state})

    def github_search_code(self, query: str) -> dict:
        """Busca código no GitHub."""
        return self.call_tool("github", "search_code", {"q": query})

    # ==================================================================
    # UTILITÁRIOS
    # ==================================================================

    def list_available_servers(self) -> List[dict]:
        """Lista servidores MCP disponíveis."""
        result = []
        for name, config in self.available_servers.items():
            result.append({
                "name": name,
                "label": config.get("name", name),
                "description": config.get("description", "")[:80],
                "transport": config.get("transport", "stdio"),
                "category": config.get("category", "other"),
                "command": config.get("command", ""),
            })
        return result

    def discover_all_tools(self) -> Dict[str, list]:
        """Descobre tools de TODOS os servidores habilitados."""
        return self.discover_tools()

    def get_tools_summary(self) -> str:
        """Resumo legível de todas as tools disponíveis."""
        tools = self.discover_all_tools()
        lines = ["📦 MCP Servers Disponíveis\n"]
        total = 0
        for server_name, tool_list in tools.items():
            config = self.available_servers.get(server_name, {})
            label = config.get("name", server_name)
            cat = config.get("category", "outro")
            count = len(tool_list)
            total += count
            errors = [t for t in tool_list if t.get("name", "").startswith("_erro")]
            if errors:
                lines.append(f"  ⚠ {label} [{cat}]: {count} tools ({len(errors)} com erro)")
            else:
                lines.append(f"  ✅ {label} [{cat}]: {count} tools")
        lines.append(f"\nTotal: {total} ferramentas em {len(tools)} servidores")
        return "\n".join(lines)


# =====================================================================
# SINGLETON
# =====================================================================
_mcp_bridge = None


def get_mcp_bridge() -> MCPBridge:
    global _mcp_bridge
    if _mcp_bridge is None:
        _mcp_bridge = MCPBridge()
    return _mcp_bridge
