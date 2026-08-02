# 🛠️ Job Searcher Architecture Sitemap & Diagnostic Guide

Ez a dokumentum lépésről lépésre bemutatja a **Job Searcher (`job-searcher`)** rendszer pontos felépítését, az ellenőrzési pontokat és a hibadiagnosztikai parancsokat.

---

## 0. ⚙️ Telepítés (Első Futtatás Előtt)

```bash
# 1. Repozitórium klónozása
git clone <repo-url> job-searcher
cd job-searcher

# 2. Virtuális környezet létrehozása és aktiválása
python3 -m venv .venv
source .venv/bin/activate

# 3. Függőségek telepítése
pip install -r requirements.txt

# 4. Környezeti változók beállítása
cp .env.example .env
# ...majd töltsd ki a .env-et: GEMINI_API_KEY, FIRECRAWL_API_KEY,
# TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GCP_PROJECT_ID

# 5. Tesztek futtatása (MOCK_MODE-ban, API kulcs nélkül is működik)
python3 -m pytest tests/ -v

# 6. (Opcionális) Lint futtatása kódminőség-ellenőrzéshez
pip install -r requirements-dev.txt
ruff check .
```

**Fontos:** a `systemd/job-searcher.service` és a lenti cron példa is a `.venv/bin/python3`-at
hívja, nem a rendszer Python-ját — a rendszer Python-nak nincsenek telepítve a projekt
függőségei (firecrawl-py, google-genai, python-telegram-bot stb.), így `ExecStart=/usr/bin/python3 ...`
azonnal `ModuleNotFoundError`-ral elszállna éles telepítés esetén.

---

## 1. 🏗️ Rendszerarchitektúra és Adatáramlási Térkép

```mermaid
flowchart TD
    A[Profession.hu URLs] -->|1. Scrape| B[tools/scraper.py]
    B -->|Markdown Listings| C[agents/job_search_agent.py]
    C -->|2. Local Keyword Check| D{Obvious Non-IT?}
    D -->|Yes| E[Skip Local]
    D -->|No| F[tools/analyzer.py]
    F -->|3. Read Learning Persona| G[profile/persona.md]
    F -->|4. Call Gemini AI| H{Gemini API Response}
    H -->|429/Error| I[Log Error & Fallback]
    H -->|200 OK Json| J[Score 0-100 & Summary]
    J -->|5. Filter Score >= 60| K[tools/notifier.py]
    K -->|6. Send Telegram Card| L[User Phone Telegram]
    L -->|7. Click Button| M[tools/feedback.py]
    M -->|8. Save Feedback| N[profile/feedback_history.json]
    N -->|9. Auto Sync Memory| G
```

---

## 2. 🔍 Ellenőrzési Pontok és Diagnosztikai Fájlok

