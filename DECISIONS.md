# Fejlesztési Döntések Logja (DECISIONS.md)

Ez a fájl tartalmazza azokat az interim döntéseket, amelyeket az fejlesztés során hoztunk az egyértelműség és a konzervatív működés érdekében.

## 1. MOCK_MODE alapértelmezett működés
- **Kérdés:** Hogyan kezelje a rendszer a tesztelést külső API kulcsok hiányában?
- **Döntés:** Ha a `MOCK_MODE=true` be van állítva, az összes modul (`scraper`, `analyzer`, `storage`, `notifier`) a `tests/fixtures/` könyvtárban található tesztadatokból olvas és nem indít valódi hálózati kéréseket.

## 2. Hard Limits és Rate Limits
- **Scraper:** Szigorú 100 hirdetés/futás korlát bevezetése kódszinten.
- **Analyzer:** Gemini API hívások esetén max 10 kérés/perc betartása, 3 kísérletig terjedő exponenciális retry logikával.
- **Firecrawl:** Kizárólag sima markdown kimenet kérése (JSON extraction mód elkerülése az 1 kredit/oldal arány megőrzéséhez).
