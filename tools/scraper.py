import os
import json
import logging
from typing import List, Dict, Any
from urllib.parse import urlparse

from abc import ABC, abstractmethod
import re

logger = logging.getLogger(__name__)

MAX_JOBS_LIMIT = 100

PROFESSION_ALLAS_REGEX = re.compile(r'https?://(?:www\.)?profession\.hu/allas/[a-zA-Z0-9_-]+')

class BaseScraper(ABC):
    @abstractmethod
    def scrape_jobs(self, search_queries: List[str] = None) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def validate_url(self, url: str) -> bool:
        pass

class JobScraper(BaseScraper):
    def __init__(self, api_key: str = None, mock_mode: bool = None):
        self.mock_mode = mock_mode if mock_mode is not None else (os.getenv("MOCK_MODE", "false").lower() == "true")
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY", "")
        self.client = None
        if not self.mock_mode and self.api_key:
            try:
                # firecrawl-py >=2.0 repointed the top-level `FirecrawlApp`/
                # `Firecrawl` export at a new v2 client. Its class only
                # declares `.parse()` (local file parsing); `scrape_url()`
                # is added dynamically per-instance and its own docstring
                # calls it "a V1 compatibility alias for agent recovery.
                # Prefer scrape()." — a narrow-purpose internal shim, not a
                # documented stable API, with a bare `(url, **kwargs)`
                # signature instead of the typed one this module was
                # written against. `V1FirecrawlApp` is the package's actual
                # supported v1-compatible class (matching `.markdown`
                # response shape, explicit `formats=`/`timeout=` params)
                # — use that instead of relying on the alias. Requirements.txt
                # only pinned `>=1.0.0`, so a plain `pip install` silently
                # pulls whatever the latest major version resolves to.
                from firecrawl import V1FirecrawlApp as FirecrawlApp
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
        env_target_urls = os.getenv("TARGET_URLS", "").strip()
        if env_target_urls:
            target_urls = [u.strip() for u in env_target_urls.split(",") if u.strip()]
        else:
            target_urls = [
                "https://www.profession.hu/allasok/it-uzemeltetes-telekommunikacio/1,25,0,it%20vezet%C5%91",
                "https://www.profession.hu/allasok/it-telecom-vezeto/1,25,0,it%20vezet%C5%91,70",
                "https://www.profession.hu/allasok/projektmenedzsment/1,25,0,it%20vezet%C5%91,365",
                "https://www.profession.hu/allasok/informaciobiztonsag/1,25,0,it%20vezet%C5%91,338",
                "https://www.profession.hu/allasok/1,0,0,informatikai%20vezet%C5%91",
                "https://nofluffjobs.com/hu/it-management",
                "https://www.cvonline.hu/hu/allasok/it-manager"
            ]
        self.last_scraped_urls_count = len(target_urls)

        for target_url in target_urls:
            try:
                # Ask firecrawl for markdown format
                result = self.client.scrape_url(target_url, formats=['markdown'])
                markdown_content = ""
                if hasattr(result, 'markdown') and result.markdown:
                    markdown_content = result.markdown
                elif hasattr(result, 'data'):
                    data = result.data
                    markdown_content = getattr(data, 'markdown', '') if not isinstance(data, dict) else data.get('markdown', '')
                elif isinstance(result, dict):
                    markdown_content = result.get('markdown', '')
                
                # Parse basic listings from markdown
                parsed_items = self._parse_markdown_listings(markdown_content, target_url)
                if not parsed_items:
                    logger.error(f"0 listings extracted from URL: {target_url}")
                    from tools.notifier import TelegramNotifier
                    TelegramNotifier(mock_mode=self.mock_mode).send_error_notification(f"0 találat jött erről az URL-ről: {target_url}")
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

        try:
            # `timeout` here was previously only used to reject the caller
            # up front (see the `if timeout > 10` guard above) — the actual
            # network call had no real time limit and could hang
            # indefinitely. V1FirecrawlApp.scrape_url accepts a real
            # `timeout` in milliseconds; wire the validated value through.
            result = self.client.scrape_url(url, formats=['markdown'], timeout=timeout * 1000)
            markdown_content = ""
            if hasattr(result, 'markdown') and result.markdown:
                markdown_content = result.markdown
            elif hasattr(result, 'data'):
                data = result.data
                markdown_content = getattr(data, 'markdown', '') if not isinstance(data, dict) else data.get('markdown', '')
            elif isinstance(result, dict):
                markdown_content = result.get('markdown', '')

            return {
                "url": url,
                "description": markdown_content
            }
        except Exception as e:
            logger.error(f"Error scraping detail page {url}: {e}")
            return {"url": url, "error": str(e)}

    def _parse_markdown_listings(self, markdown: str, base_url: str) -> List[Dict[str, Any]]:
        items = []
        lines = markdown.splitlines()

        irrelevant_keywords = [
            "üzletvezető", "uzletvezeto", "áruösszekészítő", "aruosszekeszito", "gipszkartonszerelő", "gipszkartonszerelo",
            "cukrász", "cukrasz", "diákmunka", "diakmunka", "technológiai kezelő", "technologiai kezelo",
            "konyhai", "eladó", "elado", "sofőr", "sofor", "gépjárművezető", "gepjarmuvezeto",
            "tehergépkocsi", "tehergepkocsi", "pultos", "takarító", "takarito", "vagyonőr", "vagyonor",
            "ügyvédjelölt", "ugyvedjelolt", "gyógypedagógus", "gyogypedagogus", "szakorvos", "calzedonia"
        ]

        for line in lines:
            if "[" in line and "](" in line:
                start_title = line.find("[") + 1
                end_title = line.find("]")
                start_link = line.find("](") + 2
                end_link = line.find(")", start_link)
                if start_title < end_title and start_link < end_link:
                    title = line[start_title:end_title].strip()
                    url = line[start_link:end_link].split()[0].replace('"', '').replace('<', '').replace('>', '').strip()
                    title_lower = title.lower()

                    if title and title_lower not in ("megnézem az állást", "részletek", "szűrési beállításaid alapján értesítőt állítottunk be!"):
                        if url.startswith("/"):
                            domain = "https://www.profession.hu" if "profession" in base_url else "https://www.cvonline.hu"
                            url = domain + url
                        
                        is_irrelevant = any(kw in title_lower for kw in irrelevant_keywords)
                        has_override = any(okw in title_lower for okw in ["it", "vezető", "vezeto", "manager", "igazgató", "igazgato", "cio", "head of"])
                        if is_irrelevant and has_override:
                            is_irrelevant = False

                        valid_domains = ("profession.hu/allas/", "cvonline.hu/allas/", "cvonline.hu/job/", "nofluffjobs.com/hu/job/", "nofluffjobs.com/job/")
                        is_valid_url = any(dom in url for dom in valid_domains)
                        if not is_valid_url and self.validate_url(url):
                            # Ensure it's not a category aggregation page like /allasok/ or /kategoria/
                            if "/allasok/" not in url and "/kategoria/" not in url:
                                is_valid_url = True

                        if not is_irrelevant and is_valid_url and url not in [i["url"] for i in items]:
                            items.append({
                                "url": url,
                                "title": title,
                                "description": line
                            })
        return items
