import os
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def _load_persona() -> str:
    persona_path = os.path.join(
        os.path.dirname(__file__), "..", "profile", "persona.md"
    )
    with open(persona_path, "r", encoding="utf-8") as f:
        return f.read()

TARGET_PERSONA_PROMPT = _load_persona()

class JobAnalyzer:
    def __init__(self, api_key: str = None, mock_mode: bool = None):
        self.mock_mode = mock_mode if mock_mode is not None else (os.getenv("MOCK_MODE", "false").lower() == "true")
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.last_call_time = 0.0

        if not self.mock_mode and self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
                try:
                    self.model = genai.GenerativeModel(model_name)
                except Exception:
                    self.model = genai.GenerativeModel('gemini-2.0-flash')
            except Exception as e:
                logger.error(f"Error initializing Gemini API: {e}")
                self.model = None

    def analyze_job(self, job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Analyzes job listing relevance (0-100 score) and generates a 2-3 sentence summary."""
        title = job.get("title", "")
        description = job.get("description", "")
        full_text = f"{title} {description}".lower()

        if self.mock_mode:
            # Deterministic mock scoring logic based on target persona profile rules
            # Exclusion rules
            if any(term in full_text for term in ["helpdesk", "1st line", "pék", "junior", "fejlesztő", "éttermi"]):
                if not any(term in full_text for term in ["vezető", "manager", "projektmenedzser"]):
                    return {
                        "score": 0,
                        "summary": "Ez a pozíció a kizáró feltételek hatálya alá esik (helpdesk / junior / fejlesztő / nem IT)."
                    }
            
            # High relevance cases
            if any(term in full_text for term in ["it vezető", "infrastruktúra és üzemeltetési vezető", "cio", "digitalizációs vezető"]):
                return {
                    "score": 85,
                    "summary": "Kiemelkedően releváns IT vezetői pozíció. Tartalmazza a csapatirányítási, M365/Azure és stratégiai feladatokat."
                }
            elif "projektmenedzser" in full_text:
                return {
                    "score": 75,
                    "summary": "Releváns IT projektmenedzseri pozíció. Tervezési és digitalizációs feladatokat foglal magában."
                }
            elif "rendszergazda" in full_text:
                return {
                    "score": 55,
                    "summary": "Közepesen releváns üzemeltetői pozíció, de hiányoznak a vezetői feladatok."
                }
            else:
                return {
                    "score": 20,
                    "summary": "Alacsony relevanciájú álláshirdetés."
                }

        # Real Gemini API call with rate limiting and exponential retry
        if not self.model:
            logger.error("Gemini model is not initialized.")
            return None

        # Rate limiting: max 5 calls / min (12.5 seconds delay)
        now = time.time()
        time_since_last = now - self.last_call_time
        if time_since_last < 12.5:
            time.sleep(12.5 - time_since_last)

        # Reload fresh persona (which includes recent Human-in-the-Loop learnings)
        current_persona = _load_persona()

        prompt = f"""
A megadott profil alapján értékeld az alábbi állásajánlatot!

Profil és Szabályok:
{current_persona}

Álláshirdetés:
Cím: {title}
Leírás: {description[:3000]}

Válaszolj KIZÁRÓLAG az alábbi JSON formátumban:
{{
  "score": <0 és 100 közötti egész szám>,
  "summary": "<2-3 mondatos magyar nyelvű összefoglaló, hogy miért releváns vagy miért nem>"
}}
"""

        for attempt in range(4):
            try:
                self.last_call_time = time.time()
                response = self.model.generate_content(prompt)
                text = response.text.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
                
                data = json.loads(text)
                return {
                    "score": int(data.get("score", 0)),
                    "summary": str(data.get("summary", ""))
                }
            except Exception as e:
                logger.warning(f"Gemini API call attempt {attempt + 1} failed: {e}")
                time.sleep(15 * (attempt + 1))

        return {"score": 0, "summary": "Gemini elemzési hiba."}
