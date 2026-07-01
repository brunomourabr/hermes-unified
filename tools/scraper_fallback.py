"""
ScraperFallback - HTTP fallback scraper using requests + BeautifulSoup
Provides direct HTTP web scraping when Firecrawl is unavailable or fails
"""
import os
import re
import json
import requests
from typing import List, Tuple, Optional
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup


class ScraperFallback:
    """
    Fallback scraper that uses requests + BeautifulSoup directly as HTTP fallback.
    Used when Firecrawl CLI fails or is unavailable.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
        })
        self.timeout = 30

    def _request(self, url: str) -> Tuple[Optional[BeautifulSoup], bool, str]:
        """Make HTTP request and return parsed BeautifulSoup."""
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            # Detect encoding from content
            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            return soup, True, f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            return None, False, f"Timeout after {self.timeout}s"
        except requests.exceptions.HTTPError as e:
            return None, False, f"HTTP error: {e}"
        except requests.exceptions.ConnectionError as e:
            return None, False, f"Connection error: {e}"
        except Exception as e:
            return None, False, f"Request failed: {str(e)[:200]}"

    def _clean_text(self, soup: BeautifulSoup) -> str:
        """Extract clean text from BeautifulSoup object."""
        # Remove script and style elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Get title
        title = ""
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        # Get body text
        body = soup.find("body")
        if body:
            text = body.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)

        # Clean up whitespace
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        text = "\n".join(lines)

        if title:
            return f"# {title}\n\n{text}"
        return text

    def scrape_url(self, url: str) -> Tuple[str, bool, str]:
        """
        Scrape a URL and extract clean text content.

        Args:
            url: The URL to scrape

        Returns:
            Tuple[clean_text, success, message]
        """
        soup, success, msg = self._request(url)
        if not success or soup is None:
            return "", False, msg

        try:
            text = self._clean_text(soup)
            if len(text) < 50:
                return text, True, f"Limited content ({len(text)} chars)"
            return text, True, f"Scraped {len(text)} chars"
        except Exception as e:
            return "", False, f"Parse error: {str(e)[:200]}"

    def extract_tables(self, url: str) -> Tuple[List[dict], bool, str]:
        """
        Find HTML tables and convert to list of dicts.

        Args:
            url: The URL to scrape

        Returns:
            Tuple[list_of_dicts, success, message]
        """
        soup, success, msg = self._request(url)
        if not success or soup is None:
            return [], False, msg

        try:
            tables = soup.find_all("table")
            if not tables:
                return [], True, "No tables found"

            results = []
            for i, table in enumerate(tables):
                rows = table.find_all("tr")
                if not rows:
                    continue

                # Extract headers from first row
                headers = []
                header_cells = rows[0].find_all(["th", "td"])
                for cell in header_cells:
                    headers.append(cell.get_text(strip=True))

                # If no headers found, use column indices
                if not headers or all(h == "" for h in headers):
                    num_cols = len(header_cells)
                    headers = [f"col_{j}" for j in range(num_cols)]

                # Extract data rows
                table_data = []
                for row in rows[1:]:
                    cells = row.find_all(["td", "th"])
                    row_data = {}
                    for j, cell in enumerate(cells):
                        if j < len(headers):
                            row_data[headers[j]] = cell.get_text(strip=True)
                    if row_data:
                        table_data.append(row_data)

                if table_data:
                    results.append({
                        "table_index": i,
                        "headers": headers,
                        "rows": len(table_data),
                        "data": table_data
                    })

            return results, True, f"{len(results)} tables extracted"
        except Exception as e:
            return [], False, f"Table extraction error: {str(e)[:200]}"

    def extract_links(self, url: str, filter_pattern: str = None) -> Tuple[List[dict], bool, str]:
        """
        Extract all links from a page, optionally filtered by regex pattern.

        Args:
            url: The URL to scrape
            filter_pattern: Optional regex pattern to filter links by URL

        Returns:
            Tuple[list_of_link_dicts, success, message]
        """
        soup, success, msg = self._request(url)
        if not success or soup is None:
            return [], False, msg

        try:
            links = []
            seen = set()
            base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                # Resolve relative URLs
                absolute_url = urljoin(base_url, href)
                # Clean fragment
                clean_url = absolute_url.split("#")[0]
                if not clean_url or clean_url in seen:
                    continue
                seen.add(clean_url)

                text = a_tag.get_text(strip=True)
                link_info = {
                    "url": clean_url,
                    "text": text[:100] if text else "",
                    "is_external": urlparse(clean_url).netloc != urlparse(url).netloc
                }

                # Apply optional filter
                if filter_pattern:
                    if re.search(filter_pattern, clean_url, re.IGNORECASE):
                        links.append(link_info)
                else:
                    links.append(link_info)

            return links, True, f"{len(links)} links found"
        except Exception as e:
            return [], False, f"Link extraction error: {str(e)[:200]}"

    def search_google(self, query: str, max_results: int = 5) -> Tuple[List[dict], bool, str]:
        """
        Search usando scraping direto do Google (fallback quando nao ha API de busca).

        Usa scraping do Google Search com User-Agent padrao.
        NOTA: Google pode bloquear apos muitas requisicoes.

        Args:
            query: Search query
            max_results: Maximum results to return (1-10)

        Returns:
            Tuple[list_of_result_dicts, success, message]
        """
        search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}&num={min(max_results, 10)}"
        soup, success, msg = self._request(search_url)
        if not success or soup is None:
            return [], False, msg

        try:
            results = []
            # Google search result divs
            result_divs = soup.find_all("div", class_="g")

            for div in result_divs:
                if len(results) >= max_results:
                    break

                # Extract link
                a_tag = div.find("a", href=True)
                if not a_tag:
                    continue
                href = a_tag.get("href", "")
                # Google wraps URLs in /url?q=...
                if "/url?q=" in href:
                    href = href.split("/url?q=")[1].split("&")[0]

                # Extract title
                h3 = div.find("h3")
                title = h3.get_text(strip=True) if h3 else ""

                # Extract snippet
                snippet_div = div.find("div", class_=["VwiC3b", "yXK7lf"])
                snippet = snippet_div.get_text(strip=True) if snippet_div else ""

                if title and href:
                    results.append({
                        "title": title,
                        "url": href,
                        "description": snippet
                    })

            if results:
                return results, True, f"{len(results)} Google results"
            else:
                # Fallback: try alternative parsing
                for a_tag in soup.find_all("a", href=True):
                    if len(results) >= max_results:
                        break
                    href = a_tag.get("href", "")
                    if href.startswith("http") and not "google.com" in href:
                        text = a_tag.get_text(strip=True)
                        if text and len(text) > 10:
                            results.append({
                                "title": text[:150],
                                "url": href,
                                "description": ""
                            })

                if results:
                    return results, True, f"{len(results)} results (alt parsing)"
                return [], True, "No results found"

        except Exception as e:
            return [], False, f"Search parsing error: {str(e)[:200]}"


# Singleton for reusability
_scraper_fallback = None

def get_scraper_fallback() -> ScraperFallback:
    global _scraper_fallback
    if _scraper_fallback is None:
        _scraper_fallback = ScraperFallback()
    return _scraper_fallback
