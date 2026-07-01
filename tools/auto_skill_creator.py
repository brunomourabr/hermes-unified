#!/usr/bin/env python3
"""
Auto Skill Creator - Sugestao automatica de criacao de skills.

Monitora tool calls por tarefa e sugere salvar como skill
quando detecta 5+ tool calls na mesma sequencia.

Singleton + get_bridge() pattern, integrado com graph.py.

Metodo principal:
    check_and_suggest_skill(last_agent, messages, tool_calls_count) -> dict

Retorna:
    {"suggested": bool, "skill_name": str or None,
     "skill_path": str or None, "message": str}
"""

import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# =============================================
# CONSTANTES
# =============================================

COUNTER_FILE = Path("/opt/projetos/hermes-unified/.session_skill_counter.json")
SKILLS_BASE = Path("/opt/data/skills")
TOOL_CALL_THRESHOLD = 5

# Categorias validas para skills (reflete a estrutura de /opt/data/skills/)
VALID_CATEGORIES = [
    "ai-ml", "apple", "autonomous-ai-agents", "creative", "data-science",
    "devops", "diagramming", "domain", "email", "feeds", "financeiro-multi-fonte",
    "gaming", "gifs", "github", "inference-sh", "mcp", "media", "mlops",
    "note-taking", "production-agentic-rag", "productivity", "research",
    "scraping-with-firecrawl", "smart-home", "social-media", "software-development",
]

# Subistrings que ajudam a inferir categoria da mensagem
_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "software-development": [
        "codigo", "código", "code", "python", "javascript", "typescript",
        "programar", "script", "funcao", "função", "função", "funcao", "api",
        "endpoint", "bug", "refatorar", "refactor", "test", "teste",
        "deploy", "git", "github", "pull request", "pr", "commit",
    ],
    "data-science": [
        "analise", "análise", "analise de dados", "data science", "dataframe",
        "pandas", "numpy", "estatistica", "estatística", "grafico", "gráfico",
        "plot", "chart", "ml", "machine learning", "deep learning", "dataset",
        "treinamento", "modelo", "predicao", "previsão", "features",
    ],
    "research": [
        "pesquisa", "research", "artigo", "paper", "levantamento",
        "investigacao", "investigação", "estudo", "relatorio", "relatório",
        "report", "documentacao", "documentação", "citar", "citacao", "citação",
        "referencia", "referência", "bibliografia", "fonte", "source",
    ],
    "devops": [
        "docker", "kubernetes", "k8s", "deploy", "infra", "infraestrutura",
        "terraform", "ansible", "ci/cd", "pipeline", "monitoramento",
        "nginx", "linux", "servidor", "cloud", "aws", "gcp", "azure",
    ],
    "productivity": [
        "automacao", "automação", "automacao", "automatizar", "workflow",
        "produtividade", "organizar", "organizacao", "organização",
        "gerenciar", "gerenciamento", "tarefa", "tarefas", "todo",
        "notificacao", "notificação", "alerta", "lembrete",
    ],
    "creative": [
        "escrever", "criar", "criativo", "conteudo", "conteúdo",
        "texto", "artigo", "blog", "post", "redacao", "redação",
        "copywriting", "marketing", "storytelling", "narrativa",
    ],
}

# =============================================
# SINGLETON
# =============================================

_auto_skill_creator_instance = None


def get_bridge():
    """Retorna a instancia singleton do AutoSkillCreator."""
    global _auto_skill_creator_instance
    if _auto_skill_creator_instance is None:
        _auto_skill_creator_instance = AutoSkillCreator()
    return _auto_skill_creator_instance


# =============================================
# ESTADO DO CONTADOR (JSON)
# =============================================

