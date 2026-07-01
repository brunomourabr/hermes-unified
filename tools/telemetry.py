"""
Middleware de Telemetria — wrapper para bridges que mede latência, erros,
cache_hit, custo estimado de LLM e armazena em SQLite + JSONL.

Uso:
    from tools.telemetry import TelemetryMiddleware, telemetry

    # Como decorator em funções de bridge:
    @telemetry.track("scraper_bridge", "scrape_url")
    def scrape_url(url):
        ...

    # Ou como context manager:
    with telemetry.span("viz_bridge", "generate_chart"):
        ...
"""
import os
import json
import time
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable, Any

# =====================================================================
# CONFIG
# =====================================================================
DB_PATH = Path("/opt/projetos/hermes-unified/data/telemetry.db")
JSONL_PATH = Path("/opt/projetos/hermes-unified/data/telemetry.jsonl")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# =====================================================================
# DATABASE SETUP
# =====================================================================
_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    bridge TEXT NOT NULL,
    operation TEXT NOT NULL,
    latency_ms REAL NOT NULL,
    error TEXT,
    cache_hit INTEGER DEFAULT 0,
    llm_tokens_input INTEGER DEFAULT 0,
    llm_tokens_output INTEGER DEFAULT 0,
    llm_cost_usd REAL DEFAULT 0.0,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_telemetry_bridge ON telemetry(bridge);
CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON telemetry(timestamp);
CREATE INDEX IF NOT EXISTS idx_telemetry_error ON telemetry(error);
"""

# Cache de custo: modelo -> $/1K tokens
LLM_COST_PER_1K = {
    "gpt-4o-mini": {"input": 0.00015, "output": 0.00060},
    "deepseek-chat": {"input": 0.00027, "output": 0.00110},
    "claude-sonnet-4": {"input": 0.00300, "output": 0.01500},
    "kimi-k2.5": {"input": 0.00200, "output": 0.00800},
    "default": {"input": 0.00100, "output": 0.00400},
}


def _init_db():
    with _lock:
        conn = sqlite3.connect(str(DB_PATH))
        conn.executescript(_SCHEMA)
        conn.commit()
        conn.close()


def _write_jsonl(entry: dict):
    with _lock:
        with open(str(JSONL_PATH), "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# =====================================================================
# TELEMETRY MIDDLEWARE
# =====================================================================
class TelemetryMiddleware:
    """Wrapper de telemetria para bridges. Thread-safe, escreve em SQLite + JSONL."""

    def __init__(self):
        _init_db()

    def track(
        self,
        bridge: str,
        operation: str,
        llm_model: str = "default",
        metadata: Optional[dict] = None,
    ):
        """Decorator: @telemetry.track('scraper', 'scrape_url')."""
        def decorator(func: Callable) -> Callable:
            def wrapper(*args, **kwargs):
                start = time.time()
                error = None
                cache_hit = 0
                try:
                    result = func(*args, **kwargs)
                    # Detecta cache hit no resultado (se a bridge retornar dict com '_cache_hit')
                    if isinstance(result, dict) and result.get("_cache_hit"):
                        cache_hit = 1
                    return result
                except Exception as e:
                    error = str(e)[:500]
                    raise
                finally:
                    latency_ms = round((time.time() - start) * 1000, 2)
                    self._record(
                        bridge=bridge,
                        operation=operation,
                        latency_ms=latency_ms,
                        error=error,
                        cache_hit=cache_hit,
                        llm_model=llm_model,
                        metadata=metadata,
                    )

            wrapper.__name__ = func.__name__
            wrapper.__qualname__ = func.__qualname__
            return wrapper
        return decorator

    def span(self, bridge: str, operation: str, llm_model: str = "default"):
        """Context manager: with telemetry.span('viz', 'generate_chart'): ..."""
        return _TelemetrySpan(self, bridge, operation, llm_model)

    def _record(
        self,
        bridge: str,
        operation: str,
        latency_ms: float,
        error: Optional[str] = None,
        cache_hit: int = 0,
        llm_tokens_input: int = 0,
        llm_tokens_output: int = 0,
        llm_model: str = "default",
        metadata: Optional[dict] = None,
    ):
        """Registra entrada de telemetria."""
        now = datetime.utcnow().isoformat() + "Z"

        # Calcula custo estimado de LLM
        cost = llm_tokens_input / 1000 * LLM_COST_PER_1K.get(llm_model, LLM_COST_PER_1K["default"])["input"]
        cost += llm_tokens_output / 1000 * LLM_COST_PER_1K.get(llm_model, LLM_COST_PER_1K["default"])["output"]
        llm_cost_usd = round(cost, 6)

        entry = {
            "timestamp": now,
            "bridge": bridge,
            "operation": operation,
            "latency_ms": latency_ms,
            "error": error,
            "cache_hit": cache_hit,
            "llm_tokens_input": llm_tokens_input,
            "llm_tokens_output": llm_tokens_output,
            "llm_cost_usd": llm_cost_usd,
            "metadata": json.dumps(metadata, ensure_ascii=False) if metadata else None,
        }

        # SQLite
        try:
            with _lock:
                conn = sqlite3.connect(str(DB_PATH))
                conn.execute(
                    """INSERT INTO telemetry
                       (timestamp, bridge, operation, latency_ms, error, cache_hit,
                        llm_tokens_input, llm_tokens_output, llm_cost_usd, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        entry["timestamp"],
                        entry["bridge"],
                        entry["operation"],
                        entry["latency_ms"],
                        entry["error"],
                        entry["cache_hit"],
                        entry["llm_tokens_input"],
                        entry["llm_tokens_output"],
                        entry["llm_cost_usd"],
                        entry["metadata"],
                    ),
                )
                conn.commit()
                conn.close()
        except Exception as e:
            print(f"[TELEMETRY] DB write error: {e}")

        # JSONL (fallback/redundância)
        try:
            _write_jsonl(entry)
        except Exception as e:
            print(f"[TELEMETRY] JSONL write error: {e}")


