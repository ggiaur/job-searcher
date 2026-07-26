import os
import time
import json
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class JobEvaluationSchema(BaseModel):
    score: int = Field(description="0 és 100 közötti egész szám a relevanciára")
    summary: str = Field(description="2-3 mondatos magyar nyelvű összefoglaló, hogy miért releváns vagy miért nem")

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
        self.client = None

        if not self.mock_mode and self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
                self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
            except Exception as e:
                logger.error(f"Error initializing google.genai SDK Client: {e}")
                self.client = None

    def analyze_job(self, job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Analyzes job listing relevance (0-100 score) and generates a 2-3 sentence summary using official google.genai SDK."""
        title = job.get("title", "")
        description = job.get("description", "")
        full_text = f"{title} {description}".lower()

        if self.mock_mode:
            # Deterministic mock scoring logic based on target persona profile rules
            if any(term in full_text for term in ["helpdesk", "1st line", "pék", "junior", "fejlesztő", "éttermi"]):
                if not any(term in full_text for term in ["vezető", "manager", "projektmenedzser"]):
                    return {
                        "score": 0,
                        "summary": "Ez a pozíció a kizáró feltételek hatálya alá esik (helpdesk / junior / fejlesztő / nem IT)."
                    }
            
            if any(term in full_text for term in ["it vezető", "infrastruktúra és üzemeltetési vezető", "cio", "digitalizációs vezető"]):
                return {
                    "score": 85,
                    "summary": "Kiemelkedően releváns IT vezetői pozíció. Tartalmazza a csapatirányítási, M365/Azure és stratégiai feladatokat."
                }
            elif "projektmenedzser" in full_text:
                return {
                    "score": 75,
                    "summary": "Releváns projektmenedzseri pozíció."
                }
            elif any(term in full_text for term in ["csoportvezető", "üzemeltetési"]):
                return {
                    "score": 55,
                    "summary": "Közepesen releváns üzemeltetői pozíció, de hiányoznak a vezetői feladatok."
                }
            else:
                return {
                    "score": 20,
                    "summary": "Alacsony relevanciájú álláshirdetés."
                }

        if not self.client:
            logger.error("google.genai client is not initialized.")
            return None

        # Safety delay (2 seconds between calls) to prevent token spike
        now = time.time()
        time_since_last = now - self.last_call_time
        if time_since_last < 2.0:
            time.sleep(2.0 - time_since_last)

        current_persona = _load_persona()

        prompt = f"""
A megadott profil alapján értékeld az alábbi állásajánlatot!

Profil és Szabályok:
{current_persona}

Álláshirdetés:
Cím: {title}
Leírás: {description[:3000]}
"""

        for attempt in range(4):
            try:
                self.last_call_time = time.time()
                from google.genai import types
                
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=JobEvaluationSchema,
                    ),
                )
                
                text_content = response.text or ""
                data = self._parse_json_response(text_content)
                if not data or "score" not in data:
                    return {"score": 0, "summary": "Gemini elemzési hiba."}
                return {
                    "score": int(data.get("score", 0)),
                    "summary": str(data.get("summary", ""))
                }
            except Exception as e:
                logger.warning(f"google.genai API attempt {attempt + 1} failed: {e}")
                if "429" in str(e) or "Quota" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    try:
                        logger.info("Attempting automatic fallback with gemini-2.0-flash...")
                        from google.genai import types
                        res = self.client.models.generate_content(
                            model="gemini-2.0-flash",
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                                response_schema=JobEvaluationSchema,
                            ),
                        )
                        data = self._parse_json_response(res.text or "")
                        if data and "score" in data:
                            return {
                                "score": int(data.get("score", 0)),
                                "summary": str(data.get("summary", ""))
                            }
                    except Exception as fallback_err:
                        logger.error(f"Fallback model failed: {fallback_err}")
                import random
                jitter = random.uniform(0.5, 1.5)
                sleep_time = (2 ** attempt) + jitter
                time.sleep(sleep_time)

        return {"score": 0, "summary": "Gemini elemzési hiba."}

    def _parse_json_response(self, text: str) -> Optional[Dict[str, Any]]:
        """Cleans markdown blocks or extra surrounding text and parses JSON robustly."""
        if not text:
            return None
        text_clean = text.strip()
        if "```" in text_clean:
            import re
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text_clean, re.DOTALL)
            if match:
                text_clean = match.group(1)
        else:
            import re
            match = re.search(r"(\{.*?\})", text_clean, re.DOTALL)
            if match:
                text_clean = match.group(1)
        try:
            return json.loads(text_clean)
        except Exception:
            return None
