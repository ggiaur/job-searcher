import os
import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

FEEDBACK_FILE = os.path.join(os.path.dirname(__file__), "..", "profile", "feedback_history.json")

class FeedbackStore:
    """Manages user feedback history and integrates human learnings back to persona.md"""

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

    def record_feedback(self, job_url: str, job_title: str, action: str, reason: str = "") -> Dict[str, Any]:
        """Actions: 'LIKE' (érdekel), 'DISLIKE' (nem érdekel), 'APPLIED' (jelentkeztem)"""
        feedbacks = self.load_feedbacks()
        entry = {
            "job_url": job_url,
            "job_title": job_title,
            "action": action,
            "reason": reason,
            "timestamp": os.popen("date -u +%Y-%m-%dT%H:%M:%SZ").read().strip()
        }
        feedbacks.append(entry)
        with open(self.feedback_file, "w", encoding="utf-8") as f:
            json.dump(feedbacks, f, ensure_ascii=False, indent=2)

        self._sync_feedback_to_persona()
        return entry

    def _sync_feedback_to_persona(self):
        """Appends recent negative & positive human feedback rules to profile/persona.md to update AI memory."""
        feedbacks = self.load_feedbacks()
        if not feedbacks:
            return

        dislikes = [f for f in feedbacks if f.get("action") == "DISLIKE" and f.get("reason")]
        likes = [f for f in feedbacks if f.get("action") in ("LIKE", "APPLIED") and f.get("reason")]

        persona_path = os.path.join(os.path.dirname(__file__), "..", "profile", "persona.md")
        if not os.path.exists(persona_path):
            return

        with open(persona_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Add section if not exists
        if "## Tanult Emberi Preferenciák (Human-in-the-Loop Feedback)" not in content:
            content += "\n\n## Tanult Emberi Preferenciák (Human-in-the-Loop Feedback)\n"

        # Update feedback section
        base_content = content.split("## Tanult Emberi Preferenciák (Human-in-the-Loop Feedback)")[0].strip()
        
        feedback_section = "\n\n## Tanult Emberi Preferenciák (Human-in-the-Loop Feedback)\n"
        if dislikes:
            feedback_section += "### Elutasított minták (Pontszám csökkentő / Kizáró tényezők):\n"
            for d in dislikes[-10:]:
                feedback_section += f"- [{d['job_title']}] ok: {d['reason']}\n"

        if likes:
            feedback_section += "### Preferált minták (Kiemelt relevancia):\n"
            for l in likes[-10:]:
                feedback_section += f"- [{l['job_title']}] ok: {l['reason']}\n"

        new_content = base_content + feedback_section
        with open(persona_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        logger.info("Synced Human-in-the-Loop feedback rules into profile/persona.md")
