"""
Tests for the 4 new bridges: Sheets, Social, Reporter, Campaign
"""
import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.sheets_bridge import SheetsBridge, get_sheets_bridge
from tools.reporter_bridge import ReporterBridge, get_reporter_bridge
from tools.campaign_bridge import CampaignBridge, get_campaign_bridge


class TestSheetsBridge(unittest.TestCase):
    """Test cases for SheetsBridge (offline mode without Google creds)."""

    def setUp(self):
        self.bridge = SheetsBridge()
        self.assertIsNotNone(self.bridge)

    def test_init(self):
        """Test initialization - should run in offline mode."""
        self.assertIsNotNone(self.bridge)
        self.assertTrue(os.path.exists(self.bridge.output_dir))
        # Should be None since we don't have google creds in test
        self.assertIsNone(self.bridge.client)

    def test_create_sheet_offline(self):
        """Test create_sheet in offline mode (local JSON/CSV)."""
        result, success, msg = self.bridge.create_sheet(
            "Test Sheet",
            ["Name", "Email", "Score"],
            [
                ["Alice", "alice@test.com", "95"],
                ["Bob", "bob@test.com", "87"]
            ]
        )
        self.assertTrue(success)
        self.assertIn("Sheet saved locally", msg)
        self.assertTrue(os.path.exists(result) or ", " in str(result))

        # Check that files were created in output dir
        files = os.listdir(self.bridge.output_dir)
        json_files = [f for f in files if f.endswith(".json")]
        csv_files = [f for f in files if f.endswith(".csv")]
        self.assertGreater(len(json_files), 0)
        self.assertGreater(len(csv_files), 0)

    def test_read_sheet_local(self):
        """Test reading a sheet we just created."""
        # Clean test-specific sheet
        result, success, msg = self.bridge.create_sheet(
            "Read Test Only",
            ["A", "B"],
            [["1", "2"], ["3", "4"]]
        )
        self.assertTrue(success)

        # Now read it using the exact path returned
        data, success, msg = self.bridge.read_sheet(result)
        self.assertTrue(success)
        self.assertIn("Read Test Only", str(data))

    def test_append_row(self):
        """Test appending a row to a local sheet."""
        result, success, msg = self.bridge.create_sheet(
            "Append Test",
            ["X", "Y"],
            [["1", "2"]]
        )
        self.assertTrue(success)

        # Get the JSON path
        files = sorted([f for f in os.listdir(self.bridge.output_dir) if f.endswith(".json")])
        self.assertGreater(len(files), 0)

        # Append
        ok, msg = self.bridge.append_row(
            os.path.join(self.bridge.output_dir, files[-1]),
            ["3", "4"]
        )
        self.assertTrue(ok)

    def test_list_sheets(self):
        """Test listing available sheets."""
        sheets, success, msg = self.bridge.list_sheets()
        self.assertTrue(success)
        self.assertIsInstance(sheets, list)

    def test_export_to_csv(self):
        """Test export to CSV."""
        result, success, msg = self.bridge.create_sheet(
            "Export Test",
            ["A", "B"],
            [["1", "2"]]
        )
        self.assertTrue(success)

        files = sorted([f for f in os.listdir(self.bridge.output_dir) if f.endswith(".json")])
        if files:
            csv_path, ok, msg = self.bridge.export_to_csv(
                os.path.join(self.bridge.output_dir, files[-1])
            )
            self.assertTrue(ok)
            self.assertTrue(csv_path.endswith(".csv"))

    def test_singleton(self):
        """Test get_sheets_bridge returns the same instance."""
        bridge1 = get_sheets_bridge()
        bridge2 = get_sheets_bridge()
        self.assertIs(bridge1, bridge2)



