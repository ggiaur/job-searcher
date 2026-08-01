import json
import logging
import os
import time
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class JobEvaluationSchema(BaseModel):
    score: int = Field(description="0 és 100 közötti egész szám a relevanciára")
    summary: str = Field(description="2-3 mondatos magyar nyelvű összefoglaló, hogy miért releváns vagy miért nem")

def _load_persona() -> str:
    profile_dir = os.path.join(os.path.dirname(__file__), "..", "profile")
    persona_path = os.path.join(profile_dir, "persona.md")
    pref_path = os.path.join(profile_dir, "learned_preferences.md")
    
    content = ""
    if os.path.exists(persona_path):
        with open(persona_path, encoding="utf-8") as f:
            content += f.read()
    
    if os.path.exists(pref_path):
        with open(pref_path, encoding="utf-8") as f:
            content += "\n\n" + f.read()
            
    return content

TARGET_PERSONA_PROMPT = _load_persona()

class GeminiQuotaExceededError(Exception):
    """Raised when Gemini API quota is exceeded (429 / RESOURCE_EXHAUSTED)."""
    pass

class JobAnalyzer:
    def __init__(self, api_key: str = None, mock_mode: bool = None):
        self.mock_mode = mock_mode if mock_mode is not None else (os.getenv("MOCK_MODE", "false").lower() == "true")
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
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

    def analyze_job(self, job: dict[str, Any]) -> dict[str, Any] | None:
        """Analyzes job listing relevance (0-100 score) and generates a 2-3 sentence summary using official google.genai SDK."""
        title = job.get("title", "")
        company = job.get("company", "").strip()
        description = job.get("description", "")
        full_text = f"{title} {description}".lower()

        # Check YAML company exclusions (0 score) & preferences (+10 bonus)
        import yaml
        profile_dir = os.path.join(os.path.dirname(__file__), "..", "profile")
        excl_path = os.path.join(profile_dir, "exclusions.yaml")
        pref_path = os.path.join(profile_dir, "preferred_companies.yaml")

        excluded_companies = []
        if os.path.exists(excl_path):
            try:
                with open(excl_path, encoding="utf-8") as f:
                    excl_data = yaml.safe_load(f) or {}
                    excluded_companies = excl_data.get("excluded_companies", [])
            except Exception:
                pass

        if company and company in excluded_companies:
            logger.info(f"Company '{company}' is in exclusions.yaml -> 0 score assigned.")
            return {
                "score": 0,
                "summary": f"Ez a cég ({company}) szerepel a kizárt cégek (exclusions.yaml) listáján."
            }

        preferred_companies = []
        if os.path.exists(pref_path):
            try:
                with open(pref_path, encoding="utf-8") as f:
                    pref_data = yaml.safe_load(f) or {}
                    preferred_companies = pref_data.get("preferred_companies", [])
            except Exception:
                pass

        if self.mock_mode:
            # Deterministic mock scoring logic based on target persona profile rules
            if any(term in full_text for term in ["helpdesk", "1st line", "pék", "junior", "fejlesztő", "éttermi"]):
                return {
                    "score": 15,
                    "summary": f"A pozíció ({title}) alacsony relevanciájú, mivel nem vezetői szintre fókuszál."
                }
            if any(term in full_text for term in ["it vezető", "it manager", "infrastruktúra vezető", "osztályvezető", "projektmenedzser", "cio"]):
                score = 90
                if company and company in preferred_companies:
                    score = min(100, score + 10)
                return {
                    "score": score,
                    "summary": f"A pozíció ({title}) kiemelkedően releváns a megadott vezetői profil alapján."
                }
            return {
                "score": 50,
                "summary": f"A pozíció ({title}) közepesen releváns."
            }

        if not self.client:
            logger.error("Gemini SDK Client is not initialized.")
            return {"score": 0, "summary": "Gemini kliens nincs inicializálva."}

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
                score = int(data.get("score", 0))
                if company and company in preferred_companies:
                    score = min(100, score + 10)
                    logger.info(f"Added +10 bonus for preferred company '{company}' -> new score: {score}")
                return {
                    "score": score,
                    "summary": str(data.get("summary", ""))
                }
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "Quota" in err_str or "RESOURCE_EXHAUSTED" in err_str or "prepayment credits are depleted" in err_str.lower():
                    logger.error("Gemini API napi kvóta kimerült. Hirdetések elemzése leállítva.")
                    raise GeminiQuotaExceededError("Gemini API napi kvóta kimerült. Hirdetések elemzése leállítva.")
                logger.warning(f"google.genai API attempt {attempt + 1} failed: {e}")
                import random
                jitter = random.uniform(0.5, 1.5)
                sleep_time = (2 ** attempt) + jitter
                time.sleep(sleep_time)

        return {"score": 0, "summary": "Gemini elemzési hiba."}

    def _parse_json_response(self, text: str) -> dict[str, Any] | None:
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
