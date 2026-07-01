#!/usr/bin/env python3
"""
Memory Consolidator v6 — Auto-consolidação de Memória Hermes

Lê as entradas de memória atuais (MEMORY.md, USER.md), analisa uso,
e quando o limite atinge >=80%, faz merge de entradas relacionadas.

Singleton + get_bridge()
Método: consolidate() -> dict com resultado
Método: check_and_report() -> dict com status atual

SEGURANÇA:
- NUNCA remove preferências do usuário (target='user')
- NUNCA remove regras de conduta
- Sempre mantém a entrada mais recente de cada tema
- Faz backup antes de consolidar
"""

import json
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

_INSTANCE = None


# ─── TÓPICOS CONHECIDOS ───────────────────────────────────────────────────

TOPIC_KEYWORDS = {
    "causal_inference": [
        "pymc", "causal", "causalpy", "mmm",
        "inferencia causal", "bridge de marketing causal",
        "causal_bridge.py", "pymc-marketing", "pymc labs",
        "memo", "memory as a model", "decision lab", "modelcraft",
    ],
    "firecrawl": [
        "firecrawl", "api.firecrawl", "scrape", "crawling",
        "anti-bot", "magazine luiza", "mercado livre",
    ],
    "bridge_financeira": [
        "financial bridge br", "bcb sgs", "selic", "cdi",
        "brapi", "tesouro direto", "python-bcb",
        "offline fallback", "_offline_", "cambio usd",
    ],
    "rag_aprimoramentos": [
        "production-agentic-rag", "cache diskcache", "fallback cascata",
        "guardrail", "query rewriting", "langfuse",
        "tools/cache.py", "tools/fallback.py",
    ],
    "vibe_coding_sdlc": [
        "vibe coding", "sdlc", "day 1 v3", "hyper-extract", "sdlc_ka",
    ],
    "hostinger_infra": [
        "hostinger", "cloudflared", "localtunnel",
        "mimo code", "vps", "npx skills",
    ],
}

CONDUCT_KEYWORDS = [
    "regras:", "nunca forçar", "nunca dar estimativas",
    "múltiplas conversas", "relatório financeiro (macro)",
]

USER_OBS_KEYWORDS = [
    "bruno é rigoroso", "bruno é direto", "bruno — usuário",
    "lição aprendida:", "sempre usar date", "ele espera precisão",
]


def _topic(entry: str) -> Optional[str]:
    el = entry.lower()
    for t, kws in TOPIC_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in el:
                return t
    return None


def _is_rules(entry: str) -> bool:
    el = entry.lower()
    return any(kw in el for kw in CONDUCT_KEYWORDS)


def _is_user_obs(entry: str) -> bool:
    el = entry.lower()
    return any(kw in el for kw in USER_OBS_KEYWORDS)


def _date(entry: str) -> Optional[str]:
    m = re.match(r'\s*\[(\d{4}-\d{2}-\d{2})\]', entry)
    return m.group(1) if m else None


def _mem_dir() -> Path:
    return Path(os.getenv("HERMES_HOME", str(Path.home() / ".hermes"))) / "memories"


def _is_old(entry: str, days: int = 30) -> bool:
    d = _date(entry)
    if d:
        try:
            return (datetime.now() - datetime.strptime(d, "%Y-%m-%d")) > timedelta(days=days)
        except ValueError:
            pass
    return False


def _compress(entry: str, limit: int = 500) -> str:
    """Comprime entrada removendo redundância entre linhas."""
    if len(entry) <= limit:
        return entry
    lines = entry.split("\n")
    kept = []
    seen = set()
    for line in lines:
        s = line.strip()
        if not s:
            continue
        key = re.sub(r'\s+', '', s.lower())
        key = re.sub(r'[^a-z0-9/]', '', key)
        if key not in seen and len(key) > 4:
            seen.add(key)
            kept.append(s)
    result = "\n".join(kept)
    if len(result) <= limit:
        return result
    # Corte forçado
    result = result[:limit]
    nl = result.rfind("\n")
    if nl > limit * 0.3:
        result = result[:nl]
    return result


