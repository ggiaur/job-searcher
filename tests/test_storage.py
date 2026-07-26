import pytest
import os
from tools.storage import JobStorage

def test_storage_mock_mode_duplicate_detection():
    storage = JobStorage(mock_mode=True)
    known_url = "https://www.profession.hu/allas/old-job-already-seen-999"
    new_url = "https://www.profession.hu/allas/new-job-12345"

    assert storage.is_duplicate(known_url) is True
    assert storage.is_duplicate(new_url) is False

def test_storage_mock_mode_save_and_duplicate():
    storage = JobStorage(mock_mode=True)
    new_job = {
        "url": "https://www.profession.hu/allas/test-unique-url-777",
        "title": "Test IT Lead"
    }

    # First save succeeds
    assert storage.save_job(new_job) is True
    # Second save fails (duplicate)
    assert storage.save_job(new_job) is False
    assert storage.is_duplicate(new_job["url"]) is True

def test_storage_firestore_connection_error():
    # MOCK_MODE=False without valid project/creds should return False gracefully on error
    storage = JobStorage(project_id="non-existent-project-id", mock_mode=False)
    assert storage.is_duplicate("https://www.profession.hu/allas/12345") is False
