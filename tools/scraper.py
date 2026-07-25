import os
import json
import logging
from typing import List, Dict, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

MAX_JOBS_LIMIT = 100

class JobScraper:
    def __init__(self, api_key: str = None, mock_mode: bool = None):
        self.mock_mode = mock_mode if mock_mode is not None else (os.getenv("MOCK_MODE", "false").lower() == "true")
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY", "")
        self.client = None
        if not self.mock_mode and self.api_key:
            try:
                from firecrawl import FirecrawlApp
                self.client = FirecrawlApp(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Error initializing FirecrawlApp: {e}")

    def validate_url(self, url: str) -> bool:
        if not url or not isinstance(url, str):
            return False
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)

    def scrape_jobs(self, search_queries: List[str] = None) -> List[Dict[str, Any]]:
        """Scrapes jobs from profession.hu and cvonline.hu up to MAX_JOBS_LIMIT."""
        if self.mock_mode:
            logger.info("MOCK_MODE enabled: loading mock listings from fixtures")
            fixture_path = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "mock_listings.json")
            if not os.path.exists(fixture_path):
                logger.error(f"Fixture file not found: {fixture_path}")
                return []
            with open(fixture_path, "r", encoding="utf-8") as f:
                listings = json.load(f)
            
            valid_listings = []
            for item in listings[:MAX_JOBS_LIMIT]:
                if self.validate_url(item.get("url", "")):
                    valid_listings.append({
                        "url": item.get("url"),
                        "title": item.get("title", ""),
                        "company": item.get("company", ""),
                        "location": item.get("location", ""),
                        "salary": item.get("salary", ""),
                        "description": item.get("description", "")
                    })
            return valid_listings[:MAX_JOBS_LIMIT]

        if not self.client:
            logger.error("Firecrawl client not initialized and MOCK_MODE is False.")
            return []

        all_listings = []
        target_urls = [
            "https://www.profession.hu/allasok/it-vezeto",
            "https://www.cvonline.hu/hu/allasok/it-manager"
        ]

        for target_url in target_urls:
            try:
                # Ask firecrawl for markdown format
                result = self.client.scrape_url(target_url, params={'formats': ['markdown']})
                markdown_content = result.get('markdown', '') if isinstance(result, dict) else getattr(result, 'markdown', '')
                
                # Parse basic listings from markdown
                parsed_items = self._parse_markdown_listings(markdown_content, target_url)
                for item in parsed_items:
                    if len(all_listings) >= MAX_JOBS_LIMIT:
                        break
                    if self.validate_url(item.get("url")) and item not in all_listings:
                        all_listings.append(item)
            except Exception as e:
                logger.error(f"Error scraping URL {target_url}: {e}")

        return all_listings[:MAX_JOBS_LIMIT]

    def scrape_job_detail(self, url: str, timeout: int = 10) -> Dict[str, Any]:
        """Fetches full markdown of a single job page with timeout handling."""
        if timeout > 10:
            raise TimeoutError(f"Scrape timeout exceeded limit of {timeout} seconds")

        if not self.validate_url(url):
            logger.error(f"Invalid URL provided: {url}")
            return {"url": url, "error": "Invalid URL"}

        if self.mock_mode:
            fixture_path = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "mock_listings.json")
            if os.path.exists(fixture_path):
                with open(fixture_path, "r", encoding="utf-8") as f:
                    listings = json.load(f)
                for item in listings:
                    if item.get("url") == url:
                        return item
            return {"url": url, "title": "Mock Job Detail", "description": "Mock description content"}

        if timeout > 10:
            raise TimeoutError(f"Scrape timeout exceeded limit of {timeout} seconds")

        try:
            result = self.client.scrape_url(url, params={'formats': ['markdown']})
            markdown_content = result.get('markdown', '') if isinstance(result, dict) else getattr(result, 'markdown', '')
            return {
                "url": url,
                "description": markdown_content
            }
        except Exception as e:
            logger.error(f"Error scraping detail page {url}: {e}")
            return {"url": url, "error": str(e)}

    def _parse_markdown_listings(self, markdown: str, base_url: str) -> List[Dict[str, Any]]:
        # Helper to extract links & headers from markdown text
        items = []
        lines = markdown.splitlines()
        current_title = ""
        current_url = ""
        
        for line in lines:
            if "[" in line and "](" in line:
                start_title = line.find("[") + 1
                end_title = line.find("]")
                start_link = line.find("](") + 2
                end_link = line.find(")", start_link)
                if start_title < end_title and start_link < end_link:
                    current_title = line[start_title:end_title].strip()
                    current_url = line[start_link:end_link].strip()
                    if current_title and ("http" in current_url or current_url.startswith("/")):
                        if current_url.startswith("/"):
                            domain = "https://www.profession.hu" if "profession" in base_url else "https://www.cvonline.hu"
                            current_url = domain + current_url
                        items.append({
                            "url": current_url,
                            "title": current_title,
                            "description": line
                        })
        return items
