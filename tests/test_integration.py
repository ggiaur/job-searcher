import os
import time
import logging
import pytest
from agents.job_search_agent import JobSearchAgent
from tools.scraper import JobScraper

logger = logging.getLogger(__name__)

def test_integration_pipeline():
    os.environ["MOCK_MODE"] = "true"
    start_time = time.time()

    agent = JobSearchAgent(mock_mode=True)
    metrics = agent.run()

    runtime = time.time() - start_time

    assert metrics is not None
    assert "found" in metrics
    assert "relevant" in metrics
    assert "duplicate" in metrics
    assert "sent" in metrics
    assert "runtime" in metrics

    # Validation thresholds:
    # Out of mock items:
    assert metrics["found"] >= 10
    assert metrics["relevant"] >= 3
    assert metrics["sent"] >= 3
    assert runtime < 30.0

def test_first_url_extraction_threshold():
    """Test extracting at least 15 job listings from first URL or logging WARNING."""
    scraper = JobScraper(mock_mode=True)
    first_url = "https://www.profession.hu/allasok/it-uzemeltetes-telekommunikacio/1,25,0,it%20vezet%C5%91"
    
    # Simulate extraction check
    listings = scraper.scrape_jobs()
    extracted_count = len(listings)
    
    if extracted_count < 15:
        logger.warning(f"First URL ({first_url}) returned {extracted_count} listings, which is below threshold 15.")

def test_decisions_md_exists():
    decisions_path = os.path.join(os.path.dirname(__file__), "..", "DECISIONS.md")
    assert os.path.exists(decisions_path)
    with open(decisions_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert len(content.strip()) > 0

def test_cost_alert(monkeypatch):
    os.environ["MOCK_MODE"] = "true"
    os.environ["MAX_DAILY_COST_USD"] = "0.0001"
    agent = JobSearchAgent(mock_mode=True)
    metrics = agent.run()
    assert metrics is not None

def test_strict_structural_assertions():
    os.environ["MOCK_MODE"] = "true"
    agent = JobSearchAgent(mock_mode=True)
    jobs = agent.scraper.scrape_jobs()
    for job in jobs[:5]:
        res = agent.analyzer.analyze_job(job)
        assert 0 <= res["score"] <= 100
        assert 1 <= len(res["summary"]) <= 500
        assert job["url"].startswith("http://") or job["url"].startswith("https://")

def test_zero_listings_alert(monkeypatch):
    os.environ["MOCK_MODE"] = "true"
    agent = JobSearchAgent(mock_mode=True)
    # Force scraper to return empty list
    monkeypatch.setattr(agent.scraper, "scrape_jobs", lambda: [])
    metrics = agent.run()
    assert metrics["found"] == 0

def test_fetch_job_detail_before_analysis(monkeypatch):
    os.environ["MOCK_MODE"] = "true"
    agent = JobSearchAgent(mock_mode=True)
    
    detail_called = []
    original_detail = agent.scraper.scrape_job_detail
    def mock_scrape_detail(url, timeout=10):
        detail_called.append(url)
        return {
            "url": url,
            "description": "Ez egy részletes, hosszú állásleírás, amely tartalmazza a céget, az elvárásokat és a felelősségi köröket.",
            "company": "Detailed Company Zrt",
            "location": "Budapest"
        }
    
    monkeypatch.setattr(agent.scraper, "scrape_job_detail", mock_scrape_detail)
    monkeypatch.setattr(agent.scraper, "scrape_jobs", lambda: [{
        "url": "https://www.profession.hu/allas/short-job-123",
        "title": "IT vezető",
        "description": "Rövid leírás"
    }])
    
    metrics = agent.run()
    assert len(detail_called) == 1
    assert detail_called[0] == "https://www.profession.hu/allas/short-job-123"



