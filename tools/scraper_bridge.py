"""
Scraper Bridge - Integrates Firecrawl CLI + browser fallback for web scraping
Provides web scraping and search capabilities to the LangGraph system
"""

import subprocess
import os
import json
import re
from typing import Dict, Optional, List, Tuple
from pathlib import Path

from config import get_api_key


class ScraperBridge:
    """
    Bridge between LangGraph and Firecrawl CLI.
    Allows web scraping, searching, and content extraction.
    """

    def __init__(self):
        self.firecrawl_path = os.path.expanduser(
            "~/.nvm/versions/node/v22.23.1/bin/firecrawl"
        )
        self.api_key = get_api_key("FIRECRAWL_API_KEY")

    def _run_firecrawl(self, args: List[str]) -> Tuple[str, bool, str]:
        """Execute firecrawl CLI with given arguments."""
        if not self.api_key:
            return "", False, "FIRECRAWL_API_KEY not configured"

        env = os.environ.copy()
        env["FIRECRAWL_API_KEY"] = self.api_key

        cmd = [self.firecrawl_path] + args

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )

            if result.returncode == 0:
                return result.stdout, True, "Success"
            else:
                stderr = result.stderr or ""
                return stderr, False, f"Firecrawl error: {stderr[:500]}"

        except subprocess.TimeoutExpired:
            return "", False, "Timeout after 120 seconds"
        except FileNotFoundError:
            return "", False, f"Firecrawl CLI not found at {self.firecrawl_path}"
        except Exception as e:
            return "", False, f"Exception: {str(e)}"

    def scrape_url(self, url: str, format: str = "markdown") -> Tuple[str, bool, str]:
        """
        Scrape a single URL using Firecrawl.

        Args:
            url: The URL to scrape
            format: Output format ("markdown", "html", "text")

        Returns:
            Tuple[content, success, message]
        """
        content, success, msg = self._run_firecrawl([
            "scrape", url,
            "--format", format
        ])

        if success and content:
            # Try to parse JSON response from Firecrawl
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    # Extract the actual content from response
                    if "data" in data and isinstance(data["data"], dict):
                        extracted = data["data"].get("markdown",
                                     data["data"].get("content",
                                     data["data"].get("text", content)))
                        return extracted, True, f"Scraped {url}"
                    elif "content" in data:
                        return data["content"], True, f"Scraped {url}"
            except (json.JSONDecodeError, TypeError):
                pass

            return content, True, f"Scraped {url} ({len(content)} chars)"

        return "", False, msg

    def search_web(self, query: str, max_results: int = 5) -> Tuple[List[dict], bool, str]:
        """
        Search the web using Firecrawl.

        Args:
            query: Search query string
            max_results: Maximum number of results to return

        Returns:
            Tuple[results_list, success, message]
        """
        content, success, msg = self._run_firecrawl([
            "search", query,
            "--limit", str(max_results)
        ])

        if success and content:
            # Firecrawl search returns plain text, not JSON
            # Format: "Title\n  URL: https://...\n  Description..."
            results = []
            lines = content.split('\n')
            current = {}
            for line in lines:
                line = line.strip()
                if line.startswith('URL:'):
                    current['url'] = line[4:].strip()
                elif line and not line.startswith('URL:') and not line.startswith('  '):
                    if current.get('title'):
                        results.append(current)
                    current = {'title': line, 'url': '', 'description': ''}
                elif line and line.startswith('  ') and not line.startswith('  URL'):
                    current['description'] = (current.get('description', '') + ' ' + line.strip()).strip()

            if current.get('title'):
                results.append(current)

            results = results[:max_results]
            if results:
                return results, True, f"{len(results)} results found"
            else:
                # Fallback: return raw text
                return [{"title": "Search Results", "url": "", "description": content[:2000]}], True, "Raw text"

        return [], False, msg

    def scrape_with_fallback(self, url: str) -> Tuple[str, bool, str]:
        """
        Scrape a URL using Firecrawl first, with fallback instructions.

        First tries Firecrawl CLI. If that fails, returns instructions
        for browser-based fallback using Playwright/Selenium.

        Args:
            url: The URL to scrape

        Returns:
            Tuple[content_or_instructions, success, message]
        """
        content, success, msg = self.scrape_url(url, format="markdown")

        if success:
            return content, True, msg

        # Fallback: provide instructions for browser-based scraping
        fallback_script = f'''#!/usr/bin/env python3
"""
Browser fallback scraper for: {url}
Install: pip install playwright
Then: playwright install chromium

Usage: python {url.replace("/", "_").replace(":", "_")}_scraper.py
"""
import asyncio
import sys

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Install playwright: pip install playwright && playwright install chromium")
    sys.exit(1)

async def scrape():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("{url}", wait_until="networkidle")
        page_text = await page.inner_text("body")
        with open("scraped_output.md", "w") as f:
            f.write(page_text)
        print("Scraped", len(page_text), "chars to scraped_output.md")

asyncio.run(scrape())
'''
        return fallback_script, False, f"Firecrawl failed: {msg}. Fallback script generated."

    def extract_links(self, content: str) -> List[str]:
        """Extract URLs from scraped content."""
        url_pattern = r'https?://[^\s<>"\']+'
        return list(set(re.findall(url_pattern, content)))

    def get_page_title(self, content: str) -> str:
        """Extract likely page title from first line or heading."""
        lines = [l.strip() for l in content.split('\n') if l.strip()]
        if lines:
            # First non-empty line is often the title
            return lines[0][:100]
        return "Untitled"

    def batch_scrape(self, urls: List[str], format: str = "markdown") -> Dict[str, Tuple[str, bool, str]]:
        """
        Scrape multiple URLs sequentially.

        Args:
            urls: List of URLs to scrape
            format: Output format

        Returns:
            Dict mapping URL to (content, success, message)
        """
        results = {}
        for url in urls:
            results[url] = self.scrape_url(url, format)
        return results


# Singleton for reusability
_scraper_bridge = None

def get_scraper_bridge() -> ScraperBridge:
    global _scraper_bridge
    if _scraper_bridge is None:
        _scraper_bridge = ScraperBridge()
    return _scraper_bridge
