import pytest
import os
from tools.scraper import JobScraper, MAX_JOBS_LIMIT

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

