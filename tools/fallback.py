"""
Fallback helpers — padrão Fallback em Cascata do Agentic RAG.

Três níveis:
1. LLM / API → resultado desejado
2. Heurística simples → fallback determinístico
3. Mensagem amigável → explica fallback ao usuário

Inspirado em: jamwithai/production-agentic-rag-course
"""
import logging
from typing import Any, Callable, Optional, Tuple

logger = logging.getLogger(__name__)


def with_cascade_fallback(
    primary: Callable[[], Any],
    heuristic: Optional[Callable[[], Any]] = None,
    fallback_msg: str = "Não foi possível processar sua solicitação no momento.",
    name: str = "unknown",
) -> Tuple[Any, bool, str]:
    """
    Executa uma função com fallback em cascata.

    Args:
        primary: Função principal (LLM, API, etc)
        heuristic: Fallback heurístico (opcional)
        fallback_msg: Mensagem de fallback final
        name: Nome do componente para logging

    Returns:
        (resultado, success, mensagem)
    """
    # Nível 1: Primário
    try:
        result = primary()
        if result is not None and result != "":
            logger.info(f"[{name}] Primário OK")
            return result, True, "OK"
        logger.warning(f"[{name}] Primário retornou vazio")
    except Exception as e:
        logger.warning(f"[{name}] Primário falhou: {e}")

    # Nível 2: Heurística
    if heuristic is not None:
        try:
            result = heuristic()
            if result is not None:
                logger.info(f"[{name}] Heurística OK")
                return result, True, "Fallback heurístico"
        except Exception as e:
            logger.warning(f"[{name}] Heurística falhou: {e}")

    # Nível 3: Mensagem amigável
    logger.warning(f"[{name}] Todos fallbacks exauridos")
    return fallback_msg, False, fallback_msg


def safe_execute(fn: Callable, default: Any = None, log_name: str = "") -> Any:
    """Executa função com try/except silencioso."""
    try:
        return fn()
    except Exception as e:
        if log_name:
            logger.debug(f"[{log_name}] safe_execute: {e}")
        return default
