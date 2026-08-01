import logging
import os
import time

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
    assert metrics["found"] >= 1
    assert metrics["relevant"] >= 3
    assert metrics["sent"] >= 3
    assert metrics["runtime"] > 0
    assert runtime < 30.0

def test_first_url_extraction_threshold():
    """Test that every item in scraper.scrape_jobs() contains url, title, and description keys."""
    scraper = JobScraper(mock_mode=True)
    listings = scraper.scrape_jobs()
    assert len(listings) > 0
    for item in listings:
        assert "url" in item and item["url"]
        assert "title" in item and item["title"]
        assert "description" in item and item["description"] is not None

def test_decisions_md_exists():
    decisions_path = os.path.join(os.path.dirname(__file__), "..", "DECISIONS.md")
    assert os.path.exists(decisions_path)
    with open(decisions_path, encoding="utf-8") as f:
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
    
    agent.run()
    assert len(detail_called) == 1
    assert detail_called[0] == "https://www.profession.hu/allas/short-job-123"

def test_circuit_breaker_detail_scraping(monkeypatch):
    os.environ["MOCK_MODE"] = "true"
    agent = JobSearchAgent(mock_mode=True)
    
    def failing_detail(url, timeout=10):
        raise TimeoutError("Scrape timeout exceeded 10 seconds")

    monkeypatch.setattr(agent.scraper, "scrape_job_detail", failing_detail)
    monkeypatch.setattr(agent.scraper, "scrape_jobs", lambda: [
        {"url": f"https://www.profession.hu/allas/short-{i}", "title": "IT Lead", "description": "Rövid"} for i in range(5)
    ])

    agent.run()
    assert agent.detail_circuit_broken is True

def test_feedback_pattern_recognition_yaml():
    import yaml

    from tools.feedback import FeedbackStore
    
    test_fb_file = "tests/fixtures/test_feedback.json"
    try:
        store = FeedbackStore(feedback_file=test_fb_file)
        company_name = "BadCompanyKft"
        store.record_feedback("url1", "Title 1", "DISLIKE", "Rossz", company=company_name)
        store.record_feedback("url2", "Title 2", "DISLIKE", "Nem szimpatikus", company=company_name)
        
        excl_path = os.path.join(os.path.dirname(__file__), "..", "profile", "exclusions.yaml")
        assert os.path.exists(excl_path)
        with open(excl_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert company_name in data.get("excluded_companies", [])
    finally:
        if os.path.exists(test_fb_file):
            os.remove(test_fb_file)

def test_firestore_run_log():
    os.environ["MOCK_MODE"] = "true"
    agent = JobSearchAgent(mock_mode=True)
    agent.run()
    assert hasattr(agent.storage, "mock_run_logs")
    assert len(agent.storage.mock_run_logs) >= 1
    log = list(agent.storage.mock_run_logs.values())[-1]
    assert log["status"] == "completed"
    assert "found" in log




