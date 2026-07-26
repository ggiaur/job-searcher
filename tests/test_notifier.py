import pytest
import os
from tools.notifier import TelegramNotifier

def test_notifier_format_message_with_salary():
    notifier = TelegramNotifier(mock_mode=True)
    job = {
        "title": "IT vezető",
        "company": "Tech Corp",
        "location": "Budapest",
        "salary": "Bruttó 1.200.000 Ft",
        "url": "https://www.profession.hu/allas/1001"
    }
    msg = notifier.format_job_message(job, 85, "Remek vezetői pozíció.")
    assert "🎯 IT vezető" in msg
    assert "🏢 Tech Corp" in msg
    assert "📍 Budapest" in msg
    assert "💰 Bruttó 1.200.000 Ft" in msg
    assert "⭐ Relevancia: 85/100" in msg
    assert "🔗 https://www.profession.hu/allas/1001" in msg

def test_notifier_format_message_without_salary():
    notifier = TelegramNotifier(mock_mode=True)
    job = {
        "title": "IT Director",
        "company": "Global Solutions",
        "location": "Budapest",
        "url": "https://www.profession.hu/allas/1002"
    }
    msg = notifier.format_job_message(job, 90, "Vezetői pozíció.")
    assert "🎯 IT Director" in msg
    assert "💰" not in msg

def test_notifier_message_truncation():
    notifier = TelegramNotifier(mock_mode=True)
    job = {"title": "Test Title", "url": "http://example.com"}
    long_summary = "A" * 5000
    msg = notifier.format_job_message(job, 70, long_summary)
    assert len(msg) <= 4096
    assert msg.endswith("\n...")

def test_notifier_mock_mode_send():
    notifier = TelegramNotifier(mock_mode=True)
    job = {"title": "Test Job", "url": "http://example.com"}
    assert notifier.send_job_notification(job, 80, "Test Summary") is True
    assert notifier.send_summary_notification(10, 3, 1, 3, 5.2) is True

def test_notifier_api_error_handling(monkeypatch):
    notifier = TelegramNotifier(bot_token="invalid", chat_id="invalid", mock_mode=False)
    # Raising error in bot send_message shouldn't crash
    class ErrorBot:
        def send_message(self, *args, **kwargs):
            raise Exception("Telegram Connection Failed")
    notifier.bot = ErrorBot()
    assert notifier.send_job_notification({"title": "Test", "url": "http://example.com"}, 80, "Sum") is False

def test_notifier_inline_keyboard():
    notifier = TelegramNotifier(mock_mode=True)
    job = {"title": "IT Director", "url": "https://www.profession.hu/allas/9999"}
    res = notifier.send_job_notification(job, 95, "Kiváló pozíció")
    assert res is True

def test_notifier_html_escaping():
    notifier = TelegramNotifier(mock_mode=True)
    job = {
        "title": "<script>IT & Cloud Manager</script>",
        "company": "Company <A&B>",
        "location": "Budapest & Pest",
        "url": "https://www.profession.hu/allas/123"
    }
    msg = notifier.format_job_message(job, 90, "Teszt <summary> & leírás")
    assert "&lt;script&gt;" in msg
    assert "IT &amp; Cloud Manager" in msg
    assert "Company &lt;A&amp;B&gt;" in msg
    assert "Teszt &lt;summary&gt; &amp; leírás" in msg


