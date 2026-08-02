import asyncio
import logging
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

BUDAPEST_TZ = ZoneInfo("Europe/Budapest")

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, bot_token: str = None, chat_id: str = None, mock_mode: bool = None):
        self.mock_mode = mock_mode if mock_mode is not None else (os.getenv("MOCK_MODE", "false").lower() == "true")
        self.bot_token = (bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        self.chat_id = (chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
        self.bot = None

        if not self.mock_mode and self.bot_token:
            try:
                from telegram import Bot
                self.bot = Bot(token=self.bot_token)
            except Exception as e:
                logger.error(f"Error initializing Telegram bot: {e}")

    def format_job_message(self, job: dict[str, Any], score: int, summary: str) -> str:
        # Escape HTML characters to prevent Telegram API Markdown/HTML parsing crashes
        def escape_html(text: str) -> str:
            if not text:
                return ""
            return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        title = escape_html(job.get("title", "Ismeretlen pozíció"))
        company = escape_html(job.get("company", "Nincs megadva cég"))
        location = escape_html(job.get("location", "Nincs megadva"))
        salary = escape_html(job.get("salary", "").strip())
        url = job.get("url", "")
        summary_escaped = escape_html(summary)

        msg_lines = [
            f"🎯 {title}",
            f"🏢 {company}",
            f"📍 {location}",
            f"📌 Forrás: {escape_html(job.get('source_url', 'Profession.hu IT vezető'))}",
        ]

        if salary:
            msg_lines.append(f"💰 {salary}")

        msg_lines.extend([
            f"⭐ Relevancia: {score}/100",
            f"📝 {summary_escaped}",
            f"🔗 {url}",
            # A felhasználó kérésére az üzenet ALJÁN, hogy óránkénti futásoknál
            # könnyen látszódjon, melyik kártya melyik futásból jött.
            f"🕐 {datetime.now(BUDAPEST_TZ).strftime('%Y-%m-%d %H:%M')}",
        ])

        full_msg = "\n".join(msg_lines)
        if len(full_msg) > 4096:
            full_msg = full_msg[:4090] + "\n..."
        return full_msg

    def send_job_notification(self, job: dict[str, Any], score: int, summary: str) -> bool:
        """Formats and sends Telegram notification for a relevant job listing with Inline Action Buttons."""
        message = self.format_job_message(job, score, summary)

        if self.mock_mode:
            logger.info(f"[MOCK TELEGRAM NOTIFICATION WITH BUTTONS]\n{message}")
            return True

        if not self.bot or not self.chat_id:
            logger.error("Telegram bot or chat_id not initialized.")
            return False

        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [
                [
                    InlineKeyboardButton("⭐ Kiemelt", callback_data=f"star|{job.get('title', '')[:25]}"),
                    InlineKeyboardButton("👍 Releváns", callback_data=f"like|{job.get('title', '')[:25]}"),
                    InlineKeyboardButton("🤔 Fontolóra veszem", callback_data=f"consider|{job.get('title', '')[:25]}"),
                ],
                [
                    InlineKeyboardButton("👎 Elutasítom", callback_data=f"dislike|{job.get('title', '')[:25]}"),
                    InlineKeyboardButton("📩 Jelentkeztem", callback_data=f"applied|{job.get('title', '')[:25]}"),
                ],
                [
                    InlineKeyboardButton("🔗 Hirdetés Megtekintése", url=job.get("url", "https://profession.hu"))
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            from telegram import Bot
            bot = Bot(token=self.bot_token)
            asyncio.run(bot.send_message(
                chat_id=self.chat_id,
                text=message,
                reply_markup=reply_markup
            ))
            return True
        except Exception as e:
            logger.error(f"Telegram API error when sending job notification: {e}")
            return False

    def build_summary_message(self, found: int, relevant: int, duplicate: int, sent: int, runtime: float, scraped_urls: int = 5) -> str:
        """Builds the run summary message text. Split out from send_summary_notification
        so the message content (incl. the run timestamp) can be unit-tested without a
        real/mocked Telegram send."""
        # Cost calculation estimations:
        # Firecrawl: ~5 URL scrapes = $0.01 (or free tier quota)
        # Gemini 2.5 Flash: ~$0.000075 / 1k input tokens (average ~1500 tokens / job) -> ~$0.0001 / job
        estimated_gemini_usd = found * 0.00015
        estimated_firecrawl_usd = scraped_urls * 0.002
        total_usd = estimated_gemini_usd + estimated_firecrawl_usd
        total_huf = total_usd * 365

        # Calculate conversion & drop-off percentages
        filtered_out = found - relevant
        relevant_pct = (relevant / found * 100) if found > 0 else 0.0
        filtered_pct = (filtered_out / found * 100) if found > 0 else 0.0

        return (
            f"📊 **Futási Összefoglaló & Költségek**\n"
            f"• Scraped URL-ek száma: {scraped_urls}\n"
            f"• Talált hirdetések összesen: {found}\n"
            f"• Duplikátumok: {duplicate}\n"
            f"• Releváns (60+ pont): {relevant} ({relevant_pct:.1f}%)\n"
            f"• Kiszűrt / Kiesett állások: {filtered_out} ({filtered_pct:.1f}%)\n"
            f"• Elküldött értesítések: {sent}\n"
            f"• Futási idő: {runtime:.2f} mp\n"
            f"💵 **Becsült futási költség:** ~${total_usd:.4f} USD (~{total_huf:.2f} Ft)\n"
            f"   _(Gemini AI: ${estimated_gemini_usd:.4f} | Firecrawl Scrape: ${estimated_firecrawl_usd:.4f})_\n"
            # A felhasználó kérésére az üzenet ALJÁN, hogy óránkénti futásoknál
            # könnyen látszódjon, melyik összefoglaló melyik futásból jött.
            f"🕐 {datetime.now(BUDAPEST_TZ).strftime('%Y-%m-%d %H:%M')}"
        )

    def send_summary_notification(self, found: int, relevant: int, duplicate: int, sent: int, runtime: float, scraped_urls: int = 5) -> bool:
        """Sends run summary notification."""
        summary_msg = self.build_summary_message(found, relevant, duplicate, sent, runtime, scraped_urls)

        if self.mock_mode:
            logger.info(f"[MOCK TELEGRAM SUMMARY]\n{summary_msg}")
            return True

        return self._safe_send_message(summary_msg, parse_mode="Markdown")

    def send_error_notification(self, error_message: str) -> bool:
        """Sends an error alert via Telegram."""
        msg = f"🚨 **Job Searcher Hibaüzenet**\n{error_message}"
        if self.mock_mode:
            logger.info(f"[MOCK TELEGRAM ERROR]\n{msg}")
            return True
        return self._safe_send_message(msg, parse_mode="Markdown")

    def _safe_send_message(self, text: str, reply_markup=None, parse_mode: str = "HTML") -> bool:
        """Sends a message safely checking event loops."""
        if not self.bot_token or not self.chat_id:
            logger.error("Telegram bot_token or chat_id not initialized.")
            return False

        try:
            from telegram import Bot
            bot = Bot(token=self.bot_token)
            
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # Running inside existing loop
                import nest_asyncio
                nest_asyncio.apply()
                loop.run_until_complete(bot.send_message(chat_id=self.chat_id, text=text, parse_mode=parse_mode, reply_markup=reply_markup))
            else:
                asyncio.run(bot.send_message(chat_id=self.chat_id, text=text, parse_mode=parse_mode, reply_markup=reply_markup))
            return True
        except Exception as e:
            logger.error(f"Telegram API error in _safe_send_message: {e}")
            return False
