"""
Tests for Ad Analytics Bridges (DV360 and TikTok Ads)
Verifies both bridges work correctly in offline mode.
"""
import os
import sys
import json
import tempfile
from pathlib import Path

# Ensure project root is in path
project_root = "/opt/projetos/hermes-unified"
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def test_dv360_bridge_offline():
    """Test DV360Bridge in offline mode - no credentials needed."""
    print("\n" + "=" * 60)
    print("TEST: DV360 Bridge - Offline Mode")
    print("=" * 60)

    from tools.dv360_bridge import DV360Bridge, get_dv360_bridge

    # Test singleton pattern
    b1 = get_dv360_bridge()
    b2 = get_dv360_bridge()
    assert b1 is b2, "Singleton pattern failed: instances should be identical"
    print("  [OK] Singleton pattern works")

    bridge = DV360Bridge()
    assert bridge._is_online() == False, "Should be offline without credentials"
    print("  [OK] Bridge starts in offline mode")

    # Test list_advertisers
    advertisers, success, msg = bridge.list_advertisers()
    assert success, f"list_advertisers should succeed in offline mode: {msg}"
    assert len(advertisers) > 0, "Should return at least instructions"
    print(f"  [OK] list_advertisers: {msg}")

    # Test get_performance
    perf, success, msg = bridge.get_performance(
        advertiser_id="123456789",
        start_date="2024-01-01",
        end_date="2024-12-31"
    )
    assert success, f"get_performance should succeed in offline mode: {msg}"
    assert "advertiserId" in perf, "Performance data should contain advertiserId"
    assert "summary" in perf, "Performance data should contain summary"
    print(f"  [OK] get_performance: {msg}")

    # Test generate_report
    report_path, success, msg = bridge.generate_report(
        advertiser_id="123456789",
        start_date="2024-01-01",
        end_date="2024-12-31"
    )
    assert success, f"generate_report should succeed: {msg}"
    assert os.path.exists(report_path), f"Report file should exist: {report_path}"
    print(f"  [OK] generate_report: {msg}")
    print(f"       File: {report_path}")

    # Verify report content
    with open(report_path) as f:
        report = json.load(f)
    assert report["report_type"] == "dv360_performance"
    assert report["advertiser_id"] == "123456789"
    print(f"  [OK] Report content valid")

    # Test compare_periods
    comp_path, success, msg = bridge.compare_periods(
        advertiser_id="123456789",
        period1_start="2024-01-01",
        period1_end="2024-03-31",
        period2_start="2024-04-01",
        period2_end="2024-06-30"
    )
    assert success, f"compare_periods should succeed: {msg}"
    assert os.path.exists(comp_path), f"Comparison file should exist: {comp_path}"
    print(f"  [OK] compare_periods: {msg}")
    print(f"       File: {comp_path}")

    # Verify comparison content
    with open(comp_path) as f:
        comp = json.load(f)
    assert comp["type"] == "dv360_period_comparison"
    assert "deltas" in comp
    print(f"  [OK] Comparison content valid (deltas: {list(comp['deltas'].keys())})")

    # Test status
    status = bridge.status()
    assert status["online"] == False
    assert "available_methods" in status
    assert "setup_docs" in status
    print(f"  [OK] status() reports offline correctly")

    print(f"\n  >>> DV360 Bridge ALL TESTS PASSED <<<")
    return True


