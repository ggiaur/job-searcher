import os
import time
import logging
from typing import Dict, Any

from tools.scraper import JobScraper
from tools.analyzer import JobAnalyzer
from tools.storage import JobStorage
from tools.notifier import TelegramNotifier

logger = logging.getLogger(__name__)

RELEVANCE_THRESHOLD = 60

class JobSearchAgent:
    """Main ADK Agent orchestrating scraping, AI relevance scoring, storage, and notification."""

    def __init__(self, mock_mode: bool = None):
        self.mock_mode = mock_mode if mock_mode is not None else (os.getenv("MOCK_MODE", "false").lower() == "true")
        self.scraper = JobScraper(mock_mode=self.mock_mode)
        self.analyzer = JobAnalyzer(mock_mode=self.mock_mode)
        self.storage = JobStorage(mock_mode=self.mock_mode)
        self.notifier = TelegramNotifier(mock_mode=self.mock_mode)
        self.detail_circuit_broken = False
        self.consecutive_detail_failures = 0

    def run(self) -> Dict[str, Any]:
        start_time = time.time()
        import uuid
        run_id = "run_" + str(uuid.uuid4())[:8]
        logger.info(f"Starting JobSearchAgent pipeline execution (run_id: {run_id})...")
        self.storage.create_run_log(run_id)

        listings = self.scraper.scrape_jobs()
        found_count = len(listings)
        duplicate_count = 0
        relevant_count = 0
        sent_count = 0

        # Prioritize listings by title keywords
        priority_keywords = ["vezető", "manager", "igazgató", "cio", "head of", "osztályvezető", "projektmenedzser"]
        high_priority = []
        low_priority = []

        for job in listings:
            t_lower = job.get("title", "").lower()
            if any(pk in t_lower for pk in priority_keywords):
                high_priority.append(job)
            else:
                low_priority.append(job)

        ordered_listings = high_priority + low_priority

        for job in ordered_listings:
            url = job.get("url")
            if not url:
                continue

            if self.storage.is_duplicate(url):
                logger.info(f"Skipping duplicate URL: {url}")
                duplicate_count += 1
                continue

            # Fast local pre-filtering to save Gemini API quota & speed up processing
            title_lower = job.get("title", "").lower()
            irrelevant_keywords = ["tehergépkocsi", "pultos", "szakács", "cukrász", "áruösszekészítő", "takarító", "konyhai", "eladó", "sofőr", "gépjárművezető", "vagyonőr"]
            if any(kw in title_lower for kw in irrelevant_keywords) and not any(it_kw in title_lower for it_kw in ["it", "vezető", "manager", "igazgató", "szerver"]):
                logger.info(f"Skipping obvious non-IT job locally: {job.get('title')}")
                continue

            # Enrich short descriptions with full detail page markdown using Circuit Breaker
            description = job.get("description", "")
            if len(description) < 200:
                if getattr(self, "detail_circuit_broken", False):
                    logger.warning(f"Circuit Breaker ACTIVE: skipping detail scrape for {url}")
                else:
                    logger.info(f"Description short ({len(description)} chars), fetching detail for: {url}")
                    try:
                        detail = self.scraper.scrape_job_detail(url, timeout=10)
                        if detail and isinstance(detail, dict) and not detail.get("error"):
                            self.consecutive_detail_failures = 0
                            job["description"] = detail.get("description") or detail.get("markdown") or description
                            if detail.get("company"):
                                job["company"] = detail.get("company")
                            if detail.get("location"):
                                job["location"] = detail.get("location")
                            if detail.get("salary"):
                                job["salary"] = detail.get("salary")
                        else:
                            self.consecutive_detail_failures = getattr(self, "consecutive_detail_failures", 0) + 1
                            logger.warning(f"Detail scrape failed or empty ({self.consecutive_detail_failures}/3): {url}")
                    except Exception as detail_err:
                        self.consecutive_detail_failures = getattr(self, "consecutive_detail_failures", 0) + 1
                        logger.warning(f"Detail scrape timeout/error ({self.consecutive_detail_failures}/3) for {url}: {detail_err}")

                    if getattr(self, "consecutive_detail_failures", 0) >= 3:
                        self.detail_circuit_broken = True
                        logger.warning("Circuit Breaker TRIGGERED: Max 3 consecutive detail failures reached. Disabling detail scraping for this run.")

            logger.info(f"Analyzing job [{job.get('title')}]: {url}")
            try:
                analysis = self.analyzer.analyze_job(job)
            except Exception as e:
                from tools.analyzer import GeminiQuotaExceededError
                if isinstance(e, GeminiQuotaExceededError) or "kvóta kimerült" in str(e).lower():
                    logger.error("Gemini API quota exceeded exception caught. Immediately stopping pipeline and sending Telegram summary.")
                    break
                else:
                    logger.warning(f"Could not analyze job (API error): {url} - {e}")
                    continue

            if not analysis:
                logger.warning(f"Could not analyze job (API error or skipped): {url}")
                continue

            score = analysis.get("score", 0)
            summary = analysis.get("summary", "")
            logger.info(f"Job [{job.get('title')}] Score: {score}/100 - Summary: {summary[:100]}...")

            job_record = {
                "url": url,
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "location": job.get("location", ""),
                "salary": job.get("salary", ""),
                "description": job.get("description", ""),
                "relevance_score": score,
                "ai_summary": summary,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }

            if score >= RELEVANCE_THRESHOLD:
                relevant_count += 1
                saved = self.storage.save_job(job_record)
                if saved:
                    sent = self.notifier.send_job_notification(job_record, score, summary)
                    if sent:
                        sent_count += 1
            else:
                logger.info(f"Job score {score} below threshold {RELEVANCE_THRESHOLD}: {url}")

        if found_count == 0:
            logger.warning("Zero job listings scraped! Scraper or portal structure might have changed.")
            self.notifier.send_error_notification("⚠️ Figyelem: A Scraper 0 hirdetést talált. Lehetséges,hogy megváltozott a Profession.hu felépítése!")

        runtime = time.time() - start_time
        scraped_urls_count = getattr(self.scraper, "last_scraped_urls_count", 5)

        # Cost calculation check against MAX_DAILY_COST_USD
        max_daily_cost = float(os.getenv("MAX_DAILY_COST_USD", "0.05"))
        estimated_gemini_usd = found_count * 0.00015
        estimated_firecrawl_usd = scraped_urls_count * 0.002
        total_run_cost = estimated_gemini_usd + estimated_firecrawl_usd

        if total_run_cost > max_daily_cost:
            logger.warning(f"Cost threshold exceeded: ${total_run_cost:.4f} > ${max_daily_cost:.4f}")
            self.notifier.send_error_notification(
                f"💸 **Költségkeret Riasztás!** A futási költség (~${total_run_cost:.4f} USD) meghaladja a beállított maximum napi keretet (~${max_daily_cost:.4f} USD)!"
            )

        self.notifier.send_summary_notification(
            found=found_count,
            relevant=relevant_count,
            duplicate=duplicate_count,
            sent=sent_count,
            runtime=runtime,
            scraped_urls=scraped_urls_count
        )

        summary_metrics = {
            "found": found_count,
            "relevant": relevant_count,
            "duplicate": duplicate_count,
            "sent": sent_count,
            "errors": 0,
            "runtime": runtime
        }
        self.storage.update_run_log(run_id, "completed", summary_metrics)
        logger.info(f"Pipeline Summary: {summary_metrics}")
        return summary_metrics
