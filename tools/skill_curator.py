"""
Skill Curator Bridge - Curador automatico de skills para Hermes
Executa semanalmente via cron para:
  FASE 1 (deterministica): marcar skills stale/mover para archive
  FASE 2 (LLM opcional): detectar similaridades e skills quebradas

Singleton + get_bridge() padrao. Retorna (dict, bool, str).
"""
import os
import json
import sys
import tarfile
import shutil
import re
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional, Set

SKILLS_DIR = Path("/opt/data/skills")
ARCHIVE_DIR = SKILLS_DIR / ".archive"
SNAPSHOT_DIR = SKILLS_DIR / ".snapshots"
BUNDLED_MANIFEST = SKILLS_DIR / ".bundled_manifest"
PROTECTED_CATEGORIES = {"software-development", "devops", "github"}
STALE_DAYS = 30
ARCHIVE_DAYS = 90

# --- Estado singleton ---
_curator_bridge = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(msg: str):
    print(f"[skill_curator] {msg}", flush=True)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_bundled_set() -> Set[str]:
    """Carrega o conjunto de skill names que sao bundled (protegidos)."""
    if not BUNDLED_MANIFEST.exists():
        return set()
    bundled: Set[str] = set()
    with open(BUNDLED_MANIFEST) as f:
        for line in f:
            line = line.strip()
            if not line or ":" not in line:
                continue
            name = line.split(":")[0].strip()
            if name:
                bundled.add(name)
    return bundled


def _find_all_skills() -> List[Dict]:
    """
    Varre o diretorio de skills e retorna uma lista de dicts:
      {
        "name": str,
        "category": str,
        "path": Path (caminho da pasta da skill),
        "skill_md": Path (caminho do SKILL.md),
        "depth": 2 ou 3 (se SKILL.md esta na raiz da categoria ou subdir),
      }
    """
    skills = []
    # Depth 2: category/SKILL.md
    for cat_dir in SKILLS_DIR.iterdir():
        if not cat_dir.is_dir() or cat_dir.name.startswith("."):
            continue
        skill_md = cat_dir / "SKILL.md"
        if skill_md.exists():
            skills.append({
                "name": cat_dir.name,
                "category": cat_dir.name,
                "path": cat_dir,
                "skill_md": skill_md,
                "depth": 2,
            })
        # Depth 3: category/skillname/SKILL.md
        for sub_dir in cat_dir.iterdir():
            if not sub_dir.is_dir() or sub_dir.name.startswith("."):
                continue
            skill_md = sub_dir / "SKILL.md"
            if skill_md.exists():
                skills.append({
                    "name": sub_dir.name,
                    "category": cat_dir.name,
                    "path": sub_dir,
                    "skill_md": skill_md,
                    "depth": 3,
                })
    return skills


def _is_pinned(skill_path: Path) -> bool:
    """Verifica se existe .hermes_curator_pin na pasta da skill."""
    return (skill_path / ".hermes_curator_pin").exists()


def _is_protected_category(category: str) -> bool:
    return category in PROTECTED_CATEGORIES


def _is_bundled(skill_name: str, bundled_set: Set[str]) -> bool:
    return skill_name in bundled_set


