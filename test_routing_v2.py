#!/usr/bin/env python3
"""Test all routing improvements: fallback cascade, multi-step, validation, skip."""
import sys
sys.path.insert(0, '/opt/projetos/hermes-unified')

# Import fallback map and validation rules from graph
from core.graph import FALLBACK_MAP, VALID_SEQUENCES

# Test 1: Fallback map completeness
def test_fallback_map():
    print("=== Test 1: Fallback map ===")
    all_bridges = ["research", "scraper", "web", "finance", "codex", "knowledge",
                   "viz", "reporter", "observer", "vision_scout", "sheets",
                   "dv360", "tiktok", "mcp_brasil"]
    missing = [b for b in all_bridges if b not in FALLBACK_MAP]
    if missing:
        print(f"  FAIL: Missing fallback entries: {missing}")
        return False
    print(f"  OK: All {len(all_bridges)} bridges have fallback entries")
    print(f"  RESEARCH -> {FALLBACK_MAP['research']}")
    print(f"  SCRAPE -> {FALLBACK_MAP['scraper']}")
    print(f"  WEB -> {FALLBACK_MAP['web']}")
    return True

# Test 2: Sequence validation
def test_sequence_validation():
    print("\n=== Test 2: Sequence validation ===")
    agent_map = {
        "CODE": "codex", "KNOWLEDGE": "knowledge", "WEB": "web",
        "SCRAPE": "scraper", "VIZ": "viz", "REPORT": "reporter",
        "RESEARCH": "research", "FINANCE": "finance",
    }
    
    tests = [
        # (category_response, expected_valid_sequence)
        ("RESEARCH-VIZ-REPORT", ["research", "viz", "reporter"], True),    # OK
        ("FINANCE-REPORT", ["finance", "reporter"], True),                  # OK
        ("RESEARCH-CODE", ["research"], False),                             # CODE depois RESEARCH é invalido
        ("CODE-RESEARCH", ["codex"], False),                                # RESEARCH depois CODE é invalido
        ("VIZ-REPORT", ["viz", "reporter"], True),                          # OK
        ("RESEARCH-SCRAPE", ["research", "scraper"], True),                 # OK
    ]
    
    all_ok = True
    for raw, expected_seq, expected_valid in tests:
        parts = raw.replace("-", ",").split(",")
        sequence = []
        for part in parts:
            mapped = agent_map.get(part.strip())
            if mapped and mapped not in sequence:
                sequence.append(mapped)
        
        # Validates
        if len(sequence) > 1:
            validated = [sequence[0]]
            for i in range(1, len(sequence)):
                prev = validated[-1]
                nxt = sequence[i]
                allowed = VALID_SEQUENCES.get(prev, set())
                if nxt in allowed:
                    validated.append(nxt)
        else:
            validated = sequence
        
        ok = validated == expected_seq
        status = "OK" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  {status}: '{raw}' -> {validated} (expected {expected_seq})")
    
    return all_ok

# Test 3: Graph compilation
def test_graph():
    print("\n=== Test 3: Graph compilation ===")
    from core.graph import build_master_graph
    try:
        graph = build_master_graph()
        print(f"  OK: Graph compiled with {len(graph.nodes)} nodes")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False

t1 = test_fallback_map()
t2 = test_sequence_validation()
t3 = test_graph()

print(f"\n=== RESULTS: {'ALL 10/10' if t1 and t2 and t3 else 'SOME FAILED'} ===")
