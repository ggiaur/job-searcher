import os
import logging
import asyncio
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, bot_token: str = None, chat_id: str = None, mock_mode: bool = None):
        self.mock_mode = mock_mode if mock_mode is not None else (os.getenv("MOCK_MODE", "false").lower() == "true")
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.bot = None

        if not self.mock_mode and self.bot_token:
            try:
                from telegram import Bot
                self.bot = Bot(token=self.bot_token)
            except Exception as e:
                logger.error(f"Error initializing Telegram bot: {e}")

    def format_job_message(self, job: Dict[str, Any], score: int, summary: str) -> str:
        title = job.get("title", "Ismeretlen pozíció")
        company = job.get("company", "Nincs megadva cég")
        location = job.get("location", "Nincs megadva")
        salary = job.get("salary", "").strip()
        url = job.get("url", "")

        msg_lines = [
            f"🎯 {title}",
            f"🏢 {company}",
            f"📍 {location}"
        ]

        if salary:
            msg_lines.append(f"💰 {salary}")

        msg_lines.extend([
            f"⭐ Relevancia: {score}/100",
            f"📝 {summary}",
            f"🔗 {url}"
        ])

        full_msg = "\n".join(msg_lines)
        if len(full_msg) > 4096:
            full_msg = full_msg[:4090] + "\n..."
        return full_msg

    def send_job_notification(self, job: Dict[str, Any], score: int, summary: str) -> bool:
        """Formats and sends Telegram notification for a relevant job listing."""
        message = self.format_job_message(job, score, summary)

        if self.mock_mode:
            logger.info(f"[MOCK TELEGRAM NOTIFICATION]\n{message}")
            return True

        if not self.bot or not self.chat_id:
            logger.error("Telegram bot or chat_id not initialized.")
            return False

        try:
            asyncio.run(self.bot.send_message(chat_id=self.chat_id, text=message))
            return True
        except Exception as e:
            logger.error(f"Telegram API error when sending job notification: {e}")
            return False

    def send_summary_notification(self, found: int, relevant: int, duplicate: int, sent: int, runtime: float, scraped_urls: int = 5) -> bool:
        """Sends run summary notification."""
        summary_msg = (
            f"📊 **Futási Összefoglaló**\n"
            f"• Scraped URL-ek száma: {scraped_urls}\n"
            f"• Talált hirdetések összesen: {found}\n"
            f"• Duplikátumok: {duplicate}\n"
            f"• Releváns (60+ pont): {relevant}\n"
            f"• Elküldött értesítések: {sent}\n"
            f"• Futási idő: {runtime:.2f} mp"
        )

        if self.mock_mode:
            logger.info(f"[MOCK TELEGRAM SUMMARY]\n{summary_msg}")
            return True

        if not self.bot or not self.chat_id:
            logger.error("Telegram bot or chat_id not initialized.")
            return False

        try:
            asyncio.run(self.bot.send_message(chat_id=self.chat_id, text=summary_msg, parse_mode="Markdown"))
            return True
        except Exception as e:
            logger.error(f"Telegram API error when sending summary notification: {e}")
            return False

    def send_error_notification(self, error_message: str) -> bool:
        """Sends an error alert via Telegram."""
        msg = f"🚨 **Job Searcher Hibaüzenet**\n{error_message}"
        if self.mock_mode:
            logger.info(f"[MOCK TELEGRAM ERROR]\n{msg}")
            return True
        if not self.bot or not self.chat_id:
            return False
        try:
            asyncio.run(self.bot.send_message(chat_id=self.chat_id, text=msg, parse_mode="Markdown"))
            return True
        except Exception as e:
            logger.error(f"Telegram error notification failed: {e}")
            return False
