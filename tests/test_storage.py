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
    try:
        storage = JobStorage(project_id="non-existent-project-id", mock_mode=False)
        assert storage.is_duplicate("https://www.profession.hu/allas/12345") is False
    except Exception:
        pass

def test_storage_save_feedback():
    storage = JobStorage(mock_mode=True)
    res = storage.save_feedback("https://www.profession.hu/allas/test-feedback-123", "LIKE")
    assert res is True
    assert hasattr(storage, "mock_feedback")
    assert len(storage.mock_feedback) == 1
    assert storage.mock_feedback[0]["rating"] == "LIKE"


def test_get_recent_jobs_queries_with_iso_string_cutoff_not_datetime():
    """Regression: agents/job_search_agent.py writes created_at as a plain
    ISO string (time.strftime(...)), never a Firestore Timestamp - but
    get_recent_jobs() built its range-query cutoff as a raw Python
    datetime object. Firestore inequality filters require the query
    bound's type to match the stored field's type; a datetime bound
    against a string-typed field silently matches nothing (or errors),
    even though jobs are being saved correctly. Verified by capturing the
    exact value passed to the fake Firestore client's .where() call."""
    storage = JobStorage(mock_mode=True)
    storage.mock_mode = False  # exercise the real (non-mock) code path

    captured = {}

    class FakeCollection:
        def where(self, field, op, value):
            captured["field"] = field
            captured["op"] = op
            captured["value"] = value
            return self

        def stream(self):
            return []

    class FakeDb:
        def collection(self, name):
            return FakeCollection()

    storage.db = FakeDb()
    storage.get_recent_jobs(days=30)

    assert captured["field"] == "created_at"
    assert captured["op"] == ">="
    assert isinstance(captured["value"], str), (
        f"cutoff must be an ISO string to match how created_at is stored, got {type(captured['value'])}"
    )
    import re
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", captured["value"]), captured["value"]

