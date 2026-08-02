"""bot_service.py's actual Telegram connection (run_polling/run_webhook)
can't be unit-tested without a live server, but the mode-selection logic
(get_run_mode) is pure and fully testable - and matters a lot: it's the
difference between the bot working at all on Cloud Run (webhook, the only
mode Cloud Run Services can actually route inbound Telegram updates to)
and silently doing nothing (polling never receives anything there, since
Cloud Run only delivers traffic it can route to a listening port)."""

import importlib

import bot_service


def _reload_with_env(monkeypatch, **env):
    for key in ("WEBHOOK_URL", "PORT", "WEBHOOK_URL_PATH", "WEBHOOK_SECRET_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    importlib.reload(bot_service)
    return bot_service


def test_no_webhook_url_falls_back_to_polling_for_local_dev(monkeypatch):
    mod = _reload_with_env(monkeypatch)
    assert mod.get_run_mode() == {"mode": "polling"}


def test_webhook_url_set_selects_webhook_mode_with_defaults(monkeypatch):
    mod = _reload_with_env(monkeypatch, WEBHOOK_URL="https://job-searcher-bot-abc123.a.run.app")
    config = mod.get_run_mode()
    assert config["mode"] == "webhook"
    assert config["port"] == 8080
    assert config["url_path"] == "/telegram-webhook"
    assert config["webhook_url"] == "https://job-searcher-bot-abc123.a.run.app/telegram-webhook"
    assert config["secret_token"] is None


def test_webhook_mode_respects_cloud_run_port_env_var(monkeypatch):
    """Cloud Run injects $PORT and requires the container to listen on it -
    a hardcoded port would break the deployment."""
    mod = _reload_with_env(monkeypatch, WEBHOOK_URL="https://example.run.app", PORT="9090")
    assert mod.get_run_mode()["port"] == 9090


def test_webhook_url_trailing_slash_does_not_produce_double_slash(monkeypatch):
    mod = _reload_with_env(monkeypatch, WEBHOOK_URL="https://example.run.app/")
    assert mod.get_run_mode()["webhook_url"] == "https://example.run.app/telegram-webhook"


def test_webhook_secret_token_passed_through_when_set(monkeypatch):
    mod = _reload_with_env(monkeypatch, WEBHOOK_URL="https://example.run.app", WEBHOOK_SECRET_TOKEN="s3cr3t")
    assert mod.get_run_mode()["secret_token"] == "s3cr3t"


def test_build_application_registers_all_three_handlers():
    app = bot_service.build_application(token="fake-token-for-handler-registration-only")
    handler_types = {type(h).__name__ for group in app.handlers.values() for h in group}
    assert handler_types == {"CommandHandler", "CallbackQueryHandler", "MessageHandler"}


def test_main_strips_whitespace_from_telegram_bot_token(monkeypatch, capsys):
    """Regression: the same CRLF-in-Secret-Manager-value bug already found
    and fixed in tools/notifier.py, tools/scraper.py, tools/analyzer.py,
    tools/storage.py this session (Windows cmd's --data-file=- + Ctrl+Z
    leaves a trailing \\r\\n) was never fixed here - main() read
    TELEGRAM_BOT_TOKEN with no .strip(). A token with a trailing \\r\\n
    would build an Application with an invalid token and fail opaquely."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token-with-crlf\r\n")
    monkeypatch.delenv("WEBHOOK_URL", raising=False)

    captured_token = {}

    def fake_build_application(token):
        captured_token["value"] = token
        raise SystemExit("stop before actually starting a bot connection")

    monkeypatch.setattr(bot_service, "build_application", fake_build_application)

    try:
        bot_service.main()
    except SystemExit:
        pass

    assert captured_token["value"] == "fake-token-with-crlf"


def test_requirements_declares_webhooks_extra():
    """Regression: a bot_service.py webhook módja (Application.run_webhook)
    a python-telegram-bot [webhooks] extra csomagját igényli
    (tornado/uvicorn-alapú webszerver komponens). Enélkül élesben, Cloud Run
    Service-ként telepítve a konténer induláskor RuntimeError-ral elszáll:
    "To use `start_webhook`, PTB must be installed via
    `pip install \"python-telegram-bot[webhooks]\"`" - MÉG MIELŐTT a portra
    kezdene figyelni, tehát a Cloud Run health check timeoutol és a
    deployment meghiúsul. Ez pontosan a requirements.txt-drift hibaosztály,
    ami már többször előfordult ebben a projektben (DECISIONS.md #4)."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    requirements = (root / "requirements.txt").read_text()

    assert "python-telegram-bot[webhooks]" in requirements, (
        "a requirements.txt-nek a [webhooks] extrával kell telepítenie a "
        "python-telegram-bot csomagot, különben a webhook mód éles "
        "induláskor RuntimeError-ral elszáll"
    )


def test_dislike_button_then_text_reason_records_feedback(tmp_path, monkeypatch):
    """A teljes "szöveges tanítás" folyamat: elutasítás gomb -> a bot
    indoklást kér -> a felhasználó szöveges választ ír -> a rendszer
    elmenti a FeedbackStore-ba. Ez a funkció, amit a felhasználó jelzett,
    hogy nem működik - itt valós, izolált (nem élő webhookon át küldött)
    hívásokkal bizonyítjuk, hogy az ÜZLETI LOGIKA helyes.

    (Élő webhookon át NEM szimulálható megbízhatóan: a query.answer()
    valós, Telegram-szerver által ellenőrzött callback_query id-t igényel,
    amit csak egy tényleges felhasználói kattintás tud generálni.)
    """
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from tools.feedback import FeedbackStore

    importlib.reload(bot_service)
    feedback_file = tmp_path / "feedback_history.json"
    bot_service.feedback_store = FeedbackStore(feedback_file=str(feedback_file))
    bot_service.USER_STATE.clear()

    user_id = 12345

    # 1) Elutasítás gomb megnyomása
    callback_query = MagicMock()
    callback_query.answer = AsyncMock()
    callback_query.data = "dislike|Teszt Allas"
    callback_query.from_user.id = user_id
    callback_query.message.reply_markup.inline_keyboard = [
        [MagicMock(url="https://example.hu/teszt-allas")]
    ]
    callback_query.edit_message_reply_markup = AsyncMock()
    callback_query.message.reply_text = AsyncMock()

    update1 = MagicMock()
    update1.callback_query = callback_query

    asyncio.run(bot_service.button_callback(update1, MagicMock()))

    assert user_id in bot_service.USER_STATE, "a gombnyomás után USER_STATE-nek tartalmaznia kell a felhasználót"
    assert bot_service.USER_STATE[user_id]["action"] == "DISLIKE"
    assert bot_service.USER_STATE[user_id]["job_url"] == "https://example.hu/teszt-allas"

    # 2) Szöveges indoklás küldése
    message = MagicMock()
    message.from_user.id = user_id
    message.text = "Túl sok utazást igényel a pozíció."
    message.reply_text = AsyncMock()

    update2 = MagicMock()
    update2.message = message

    asyncio.run(bot_service.handle_text_message(update2, MagicMock()))

    # 3) Ellenőrzés: tényleg elmentődött-e a FeedbackStore-ba
    saved = bot_service.feedback_store.load_feedbacks()
    assert len(saved) == 1, f"pontosan 1 mentett visszajelzésnek kellene lennie, kaptunk: {saved}"
    assert saved[0]["action"] == "DISLIKE"
    assert saved[0]["job_title"] == "Teszt Allas"
    assert saved[0]["reason"] == "Túl sok utazást igényel a pozíció."
    assert user_id not in bot_service.USER_STATE, "a state-nek törlődnie kell mentés után"
