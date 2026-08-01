# Fejlesztési Döntések Logja (DECISIONS.md)

Ez a fájl tartalmazza azokat az interim döntéseket, amelyeket az fejlesztés során hoztunk az egyértelműség és a konzervatív működés érdekében.

## 1. MOCK_MODE alapértelmezett működés
- **Kérdés:** Hogyan kezelje a rendszer a tesztelést külső API kulcsok hiányában?
- **Döntés:** Ha a `MOCK_MODE=true` be van állítva, az összes modul (`scraper`, `analyzer`, `storage`, `notifier`) a `tests/fixtures/` könyvtárban található tesztadatokból olvas és nem indít valódi hálózati kéréseket.

## 2. Hard Limits és Rate Limits
- **Scraper:** Szigorú 100 hirdetés/futás korlát bevezetése kódszinten.
- **Analyzer:** Gemini API hívások esetén max 10 kérés/perc betartása, 3 kísérletig terjedő exponenciális retry logikával.

## 3. Diagnosztikai Teszt Eredmények (Éles URL Validáció)
- **Tesztelt első URL:** `https://www.profession.hu/allasok/it-uzemeltetes-telekommunikacio/1,25,0,it%20vezet%C5%91`
- **Eredmény:** **20 hirdetés** került kinyerésre (ami meghaladja a 15-ös minimális elvárási küszöbértéket).
- **Minta találatok:**
  - *Vezető felügyelő (IT felügyelet)* - Magyar Nemzeti Bank
  - *IT/OT Security Governance és Szabályozási osztályvezető* - MVM Services Zrt.
  - *IT service desk csoportvezető* - BKM Budapesti Közművek Zrt.
  - *IT Manager* - Howmet KÖFÉM Kft.

## 4. Kritikus Függőségi Hibák Feltárása és Javítása (Kódminőségi Átvizsgálás, 2026-08-01)
- **Kérdés:** A `requirements.txt`-ben megadott csomagok tényleg megfelelnek-e a kódban ténylegesen használt API-knak? (Ezt korábban egyetlen teszt sem ellenőrizte, mert a tesztsuit kizárólag `MOCK_MODE=true` mellett fut, ami sosem érinti a valódi kliens-importokat.)
- **Talált hiba #1 — Firecrawl:** a `firecrawl-py` csomag `>=1.0.0` verziómegkötése a legújabb (4.x) verziót telepíti, ahol a `FirecrawlApp`/`Firecrawl` osztály `scrape_url()` metódusa csak egy szűk célú, "agent recovery" belső csökevényként létezik (`(url, **kwargs)` szignatúrával), nem a `tools/scraper.py` által elvárt, teljesen tipizált v1 API-ként. **Döntés:** explicit a csomag saját, megőrzött `V1FirecrawlApp` osztályát importáljuk (`from firecrawl import V1FirecrawlApp as FirecrawlApp`).
- **Talált hiba #2 — Gemini SDK:** a `requirements.txt` még mindig a régi, elavult `google-generativeai` csomagot listázta, miközben a `tools/analyzer.py` már rég átállt az új `google-genai` csomagra (`from google import genai`) — egy teljesen más PyPI csomagnév. Friss telepítés esetén az AI-elemzés `ImportError`-ral azonnal elszállt volna. **Döntés:** `requirements.txt` javítva `google-genai>=1.0.0`-ra, a régi csomag eltávolítva.
- **Megelőzés:** mindkét hibához regressziós teszt készült (`tests/test_scraper.py::test_firecrawl_client_uses_the_real_v1_compatible_scrape_url`, `tests/test_analyzer.py::test_genai_package_is_installed_and_client_api_matches`), amik a valós klienskönyvtárak API-felületét ellenőrzik `MOCK_MODE`-tól függetlenül — mindkettőt igazoltan megbuktattam a hibás állapot ellen, mielőtt commitoltam a javítást.
