import os
import json
import logging
from typing import Dict, Any, List

import datetime

logger = logging.getLogger(__name__)

FEEDBACK_FILE = os.path.join(os.path.dirname(__file__), "..", "profile", "feedback_history.json")

class FeedbackStore:
    """Manages user feedback history and integrates human learnings back to learned_preferences.md"""

    def __init__(self, feedback_file: str = None):
        self.feedback_file = feedback_file or FEEDBACK_FILE
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        if not os.path.exists(self.feedback_file):
            os.makedirs(os.path.dirname(self.feedback_file), exist_ok=True)
            with open(self.feedback_file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def load_feedbacks(self) -> List[Dict[str, Any]]:
        try:
            with open(self.feedback_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading feedback history: {e}")
            return []

    def record_feedback(self, job_url: str, job_title: str, action: str, reason: str = "", company: str = "") -> Dict[str, Any]:
        """Actions: 'STAR' (kiemelt), 'LIKE' (releváns), 'CONSIDER' (fontolóra veszem), 'DISLIKE' (elutasítom), 'APPLIED' (jelentkeztem)"""
        feedbacks = self.load_feedbacks()
        entry = {
            "job_url": job_url,
            "job_title": job_title,
            "company": company,
            "action": action,
            "reason": reason,
            "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        feedbacks.append(entry)
        with open(self.feedback_file, "w", encoding="utf-8") as f:
            json.dump(feedbacks, f, ensure_ascii=False, indent=2)

        self._sync_feedback_to_learned_preferences()
        self._check_company_patterns(feedbacks)
        return entry

    def _sync_feedback_to_learned_preferences(self):
        """Appends recent negative & positive human feedback rules to profile/learned_preferences.md."""
        feedbacks = self.load_feedbacks()
        if not feedbacks:
            return

        dislikes = [f for f in feedbacks if f.get("action") == "DISLIKE" and f.get("reason")]
        likes = [f for f in feedbacks if f.get("action") in ("STAR", "LIKE", "CONSIDER", "APPLIED") and f.get("reason")]

        pref_path = os.path.join(os.path.dirname(__file__), "..", "profile", "learned_preferences.md")
        content = "# Tanult Emberi Preferenciák (Human-in-the-Loop Feedback)\n\n"
        
        if dislikes:
            content += "## Elutasított minták (Pontszám csökkentő / Kizáró tényezők):\n"
            for d in dislikes[-10:]:
                content += f"- [{d['job_title']}] ok: {d['reason']}\n"

        if likes:
            content += "\n## Preferált minták (Kiemelt relevancia):\n"
            for l in likes[-10:]:
                content += f"- [{l['job_title']}] ok: {l['reason']}\n"

        with open(pref_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("Synced Human-in-the-Loop feedback rules into profile/learned_preferences.md")

    def _check_company_patterns(self, feedbacks: List[Dict[str, Any]]):
        """Identifies 2x dislike / 2x like company patterns and updates exclusions.yaml / preferred_companies.yaml."""
        import yaml
        
        company_dislikes = {}
        company_likes = {}
        
        for f in feedbacks:
            company = f.get("company", "").strip()
            if not company:
                continue
            action = f.get("action")
            if action == "DISLIKE":
                company_dislikes[company] = company_dislikes.get(company, 0) + 1
            elif action in ("STAR", "LIKE"):
                company_likes[company] = company_likes.get(company, 0) + 1

        # 2x DISLIKE -> exclusions.yaml
        excl_path = os.path.join(os.path.dirname(__file__), "..", "profile", "exclusions.yaml")
        excl_data = {"excluded_companies": []}
        if os.path.exists(excl_path):
            try:
                with open(excl_path, "r", encoding="utf-8") as f:
                    excl_data = yaml.safe_load(f) or {"excluded_companies": []}
            except Exception:
                pass
        
        for comp, count in company_dislikes.items():
            if count >= 2 and comp not in excl_data.get("excluded_companies", []):
                excl_data.setdefault("excluded_companies", []).append(comp)
                logger.info(f"Company '{comp}' added to exclusions.yaml due to 2x DISLIKE")

        with open(excl_path, "w", encoding="utf-8") as f:
            yaml.dump(excl_data, f, allow_unicode=True)

        # 2x STAR/LIKE -> preferred_companies.yaml
        pref_path = os.path.join(os.path.dirname(__file__), "..", "profile", "preferred_companies.yaml")
        pref_data = {"preferred_companies": []}
        if os.path.exists(pref_path):
            try:
                with open(pref_path, "r", encoding="utf-8") as f:
                    pref_data = yaml.safe_load(f) or {"preferred_companies": []}
            except Exception:
                pass

        for comp, count in company_likes.items():
            if count >= 2 and comp not in pref_data.get("preferred_companies", []):
                pref_data.setdefault("preferred_companies", []).append(comp)
                logger.info(f"Company '{comp}' added to preferred_companies.yaml due to 2x LIKE")

        with open(pref_path, "w", encoding="utf-8") as f:
            yaml.dump(pref_data, f, allow_unicode=True)
