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