def _parse_yaml_frontmatter(content: str) -> Optional[Dict]:
    """Tenta parsear YAML frontmatter de um SKILL.md.
    Retorna dict se valido, None se invalido/ausente.
    """
    # Padrao: ---\n... YAML ...\n---\n
    match = re.match(r"^---\s*\n(.+?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return None
    yaml_block = match.group(1)
    # Validacao basica: deve conter ao menos "name:" ou chave similar
    if not re.search(r"^\w+:", yaml_block, re.MULTILINE):
        return None
    # Parse minimo: extrai algumas chaves conhecidas
    result = {}
    for line in yaml_block.splitlines():
        m = re.match(r"^(\w[\w_-]*)\s*:\s*(.+)$", line)
        if m:
            key = m.group(1)
            value = m.group(2).strip()
            if value.startswith("[") or value.startswith("{"):
                continue  # pula listas/dicts complexos no parse simples
            result[key] = value
    return result if result else None


def _get_file_mtime_days(path: Path) -> int:
    """Retorna quantos dias passaram desde a ultima modificacao do arquivo."""
    if not path.exists():
        return 0
    mtime = os.path.getmtime(path)
    mtime_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
    delta = datetime.now(timezone.utc) - mtime_dt
    return delta.days


def _take_snapshot(skills_affected: List[Path], snapshot_name: str) -> bool:
    """Faz um snapshot tar.gz das skills que serao alteradas."""
    try:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        snapshot_path = SNAPSHOT_DIR / f"{snapshot_name}.tar.gz"
        with tarfile.open(snapshot_path, "w:gz") as tar:
            for skill_path in skills_affected:
                if skill_path.exists():
                    arcname = str(skill_path.relative_to(SKILLS_DIR))
                    tar.add(skill_path, arcname=arcname)
        _log(f"Snapshot salvo: {snapshot_path}")
        return True
    except Exception as e:
        _log(f"Erro ao criar snapshot: {e}")
        return False


def _call_llm_for_merge_suggestions(skills: List[Dict]) -> List[Dict]:
    """
    Usa LLM (via hermes_bridge ou subprocess) para sugerir merges
    entre skills similares. Retorna lista de dicts com sugestoes.
    """
    # Tenta usar deepseek via API
    try:
        # Primeiro tenta importar config do projeto
        sys.path.insert(0, str(Path("/opt/projetos/hermes-unified")))
        from config import get_api_key

        api_key = get_api_key("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            return []

        # Prepara lista compacta de skills
        skill_list = []
        for s in skills:
            name = s["name"]
            cat = s["category"]
            desc = ""
            try:
                content = s["skill_md"].read_text()
                fm = _parse_yaml_frontmatter(content)
                if fm:
                    desc = fm.get("description", "")
            except Exception:
                pass
            skill_list.append(f"  - {cat}/{name}: {desc[:200]}")

        prompt = f"""You are a skill curator for an AI agent system. Analyze these skills for similarities and suggest merges.

Rules:
- Only suggest merging skills that are CLEARLY redundant or near-identical
- Ignore skills in different categories unless they overlap completely
- For each suggested merge: name the primary skill and the skill(s) to merge into it
- Output as a JSON array of objects: [{{"primary": "skill-name", "merge": ["other-skill"], "reason": "..."}}]
- Return empty array [] if no merges are needed

Skills:
{chr(10).join(skill_list)}

Output ONLY valid JSON, no other text."""

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "You are a precise JSON-only assistant. Respond only with valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 2000,
        }

        import requests
        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        if resp.status_code != 200:
            _log(f"LLM API error: {resp.status_code} - {resp.text[:200]}")
            return []

        data = resp.json()
        text = data["choices"][0]["message"]["content"].strip()
        # Limpa possiveis delimitadores markdown
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

        suggestions = json.loads(text)
        if isinstance(suggestions, list):
            _log(f"LLM sugeriu {len(suggestions)} merge(s)")
            return suggestions
        return []

    except ImportError:
        _log("config module not available for LLM calls")
        return []
    except Exception as e:
        _log(f"LLM call failed: {e}")
        return []


def _check_broken_skills(skills: List[Dict]) -> List[Dict]:
    """
    Verifica skills quebradas (SKILL.md sem YAML frontmatter valido).
    Retorna lista de dicts: [{"name": ..., "path": ..., "issue": ...}]
    """
    broken = []
    for s in skills:
        try:
            content = s["skill_md"].read_text()
            fm = _parse_yaml_frontmatter(content)
            if fm is None:
                broken.append({
                    "name": s["name"],
                    "category": s["category"],
                    "path": str(s["skill_md"]),
                    "issue": "YAML frontmatter invalido ou ausente",
                })
            elif "name" not in fm:
                broken.append({
                    "name": s["name"],
                    "category": s["category"],
                    "path": str(s["skill_md"]),
                    "issue": "Frontmatter sem campo 'name'",
                })
        except Exception as e:
            broken.append({
                "name": s["name"],
                "category": s["category"],
                "path": str(s["skill_md"]),
                "issue": f"Erro de leitura: {e}",
            })
    return broken

# ---------------------------------------------------------------------------
# Bridge Class
# ---------------------------------------------------------------------------

class SkillCuratorBridge:
    """
    Curador automatico de skills.
    FASE 1: Stale detection + arquivamento (deterministico).
    FASE 2: Similaridade + broken detection (LLM opcional).
    """
    def __init__(self):
        self.skills_dir = SKILLS_DIR
        self.archive_dir = ARCHIVE_DIR
        self.snapshot_dir = SNAPSHOT_DIR
        self.bundled_set = _load_bundled_set()

    def run_curation(self, run_llm_phase: bool = False) -> Tuple[Dict, bool, str]:
        """
        Executa a curadoria completa.
        
        Args:
            run_llm_phase: Se True, executa FASE 2 com LLM.
        
        Returns:
            (result_dict, success, message)
        """
        results = {
            "timestamp": _timestamp(),
            "stale_marked": [],
            "archived": [],
            "protected_skipped": [],
            "bundled_skipped": [],
            "pinned_skipped": [],
            "broken_found": [],
            "merge_suggestions": [],
            "snapshot": None,
            "errors": [],
        }
        success = True
        messages = []

        try:
            all_skills = _find_all_skills()
            _log(f"Total skills encontradas: {len(all_skills)}")

            # --- FASE 1: Stale detection + archive ---
            archived_skills = []
            stale_to_mark = []
            snapshot_paths = []

            for skill in all_skills:
                name = skill["name"]
                cat = skill["category"]
                skill_path = skill["path"]

                # Seguranca: bundled
                if _is_bundled(name, self.bundled_set):
                    _log(f"  [SKIP] {name} e bundled, pulando")
                    results["bundled_skipped"].append(f"{cat}/{name}")
                    continue

                # Seguranca: pinned
                if _is_pinned(skill_path):
                    _log(f"  [SKIP] {name} tem .hermes_curator_pin, pulando")
                    results["pinned_skipped"].append(f"{cat}/{name}")
                    continue

                # Protecao: archive nunca para categorias protegidas
                protected = _is_protected_category(cat)
                if protected:
                    _log(f"  [PROTECTED] {name} na categoria protegida '{cat}'")

                mtime_days = _get_file_mtime_days(skill["skill_md"])
                _log(f"  {cat}/{name}: {mtime_days} dias sem modificacao")

                # Arquiva se 90+ dias (e nao protegido)
                if mtime_days >= ARCHIVE_DAYS and not protected:
                    snapshot_paths.append(skill_path)
                    archived_skills.append(skill)
                    results["archived"].append({
                        "name": name,
                        "category": cat,
                        "days_inactive": mtime_days,
                    })
                    continue

                # Marca stale se 30+ dias (pode estar em categorias protegidas)
                if mtime_days >= STALE_DAYS:
                    snapshot_paths.append(skill_path)
                    stale_to_mark.append(skill)
                    results["stale_marked"].append({
                        "name": name,
                        "category": cat,
                        "days_inactive": mtime_days,
                    })

                # Protegidas que nao entraram em stale/archive
                if protected and mtime_days >= STALE_DAYS:
                    results["protected_skipped"].append(f"{cat}/{name}")

            # --- Snapshot antes de alterar ---
            if snapshot_paths:
                snap_name = f"curation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                snap_ok = _take_snapshot(snapshot_paths, snap_name)
                results["snapshot"] = snap_name if snap_ok else None
                if not snap_ok:
                    results["errors"].append("Falha ao criar snapshot")
                    # Continua mesmo assim (operacoes sao reversiveis)

            # --- Executa archive moves ---
            for skill in archived_skills:
                try:
                    self._archive_skill(skill)
                    _log(f"  [ARCHIVED] {skill['category']}/{skill['name']}")
                except Exception as e:
                    results["errors"].append(f"Erro ao arquivar {skill['name']}: {e}")
                    success = False

            # --- Executa stale rename ---
            for skill in stale_to_mark:
                try:
                    self._mark_stale(skill)
                    _log(f"  [STALE] {skill['category']}/{skill['name']}")
                except Exception as e:
                    results["errors"].append(f"Erro ao marcar stale {skill['name']}: {e}")
                    success = False

            # --- FASE 2: LLM opcional ---
            if run_llm_phase:
                _log("Iniciando FASE 2 (LLM)...")

                # Broken skills
                try:
                    broken = _check_broken_skills(all_skills)
                    results["broken_found"] = broken
                    _log(f"Encontradas {len(broken)} skills quebradas")
                except Exception as e:
                    results["errors"].append(f"Erro ao checar broken skills: {e}")

                # Merge suggestions
                try:
                    merge_suggestions = _call_llm_for_merge_suggestions(all_skills)
                    results["merge_suggestions"] = merge_suggestions
                    _log(f"Recebidas {len(merge_suggestions)} sugestoes de merge")
                except Exception as e:
                    results["errors"].append(f"Erro ao sugerir merges: {e}")

            # --- Build summary message ---
            parts = []
            if results["stale_marked"]:
                parts.append(f"{len(results['stale_marked'])} stale(s)")
            if results["archived"]:
                parts.append(f"{len(results['archived'])} arquivada(s)")
            if results["broken_found"]:
                parts.append(f"{len(results['broken_found'])} quebrada(s)")
            if results["merge_suggestions"]:
                parts.append(f"{len(results['merge_suggestions'])} merge(s) sugerido(s)")
            if results["errors"]:
                parts.append(f"{len(results['errors'])} erro(s)")

            summary = " | ".join(parts) if parts else "Nenhuma acao necessaria"
            msg = f"Curadoria concluida: {summary}"
            messages.append(msg)

            _log(msg)

        except Exception as e:
            success = False
            results["errors"].append(f"Erro fatal: {e}")
            msg = f"Erro fatal na curadoria: {e}"
            messages.append(msg)
            _log(msg)

        return results, success, "; ".join(messages)

    # ------------------------------------------------------------------
    # Operacoes de arquivo
    # ------------------------------------------------------------------

    def _archive_skill(self, skill: Dict):
        """Move a skill para .archive/."""
        name = skill["name"]
        skill_path = skill["path"]
        cat = skill["category"]

        # Cria diretorio .archive com mesma estrutura
        archive_path = self.archive_dir / cat / name
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        # Move
        shutil.move(str(skill_path), str(archive_path))
        _log(f"Movido {cat}/{name} -> {archive_path}")

    def _mark_stale(self, skill: Dict):
        """Renomeia SKILL.md para SKILL.stale.md."""
        skill_md = skill["skill_md"]
        stale_md = skill_md.with_name("SKILL.stale.md")
        if stale_md.exists():
            stale_md.unlink()
        shutil.move(str(skill_md), str(stale_md))
        # Cria um arquivo de metadata
        meta = skill_md.with_name(".stale_info")
        meta.write_text(json.dumps({
            "stale_at": _timestamp(),
            "days_inactive": _get_file_mtime_days(skill_md),
            "original": "SKILL.md",
        }, indent=2))
        _log(f"Marcado stale: {skill['category']}/{skill['name']}")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

def get_bridge() -> SkillCuratorBridge:
    """Retorna instancia singleton do SkillCuratorBridge."""
    global _curator_bridge
    if _curator_bridge is None:
        _curator_bridge = SkillCuratorBridge()
    return _curator_bridge


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """CLI para teste manual."""
    import argparse
    parser = argparse.ArgumentParser(description="Skill Curator - Curador automatico de skills")
    parser.add_argument("--llm", action="store_true", help="Executa FASE 2 com LLM")
    parser.add_argument("--dry-run", action="store_true", help="Apenas loga, nao executa alteracoes")
    args = parser.parse_args()

    if args.dry_run:
        _log("=== DRY RUN ===")
        _log("Skills encontradas:")
        for s in _find_all_skills():
            mtime = _get_file_mtime_days(s["skill_md"])
            bundled = "BUNDLED" if _is_bundled(s["name"], _load_bundled_set()) else ""
            pinned = "PINNED" if _is_pinned(s["path"]) else ""
            protected = "PROTECTED" if _is_protected_category(s["category"]) else ""
            flags = " ".join(filter(None, [bundled, pinned, protected]))
            _log(f"  {s['category']}/{s['name']}: {mtime}d {flags}")
        _log("=== FIM DRY RUN ===")
        return

    bridge = get_bridge()
    results, success, message = bridge.run_curation(run_llm_phase=args.llm)
    print(json.dumps(results, indent=2, default=str))
    print(f"\nSuccess: {success}")
    print(f"Message: {message}")


if __name__ == "__main__":
    main()