def _load_counter() -> dict:
    """Carrega o contador do arquivo JSON."""
    if COUNTER_FILE.exists():
        try:
            with open(COUNTER_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Erro ao ler contador: {e}")
    return {}


def _save_counter(data: dict) -> None:
    """Salva o contador no arquivo JSON."""
    try:
        COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(COUNTER_FILE, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError as e:
        logger.error(f"Erro ao salvar contador: {e}")


def _now_iso() -> str:
    """Retorna timestamp ISO8601 sem dependencias externas."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# =============================================
# AUTO SKILL CREATOR
# =============================================

class AutoSkillCreator:
    """Monitora tool calls e sugere criacao de skills."""

    def __init__(self):
        self._suggested_in_session: set = set()  # Evita sugerir a mesma skill 2x

    # --------------------------------------------------
    # API PUBLICA
    # --------------------------------------------------

    def check_and_suggest_skill(
        self,
        last_agent: str,
        messages: list,
        tool_calls_count: int,
        objective: str = "",
    ) -> dict:
        """Metodo principal: verifica contagem e sugere criacao de skill.

        Args:
            last_agent: Nome do ultimo agente que executou (e.g. "codex", "web")
            messages: Lista de mensagens da conversa/estado
            tool_calls_count: Numero de tool calls nesta sequencia/tarefa
            objective: Objetivo/task description da tarefa (opcional)

        Returns:
            dict com:
                suggested: bool - se uma sugestao foi gerada
                skill_name: str or None - nome sugerido para a skill
                skill_path: str or None - caminho onde seria salva
                message: str - mensagem para o usuario/LLM
        """
        # Atualiza contador
        sequence_id = self._get_or_create_sequence(objective)
        counter = _load_counter()
        seq_data = counter.get(sequence_id, {"tool_calls": 0, "agents": [], "last_update": _now_iso()})

        seq_data["tool_calls"] = seq_data.get("tool_calls", 0) + tool_calls_count
        if last_agent and last_agent not in seq_data.get("agents", []):
            seq_data.setdefault("agents", []).append(last_agent)
        seq_data["last_update"] = _now_iso()
        counter[sequence_id] = seq_data
        _save_counter(counter)

        total_tool_calls = seq_data["tool_calls"]

        # So sugere quando atinge o threshold
        if total_tool_calls < TOOL_CALL_THRESHOLD:
            return {
                "suggested": False,
                "skill_name": None,
                "skill_path": None,
                "message": f"Monitorando: {total_tool_calls}/{TOOL_CALL_THRESHOLD} tool calls.",
            }

        # Ja sugeriu nesta sessao?
        if sequence_id in self._suggested_in_session:
            return {
                "suggested": False,
                "skill_name": None,
                "skill_path": None,
                "message": f"Skill ja sugerida para esta sequencia.",
            }

        # Extrai nome e metadados da skill a partir do contexto
        skill_name = self._extract_skill_name(objective, messages)
        if not skill_name:
            skill_name = self._generate_skill_name(objective, messages)

        category = self._infer_category(objective, messages)
        skill_path = str(SKILLS_BASE / category / skill_name)

        # Extrai descricao e procedimento
        description = self._extract_description(objective, messages)
        procedure = self._extract_procedure(messages)

        # Salva a sugestao (sem criar a skill de fato)
        suggestion = self._save_suggestion(
            sequence_id, skill_name, category, description, procedure,
        )

        # Marca como sugerido
        self._suggested_in_session.add(sequence_id)

        # Tambem marca no JSON que ja foi sugerido
        counter[sequence_id]["suggested"] = True
        counter[sequence_id]["suggested_skill"] = skill_name
        counter[sequence_id]["suggested_at"] = _now_iso()
        _save_counter(counter)

        return {
            "suggested": True,
            "skill_name": skill_name,
            "skill_path": skill_path,
            "message": (
                f"Detectei {total_tool_calls} tool calls nesta tarefa! "
                f"Sugiro criar uma skill '{skill_name}' (categoria: {category}). "
                f"Use o comando 'skill_manage action=create' se quiser salvar. "
                f"Sugestao salva em: .session_skill_suggestions/{sequence_id}.json"
            ),
        }

    # --------------------------------------------------
    # EXTRACAO DE METADADOS
    # --------------------------------------------------

    def _extract_skill_name(self, objective: str, messages: list) -> Optional[str]:
        """Tenta extrair um nome de skill significativo do contexto."""
        candidates = []

        # Priority 1: objective (always best source)
        if objective and len(objective) > 5:
            name = self._sanitize_name(objective)
            if name and 3 <= len(name) <= 64:
                candidates.append(name)

        # Priority 2: ultima mensagem do usuario (busca a primeira mensagem, nao tool outputs)
        for msg in reversed(messages):
            if hasattr(msg, "content") and isinstance(msg.content, str):
                content = msg.content.strip()
                # Ignora mensagens de sistema/ferramenta (CODEX:, WEB:, etc)
                if content and len(content) > 10 and len(content) < 300:
                    # Prefere mensagens que NAO começam com codigo de agente
                    if not re.match(r'^(CODEX|WEB|KNOWLEDGE|INTEGRATOR|SCRAPE|VIZ|SHEETS|REPORT|DV360|RESEARCH|FINANCE|OBSERVER|MCP_BRASIL|VISION):', content):
                        name = self._sanitize_name(content)
                        if name and 3 <= len(name) <= 64:
                            candidates.append(name)
                            break

        # Priority 3: extrair substantivo-chave do objective (camelCase/PascalCase words)
        if objective:
            for word in re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', objective)[:3]:
                clean = word.lower().replace(" ", "-").replace("_", "-")
                clean = re.sub(r'[^a-z0-9\-]', '', clean)
                if 3 <= len(clean) <= 64:
                    candidates.append(clean)

        if not candidates:
            return None

        # Prefere o nome mais descritivo (mais longo), nao o mais curto
        candidates.sort(key=len, reverse=True)
        return candidates[0][:64]

    def _generate_skill_name(self, objective: str, messages: list) -> str:
        """Gera um nome fallback quando a extracao falha."""
        if objective:
            words = re.findall(r'\b\w+\b', objective.lower())
            # Filtra palavras comuns
            stopwords = {"de", "da", "do", "em", "para", "com", "um", "uma",
                         "os", "as", "e", "ou", "a", "o", "que", "se", "por"}
            content_words = [w for w in words if w not in stopwords and len(w) > 2]
            if content_words:
                base = "-".join(content_words[:3])
                return base[:64]
        return f"auto-skill-{uuid.uuid4().hex[:8]}"

    def _extract_description(self, objective: str, messages: list) -> str:
        """Extrai descricao do objetivo ou contexto."""
        if objective and len(objective) > 10:
            return objective[:1024]

        for msg in reversed(messages):
            if hasattr(msg, "content") and isinstance(msg.content, str):
                content = msg.content.strip()
                if len(content) > 10:
                    return content[:1024]

        return "Skill criada automaticamente a partir de sequencia de tool calls."

    def _extract_procedure(self, messages: list) -> str:
        """Extrai o procedimento executado a partir das mensagens."""
        steps = []
        for msg in messages:
            if hasattr(msg, "content") and isinstance(msg.content, str):
                content = msg.content.strip()
                # Pega mensagens que parecem passos (CODEX:, WEB:, etc)
                if content and (":" in content or content.startswith("-") or content[0].isdigit()):
                    steps.append(content)

        if not steps:
            # Fallback: pega as ultimas N mensagens como procedimento
            for msg in messages[-10:]:
                if hasattr(msg, "content") and isinstance(msg.content, str):
                    c = msg.content.strip()
                    if c and len(c) > 5:
                        steps.append(c)

        if not steps:
            return "Procedimento nao disponivel. Consulte o arquivo de sugestao para detalhes."

        return "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))

    def _infer_category(self, objective: str, messages: list) -> str:
        """Tenta inferir a categoria da skill a partir do contexto."""
        # Junta texto do objective + mensagens
        text = (objective + " " + " ".join(
            m.content for m in messages[-5:]
            if hasattr(m, "content") and isinstance(m.content, str)
        )).lower()

        scores = {}
        for cat, keywords in _CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in text)
            if score > 0:
                scores[cat] = score

        if scores:
            best = max(scores, key=scores.get)
            return best

        # Fallback: usa o ultimo agente
        agent_to_category = {
            "codex": "software-development",
            "knowledge": "research",
            "web": "research",
            "scraper": "research",
            "viz": "data-science",
            "sheets": "productivity",
            "reporter": "research",
            "dv360": "ai-ml",
            "research": "research",
            "finance": "data-science",
            "mcp_brasil": "devops",
        }
        for msg in reversed(messages):
            if hasattr(msg, "content") and isinstance(msg.content, str):
                for agent, cat in agent_to_category.items():
                    if agent.upper() in msg.content.upper():
                        return cat

        return "productivity"

    # --------------------------------------------------
    # FORMATACAO SKILL.md
    # --------------------------------------------------

    def _format_skill_md(self, name: str, description: str, category: str,
                         procedure: str) -> str:
        """Formata o conteudo de um SKILL.md valido."""
        # Sanitiza nome para path
        safe_name = name.lower().replace(" ", "-").replace("_", "-")
        safe_name = re.sub(r'[^a-z0-9\-]', '', safe_name)

        return f"""---
name: {safe_name[:64]}
description: {description[:1024]}
version: 1.0.0
author: Hermes Auto-Skill
license: MIT
metadata:
  hermes:
    tags: [auto-generated, skill]
    related_skills: []
---

# {safe_name.replace('-', ' ').title()}

## Descricao

{description}

## Quando Usar

Use esta skill quando precisar realizar tarefas similares a que gerou esta sugestao automatica.

## Procedimento

{procedure}

## Categoria

{category}
"""

    # --------------------------------------------------
    # PERSISTENCIA
    # --------------------------------------------------

    def _save_suggestion(self, sequence_id: str, skill_name: str,
                         category: str, description: str,
                         procedure: str) -> dict:
        """Salva a sugestao em JSON (NAO cria a skill)."""
        suggestion_dir = COUNTER_FILE.parent / ".session_skill_suggestions"
        suggestion_dir.mkdir(parents=True, exist_ok=True)

        suggestion = {
            "sequence_id": sequence_id,
            "skill_name": skill_name,
            "category": category,
            "description": description,
            "procedure": procedure,
            "skill_path": str(SKILLS_BASE / category / skill_name),
            "suggested_at": _now_iso(),
            "skill_md_content": self._format_skill_md(
                skill_name, description, category, procedure
            ),
            "status": "suggested",
        }

        suggestion_file = suggestion_dir / f"{sequence_id}.json"
        try:
            with open(suggestion_file, "w") as f:
                json.dump(suggestion, f, indent=2, ensure_ascii=False)
            logger.info(f"Sugestao de skill salva em: {suggestion_file}")
        except OSError as e:
            logger.error(f"Erro ao salvar sugestao: {e}")

        return suggestion

    def create_skill_from_suggestion(self, sequence_id: str) -> dict:
        """Cria a skill a partir de uma sugestao salva.
        
        Este metodo deve ser chamado APENAS quando o usuario confirmar.
        Retorna o caminho da skill criada ou erro.
        """
        suggestion_dir = COUNTER_FILE.parent / ".session_skill_suggestions"
        suggestion_file = suggestion_dir / f"{sequence_id}.json"

        if not suggestion_file.exists():
            return {"success": False, "error": f"Sugestao {sequence_id} nao encontrada."}

        try:
            with open(suggestion_file, "r") as f:
                suggestion = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            return {"success": False, "error": str(e)}

        skill_name = suggestion["skill_name"]
        category = suggestion["category"]
        skill_md = suggestion.get("skill_md_content", "")

        # Cria diretorio da skill — usa nome do frontmatter do SKILL.md se possivel
        # ou o nome sanitizado
        if skill_md:
            # Extrai nome do frontmatter
            name_match = re.search(r'^name:\s*(.+)$', skill_md, re.MULTILINE)
            if name_match:
                skill_name = name_match.group(1).strip()

        safe_name = skill_name.lower().replace(" ", "-").replace("_", "-")
        safe_name = re.sub(r'[^a-z0-9\-]', '', safe_name)
        skill_dir = SKILLS_BASE / category / safe_name

        try:
            skill_dir.mkdir(parents=True, exist_ok=True)
            skill_md_path = skill_dir / "SKILL.md"
            with open(skill_md_path, "w") as f:
                f.write(skill_md)

            # Atualiza status
            suggestion["status"] = "created"
            suggestion["created_at"] = _now_iso()
            with open(suggestion_file, "w") as f:
                json.dump(suggestion, f, indent=2, ensure_ascii=False)

            return {
                "success": True,
                "skill_name": safe_name,
                "skill_path": str(skill_dir),
                "skill_md_path": str(skill_md_path),
            }
        except OSError as e:
            return {"success": False, "error": str(e)}

    def get_pending_suggestions(self) -> list:
        """Retorna lista de sugestoes pendentes (status='suggested')."""
        suggestion_dir = COUNTER_FILE.parent / ".session_skill_suggestions"
        if not suggestion_dir.exists():
            return []

        pending = []
        for f in sorted(suggestion_dir.glob("*.json")):
            try:
                with open(f, "r") as fh:
                    data = json.load(fh)
                if data.get("status") == "suggested":
                    pending.append(data)
            except (json.JSONDecodeError, OSError):
                continue

        return pending

    def reset_sequence(self, objective: str = "") -> str:
        """Reseta a sequencia atual e retorna novo sequence_id."""
        sequence_id = self._get_or_create_sequence(objective, force_new=True)
        return sequence_id

    # --------------------------------------------------
    # INTERNO
    # --------------------------------------------------

    @staticmethod
    def _sanitize_name(text: str) -> Optional[str]:
        """Sanitiza texto para nome de skill (kebab-case)."""
        # Remove prefixos comuns (verbos de acao)
        clean = re.sub(r'^(crie|criar|faça|faca|gere|gerar|execute|executar|'
                       r'analise|analisar|pesquise|pesquisar|gere|mostre|'
                       r'create|make|generate|run|analyze|search|show|'
                       r'criar um|faça um|faca um|crie um|gere um|'
                       r'criar uma|faça uma|faca uma|crie uma|gere uma|'
                       r'preciso de um|preciso de uma|quero um|quero uma|'
                       r'me ajude a|me ajuda a|me ajude com|me ajuda com)\s+',
                       '', text, flags=re.IGNORECASE)
        # Pega as primeiras palavras significativas
        words = re.findall(r'\b[a-zA-ZÀ-ÿ0-9]+\b', clean)
        if not words:
            return None
        # Filtra stopwords
        stopwords = {"de", "da", "do", "em", "para", "com", "um", "uma",
                     "os", "as", "e", "ou", "a", "o", "que", "se", "por",
                     "no", "na", "dos", "das", "num", "numa", "pelo", "pela",
                     "ao", "aos", "às", "as", "a", "com", "sem", "sob",
                     "sobre", "perante", "apos", "após", "ate", "até",
                     "entre", "desde"}
        content = [w for w in words if w.lower() not in stopwords]
        if not content:
            content = words[:3]

        # Se sobrar verbo no inicio, remove
        verbos = {"criar", "crie", "cria", "gerar", "gere", "gerado",
                  "fazer", "faca", "faça", "faz", "executar", "execute",
                  "analisar", "analise", "analisa", "analisando",
                  "pesquisar", "pesquise", "pesquisa", "pesquisando"}
        while content and content[0].lower() in verbos:
            content = content[1:]

        if not content:
            return None

        # Pega ate 3-4 palavras
        name = "-".join(w.lower() for w in content[:4])
        name = re.sub(r'[^a-z0-9\-]', '', name)
        return name[:64] if len(name) >= 3 else None

    @staticmethod
    def _get_or_create_sequence(objective: str = "", force_new: bool = False) -> str:
        """Obtem ou cria um ID de sequencia baseado no objective."""
        if not objective:
            return f"seq_{uuid.uuid4().hex[:12]}"

        # Gera um ID estavel para o mesmo objective neste arquivo
        # Usa um hash simples do objective
        import hashlib
        h = hashlib.md5(objective.encode()).hexdigest()[:12]
        return f"seq_{h}"


# =============================================
# HOOK PARA INTEGRATOR NODE
# =============================================

def skill_suggestion_hook(
    last_agent: str,
    messages: list,
    objective: str = "",
    tool_calls_count: int = 1,
) -> Optional[dict]:
    """Hook para ser chamado no final do integrator_node.

    Args:
        last_agent: Nome do ultimo agente (e.g. "codex", "web")
        messages: Lista de mensagens do estado
        objective: Objetivo da tarefa
        tool_calls_count: Tool calls nesta iteracao (default 1)

    Returns:
        Dict de sugestao se aplicavel, None caso contrario.
        O chamador deve verificar result["suggested"] e enviar ao usuario.
    """
    bridge = get_bridge()
    result = bridge.check_and_suggest_skill(
        last_agent=last_agent,
        messages=messages,
        tool_calls_count=tool_calls_count,
        objective=objective,
    )
    if result["suggested"]:
        logger.info(
            f"SKILL SUGGESTION: {result['skill_name']} "
            f"(path: {result['skill_path']})"
        )
        return result
    return None