class TestReporterBridge(unittest.TestCase):
    """Test cases for ReporterBridge."""

    def setUp(self):
        self.bridge = ReporterBridge()
        self.assertIsNotNone(self.bridge)

    def test_init(self):
        """Test initialization."""
        self.assertIsNotNone(self.bridge)
        self.assertTrue(os.path.exists(self.bridge.output_dir))

    def test_generate_html_report(self):
        """Test generating an HTML report."""
        sections = [
            {"heading": "Introduction", "content": "This is the introduction section.\nIt has multiple lines."},
            {"heading": "Findings", "content": "- Finding one\n- Finding two\n- Finding three"},
            {"heading": "Conclusion", "content": "This concludes the report."}
        ]

        path, success, msg = self.bridge.generate_html_report(
            "Test HTML Report",
            sections
        )
        self.assertTrue(success)
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith(".html"))

        # Verify content
        with open(path) as f:
            content = f.read()
        self.assertIn("Test HTML Report", content)
        self.assertIn("Introduction", content)
        self.assertIn("Findings", content)
        self.assertIn("Conclusion", content)

    def test_generate_pdf(self):
        """Test generating a PDF report."""
        sections = [
            {"heading": "Section 1", "content": "Content for section 1."},
            {"heading": "Section 2", "content": "Content for section 2.\n- Bullet A\n- Bullet B"}
        ]

        path, success, msg = self.bridge.generate_pdf(
            "Test PDF Report",
            sections,
            filename="test_report_unit.pdf"
        )
        self.assertTrue(success)
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith(".pdf"))

    def test_generate_full_report(self):
        """Test generating a full report (PDF + HTML)."""
        sections = [
            {"heading": "Chapter 1", "content": "Content for chapter 1."},
            {"heading": "Chapter 2", "content": "Content for chapter 2."}
        ]

        results, success, msg = self.bridge.generate_full_report(
            "Full Report Test",
            sections
        )
        self.assertTrue(success)
        self.assertIn("pdf_path", results)
        self.assertIn("html_path", results)
        self.assertTrue(os.path.exists(results["pdf_path"]))
        self.assertTrue(os.path.exists(results["html_path"]))

    def test_singleton(self):
        """Test get_reporter_bridge returns the same instance."""
        bridge1 = get_reporter_bridge()
        bridge2 = get_reporter_bridge()
        self.assertIs(bridge1, bridge2)


class TestCampaignBridge(unittest.TestCase):
    """Test cases for CampaignBridge (scaffold)."""

    def setUp(self):
        self.bridge = CampaignBridge()
        self.assertIsNotNone(self.bridge)

    def test_init(self):
        """Test initialization."""
        self.assertIsNotNone(self.bridge)
        self.assertTrue(os.path.exists(self.bridge.output_dir))

    def test_status(self):
        """Test status returns configuration requirements."""
        status = self.bridge.status()
        self.assertIsInstance(status, dict)
        self.assertIn("google_ads_configured", status)
        self.assertIn("meta_ads_configured", status)
        self.assertIn("google_ads_needed", status)
        self.assertIn("meta_ads_needed", status)
        # Should have 5 google items and 4 meta items
        self.assertEqual(len(status["google_ads_needed"]), 5)
        self.assertEqual(len(status["meta_ads_needed"]), 4)

    def test_track_google_ads(self):
        """Test track_google_ads returns instructions (not configured)."""
        result, success, msg = self.bridge.track_google_ads("123-456-7890")
        self.assertFalse(success)  # Not configured
        self.assertIn("not configured", msg.lower())

    def test_track_meta_ads(self):
        """Test track_meta_ads returns instructions (not configured)."""
        result, success, msg = self.bridge.track_meta_ads("act_123456789")
        self.assertFalse(success)  # Not configured
        self.assertIn("not configured", msg.lower())

    def test_singleton(self):
        """Test get_campaign_bridge returns the same instance."""
        bridge1 = get_campaign_bridge()
        bridge2 = get_campaign_bridge()
        self.assertIs(bridge1, bridge2)


class TestGraphIntegration(unittest.TestCase):
    """Test that the graph can import and build with new nodes."""

    def test_graph_builds(self):
        """Test that build_master_graph compiles without errors."""
        try:
            from core.graph import build_master_graph
            graph = build_master_graph()
            self.assertIsNotNone(graph)
        except Exception as e:
            self.fail(f"Graph build failed: {e}")


if __name__ == "__main__":
    unittest.main()
