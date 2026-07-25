import os
import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class JobStorage:
    def __init__(self, project_id: str = None, mock_mode: bool = None):
        self.mock_mode = mock_mode if mock_mode is not None else (os.getenv("MOCK_MODE", "false").lower() == "true")
        self.project_id = project_id or os.getenv("GCP_PROJECT_ID", "mock-project")
        self.db = None
        self.mock_data: List[str] = []

        if self.mock_mode:
            logger.info("MOCK_MODE enabled: loading mock Firestore state from fixtures")
            fixture_path = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "mock_firestore.json")
            if os.path.exists(fixture_path):
                with open(fixture_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.mock_data = data.get("saved_jobs", [])
        else:
            try:
                from google.cloud import firestore
                self.db = firestore.Client(project=self.project_id)
            except Exception as e:
                logger.error(f"Firestore connection failed: {e}")
                raise RuntimeError(f"Firestore connection failed: {e}")

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
            logger.error(f"Error checking duplicate in Firestore: {e}")
            raise

    def save_job(self, job: Dict[str, Any]) -> bool:
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
            logger.error(f"Error saving job to Firestore: {e}")
            raise

    def get_recent_jobs(self, days: int = 30) -> List[Dict[str, Any]]:
        """Queries records from last 30 days."""
        if self.mock_mode:
            return [{"url": url} for url in self.mock_data]

        try:
            from datetime import datetime, timedelta
            cutoff = datetime.utcnow() - timedelta(days=days)
            docs = self.db.collection("jobs").where("created_at", ">=", cutoff).stream()
            return [doc.to_dict() for doc in docs]
        except Exception as e:
            logger.error(f"Error querying recent jobs from Firestore: {e}")
            raise

    def _sanitize_doc_id(self, url: str) -> str:
        import hashlib
        return hashlib.sha256(url.encode("utf-8")).hexdigest()