def test_tiktok_bridge_offline():
    """Test TikTokBridge in offline mode - no credentials needed."""
    print("\n" + "=" * 60)
    print("TEST: TikTok Ads Bridge - Offline Mode")
    print("=" * 60)

    from tools.tiktok_bridge import TikTokBridge, get_tiktok_bridge

    # Test singleton pattern
    b1 = get_tiktok_bridge()
    b2 = get_tiktok_bridge()
    assert b1 is b2, "Singleton pattern failed: instances should be identical"
    print("  [OK] Singleton pattern works")

    bridge = TikTokBridge()
    assert bridge._is_online() == False, "Should be offline without credentials"
    print("  [OK] Bridge starts in offline mode")

    # Test list_advertisers
    advertisers, success, msg = bridge.list_advertisers()
    assert success, f"list_advertisers should succeed in offline mode: {msg}"
    assert len(advertisers) > 0, "Should return at least instructions"
    print(f"  [OK] list_advertisers: {msg}")

    # Test get_campaign_performance
    camps, success, msg = bridge.get_campaign_performance(
        advertiser_id="1234567890",
        start_date="2024-01-01",
        end_date="2024-12-31"
    )
    assert success, f"get_campaign_performance should succeed: {msg}"
    assert "campaigns" in camps, "Should contain campaigns"
    assert len(camps["campaigns"]) > 0, "Should have sample campaigns"
    print(f"  [OK] get_campaign_performance: {msg} ({len(camps['campaigns'])} campaigns)")

    # Test get_adgroup_stats
    adgroups, success, msg = bridge.get_adgroup_stats(
        advertiser_id="1234567890",
        start_date="2024-01-01",
        end_date="2024-12-31"
    )
    assert success, f"get_adgroup_stats should succeed: {msg}"
    assert "adgroups" in adgroups, "Should contain adgroups"
    assert len(adgroups["adgroups"]) > 0, "Should have sample adgroups"
    print(f"  [OK] get_adgroup_stats: {msg} ({len(adgroups['adgroups'])} adgroups)")

    # Test generate_report
    report_path, success, msg = bridge.generate_report(
        advertiser_id="1234567890",
        start_date="2024-01-01",
        end_date="2024-12-31"
    )
    assert success, f"generate_report should succeed: {msg}"
    assert os.path.exists(report_path), f"Report file should exist: {report_path}"
    print(f"  [OK] generate_report: {msg}")
    print(f"       File: {report_path}")

    # Verify report content
    with open(report_path) as f:
        report = json.load(f)
    assert report["report_type"] == "tiktok_ads_performance"
    assert report["advertiser_id"] == "1234567890"
    assert "summary" in report
    print(f"  [OK] Report content valid (summary: {report['summary']})")

    # Test compare_periods
    comp_path, success, msg = bridge.compare_periods(
        advertiser_id="1234567890",
        period1_start="2024-01-01",
        period1_end="2024-03-31",
        period2_start="2024-04-01",
        period2_end="2024-06-30"
    )
    assert success, f"compare_periods should succeed: {msg}"
    assert os.path.exists(comp_path), f"Comparison file should exist: {comp_path}"
    print(f"  [OK] compare_periods: {msg}")
    print(f"       File: {comp_path}")

    # Verify comparison content
    with open(comp_path) as f:
        comp = json.load(f)
    assert comp["type"] == "tiktok_period_comparison"
    assert "deltas" in comp
    assert "campaign_comparisons" in comp
    print(f"  [OK] Comparison content valid (deltas: {list(comp['deltas'].keys())})")

    # Test status
    status = bridge.status()
    assert status["online"] == False
    assert "available_methods" in status
    assert "setup_docs" in status
    print(f"  [OK] status() reports offline correctly")

    print(f"\n  >>> TikTok Bridge ALL TESTS PASSED <<<")
    return True


def test_bridges_import_from_graph():
    """Test that the bridges can be imported from the graph module."""
    print("\n" + "=" * 60)
    print("TEST: Bridges importable from core.graph")
    print("=" * 60)

    # This tests that the imports work in graph.py
    from core.graph import build_master_graph

    # Test graph builds
    graph = build_master_graph()
    assert graph is not None, "Graph should compile successfully"

    # Check that dv360 and tiktok nodes are registered
    # We can inspect the graph's node names
    nodes = list(graph.nodes.keys())
    assert "dv360" in nodes, f"dv360 node should be in graph nodes: {nodes}"
    assert "tiktok" in nodes, f"tiktok node should be in graph nodes: {nodes}"
    print(f"  [OK] Graph nodes include dv360 and tiktok")
    print(f"  [OK] Registered nodes: {nodes}")

    print(f"\n  >>> Graph Integration TEST PASSED <<<")
    return True


def test_output_dirs():
    """Test that output directories are created."""
    print("\n" + "=" * 60)
    print("TEST: Output directories exist")
    print("=" * 60)

    dv360_dir = "/opt/projetos/hermes-unified/output/dv360/"
    tiktok_dir = "/opt/projetos/hermes-unified/output/tiktok/"

    assert os.path.exists(dv360_dir), f"DV360 output dir should exist: {dv360_dir}"
    assert os.path.exists(tiktok_dir), f"TikTok output dir should exist: {tiktok_dir}"

    # Check that files were created by previous tests
    dv360_files = [f for f in os.listdir(dv360_dir) if f.endswith(".json")]
    tiktok_files = [f for f in os.listdir(tiktok_dir) if f.endswith(".json")]

    print(f"  [OK] DV360 output dir: {dv360_dir} ({len(dv360_files)} files)")
    print(f"  [OK] TikTok output dir: {tiktok_dir} ({len(tiktok_files)} files)")

    print(f"\n  >>> Output Dir TEST PASSED <<<")
    return True


def run_all_tests():
    """Run all ad analytics bridge tests."""
    print("=" * 60)
    print("AD ANALYTICS BRIDGES - TEST SUITE")
    print("=" * 60)

    tests = [
        test_dv360_bridge_offline,
        test_tiktok_bridge_offline,
        test_bridges_import_from_graph,
        test_output_dirs,
    ]

    passed = 0
    failed = 0

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"\n  >>> FAILED: {test_fn.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
