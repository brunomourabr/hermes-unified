"""
Memory Bridge v2 — Grafo de Conhecimento Ontológico
Armazena entidades (Campaign, Metric, Claim, Source, etc.) com proveniência
e relações tipadas. Substitui o armazenamento plano anterior.
"""
import os
import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

from core.ontology import get_ontology


class KnowledgeGraphStore:
    """
    Grafo de conhecimento ontológico.
    Tabelas mapeadas 1:1 com entidades da ontologia.
    Proveniência em toda fact: que bridge salvou, quando, com que confiança.
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "memory.db")
        self.db_path = db_path
        self.ontology = get_ontology()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        """Cria schema ontológico — tabelas com FKs e proveniência."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # --- TABELAS ONTOLÓGICAS ---

        # Campaigns
        c.execute("""
            CREATE TABLE IF NOT EXISTS campaigns (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                platform TEXT,
                status TEXT DEFAULT 'active',
                start_date TEXT,
                end_date TEXT,
                budget REAL DEFAULT 0,
                currency TEXT DEFAULT 'BRL',
                objective TEXT,
                bridge_source TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        # Metrics — coração do grafo, cada métrica tem proveniência
        c.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT,
                campaign_id TEXT,
                platform TEXT,
                period_start TEXT,
                period_end TEXT,
                bridge_source TEXT,
                confidence REAL DEFAULT 1.0,
                raw_data TEXT,
                created_at TEXT,
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
            )
        """)

        # AdSets
        c.execute("""
            CREATE TABLE IF NOT EXISTS adsets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                campaign_id TEXT NOT NULL,
                platform TEXT,
                budget REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                bridge_source TEXT,
                created_at TEXT,
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
            )
        """)

        # Claims (afirmações de pesquisa, com confiança)
        c.execute("""
            CREATE TABLE IF NOT EXISTS claims (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                confidence REAL NOT NULL,
                topic TEXT,
                source_url TEXT,
                source_title TEXT,
                bridge_source TEXT,
                verified INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)

        # Sources (fontes de informação)
        c.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                title TEXT,
                domain TEXT,
                bridge_source TEXT,
                accessed_at TEXT,
                relevance_score REAL DEFAULT 0.5
            )
        """)

        # Reports
        c.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                type TEXT,
                file_path TEXT,
                bridge_source TEXT,
                generated_at TEXT
            )
        """)

        # Observations
        c.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT,
                message TEXT NOT NULL,
                source TEXT,
                severity TEXT DEFAULT 'medium',
                related_entity TEXT,
                observed_at TEXT,
                created_at TEXT
            )
        """)

        # --- TABELA DE RELAÇÕES (arestas do grafo) ---
        c.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_entity_type TEXT NOT NULL,
                source_entity_id TEXT NOT NULL,
                relationship_type TEXT NOT NULL,
                target_entity_type TEXT NOT NULL,
                target_entity_id TEXT NOT NULL,
                bridge_source TEXT,
                created_at TEXT,
                UNIQUE(source_entity_type, source_entity_id, relationship_type, target_entity_type, target_entity_id)
            )
        """)

        # Índices para performance
        for idx in [
            "CREATE INDEX IF NOT EXISTS idx_metrics_campaign ON metrics(campaign_id)",
            "CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(name)",
            "CREATE INDEX IF NOT EXISTS idx_metrics_period ON metrics(period_start, period_end)",
            "CREATE INDEX IF NOT EXISTS idx_claims_topic ON claims(topic)",
            "CREATE INDEX IF NOT EXISTS idx_adsets_campaign ON adsets(campaign_id)",
            "CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_entity_type, source_entity_id)",
            "CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_entity_type, target_entity_id)",
        ]:
            c.execute(idx)

        # Mantém tabelas legadas para compatibilidade
        c.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                objective TEXT,
                category TEXT,
                success INTEGER,
                created_at TEXT,
                summary TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                artifact TEXT,
                type TEXT,
                created_at TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_cache (
                key TEXT PRIMARY KEY,
                value TEXT,
                source TEXT,
                created_at TEXT,
                expires_at TEXT
            )
        """)

        conn.commit()
        conn.close()

    # =====================================================================
    # CAMPAIGNS
    # =====================================================================

    def save_campaign(self, campaign: dict, bridge: str = "unknown") -> str:
        """Salva ou atualiza uma campanha."""
        cid = campaign.get("id") or str(uuid.uuid4())[:12]
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO campaigns
            (id, name, platform, status, start_date, end_date, budget, currency, objective, bridge_source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM campaigns WHERE id=?), ?), ?)
        """, (
            cid,
            campaign.get("name", "Unnamed Campaign"),
            campaign.get("platform", ""),
            campaign.get("status", "active"),
            campaign.get("start_date", ""),
            campaign.get("end_date", ""),
            campaign.get("budget", 0),
            campaign.get("currency", "BRL"),
            campaign.get("objective", ""),
            bridge,
            cid, now,
            now
        ))
        conn.commit()
        conn.close()
        return cid

    def get_campaign(self, campaign_id: str) -> Optional[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def list_campaigns(self, platform: str = None) -> List[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if platform:
            rows = conn.execute("SELECT * FROM campaigns WHERE platform = ? ORDER BY created_at DESC", (platform,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM campaigns ORDER BY created_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # =====================================================================
    # METRICS — coração do grafo ontológico
    # =====================================================================

    def save_metric(self, metric: dict, campaign_id: str = None, bridge: str = "unknown") -> Tuple[str, bool]:
        """
        Salva uma métrica com validação ontológica.
        Retorna (id, validated_ok).
        """
        # Valida contra ontologia ANTES de salvar
        ok, msg = self.ontology.validate_metric(metric)
        if not ok:
            print(f"   ⚠ [KG] Métrica '{metric.get('name')}' rejeitada: {msg}")
            # Ainda salva mas marca confidence baixa
            if "confidence" not in metric:
                metric["confidence"] = 0.3

        mid = metric.get("id") or str(uuid.uuid4())[:12]
        now = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO metrics
            (id, name, value, unit, campaign_id, platform, period_start, period_end, bridge_source, confidence, raw_data, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            mid,
            metric.get("name", ""),
            metric.get("value", 0),
            metric.get("unit", ""),
            campaign_id or metric.get("campaign_id", ""),
            metric.get("platform", ""),
            metric.get("period_start", ""),
            metric.get("period_end", ""),
            bridge,
            metric.get("confidence", 1.0),
            json.dumps(metric, ensure_ascii=False),
            now
        ))
        conn.commit()
        conn.close()
        return mid, ok

    def save_metrics_bulk(self, metrics: List[dict], campaign_id: str = None, bridge: str = "unknown") -> Tuple[int, int]:
        """Salva múltiplas métricas de uma vez. Retorna (salvas, rejeitadas)."""
        saved = 0
        rejected = 0
        for m in metrics:
            _, ok = self.save_metric(m, campaign_id, bridge)
            if ok:
                saved += 1
            else:
                rejected += 1
        return saved, rejected

    def query_metrics(self, name: str = None, campaign_id: str = None,
                       platform: str = None, period: str = None,
                       limit: int = 50) -> List[dict]:
        """Consulta métricas com filtros flexíveis."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        where = []
        params = []

        if name:
            where.append("name = ?")
            params.append(name)
        if campaign_id:
            where.append("campaign_id = ?")
            params.append(campaign_id)
        if platform:
            where.append("platform = ?")
            params.append(platform)
        if period:
            where.append("(period_start LIKE ? OR period_end LIKE ?)")
            params.append(f"{period}%")
            params.append(f"{period}%")

        where_clause = " AND ".join(where) if where else "1=1"
        rows = conn.execute(
            f"SELECT * FROM metrics WHERE {where_clause} ORDER BY created_at DESC LIMIT ?",
            params + [limit]
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_metric_summary(self, name: str, campaign_id: str = None) -> dict:
        """Sumário de uma métrica específica (média, min, max, últimas)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        where = ["name = ?"]
        params = [name]
        if campaign_id:
            where.append("campaign_id = ?")
            params.append(campaign_id)

        where_clause = " AND ".join(where)
        row = conn.execute(
            f"SELECT AVG(value) as avg, MIN(value) as min, MAX(value) as max, COUNT(*) as count FROM metrics WHERE {where_clause}",
            params
        ).fetchone()

        last = conn.execute(
            f"SELECT value, period_start, period_end, created_at FROM metrics WHERE {where_clause} ORDER BY created_at DESC LIMIT 1",
            params
        ).fetchone()

        conn.close()
        result = dict(row) if row else {}
        if last:
            result["last_value"] = last["value"]
            result["last_period"] = f"{last['period_start']} - {last['period_end']}"
        return result

    # =====================================================================
    # CLAIMS
    # =====================================================================

    def save_claim(self, claim: dict, bridge: str = "unknown") -> Tuple[str, bool]:
        """Salva um claim com validação ontológica."""
        ok, msg = self.ontology.validate_claim(claim)
        if not ok:
            print(f"   ⚠ [KG] Claim rejeitado: {msg}")

        cid = str(uuid.uuid4())[:12]
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO claims
            (id, text, confidence, topic, source_url, source_title, bridge_source, verified, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cid,
            claim.get("text", ""),
            claim.get("confidence", 0.5),
            claim.get("topic", ""),
            claim.get("source_url", ""),
            claim.get("source_title", ""),
            bridge,
            1 if claim.get("verified") else 0,
            datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()
        return cid, ok

    def query_claims(self, topic: str = None, min_confidence: float = 0.0, limit: int = 20) -> List[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        where = ["confidence >= ?"]
        params = [min_confidence]
        if topic:
            where.append("topic LIKE ?")
            params.append(f"%{topic}%")

        rows = conn.execute(
            f"SELECT * FROM claims WHERE {' AND '.join(where)} ORDER BY confidence DESC LIMIT ?",
            params + [limit]
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # =====================================================================
    # SOURCES
    # =====================================================================

    def save_source(self, source: dict, bridge: str = "unknown") -> str:
        sid = source.get("id") or str(uuid.uuid4())[:12]
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO sources
            (id, url, title, domain, bridge_source, accessed_at, relevance_score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            sid,
            source.get("url", ""),
            source.get("title", ""),
            source.get("domain", ""),
            bridge,
            datetime.now().isoformat(),
            source.get("relevance_score", 0.5)
        ))
        conn.commit()
        conn.close()
        return sid

    # =====================================================================
    # RELAÇÕES (arestas do grafo)
    # =====================================================================

    def add_relationship(self, source_type: str, source_id: str,
                          rel_type: str, target_type: str, target_id: str,
                          bridge: str = "unknown"):
        """Adiciona aresta entre duas entidades no grafo."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                INSERT OR IGNORE INTO relationships
                (source_entity_type, source_entity_id, relationship_type, target_entity_type, target_entity_id, bridge_source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (source_type, source_id, rel_type, target_type, target_id, bridge, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"   ⚠ [KG] Erro ao criar relação: {e}")
            return False

    def get_relationships(self, entity_type: str, entity_id: str) -> List[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM relationships
            WHERE (source_entity_type = ? AND source_entity_id = ?)
               OR (target_entity_type = ? AND target_entity_id = ?)
            ORDER BY created_at DESC
        """, (entity_type, entity_id, entity_type, entity_id)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # =====================================================================
    # CONSULTAS CRUZADAS — queries que cruzam entidades
    # =====================================================================

    def get_campaign_performance(self, campaign_id: str) -> dict:
        """Retorna todas as métricas de uma campanha, agregadas."""
        metrics = self.query_metrics(campaign_id=campaign_id)
        summary = {}
        for m in metrics:
            name = m["name"]
            if name not in summary:
                summary[name] = {"values": [], "last": None}
            summary[name]["values"].append(m["value"])
            summary[name]["last"] = m["value"]
            summary[name]["unit"] = m.get("unit", "")
        return summary

    def search(self, text: str, limit: int = 10) -> List[dict]:
        """Busca textual em todas as entidades do grafo."""
        results = []
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        like = f"%{text}%"

        # Busca em campaigns
        for row in conn.execute("SELECT id, name, 'campaign' as type FROM campaigns WHERE name LIKE ? LIMIT ?", (like, limit)):
            results.append(dict(row))

        # Busca em metrics
        for row in conn.execute("SELECT id, name, 'metric' as type FROM metrics WHERE name LIKE ? LIMIT ?", (like, limit)):
            results.append(dict(row))

        # Busca em claims
        for row in conn.execute("SELECT id, substr(text,1,100) as name, 'claim' as type FROM claims WHERE text LIKE ? LIMIT ?", (like, limit)):
            d = dict(row)
            d["name"] = d.pop("name", "")[:80]
            results.append(d)

        # Busca em sources
        for row in conn.execute("SELECT id, url as name, 'source' as type FROM sources WHERE url LIKE ? OR title LIKE ? LIMIT ?", (like, like, limit)):
            results.append(dict(row))

        conn.close()
        return results

    def stats(self) -> dict:
        """Estatísticas do grafo ontológico."""
        conn = sqlite3.connect(self.db_path)
        stats = {}
        for table in ["campaigns", "metrics", "claims", "sources", "reports", "observations", "relationships", "adsets"]:
            try:
                row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                stats[table] = row[0]
            except Exception:
                stats[table] = 0
        conn.close()
        return stats


# =====================================================================
# WRAPPER — substitui MemoryBridge antiga mantendo compatibilidade
# =====================================================================
class MemoryBridge:
    """
    Memory Bridge v2 — mantém métodos antigos + novos métodos ontológicos.
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "memory.db")
        self.db_path = db_path
        self.kg = KnowledgeGraphStore(db_path)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # --- Métodos antigos (compatibilidade) ---

    def save_session(self, objective, category, success, artifacts=None, summary=""):
        session_id = str(uuid.uuid4())[:8]
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO sessions (id, objective, category, success, created_at, summary) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, objective, category, 1 if success else 0, datetime.now().isoformat(), summary)
        )
        if artifacts:
            for art in artifacts:
                conn.execute(
                    "INSERT INTO artifacts (session_id, artifact, type, created_at) VALUES (?, ?, ?, ?)",
                    (session_id, str(art), self._detect_type(str(art)), datetime.now().isoformat())
                )
        conn.commit()
        conn.close()
        return session_id

    def _detect_type(self, artifact):
        if artifact.endswith('.png'): return 'chart'
        if artifact.endswith('.py'): return 'code'
        if '.pptx' in artifact: return 'presentation'
        if 'search' in artifact.lower(): return 'search_result'
        if 'grafo' in artifact.lower() or 'extracao' in artifact.lower(): return 'knowledge_graph'
        return 'generic'

    def search_sessions(self, query, limit=5):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, objective, category, success, created_at, summary FROM sessions WHERE objective LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{query}%", limit)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_recent_sessions(self, limit=5):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, objective, category, success, created_at, summary FROM sessions ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def save_observation(self, watcher_name, check_type, target, result):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO observations (type, message, source, severity, related_entity, observed_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (check_type, result[:500], watcher_name, "medium", target, datetime.now().isoformat(), datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

    def get_observations(self, watcher_name=None, limit=10):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if watcher_name:
            rows = conn.execute(
                "SELECT * FROM observations WHERE source = ? ORDER BY created_at DESC LIMIT ?",
                (watcher_name, limit)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM observations ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def cache_knowledge(self, key, value, source="", ttl_hours=24):
        expires = (datetime.now() + timedelta(hours=ttl_hours)).isoformat()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO knowledge_cache (key, value, source, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (key, value, source, datetime.now().isoformat(), expires)
        )
        conn.commit()
        conn.close()

    def get_cached_knowledge(self, key):
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT value, expires_at FROM knowledge_cache WHERE key = ?", (key,)).fetchone()
        conn.close()
        if row and datetime.fromisoformat(row[1]) > datetime.now():
            return row[0]
        return None

    def stats(self):
        return self.kg.stats()


# Singleton
_memory_bridge = None

def get_memory_bridge() -> MemoryBridge:
    global _memory_bridge
    if _memory_bridge is None:
        _memory_bridge = MemoryBridge()
    return _memory_bridge

def get_kg() -> KnowledgeGraphStore:
    """Acesso direto ao KnowledgeGraphStore para bridges."""
    return get_memory_bridge().kg


# CLI de teste
if __name__ == "__main__":
    kg = get_kg()
    print("=== Knowledge Graph Store ===")
    print(f"Schema criado: {kg.db_path}")

    # Testa salvar campanha
    cid = kg.save_campaign({
        "name": "Campanha Teste Maio",
        "platform": "dv360",
        "status": "active",
        "budget": 10000,
        "start_date": "2026-05-01",
        "end_date": "2026-05-31",
    }, bridge="test")
    print(f"Campanha salva: {cid}")

    # Testa salvar métrica
    mid, ok = kg.save_metric({
        "name": "CTR",
        "value": 3.5,
        "unit": "%",
        "platform": "dv360",
        "period_start": "2026-05-01",
        "period_end": "2026-05-31",
        "confidence": 0.95
    }, campaign_id=cid, bridge="test")
    print(f"Metrica salva: {mid} (valida: {ok})")

    # Testa métrica inválida
    mid2, ok2 = kg.save_metric({
        "name": "CTR",
        "value": 150,
        "unit": "%"
    }, bridge="test")
    print(f"Metrica invalida salva: {mid2} (valida: {ok2})")

    # Testa claim
    clid, _ = kg.save_claim({
        "text": "IA aumenta ROAS em 30% em campanhas programáticas",
        "confidence": 0.85,
        "topic": "IA Marketing",
        "source_url": "https://example.com/study",
        "verified": True,
    }, bridge="research_bridge")
    print(f"Claim salvo: {clid}")

    # Testa relação
    kg.add_relationship("campaign", cid, "HAS_METRIC", "metric", mid, bridge="test")
    print(f"Relacao criada: campaign {cid} -> HAS_METRIC -> metric {mid}")

    # Estatísticas
    print(f"\nStats: {kg.stats()}")

    # Busca
    print(f"\nBusca 'CTR': {kg.search('CTR', limit=3)}")
    print(f"Busca 'Maio': {kg.search('Maio', limit=3)}")
    print(f"Busca 'IA': {kg.search('IA', limit=3)}")
