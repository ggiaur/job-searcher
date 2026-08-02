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




def test_notifier_job_message_includes_local_timestamp():
    """User wants a timestamp on every notification so they can tell which
    hourly test run each message came from (asked while switching from
    manual gcloud run jobs execute to an hourly Cloud Scheduler trigger)."""
    import re

    notifier = TelegramNotifier(mock_mode=True)
    job = {"title": "IT vezető", "company": "Tech Corp", "location": "Budapest", "url": "https://x/1"}
    msg = notifier.format_job_message(job, 85, "Remek pozíció.")
    assert re.search(r"🕐 \d{4}-\d{2}-\d{2} \d{2}:\d{2}", msg), f"no timestamp line found in: {msg}"


def test_notifier_job_message_timestamp_is_last_line():
    """User asked for the timestamp at the BOTTOM of the message, not the top -
    it was originally the first line."""
    notifier = TelegramNotifier(mock_mode=True)
    job = {"title": "IT vezető", "company": "Tech Corp", "location": "Budapest", "url": "https://x/1"}
    msg = notifier.format_job_message(job, 85, "Remek pozíció.")
    last_line = msg.splitlines()[-1]
    assert last_line.startswith("🕐 "), f"the timestamp must be the last line, got: {last_line!r}"


def test_notifier_summary_message_includes_local_timestamp():
    import re

    notifier = TelegramNotifier(mock_mode=True)
    msg = notifier.build_summary_message(found=10, relevant=2, duplicate=1, sent=2, runtime=5.0, scraped_urls=7)
    assert re.search(r"🕐 \d{4}-\d{2}-\d{2} \d{2}:\d{2}", msg), f"no timestamp line found in: {msg}"


def test_notifier_summary_message_timestamp_is_last_line():
    """User asked for the timestamp at the BOTTOM of the message, not under
    the title - it was originally the second line."""
    notifier = TelegramNotifier(mock_mode=True)
    msg = notifier.build_summary_message(found=10, relevant=2, duplicate=1, sent=2, runtime=5.0, scraped_urls=7)
    last_line = msg.splitlines()[-1]
    assert last_line.startswith("🕐 "), f"the timestamp must be the last line, got: {last_line!r}"


def test_notifier_job_message_shows_language_requirement_when_present():
    """Felhasználói kérés: minden esetben látszódjon a nyelvtudás/elvárás a
    Telegram-kártyán, hogy ellenőrizhető legyen, a szűrő jól döntött-e."""
    notifier = TelegramNotifier(mock_mode=True)
    job = {
        "title": "IT vezető",
        "company": "Tech Corp",
        "location": "Budapest",
        "url": "https://x/1",
        "language_requirement": "✅ Nincs magas szintű angol elvárás",
    }
    msg = notifier.format_job_message(job, 85, "Remek pozíció.")
    assert "🌐" in msg
    assert "Nincs magas szintű angol elvárás" in msg


def test_notifier_job_message_omits_language_line_when_absent():
    """Ha a job dict-ben nincs language_requirement kulcs (pl. régi, még nem
    frissített hívó kód), ne törjön el az üzenetformázás."""
    notifier = TelegramNotifier(mock_mode=True)
    job = {"title": "IT vezető", "company": "Tech Corp", "location": "Budapest", "url": "https://x/1"}
    msg = notifier.format_job_message(job, 85, "Remek pozíció.")
    assert "🌐" not in msg
