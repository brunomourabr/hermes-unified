"""
Cache module — disk-based caching para resultados de bridges.
Inspirado no Redis caching do production-agentic-rag-course.

Usa diskcache (SQLite-backed) — zero dependências externas,
TTL configurável, persistente entre execuções.

Speedup esperado: 150-400x em queries repetidas.
"""
import hashlib
import json
from typing import Any, Optional
from pathlib import Path

from diskcache import Cache as DiskCache

# Cache raiz
CACHE_DIR = Path("/opt/projetos/hermes-unified/data/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Caches especializados
_web_cache = DiskCache(str(CACHE_DIR / "web"))
_bridge_cache = DiskCache(str(CACHE_DIR / "bridge"))
_llm_cache = DiskCache(str(CACHE_DIR / "llm"))


def _make_key(*args, **kwargs) -> str:
    """Gera chave hash única a partir de args."""
    raw = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


# ==================================================================
# Web Cache — resultados de scraping e busca
# TTL: 1 hora (3600s)
# ==================================================================

def web_get(key: str) -> Optional[Any]:
    """Recupera resultado de web do cache."""
    return _web_cache.get(key)


def web_set(key: str, value: Any, ttl: int = 3600):
    """Armazena resultado de web no cache."""
    _web_cache.set(key, value, expire=ttl)


# ==================================================================
# Bridge Cache — resultados de bridges (MCP-Brasil, Finance, etc)
# TTL: 30 minutos (1800s)
# ==================================================================

def bridge_get(bridge_name: str, *args, **kwargs) -> Optional[Any]:
    """Recupera resultado de bridge do cache."""
    key = f"{bridge_name}:{_make_key(*args, **kwargs)}"
    return _bridge_cache.get(key)


def bridge_set(bridge_name: str, value: Any, *args, ttl: int = 1800, **kwargs):
    """Armazena resultado de bridge no cache."""
    key = f"{bridge_name}:{_make_key(*args, **kwargs)}"
    _bridge_cache.set(key, value, expire=ttl)


# ==================================================================
# LLM Cache — respostas de LLM (classificação, planejamento)
# TTL: 24 horas (86400s)
# ==================================================================

def llm_get(prompt: str, model: str = "default") -> Optional[str]:
    """Recupera resposta de LLM do cache."""
    key = _make_key(prompt, model)
    return _llm_cache.get(key)


def llm_set(prompt: str, response: str, model: str = "default", ttl: int = 86400):
    """Armazena resposta de LLM no cache."""
    key = _make_key(prompt, model)
    _llm_cache.set(key, response, expire=ttl)


# ==================================================================
# Utilitários
# ==================================================================

def clear_all():
    """Limpa todos os caches."""
    _web_cache.clear()
    _bridge_cache.clear()
    _llm_cache.clear()


def stats() -> dict:
    """Estatísticas do cache."""
    return {
        "web": {"entries": len(_web_cache), "size_mb": _web_cache.volume() / 1024 / 1024},
        "bridge": {"entries": len(_bridge_cache), "size_mb": _bridge_cache.volume() / 1024 / 1024},
        "llm": {"entries": len(_llm_cache), "size_mb": _llm_cache.volume() / 1024 / 1024},
        "total_mb": sum(
            c.volume() for c in [_web_cache, _bridge_cache, _llm_cache]
        ) / 1024 / 1024,
    }
