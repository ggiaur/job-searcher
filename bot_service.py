import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from tools.feedback import FeedbackStore

load_dotenv()
logger = logging.getLogger(__name__)

feedback_store = FeedbackStore()
USER_STATE = {}

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Üdvözöllek a Job Hunter AI Botban!\nInteraktív gombokkal és szöveges válaszokkal tudod tanítani a rendszert.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split("|", 1)
    action = parts[0]
    job_title = parts[1] if len(parts) > 1 else "Állás"

    user_id = query.from_user.id
    job_url = query.message.reply_markup.inline_keyboard[-1][0].url if query.message.reply_markup else ""

    if action == "dislike":
        USER_STATE[user_id] = {
            "action": "DISLIKE",
            "job_title": job_title,
            "job_url": job_url
        }
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(f"❌ **Elutasítva:** [{job_title}]\nKérlek írd meg egy válasz üzenetben, **miért nem releváns** ez az állás? (Az AI megjegyzi a szabályt!)")
    else:
        action_names = {
            "star": "⭐ KIEMELT",
            "like": "👍 RELEVÁNS",
            "consider": "🤔 FONTOLÓRA VESZEM",
            "applied": "📩 JELENTKEZTEM"
        }
        name = action_names.get(action, action.upper())
        feedback_store.record_feedback(job_url, job_title, action.upper(), reason=f"Gombnyomás: {name}")
        await query.message.reply_text(f"✅ Rögzítve: **{name}** [{job_title}]. Az AI frissítette a preferenciákat!")

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text

    if user_id in USER_STATE:
        state = USER_STATE.pop(user_id)
        job_title = state["job_title"]
        job_url = state["job_url"]
        action = state["action"]

        feedback_store.record_feedback(job_url, job_title, action, reason=text)
        await update.message.reply_text(f"🧠 **AI Profil Frissítve!** Megtanultam az új elutasítási szabályt:\n_\"{text}\"_\n\nA jövőbeli kereséseknél figyelembe veszem!")
    else:
        await update.message.reply_text("Köszönöm az üzenetet! Ha egy állást szeretnél értékelni, kattints a kártya alatti gombokra!")

def build_application(token: str) -> "Application":
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    return app


def get_run_mode() -> dict:
    """Cloud Run only accepts inbound HTTP on the port it assigns via $PORT
    and routes it to a public HTTPS URL - a long-polling process
    (run_polling(), the previous default) never receives Telegram's
    updates there, since polling only makes OUTBOUND requests and Cloud
    Run Jobs/Services don't keep a process alive to poll from unless
    something is actively listening for inbound traffic. WEBHOOK_URL set
    -> webhook mode (the only mode that actually works on Cloud Run
    Services). Unset -> polling, for local development convenience.

    Split out from main() so the mode-selection logic is unit-testable
    without actually starting a live Telegram connection.
    """
    webhook_url = os.getenv("WEBHOOK_URL", "").strip()
    if not webhook_url:
        return {"mode": "polling"}

    port = int(os.getenv("PORT", "8080"))
    url_path = os.getenv("WEBHOOK_URL_PATH", "/telegram-webhook").strip() or "/telegram-webhook"
    secret_token = os.getenv("WEBHOOK_SECRET_TOKEN", "").strip() or None
    return {
        "mode": "webhook",
        "listen": "0.0.0.0",
        "port": port,
        "url_path": url_path,
        "webhook_url": webhook_url.rstrip("/") + url_path,
        "secret_token": secret_token,
    }


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN missing!")
        return

    app = build_application(token)
    run_config = get_run_mode()

    if run_config["mode"] == "webhook":
        print(f"🤖 Telegram Webhook Bot Elindítva (port {run_config['port']}, {run_config['webhook_url']})...")
        app.run_webhook(
            listen=run_config["listen"],
            port=run_config["port"],
            url_path=run_config["url_path"],
            webhook_url=run_config["webhook_url"],
            secret_token=run_config["secret_token"],
        )
    else:
        print("🤖 Telegram Interaktív Callback Bot Elindítva (polling, helyi fejlesztéshez)...")
        app.run_polling()


if __name__ == "__main__":
    main()
