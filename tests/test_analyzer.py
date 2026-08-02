from tools.analyzer import JobAnalyzer, _load_persona


def test_analyzer_load_persona():
    persona = _load_persona()
    assert persona is not None
    assert "Célszemély profil" in persona

def test_analyzer_mock_mode_relevant():
    analyzer = JobAnalyzer(mock_mode=True)
    job = {
        "title": "IT vezető",
        "description": "6 fős csapat irányítása, M365 és Azure felhő stratégia"
    }
    res = analyzer.analyze_job(job)
    assert res is not None
    assert "score" in res
    assert "summary" in res
    assert 0 <= res["score"] <= 100
    assert res["score"] > 70
    assert len(res["summary"]) > 0
    assert len(res["summary"]) <= 500

def test_analyzer_mock_mode_irrelevant():
    analyzer = JobAnalyzer(mock_mode=True)
    job = {
        "title": "Helpdesk Munkatárs",
        "description": "1st line ügyfélszolgálati jelszó-helyreállítás"
    }
    res = analyzer.analyze_job(job)
    assert res is not None
    assert res["score"] < 40

def test_analyzer_retry_and_failure_handling(monkeypatch):
    analyzer = JobAnalyzer(mock_mode=False, api_key="invalid-key")
    
    class ExceptionModels:
        def generate_content(self, model, contents, config=None):
            raise Exception("API Error")

    class ExceptionClient:
        def __init__(self):
            self.models = ExceptionModels()
            
    analyzer.client = ExceptionClient()
    res = analyzer.analyze_job({"title": "Test", "description": "Test"})
    assert res == {"score": 0, "summary": "Gemini elemzési hiba."}

def test_analyzer_parse_json_raw_fixtures():
    analyzer = JobAnalyzer(mock_mode=True)
    
    # 1. Clean JSON
    clean_json = '{"score": 85, "summary": "Remek pozíció."}'
    res1 = analyzer._parse_json_response(clean_json)
    assert res1 == {"score": 85, "summary": "Remek pozíció."}

    # 2. Markdown code block
    md_json = '```json\n{"score": 75, "summary": "PM állás."}\n```'
    res2 = analyzer._parse_json_response(md_json)
    assert res2 == {"score": 75, "summary": "PM állás."}

    # 3. Conversational wrapper text
    conv_json = 'Itt a válasz:\n```json\n{"score": 90, "summary": "CIO pozíció"}\n```'
    res3 = analyzer._parse_json_response(conv_json)
    assert res3 == {"score": 90, "summary": "CIO pozíció"}

    # 4. Corrupted / invalid JSON
    corrupt_json = '{"score": "nem_szam"'
    res4 = analyzer._parse_json_response(corrupt_json)
    assert res4 is None

