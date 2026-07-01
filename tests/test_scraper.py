"""
Tests for the Scraper Bridge
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.scraper_bridge import ScraperBridge, get_scraper_bridge


class TestScraperBridge(unittest.TestCase):
    """Test cases for ScraperBridge."""

    def setUp(self):
        self.bridge = ScraperBridge()
        # Ensure it exists without raising
        self.assertIsNotNone(self.bridge)

    def test_init(self):
        """Test initialization."""
        self.assertTrue(
            self.bridge.firecrawl_path.endswith("bin/firecrawl")
        )
        # API key may or may not be set, just verify it's a string
        self.assertIsInstance(self.bridge.api_key, str)

    @patch("tools.scraper_bridge.subprocess.run")
    def test_scrape_url_success_json(self, mock_run):
        """Test scrape_url with successful JSON response."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "data": {
                "markdown": "# Test Content\n\nThis is test content."
            }
        })
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        content, success, msg = self.bridge.scrape_url("https://example.com")

        self.assertTrue(success)
        self.assertIn("Test Content", content)
        self.assertIn("Scraped", msg)

        # Verify command construction
        args = mock_run.call_args[0][0]
        self.assertIn("scrape", args)
        self.assertIn("https://example.com", args)

    @patch("tools.scraper_bridge.subprocess.run")
    def test_scrape_url_success_raw(self, mock_run):
        """Test scrape_url with raw (non-JSON) response."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "# Raw markdown content"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        content, success, msg = self.bridge.scrape_url("https://example.com")

        self.assertTrue(success)
        self.assertEqual(content, "# Raw markdown content")

    @patch("tools.scraper_bridge.subprocess.run")
    def test_scrape_url_failure(self, mock_run):
        """Test scrape_url with failure response."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: Failed to scrape"
        mock_run.return_value = mock_result

        content, success, msg = self.bridge.scrape_url("https://example.com")

        self.assertFalse(success)
        self.assertIn("Error", msg)

    @patch("tools.scraper_bridge.subprocess.run")
    def test_search_web_success(self, mock_run):
        """Test search_web with successful response."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "data": [
                {
                    "title": "Result 1",
                    "url": "https://example.com/1",
                    "description": "Description 1"
                },
                {
                    "title": "Result 2",
                    "url": "https://example.com/2",
                    "description": "Description 2"
                }
            ]
        })
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        results, success, msg = self.bridge.search_web("test query", max_results=5)

        self.assertTrue(success)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["title"], "Result 1")
        self.assertEqual(results[1]["url"], "https://example.com/2")

    @patch("tools.scraper_bridge.subprocess.run")
    def test_search_web_empty(self, mock_run):
        """Test search_web with empty results."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"data": []})
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        results, success, msg = self.bridge.search_web("test query")

        self.assertTrue(success)
        self.assertEqual(len(results), 0)

    @patch("tools.scraper_bridge.subprocess.run")
    def test_search_web_limit(self, mock_run):
        """Test search_web respects max_results."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "data": [
                {"title": f"Result {i}", "url": f"https://example.com/{i}", "description": ""}
                for i in range(10)
            ]
        })
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        results, success, msg = self.bridge.search_web("test", max_results=3)

        self.assertTrue(success)
        self.assertLessEqual(len(results), 3)

    @patch("tools.scraper_bridge.subprocess.run")
    def test_scrape_with_fallback_success(self, mock_run):
        """Test scrape_with_fallback when Firecrawl works."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "data": {"markdown": "# Success"}
        })
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        content, success, msg = self.bridge.scrape_with_fallback("https://example.com")

        self.assertTrue(success)
        self.assertEqual(content, "# Success")

    @patch("tools.scraper_bridge.subprocess.run")
    def test_scrape_with_fallback_failure(self, mock_run):
        """Test scrape_with_fallback generates fallback script on failure."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: Rate limited"
        mock_run.return_value = mock_result

        content, success, msg = self.bridge.scrape_with_fallback("https://example.com")

        self.assertFalse(success)
        self.assertIn("playwright", content)
        self.assertIn("fallback", msg.lower())

    def test_extract_links(self):
        """Test URL extraction from content."""
        content = """
        Visit https://example.com/page1 and https://example.com/page2
        Also check http://test.org
        """
        links = self.bridge.extract_links(content)

        self.assertEqual(len(links), 3)
        self.assertIn("https://example.com/page1", links)

    def test_get_page_title(self):
        """Test page title extraction."""
        title = self.bridge.get_page_title("# My Page Title\n\nSome content")
        self.assertEqual(title, "# My Page Title")

        title = self.bridge.get_page_title("")
        self.assertEqual(title, "Untitled")

    @patch("tools.scraper_bridge.subprocess.run")
    def test_batch_scrape(self, mock_run):
        """Test batch scraping multiple URLs."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "data": {"markdown": "# Content"}
        })
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        urls = ["https://example.com/a", "https://example.com/b"]
        results = self.bridge.batch_scrape(urls)

        self.assertEqual(len(results), 2)
        self.assertIn("https://example.com/a", results)

    def test_singleton(self):
        """Test get_scraper_bridge returns same instance."""
        bridge1 = get_scraper_bridge()
        bridge2 = get_scraper_bridge()
        self.assertIs(bridge1, bridge2)


if __name__ == "__main__":
    unittest.main()
