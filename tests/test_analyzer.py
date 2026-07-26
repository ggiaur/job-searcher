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

