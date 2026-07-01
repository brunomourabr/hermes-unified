#!/usr/bin/env python3
"""
Ativa o curador de skills em modo real.
Antes: snapshot + backup. Depois: relatório do que foi feito.
"""
import sys, os
sys.path.insert(0, '/opt/projetos/hermes-unified')
from tools.skill_curator import get_bridge
import json

b = get_bridge()

# 1. Mostrar o que vai acontecer
print("🧹 CURADOR DE SKILLS - ATIVAÇÃO REAL")
print("=" * 60)

# 2. Executar curadoria real
print("\n📸 Criando snapshot de segurança...")
result_list = b.run_curation(run_llm_phase=False)
result = result_list[0] if isinstance(result_list, list) and len(result_list) > 0 else result_list
if isinstance(result, tuple):
    result = result[0]

print(f"\n📊 Resultado da curadoria:")
print(f"  Skills examinadas: {result.get('total_skills_analyzed', '?')}")
print(f"  Skills bundled (puladas): {len(result.get('bundled_skipped', []))}")
print(f"  Skills protegidas (puladas): {len(result.get('protected_skipped', []))}")
print(f"  Skills pinned (puladas): {len(result.get('pinned_skipped', []))}")

stale = result.get('stale_marked', [])
archived = result.get('archived', [])
broken = result.get('broken_found', [])
merges = result.get('merge_suggestions', [])

print(f"\n  🟡 Skills marcadas como STALE: {len(stale)}")
for s in stale:
    print(f"     • {s.get('name')} ({s.get('category')}) — {s.get('days_inactive')} dias inativo")

print(f"\n  📦 Skills ARQUIVADAS: {len(archived)}")
for s in archived:
    print(f"     • {s}")

print(f"\n  🔴 Skills QUEBRADAS: {len(broken)}")
for s in broken:
    print(f"     • {s}")

print(f"\n  🔗 Sugestões de MERGE: {len(merges)}")
for s in merges:
    print(f"     • {s}")

print(f"\n  📎 Snapshot: {result.get('snapshot', 'N/A')}")
print(f"  ❌ Erros: {len(result.get('errors', []))}")

print("\n✅ Curadoria concluída.")
print("   Skills marcadas como stale serão arquivadas automaticamente se não forem usadas por mais 60 dias.")
print("   Para reverter: extraia do snapshot em /opt/data/skills/.snapshots/")
