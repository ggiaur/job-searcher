import os
import time
import pytest
from agents.job_search_agent import JobSearchAgent

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

    # Out of 10 mock items (1 duplicate, 4 high relevance >= 60, rest low/excluded)
    assert metrics["found"] == 10
    assert metrics["duplicate"] >= 1
    assert metrics["relevant"] >= 3
    assert metrics["sent"] >= 3
    assert runtime < 30.0

def test_decisions_md_exists():
    decisions_path = os.path.join(os.path.dirname(__file__), "..", "DECISIONS.md")
    assert os.path.exists(decisions_path)
    with open(decisions_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert len(content.strip()) > 0
