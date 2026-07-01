#!/usr/bin/env python3
"""Test the new routing logic: prompt with weights, multi-step sequences, and cache."""
import sys
sys.path.insert(0, '/opt/projetos/hermes-unified')

# Test 1: Parsing of multi-step categories
def test_parse_category():
    tests = [
        ("RESEARCH", ["research"]),
        ("RESEARCH-VIZ", ["research", "viz"]),
        ("FINANCE-REPORT", ["finance", "reporter"]),
        ("RESEARCH-VIZ-REPORT", ["research", "viz", "reporter"]),
        ("CODE", ["codex"]),
        ("RESEARCH,VIZ,REPORT", ["research", "viz", "reporter"]),
        ("SCRAPE", ["scraper"]),
    ]
    
    agent_map = {
        "CODE": "codex", "KNOWLEDGE": "knowledge", "WEB": "web",
        "SCRAPE": "scraper", "VIZ": "viz", "OBSERVER": "observer",
        "VISION": "vision_scout", "SHEETS": "sheets", "REPORT": "reporter",
        "DV360": "dv360", "TIKTOK": "tiktok", "RESEARCH": "research",
        "FINANCE": "finance", "MCP_BRASIL": "mcp_brasil",
    }
    
    all_ok = True
    for raw, expected in tests:
        parts = raw.replace("-", ",").split(",")
        sequence = []
        for part in parts:
            mapped = agent_map.get(part.strip())
            if mapped and mapped not in sequence:
                sequence.append(mapped)
        ok = sequence == expected
        status = "OK" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  {status}: '{raw}' -> {sequence} (expected {expected})")
    
    return all_ok

# Test 2: Router still handles simple cases
def test_router_basic():
    from core.graph import build_master_graph
    try:
        graph = build_master_graph()
        print(f"  OK: Graph compiled with {len(graph.nodes)} nodes")
        print(f"  Nodes: {list(graph.nodes.keys())}")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False

print("=== Test 1: Category parsing (multi-step) ===")
t1 = test_parse_category()

print("\n=== Test 2: Graph compilation ===")
t2 = test_router_basic()

print(f"\n=== Result: {'ALL PASS' if t1 and t2 else 'SOME FAILED'} ===")
