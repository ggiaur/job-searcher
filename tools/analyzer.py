import os
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

TARGET_PERSONA_PROMPT = """
Keresett pozíciók: IT vezető, IT manager, IT osztályvezető, infrastruktúra vezető, IT projektmenedzser, Digitalizációs vezető, CIO.
Tapasztalat: 20+ év IT, 4+ év csapatvezetés.
Kulcsszavak: IT infrastruktúra, üzemeltetés, fejlesztés, csapatirányítás (6 fős csapat), M365, Azure, Linux, Docker, VPN, IT-költségvetés, beszerzés, MI/AI.
Kizáró feltételek (0 pont): tisztán helpdesk / 1st line support, junior / entry-level, nem IT menedzsment, kizárólag szoftverfejlesztő / programozó.
"""

class JobAnalyzer:
    def __init__(self, api_key: str = None, mock_mode: bool = None):
        self.mock_mode = mock_mode if mock_mode is not None else (os.getenv("MOCK_MODE", "false").lower() == "true")
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.last_call_time = 0.0

        if not self.mock_mode and self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel('gemini-1.5-flash')
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
        if not self.api_key:
            logger.error("GEMINI_API_KEY is not set.")
            return None

        # Rate limiting: max 10 calls / min (6 seconds delay)
        now = time.time()
        time_since_last = now - self.last_call_time
        if time_since_last < 6.0:
            time.sleep(6.0 - time_since_last)

        max_retries = 3
        backoff = 2.0

        for attempt in range(max_retries):
            try:
                self.last_call_time = time.time()
                prompt = (
                    f"Értékeld az alábbi álláshirdetés relevanciáját a célszemély profilja alapján 0 és 100 közötti pontszámmal!\n"
                    f"Profil:\n{TARGET_PERSONA_PROMPT}\n\n"
                    f"Állás megnevezése: {title}\n"
                    f"Leírás: {description}\n\n"
                    f"Válasz formátum: Csak egy JSON objektumot adj meg az alábbi szerkezetben:\n"
                    f'{{"score": <int 0-100>, "summary": "<max 500 karakteres 2-3 mondatos magyar összefoglaló>"}}'
                )
                response = self.model.generate_content(prompt)
                text = response.text.strip()
                
                # Clean code blocks if present
                if text.startswith("```json"):
                    text = text[7:]
                if text.endswith("```"):
                    text = text[:-3]
                
                import json
                data = json.loads(text.strip())
                score = int(data.get("score", 0))
                summary = str(data.get("summary", ""))[:500]
                
                # Clamp score
                score = max(0, min(100, score))
                return {
                    "score": score,
                    "summary": summary
                }
            except Exception as e:
                logger.warning(f"Gemini API call attempt {attempt+1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(backoff)
                    backoff *= 2.0
                else:
                    logger.error("All 3 retries for Gemini API failed.")
                    return None
