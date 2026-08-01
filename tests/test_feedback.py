import os

from tools.feedback import FeedbackStore


def test_feedback_store_record_and_sync(tmp_path):
    test_file = str(tmp_path / "feedback_test.json")
    store = FeedbackStore(feedback_file=test_file)

    # Initial empty load
    assert store.load_feedbacks() == []

    # Record DISLIKE feedback
    entry = store.record_feedback(
        job_url="https://www.profession.hu/allas/test-1",
        job_title="Junior IT Support",
        action="DISLIKE",
        reason="Túl sokat kell utazni és nem IT vezetői pozíció"
    )

    assert entry["action"] == "DISLIKE"
    assert len(store.load_feedbacks()) == 1

    # Check learned_preferences.md updated
    pref_path = os.path.join(os.path.dirname(__file__), "..", "profile", "learned_preferences.md")
    with open(pref_path, encoding="utf-8") as f:
        content = f.read()
    
    assert "Tanult Emberi Preferenciák" in content
    assert "Junior IT Support" in content