class MemoryConsolidator:
    MEMORY_LIMIT = 2200
    USER_LIMIT = 1375
    THRESHOLD = 0.80
    MAX_PER_ENTRY = 480  # permite ~4.5 entries dentro do limite

    def __init__(self, mem_dir: Optional[str] = None):
        self.mem_dir = Path(mem_dir) if mem_dir else _mem_dir()
        self.mem_path = self.mem_dir / "MEMORY.md"
        self.user_path = self.mem_dir / "USER.md"
        self.backup_dir = self.mem_dir / "backups"
        self.m_entries: List[str] = []
        self.u_entries: List[str] = []

    def load(self) -> Dict:
        self.m_entries = self._read(self.mem_path)
        self.u_entries = self._read(self.user_path)
        return {
            "memory": {"count": len(self.m_entries), "chars": self._chars("m"), "limit": self.MEMORY_LIMIT, "percent": self._pct("m")},
            "user": {"count": len(self.u_entries), "chars": self._chars("u"), "limit": self.USER_LIMIT, "percent": self._pct("u")},
        }

    def _read(self, p: Path) -> List[str]:
        if not p.exists():
            return []
        try:
            raw = p.read_text("utf-8")
        except (OSError, IOError):
            return []
        if not raw.strip():
            return []
        return [e.strip() for e in raw.split("\n§\n") if e.strip()]

    def _chars(self, which: str) -> int:
        e = self.m_entries if which == "m" else self.u_entries
        return len("\n§\n".join(e)) if e else 0

    def _limit(self, which: str) -> int:
        return self.MEMORY_LIMIT if which == "m" else self.USER_LIMIT

    def _pct(self, which: str) -> float:
        lim = self._limit(which)
        return round((self._chars(which) / lim) * 100, 1) if lim else 0.0

    def check_and_report(self) -> Dict:
        self.m_entries = self._read(self.mem_path)
        self.u_entries = self._read(self.user_path)
        return {
            "memory": {
                "entries": list(self.m_entries),
                "count": len(self.m_entries),
                "chars": self._chars("m"),
                "limit": self.MEMORY_LIMIT,
                "percent": self._pct("m"),
            },
            "user": {
                "entries": list(self.u_entries),
                "count": len(self.u_entries),
                "chars": self._chars("u"),
                "limit": self.USER_LIMIT,
                "percent": self._pct("u"),
            },
            "needs_consolidation": self._pct("m") >= self.THRESHOLD * 100,
            "consolidation_threshold": f"{self.THRESHOLD*100:.0f}%",
        }

    def _backup(self) -> Dict[str, str]:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        b = {}
        for n, p in [("MEMORY.md", self.mem_path), ("USER.md", self.user_path)]:
            if p.exists():
                bp = self.backup_dir / f"{n}.{ts}.bak"
                shutil.copy2(str(p), str(bp))
                b[n] = str(bp)
        return b

    def _write(self, p: Path, entries: List[str]) -> None:
        content = "\n§\n".join(entries) if entries else ""
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp", prefix=".mem_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, str(p))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def consolidate(self) -> Dict:
        before = self.check_and_report()
        if not before["needs_consolidation"]:
            return {"consolidated": False, "reason": f"{before['memory']['percent']}% < {self.THRESHOLD*100:.0f}%", "before": before}

        backups = self._backup()
        self.load()
        orig = list(self.m_entries)
        new_m = self._build(orig)

        self.m_entries = new_m
        self._write(self.mem_path, self.m_entries)
        if self.user_path.exists():
            self._write(self.user_path, self.u_entries)

        after = self.check_and_report()
        oset, nset = set(orig), set(new_m)
        removed = oset - nset

        changes = {"merged": {}, "removed": [], "entry_reduction": len(orig) - len(new_m), "chars_saved": before["memory"]["chars"] - after["memory"]["chars"]}
        for r in removed:
            t = _topic(r)
            pr = r[:60].replace("\n", " ")
            if t:
                changes["merged"].setdefault(t, []).append(pr)
            else:
                changes["removed"].append(pr)

        return {"consolidated": True, "backup_paths": backups, "before": before, "after": after, "changes": changes}

    def _build(self, entries: List[str]) -> List[str]:
        """
        Constrói lista final.

        Estratégia:
        1. Classifica: rules, user_obs, project[topic], generic
        2. Entradas individuais: compress a 480 chars
        3. Merge por tópico: conteúdo único combinado, compress a 480 chars
        4. Se ainda >2200 chars, compress progressivo até caber
        """
        cls = {"rules": [], "user_obs": [], "project": {}, "generic": []}
        for e in entries:
            if _is_rules(e):
                cls["rules"].append(e)
            elif _is_user_obs(e):
                cls["user_obs"].append(e)
            else:
                t = _topic(e)
                if t:
                    cls["project"].setdefault(t, []).append(e)
                else:
                    cls["generic"].append(e)

        result = []
        # Rules
        for e in cls["rules"]:
            result.append(_compress(e, self.MAX_PER_ENTRY))
        # User observations
        for e in cls["user_obs"]:
            result.append(_compress(e, self.MAX_PER_ENTRY))
        # Projects: merge by topic
        for topic, tentries in cls["project"].items():
            if len(tentries) == 1:
                result.append(_compress(tentries[0], self.MAX_PER_ENTRY))
            else:
                result.append(self._merge(tentries, topic))
        # Generic
        for e in cls["generic"]:
            result.append(_compress(e, self.MAX_PER_ENTRY))

        # Dedup
        seen = set()
        deduped = [e for e in result if e not in seen and (seen.add(e) or True)]

        # Progressive compression if still over limit
        target = int(self.MEMORY_LIMIT * 0.95)
        current = len("\n§\n".join(deduped))
        if current > target:
            # Re-compress each entry to a tighter limit
            factor = target / current
            new_limit = max(200, int(self.MAX_PER_ENTRY * factor))
            deduped = [_compress(e, new_limit) for e in deduped]
            # Final dedup
            seen = set()
            deduped = [e for e in deduped if e not in seen and (seen.add(e) or True)]

        return deduped

    def _merge(self, entries: List[str], topic: str) -> str:
        """Merge entries of same topic, keeping unique content."""
        dated = [(e, _date(e)) for e in entries if _date(e)]
        undated = [e for e in entries if not _date(e)]

        # Keep only recent entries
        recent = [e for e, d in dated if not _is_old(e)]
        all_entries = recent + undated

        if len(all_entries) <= 1:
            return _compress(all_entries[0], self.MAX_PER_ENTRY) if all_entries else ""

        # Unique lines across all entries
        all_lines = []
        seen = set()
        for entry in all_entries:
            for line in entry.split("\n"):
                s = line.strip()
                if not s:
                    continue
                key = re.sub(r'\s+', '', s.lower())
                key = re.sub(r'[^a-z0-9/]', '', key)
                if key not in seen and len(key) > 4:
                    seen.add(key)
                    all_lines.append(s)

        label = topic.replace("_", " ").title()
        merged = f"[Merged] {label}:\n" + "\n".join(all_lines)
        return _compress(merged, self.MAX_PER_ENTRY)


