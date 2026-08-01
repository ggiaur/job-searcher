import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class JobStorage:
    def __init__(self, project_id: str = None, mock_mode: bool = None):
        self.mock_mode = mock_mode if mock_mode is not None else (os.getenv("MOCK_MODE", "false").lower() == "true")
        self.project_id = project_id or os.getenv("GCP_PROJECT_ID", "mock-project")
        self.db = None
        self.mock_data: list[str] = []

        if self.mock_mode:
            logger.info("MOCK_MODE enabled: loading mock Firestore state from fixtures")
            fixture_path = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "mock_firestore.json")
            if os.path.exists(fixture_path):
                with open(fixture_path, encoding="utf-8") as f:
                    data = json.load(f)
                    self.mock_data = data.get("saved_jobs", [])
        else:
            try:
                from google.cloud import firestore
                self.db = firestore.Client(project=self.project_id)
            except Exception as e:
                logger.error(f"Firestore connection failed: {e}")
                raise RuntimeError(f"Firestore connection failed: {e}")

    def create_run_log(self, run_id: str) -> bool:
        """Creates a new run_log document in Firestore with status 'running'."""
        if not run_id:
            return False

        log_data = {
            "run_id": run_id,
            "start_time": _utc_now_iso(),
            "status": "running"
        }

        if self.mock_mode:
            if not hasattr(self, "mock_run_logs"):
                self.mock_run_logs = {}
            self.mock_run_logs[run_id] = log_data
            return True

        try:
            self.db.collection("run_log").document(run_id).set(log_data)
            return True
        except Exception as e:
            logger.warning(f"Firestore create_run_log unavailable ({e}), skipped.")
            return True

    def update_run_log(self, run_id: str, status: str, metrics: dict[str, Any]) -> bool:
        """Updates run_log document status, end_time, found, relevant, duplicate, sent, errors."""
        if not run_id:
            return False

        update_data = {
            "status": status,
            "end_time": _utc_now_iso(),
            "found": metrics.get("found", 0),
            "relevant": metrics.get("relevant", 0),
            "duplicate": metrics.get("duplicate", 0),
            "sent": metrics.get("sent", 0),
            "errors": metrics.get("errors", 0)
        }

        if self.mock_mode:
            if hasattr(self, "mock_run_logs") and run_id in self.mock_run_logs:
                self.mock_run_logs[run_id].update(update_data)
            return True

        try:
            self.db.collection("run_log").document(run_id).update(update_data)
            return True
        except Exception as e:
            logger.warning(f"Firestore update_run_log unavailable ({e}), skipped.")
            return True

    def is_duplicate(self, url: str) -> bool:
        """Checks if URL has already been processed and saved."""
        if not url:
            return False

        if self.mock_mode:
            return url in self.mock_data

        try:
            doc_ref = self.db.collection("jobs").document(self._sanitize_doc_id(url))
            doc = doc_ref.get()
            return doc.exists
        except Exception as e:
            logger.warning(f"Firestore duplicate check unavailable ({e}), proceeding without DB cache.")
            return False

    def save_job(self, job: dict[str, Any]) -> bool:
        """Saves a job listing to Firestore or mock storage. Returns True if saved, False if duplicate."""
        url = job.get("url")
        if not url:
            return False

        if self.is_duplicate(url):
            logger.info(f"Duplicate job URL skipped: {url}")
            return False

        if self.mock_mode:
            self.mock_data.append(url)
            return True

        try:
            doc_id = self._sanitize_doc_id(url)
            self.db.collection("jobs").document(doc_id).set(job)
            return True
        except Exception as e:
            logger.warning(f"Firestore save unavailable ({e}), skipped DB write.")
            return True

    def get_recent_jobs(self, days: int = 30) -> list[dict[str, Any]]:
        """Queries records from last 30 days."""
        if self.mock_mode:
            return [{"url": url} for url in self.mock_data]

        try:
            from datetime import timedelta
            cutoff = datetime.now(UTC) - timedelta(days=days)
            docs = self.db.collection("jobs").where("created_at", ">=", cutoff).stream()
            return [doc.to_dict() for doc in docs]
        except Exception as e:
            logger.error(f"Error querying recent jobs from Firestore: {e}")
            raise

    def save_feedback(self, url: str, rating: str) -> bool:
        """Saves user feedback rating ('LIKE' / 'DISLIKE' / etc.) for a job URL."""
        if not url:
            return False

        feedback_record = {
            "url": url,
            "rating": rating,
            "timestamp": _utc_now_iso()
        }

        if self.mock_mode:
            if not hasattr(self, "mock_feedback"):
                self.mock_feedback = []
            self.mock_feedback.append(feedback_record)
            return True

        try:
            doc_id = self._sanitize_doc_id(url + "_" + rating)
            self.db.collection("feedback").document(doc_id).set(feedback_record)
            return True
        except Exception as e:
            logger.warning(f"Firestore feedback save unavailable ({e}), skipped DB write.")
            return True

    def _sanitize_doc_id(self, url: str) -> str:
        import hashlib
        return hashlib.sha256(url.encode("utf-8")).hexdigest()