class _TelemetrySpan:
    """Context manager interno para telemetry.span()."""

    def __init__(self, parent: TelemetryMiddleware, bridge: str, operation: str, llm_model: str):
        self.parent = parent
        self.bridge = bridge
        self.operation = operation
        self.llm_model = llm_model
        self.start = None
        self.error = None
        self.cache_hit = 0

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            self.error = str(exc_val)[:500]
        latency_ms = round((time.time() - self.start) * 1000, 2)
        self.parent._record(
            bridge=self.bridge,
            operation=self.operation,
            latency_ms=latency_ms,
            error=self.error,
            cache_hit=self.cache_hit,
            llm_model=self.llm_model,
        )
        return False  # não suprime exceção


# =====================================================================
# QUERIES (para dashboard)
# =====================================================================
class TelemetryQueries:
    """Consultas agregadas para o dashboard de status."""

    @staticmethod
    def _query(sql: str, params: tuple = ()) -> list:
        with _lock:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
        return rows

    @staticmethod
    def last_n_days(days: int = 7) -> list:
        """Todas as entradas dos últimos N dias."""
        since = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"
        return TelemetryQueries._query(
            "SELECT * FROM telemetry WHERE timestamp >= ? ORDER BY timestamp DESC",
            (since,),
        )

    @staticmethod
    def error_rate(days: int = 7) -> list:
        """Taxa de erro por bridge nos últimos N dias."""
        since = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"
        return TelemetryQueries._query(
            """SELECT bridge,
                      COUNT(*) as total,
                      SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as errors,
                      ROUND(100.0 * SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as error_rate_pct,
                      ROUND(AVG(latency_ms), 1) as avg_latency_ms,
                      ROUND(AVG(CASE WHEN error IS NULL THEN latency_ms END), 1) as avg_ok_latency_ms,
                      ROUND(SUM(llm_cost_usd), 4) as total_cost_usd
               FROM telemetry
               WHERE timestamp >= ?
               GROUP BY bridge
               ORDER BY total DESC""",
            (since,),
        )

    @staticmethod
    def latency_percentiles(days: int = 7) -> list:
        """Latência p50 e p95 por bridge."""
        since = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"
        # SQLite não tem percentile nativo, fazemos aproximação
        return TelemetryQueries._query(
            """SELECT bridge,
                      COUNT(*) as samples,
                      ROUND(AVG(latency_ms), 1) as avg_ms,
                      ROUND(MIN(latency_ms), 1) as min_ms,
                      ROUND(MAX(latency_ms), 1) as max_ms
               FROM telemetry
               WHERE timestamp >= ? AND error IS NULL
               GROUP BY bridge
               ORDER BY avg_ms DESC""",
            (since,),
        )

    @staticmethod
    def daily_summary(days: int = 7) -> list:
        """Resumo diário de atividade."""
        since = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"
        return TelemetryQueries._query(
            """SELECT DATE(timestamp) as day,
                      COUNT(*) as calls,
                      COUNT(DISTINCT bridge) as bridges_active,
                      ROUND(SUM(llm_cost_usd), 4) as cost_usd,
                      ROUND(AVG(latency_ms), 1) as avg_latency_ms,
                      SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as errors
               FROM telemetry
               WHERE timestamp >= ?
               GROUP BY DATE(timestamp)
               ORDER BY day DESC""",
            (since,),
        )

    @staticmethod
    def cache_hit_rate(days: int = 7) -> float:
        """Taxa de cache hit geral."""
        since = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"
        rows = TelemetryQueries._query(
            """SELECT SUM(cache_hit) as hits, COUNT(*) as total
               FROM telemetry WHERE timestamp >= ?""",
            (since,),
        )
        if rows and rows[0]["total"] > 0:
            return round(100.0 * rows[0]["hits"] / rows[0]["total"], 1)
        return 0.0

    @staticmethod
    def total_cost(days: int = 7) -> float:
        """Custo total estimado de LLM nos últimos N dias."""
        since = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"
        rows = TelemetryQueries._query(
            "SELECT ROUND(SUM(llm_cost_usd), 4) as total FROM telemetry WHERE timestamp >= ?",
            (since,),
        )
        return rows[0]["total"] if rows else 0.0

    @staticmethod
    def total_calls(days: int = 7) -> int:
        """Total de chamadas nos últimos N dias."""
        since = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"
        rows = TelemetryQueries._query(
            "SELECT COUNT(*) as total FROM telemetry WHERE timestamp >= ?",
            (since,),
        )
        return rows[0]["total"] if rows else 0


# =====================================================================
# SINGLETON
# =====================================================================
telemetry = TelemetryMiddleware()
queries = TelemetryQueries()