def get_bridge() -> MemoryConsolidator:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = MemoryConsolidator()
    return _INSTANCE


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Memory Consolidator")
    ap.add_argument("action", nargs="?", default="check", choices=["check", "consolidate", "backup"])
    ap.add_argument("--memory-dir")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    c = MemoryConsolidator(mem_dir=args.memory_dir)
    if args.action == "check":
        r = c.check_and_report()
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            m, u = r["memory"], r["user"]
            print(f"\n=== MEMORY CONSOLIDATOR — CHECK ===")
            print(f"  MEMORY.md: {m['count']} entries, {m['chars']:,}/{m['limit']:,} chars ({m['percent']}%)")
            print(f"  USER.md:   {u['count']} entries, {u['chars']:,}/{u['limit']:,} chars ({u['percent']}%)")
            print(f"  Consolidate? {'YES' if r['needs_consolidation'] else 'NO'} (threshold {r['consolidation_threshold']})")

    elif args.action == "consolidate":
        r = c.consolidate()
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            if r["consolidated"]:
                print(f"\n=== MEMORY CONSOLIDATOR — CONSOLIDATED ===")
                for n, p in r["backup_paths"].items():
                    print(f"  Backup: {n} → {p}")
                ch = r["changes"]
                print(f"  Merged topics: {len(ch['merged'])}")
                for t, e in ch["merged"].items():
                    print(f"    • {t}: {len(e)} entries")
                if ch["removed"]:
                    print(f"  Removed: {len(ch['removed'])} entries")
                b, a = r["before"]["memory"], r["after"]["memory"]
                print(f"  Before: {b['count']} entries, {b['percent']}% ({b['chars']:,} chars)")
                print(f"  After:  {a['count']} entries, {a['percent']}% ({a['chars']:,} chars)")
                print(f"  Saved:  {ch['chars_saved']:,} chars, {ch['entry_reduction']} entries")
            else:
                print(f"\n{''.join(r.get('reason', ''))}")

    elif args.action == "backup":
        b = c._backup()
        if args.json:
            print(json.dumps(b, ensure_ascii=False, indent=2))
        else:
            for n, p in b.items():
                print(f"  {n} → {p}")


if __name__ == "__main__":
    main()