def test_genai_package_is_installed_and_client_api_matches():
    """Regression guard, same class of bug as the firecrawl one in
    tools/scraper.py: requirements.txt used to list `google-generativeai`
    (the old, now-deprecated package — importable as `import
    google.generativeai`), but tools/analyzer.py was already migrated to
    the new `google-genai` package (`from google import genai`, a
    *different* PyPI distribution under the same `google.*` namespace).
    A plain `pip install -r requirements.txt` therefore installed the
    wrong package entirely, and `from google import genai` raised
    ImportError immediately — the real (non-mock) analysis path, the
    single most important feature of this tool, could not even import.
    No mock-mode test could ever catch this since mock mode never touches
    this import. Checks the actual package requirements.txt now declares
    is importable and its Client exposes the specific API surface
    analyzer.py calls (`Client(api_key=...)`,
    `.models.generate_content(model=, contents=, config=)`,
    `types.GenerateContentConfig(response_mime_type=, response_schema=)`).
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key="test-key-not-a-real-credential")
    assert hasattr(client, "models") and hasattr(client.models, "generate_content"), (
        "google.genai.Client has no models.generate_content — the SDK's API changed; "
        "tools/analyzer.py's real (non-mock) analysis is broken."
    )

    config_fields = types.GenerateContentConfig.model_fields
    for field in ("response_mime_type", "response_schema"):
        assert field in config_fields, (
            f"types.GenerateContentConfig no longer has a '{field}' field — "
            "tools/analyzer.py's structured-JSON response config will break."
        )



def test_all_runtime_imports_are_declared_in_requirements():
    """Regression: tools/analyzer.py and tools/feedback.py both `import yaml`,
    but PyYAML was never listed in requirements.txt. It was present in the
    local venv (pulled in transitively by another package), so tests passed —
    but the production Docker image installs ONLY requirements.txt, so every
    analyze_job() call died with "No module named 'yaml'".
    Confirmed in real Cloud Run logs: found=99, relevant=0, sent=0.

    Third requirements.txt drift bug in this project (see DECISIONS.md #4),
    so this checks the file itself rather than just importing the module.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parent.parent
    requirements = (root / "requirements.txt").read_text().lower()

    module_to_distribution = {
        "yaml": "pyyaml",
        "firecrawl": "firecrawl-py",
        "dotenv": "python-dotenv",
        "telegram": "python-telegram-bot",
        "pydantic": "pydantic",
    }

    runtime_files = list((root / "tools").glob("*.py")) + list((root / "agents").glob("*.py"))
    imported = set()
    for path in runtime_files:
        for line in path.read_text().splitlines():
            match = re.match(r"\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)", line)
            if match:
                imported.add(match.group(1))

    missing = [
        f"{module} (needs '{dist}')"
        for module, dist in module_to_distribution.items()
        if module in imported and dist not in requirements
    ]
    assert not missing, "Imported but missing from requirements.txt: " + ", ".join(missing)


def test_analyzer_uses_vertex_ai_when_enabled(monkeypatch):
    """A GEMINI_USE_VERTEX=true bekapcsolja a Vertex AI módot.

    Miért kell ez: az AI Studio-n keresztüli Gemini API-t a GCP $300-os
    ingyenes kerete NEM fedezi (a Google dokumentációja szó szerint kimondja:
    "The $300 credit can't pay for Gemini API in AI Studio costs"). A Vertex
    AI-on futó Gemini viszont sima GCP-szolgáltatásként számlázódik, tehát a
    keretből fedezhető.

    Vertex módban NEM API-kulccsal hitelesítünk, hanem a környezet
    alapértelmezett hitelesítő adataival (Cloud Runon a szolgáltatásfiókkal) —
    ezért a projektet és a régiót kell átadni, api_key-t nem.
    """
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import google.genai
    monkeypatch.setattr(google.genai, "Client", FakeClient)

    monkeypatch.setenv("GEMINI_USE_VERTEX", "true")
    monkeypatch.setenv("GCP_PROJECT_ID", "job-searcher-503608")
    monkeypatch.setenv("GCP_LOCATION", "europe-west1")
    monkeypatch.setenv("GEMINI_API_KEY", "should-not-be-used-in-vertex-mode")

    JobAnalyzer(mock_mode=False)

    assert captured.get("vertexai") is True, f"vertexai=True kell, kaptuk: {captured}"
    assert captured.get("project") == "job-searcher-503608"
    assert captured.get("location") == "europe-west1"
    assert "api_key" not in captured or captured.get("api_key") is None, (
        "Vertex módban nem API-kulccsal hitelesítünk, hanem ADC-vel"
    )


def test_analyzer_defaults_to_ai_studio_when_vertex_not_enabled(monkeypatch):
    """Vertex kikapcsolva (alapértelmezés) -> a régi, API-kulcsos AI Studio út.
    Ez biztosítja, hogy az átállítás visszafelé kompatibilis maradjon."""
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import google.genai
    monkeypatch.setattr(google.genai, "Client", FakeClient)

    monkeypatch.delenv("GEMINI_USE_VERTEX", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")

    JobAnalyzer(mock_mode=False)

    assert captured.get("api_key") == "test-key-123"
    assert not captured.get("vertexai")


def test_min_call_interval_is_configurable_and_free_tier_safe(monkeypatch):
    """A hívások közti minimális szünet legyen környezeti változóval állítható,
    és az alapértelmezés legyen biztonságos az ingyenes szinthez.

    Előzmény: a d46d972 commit ("Rate limiting szünetek eltávolítva a fizetős
    GCP 300$ kredit kihasználásához") kivette a fékezést azzal az indokkal,
    hogy a $300-as GCP keret fedezi a költséget. Ez tárgyi tévedés: a Google
    dokumentációja szerint a keret az AI Studio-s Gemini API-ra NEM
    használható. A fék így a felhasználó előre fizetett kreditjét égette
    maximális sebességgel.

    Az ingyenes szinten percenkénti kéréslimit van, ezért fék nélkül a futás
    azonnal 429-be futna. A hardcode-olt érték helyett legyen állítható, hogy
    a limit változásakor ne kelljen kódot módosítani.
    """
    a = JobAnalyzer(mock_mode=True)
    # Alapértelmezés: legalább 6 mp (<= 10 kérés/perc), ami a szűkös ingyenes
    # percenkénti limitek mellett is biztonságos.
    assert a.min_call_interval >= 6.0, (
        f"az alapértelmezett szünet túl rövid az ingyenes szinthez: {a.min_call_interval}"
    )

    monkeypatch.setenv("GEMINI_MIN_INTERVAL_SEC", "1.5")
    b = JobAnalyzer(mock_mode=True)
    assert b.min_call_interval == 1.5, "a szünetnek env-változóval állíthatónak kell lennie"


def test_analyzer_default_model_uses_latest_alias_not_hardcoded_version(monkeypatch):
    """Regression: a korábbi alapértelmezés egy konkrét verziószámú modellnév
    volt (gemini-2.5-flash). Élesben kiderült, hogy egy vadonatúj AI Studio
    kulcs/projekt alól ez 404-et ad ("no longer available to new users"),
    miközben egy régebbi projektnél ugyanaz a név még működik - a hozzáférés
    kulcsonként/projektenként változik, nem globálisan.

    A "-latest" alias pont ezt a problémaosztályt oldja meg: nem kell
    előre tudni, melyik konkrét verzió érhető el egy adott kulcsnál.
    """
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    a = JobAnalyzer(mock_mode=False)

    assert a.model_name == "gemini-flash-latest", (
        f"az alapértelmezésnek egy -latest aliasnak kell lennie, nem hardcode-olt "
        f"verziószámnak, kaptuk: {a.model_name}"
    )
