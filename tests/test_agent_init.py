import os
import pytest
from agents.job_search_agent import JobSearchAgent

def test_agent_init_attributes():
    agent = JobSearchAgent(mock_mode=True)
    assert agent.detail_circuit_broken is False
    assert agent.consecutive_detail_failures == 0

def test_agent_run_metrics_keys():
    os.environ["MOCK_MODE"] = "true"
    agent = JobSearchAgent(mock_mode=True)
    metrics = agent.run()
    
    assert isinstance(metrics, dict)
    required_keys = ["found", "relevant", "duplicate", "sent", "errors", "runtime"]
    for key in required_keys:
        assert key in metrics