| Komponens | Elsődleges Fájl | Mit Ellenőriz? | Hibajelenség / Diagnosztika |
| :--- | :--- | :--- | :--- |
| **1. Web Scraper** | [tools/scraper.py](file:///srv/projects/job-searcher/tools/scraper.py) | Profession.hu HTML kinyerés és hirdetés URL illesztés | Ha 0 hirdetést talál, a Firecrawl API vagy az URL pattern hibádzik. |
| **2. AI Elemző** | [tools/analyzer.py](file:///srv/projects/job-searcher/tools/analyzer.py) | Gemini API hívás, JSON parse, kvótakezelés | Ha 429 ResourceExhausted lép fel, az API kulcs ingyenes fiókhoz van kötve. |
| **3. Tanuló Persona** | [profile/persona.md](file:///srv/projects/job-searcher/profile/persona.md) | Célszemély profil és megtanult emberi szabályok | Az AI innen olvassa be a 20+ év tapasztalatot és a visszajelzéseidet. |
| **4. Telegram Notifier** | [tools/notifier.py](file:///srv/projects/job-searcher/tools/notifier.py) | 5-opciós interaktív gombsor és üzenetküldés | Ellenőrzi a Bot Token és Chat ID érvényességét. |
| **5. Feedback Memory** | [tools/feedback.py](file:///srv/projects/job-searcher/tools/feedback.py) | Telefonos gombkattintások rögzítése | Az elmentett gombnyomásokat automatikusan összefűzi a `persona.md`-vel. |

---

## 3. 🧪 Diagnosztikai Parancsok (Hogyan Ellenőrizd a Rendszert?)

### A. Teljes Automata Tesztszvit Futtatása (21 Unit & Integrációs Teszt)
```bash
python3 -m pytest tests/ -v
```

### B. Gyors Éles Elemzési Diagnosztika (3 Hirdetés Tesztelése Élőben)
Futtasd az alábbi parancsot a terminálban, amely pontról pontra kiírja a scraping, az AI válasz és a Telegram küldés stádiumát:
```bash
python3 -c "
import os, json
from dotenv import load_dotenv
from tools.scraper import JobScraper
from tools.analyzer import JobAnalyzer
from tools.notifier import TelegramNotifier

load_dotenv()
scraper = JobScraper(mock_mode=False)
analyzer = JobAnalyzer(mock_mode=False)
notifier = TelegramNotifier(mock_mode=False)

print('--- 1. SCRAPING ---')
jobs = scraper.scrape_jobs()[:2]
print(f'Kinyerve: {len(jobs)} állás.')

for j in jobs:
    print('\n--- 2. AI ELEMZÉS ---')
    print('Cím:', j['title'])
    res = analyzer.analyze_job(j)
    print('AI Eredmény:', res)
    
    print('\n--- 3. TELEGRAM KÜLDÉS ---')
    if res:
        sent = notifier.send_job_notification(j, res['score'], res['summary'])
        print('Telegram Küldés Sikeres:', sent)
"
```

### C. Folyamatban Lévő Rendszernaplók (Logs) Megtekintése
A rendszer minden futása részletes naplót generál a háttérben:
```bash
cat /home/bj/.gemini/antigravity-cli/brain/06306c6f-d8bc-4531-af8d-77f7daf3c29a/.system_generated/tasks/*.log | tail -n 50
```

---

## 5. 🖥️ GCP e2-micro VM (Always Free Tier) Architektúra & Üzemeltetés

A **Job Searcher (`job-searcher`)** kódalapja kifejezetten úgy lett felépítve, hogy a Google Cloud Platform ingyenes **e2-micro VM (1 vCPU, 1 GB RAM)** példányán 0 Ft költséggel, maximális stabilitással fusson.

### 🟢 Miért ideális ez az architektúra e2-micro gépre?
- **Alacsony Memória-lábnyom (~30-60 MB RAM):** A modulok nem használnak nehézsúlyú keretrendszereket. A szekvenciális pipeline futása során a memóriaigény messze 100 MB alatt marad, így a VM 1 GB RAM-ját nem lépi túl.
- **Kíméletes CPU Kredit Használat:** A hívások közötti biztonsági szünetek kímélik a burstable CPU-t, megelőzve a teljesítménykorlátozást (throttling).
- **Determinált Memóriahasználat:** A `MAX_JOBS_LIMIT` korlát garantálja,hogy a feldolgozott adatmennyiség kiszámítható marad.

### ⚙️ Ajánlott GCP e2-micro Beállítások:
1. **Ütemezett cron indítás (0 MB RAM passzív állapotban):** Ne fusson folyamatos daemonként. Állíts be napi 1-2 cron lefutást:
   ```bash
   0 8,17 * * * cd /srv/projects/job-searcher && .venv/bin/python3 main.py >> /var/log/job-searcher.log 2>&1
   ```
2. **4 GB SWAP Konfiguráció (Maximális OOM és Stabilitási Védelem):**
   ```bash
   sudo fallocate -l 4G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   ```
3. **Log Forgatás (Lemezterület védelme):** Állíts be `logrotate`-et vagy journalctl max méretet.
4. **Firestore Free Quota:** A napi mentések és ellenőrzések tökéletesen beleférnek a napi 50,000 ingyenes olvasási és 20,000 írási limitbe.

> **Megjegyzés (2026-08):** a ténylegesen élesített architektúra ehelyett **Cloud Run Jobs + Cloud Scheduler** lett (nem e2-micro VM) — lásd `cloudbuild.yaml`. Ugyanazok az elvek (alacsony memória, determinisztikus futásidő) itt is érvényesek, csak a hosztolás Cloud Run Jobs-on történik, ami push-onként automatikusan újratelepül.

---

## 6. 🤖 Szöveges Tanítás Bot (Cloud Run Service, Webhook)

A `bot_service.py` a Telegram-gombnyomások mellett **szabad szöveges tanítást** is kezel (pl. "miért nem releváns ez az állás?" válasz elmentése a tanult preferenciákba). Ez **külön, folyamatosan futó szolgáltatás**, nem a `main.py` batch pipeline része — ezért külön Dockerfile-lal (`Dockerfile.bot`) és külön Cloud Run **Service**-ként (nem Job-ként) települ.

**Fontos**: Cloud Run csak a saját portjára (`$PORT`) irányított HTTP-kéréseket tud kézbesíteni — egy `run_polling()`-ot futtató folyamat soha nem kapná meg a Telegram-frissítéseket ott. A `bot_service.py` ezért automatikusan **webhook módra vált**, ha a `WEBHOOK_URL` környezeti változó be van állítva (helyi fejlesztéshez üresen hagyva `run_polling()`-ra esik vissza).

### Telepítés (egyszeri):
```bash
# 1. Image build + push
gcloud builds submit --tag europe-west1-docker.pkg.dev/job-searcher-503608/job-searcher/job-searcher-bot -f Dockerfile.bot .

# 2. Cloud Run Service létrehozása (min-instances=0: csak bejövő üzenetnél fut, gyakorlatilag ingyenes)
gcloud run deploy job-searcher-bot \
  --image=europe-west1-docker.pkg.dev/job-searcher-503608/job-searcher/job-searcher-bot \
  --region=europe-west1 --min-instances=0 --max-instances=1 --allow-unauthenticated \
  --set-secrets=TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest \
  --set-env-vars=WEBHOOK_URL=PLACEHOLDER  # a valós URL csak a deploy UTÁN ismert, lásd 3. lépés

# 3. WEBHOOK_URL frissítése a most kapott valós Service URL-re, majd újra-deploy
gcloud run services update job-searcher-bot --region=europe-west1 \
  --set-env-vars=WEBHOOK_URL=$(gcloud run services describe job-searcher-bot --region=europe-west1 --format='value(status.url)')
```

---

## 7. 💳 Gemini költség: AI Studio vs. Vertex AI

A rendszer kétféleképpen érheti el a Gemini modellt, és ez **közvetlenül számít a
költségek szempontjából**:

| Út | Hitelesítés | Fedezi a GCP $300-as ingyenes kerete? |
| :--- | :--- | :--- |
| **AI Studio** (alapértelmezés) | `GEMINI_API_KEY` | ❌ **Nem.** A Google dokumentációja kimondja: *„The $300 credit can't pay for Gemini API in AI Studio costs."* |
| **Vertex AI** (`GEMINI_USE_VERTEX=true`) | ADC / szolgáltatásfiók | ✅ **Igen**, sima GCP-szolgáltatásként számlázódik |

### Mikor melyiket?

- **AI Studio ingyenes szintje** (számlázás nélküli projektben létrehozott kulcs):
  örökre ingyenes, de napi kéréslimit van rajta. Napi 2-3 futáshoz elég.
- **AI Studio előre fizetett kredittel**: ha elfogy a kredit, a rendszer
  `429 RESOURCE_EXHAUSTED / "Your prepayment credits are depleted"` hibát kap,
  és **egyetlen hirdetést sem tud kiértékelni**. Ilyenkor a bot explicit
  Telegram-riasztást küld (lásd `agents/job_search_agent.py`).
- **Vertex AI**: a GCP-keretből fedezhető, nincs napi kéréslimit, és nem kell
  API-kulcsot kezelni (Cloud Runon a szolgáltatásfiók hitelesít).

### Vertex AI bekapcsolása

```bash
# 1. API engedélyezése a projektben (egyszeri)
gcloud services enable aiplatform.googleapis.com --project=job-searcher-503608

# 2. Helyi futtatáshoz: alapértelmezett hitelesítő adatok
gcloud auth application-default login

# 3. .env
GEMINI_USE_VERTEX=true
GCP_PROJECT_ID=job-searcher-503608
GCP_LOCATION=europe-west1
# GEMINI_API_KEY ilyenkor nem szükséges

# 4. Cloud Runon a Job szolgáltatásfiókjának jogosultság kell:
gcloud projects add-iam-policy-binding job-searcher-503608 \
  --member="serviceAccount:<SZOLGALTATASFIOK>" \
  --role="roles/aiplatform.user"
```

### Nagyságrendi költség (Vertex AI, Gemini 2.5 Flash)

Árak: **$0,30 / 1M bemeneti token**, **$2,50 / 1M kimeneti token**.
Kb. 58 hirdetés/futás, ~1500 bemeneti + ~200 kimeneti token hirdetésenként:

| Futási gyakoriság | Napi költség | Havi költség |
| :--- | :--- | :--- |
| Napi 2× | ~$0,11 | ~$3 |
| Óránként | ~$1,30 | ~$40 |

> A becslés a fenti token-feltételezésen alapul, nem mért adat — az első
> néhány valós futás után érdemes a tényleges számlázáshoz igazítani.
