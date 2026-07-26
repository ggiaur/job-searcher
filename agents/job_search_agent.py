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

    def run(self) -> Dict[str, Any]:
        start_time = time.time()
        logger.info("Starting JobSearchAgent pipeline execution...")

        listings = self.scraper.scrape_jobs()
        found_count = len(listings)
        duplicate_count = 0
        relevant_count = 0
        sent_count = 0

        for job in listings:
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

            # Enrich short descriptions with full detail page markdown
            description = job.get("description", "")
            if len(description) < 200:
                logger.info(f"Description short ({len(description)} chars), fetching detail for: {url}")
                try:
                    detail = self.scraper.scrape_job_detail(url)
                    if detail and isinstance(detail, dict) and not detail.get("error"):
                        job["description"] = detail.get("description") or detail.get("markdown") or description
                        if detail.get("company"):
                            job["company"] = detail.get("company")
                        if detail.get("location"):
                            job["location"] = detail.get("location")
                        if detail.get("salary"):
                            job["salary"] = detail.get("salary")
                except Exception as detail_err:
                    logger.warning(f"Failed to fetch job detail for {url}: {detail_err}")

            logger.info(f"Analyzing job [{job.get('title')}]: {url}")
            analysis = self.analyzer.analyze_job(job)
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
            "runtime": runtime
        }
        logger.info(f"Pipeline Summary: {summary_metrics}")
        return summary_metrics
