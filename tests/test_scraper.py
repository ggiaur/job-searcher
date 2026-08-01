import os

import pytest

from tools.scraper import MAX_JOBS_LIMIT, JobScraper


def test_scraper_mock_mode():
    scraper = JobScraper(mock_mode=True)
    jobs = scraper.scrape_jobs()
    
    assert jobs is not None
    assert len(jobs) > 0
    assert len(jobs) <= MAX_JOBS_LIMIT
    
    for job in jobs:
        assert "url" in job
        assert "title" in job
        assert "description" in job
        assert job["url"].startswith("http://") or job["url"].startswith("https://")

def test_scraper_url_validation():
    scraper = JobScraper(mock_mode=True)
    assert scraper.validate_url("https://www.profession.hu/allas/123") is True
    assert scraper.validate_url("invalid-url") is False
    assert scraper.validate_url("") is False

def test_scraper_invalid_url_graceful_error():
    scraper = JobScraper(mock_mode=True)
    result = scraper.scrape_job_detail("invalid-url")
    assert result is not None
    assert "error" in result or result.get("url") == "invalid-url"

def test_scraper_timeout_handling():
    scraper = JobScraper(mock_mode=True)
    with pytest.raises(TimeoutError):
        scraper.scrape_job_detail("https://www.profession.hu/allas/123", timeout=15)

def test_scraper_max_limit():
    scraper = JobScraper(mock_mode=True)
    jobs = scraper.scrape_jobs()
    assert len(jobs) <= 100

def test_nofluffjobs_scraper():
    scraper = JobScraper(mock_mode=True)
    os.environ["TARGET_URLS"] = "https://nofluffjobs.com/hu/it-management"
    jobs = scraper.scrape_jobs()
    assert jobs is not None
    assert len(jobs) > 0

def test_parse_profession_raw_snapshot():
    scraper = JobScraper(mock_mode=True)
    snapshot_path = os.path.join(os.path.dirname(__file__), "fixtures", "snapshots", "profession_raw.md")
    with open(snapshot_path, encoding="utf-8") as f:
        raw_md = f.read()
    listings = scraper._parse_markdown_listings(raw_md, "https://www.profession.hu/allasok/it")
    urls = [item["url"] for item in listings]
    assert "https://www.profession.hu/allas/it-vezeto-company-123456?hash=abc" in urls
    assert "https://www.profession.hu/allas/infra-osztalyvezeto-999888" in urls
    assert not any("gipszkarton" in url for url in urls)
    assert not any("allasok/it-telecom" in url for url in urls)

def test_parse_cvonline_raw_snapshot():
    scraper = JobScraper(mock_mode=True)
    snapshot_path = os.path.join(os.path.dirname(__file__), "fixtures", "snapshots", "cvonline_raw.md")
    with open(snapshot_path, encoding="utf-8") as f:
        raw_md = f.read()
    listings = scraper._parse_markdown_listings(raw_md, "https://www.cvonline.hu/hu/allasok/it")
    assert len(listings) >= 1

def test_firecrawl_client_uses_the_real_v1_compatible_scrape_url():
    """Regression guard: firecrawl-py's top-level `Firecrawl`/`FirecrawlApp`
    export was repointed at a new v2 client. Its *class* only declares
    `.parse()` (local file parsing) — `hasattr(FirecrawlApp, "scrape_url")`
    is False. A `scrape_url` still shows up per-*instance*, but its own
    docstring says "V1 compatibility alias for agent recovery. Prefer
    scrape()." with a bare `(url, **kwargs)` signature — an internal,
    narrow-purpose shim, not the documented, typed v1 API this module's
    response parsing (`.markdown`, `.data`) was written against.
    `requirements.txt` only pins `>=1.0.0`, so a plain install can land on
    either shape depending on version. Mock mode never exercises
    self.client, so no mock-mode test could ever catch a regression here.

    Checks the real signature, not just method presence: the actual
    `V1FirecrawlApp.scrape_url` declares an explicit `formats` parameter;
    the "agent recovery" alias does not (everything funnels through
    `**kwargs`). That's the concrete, checkable difference between "the
    supported v1-compatible client" and "the undocumented alias".
    """
    import inspect

    scraper = JobScraper(api_key="test-key-not-a-real-credential", mock_mode=False)
    assert scraper.client is not None, "FirecrawlApp client failed to initialize at all"
    assert hasattr(scraper.client, "scrape_url"), (
        "The Firecrawl client has no scrape_url() at all — tools/scraper.py's real "
        "(non-mock) scraping is now broken; find the current equivalent method and "
        "update every call site."
    )
    sig = inspect.signature(scraper.client.scrape_url)
    assert "formats" in sig.parameters, (
        f"scraper.client.scrape_url has signature {sig} — no explicit 'formats' "
        "parameter, which means this is firecrawl-py's narrow 'agent recovery' "
        "compatibility alias, not the real v1-compatible client. "
        "tools/scraper.py must import V1FirecrawlApp (not the top-level "
        "FirecrawlApp/Firecrawl) to get the documented, typed scrape_url()."
    )


