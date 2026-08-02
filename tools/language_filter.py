"""Determinisztikus (nem AI-alapú) nyelvi-elvárás szűrő.

Miért kell ez a Gemini-alapú ítélet MELLETT: a persona.md szövegesen már
tartalmazta a szabályt ("felsőfokú/tárgyalásképes/anyanyelvi angol =
kizáró ok"), mégis élesben, valós hirdetéseknél többször átment olyan
állás, ami ezt a szabályt sértette (pl. "Angol felsőfok", "Tárgyalóképes
szakmai angol nyelvtudás", "Angol anyanyelvi szint"). Egy csak-promptban
élő szabály nem garancia: az LLM ítélete hirdetésenként ingadozhat.

Ez a modul ugyanazt a mintát követi, mint a job_search_agent.py meglévő
helyi kulcsszavas előszűrője (pl. "tehergépkocsi", "pultos" kizárása) —
egy egyszerű, kiszámítható, mindig ugyanúgy lefutó ellenőrzés, ami a
Gemini-hívás ELŐTT kizárja a nyilvánvaló eseteket. Ez egyszerre
megbízhatóbb (nem AI-döntés) és olcsóbb (nem fogyaszt Gemini-kvótát a
biztosan kizárandó hirdetéseken).
"""

import re

# Felsőfokú/tárgyalóképes/anyanyelvi szintű angol elvárás mintái.
# Mindegyik a felhasználó által ÉLESBEN, valós hirdetésekben látott,
# átment (hibásan nem kiszűrt) szövegre illeszkedik.
_HIGH_LEVEL_ENGLISH_PATTERNS = [
    r"fels[őo]fok",                          # "Angol felsőfok", "felsőfokú angol"
    r"anyanyelv",                             # "Angol anyanyelvi szint", "anyanyelvű"
    r"t[áa]rgyal[óo]k[ée]pes",                # "Tárgyalóképes szakmai angol nyelvtudás"
    r"t[áa]rgyal[áa]si szint",                # "tárgyalási szintű angol nyelvtudással"
    r"magabiztos[^.\n]{0,30}angol",           # "Magabiztos, tárgyalási szintű angol..."
    r"kommunik[áa]ci[óo]s szint[űu][^.\n]{0,15}angol",  # "kommunikációs szintű angol nyelvtudás"
    r"fluent english",
    r"native (english|speaker)",
    r"advanced english",
    r"business[- ]level english",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _HIGH_LEVEL_ENGLISH_PATTERNS]

# Magyar ékezetes karakterek. A magyar szöveg sűrűn tartalmazza ezeket -
# valós hirdetés-mintán mérve kb. 9% (301 karakteres részlet, 27 ékezetes
# karakter). Egy hasonló hosszúságú angol szöveg 0%-ot ad. Az 1%-os küszöb
# bőséges biztonsági tartalékot hagy mindkét irányban.
_HU_ACCENTED_CHARS = set("áéíóöőúüűÁÉÍÓÖŐÚÜŰ")
_ENGLISH_DENSITY_THRESHOLD = 0.01
_ENGLISH_MIN_LENGTH = 150


def detect_high_level_english_requirement(text: str) -> str | None:
    """Visszaadja az illeszkedő szövegrészletet, ha a szöveg felsőfokú/
    tárgyalóképes/anyanyelvi szintű angolt ír elő kötelezőként.
    None, ha nincs ilyen (az alap-/középfokú angol elvárás rendben van)."""
    if not text:
        return None
    for pattern in _COMPILED_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0)
    return None


def is_listing_written_in_english(text: str) -> bool:
    """Heurisztika: a magyar szöveg szinte mindig sűrűn tartalmaz ékezetes
    karaktereket. Egy kellően hosszú szövegben ezek szinte teljes hiánya
    arra utal, hogy a hirdetés angol nyelven van írva.

    Rövid szövegre (cím) szándékosan False-t ad vissza - egy pár szavas
    angol cím ("Head of IT") még nem jelenti, hogy a teljes hirdetés
    angol nyelvű."""
    if not text or len(text) < _ENGLISH_MIN_LENGTH:
        return False
    accented_count = sum(1 for ch in text if ch in _HU_ACCENTED_CHARS)
    density = accented_count / len(text)
    return density < _ENGLISH_DENSITY_THRESHOLD


def language_requirement_label(title: str, description: str) -> str:
    """Ember-olvasható címke a Telegram-kártyához - MINDEN kiküldött
    hirdetésnél megjelenik, hogy a felhasználó láthassa, mi alapján
    döntött a szűrő (vagy miért NEM szűrt semmit)."""
    full_text = f"{title} {description}"
    match = detect_high_level_english_requirement(full_text)
    if match:
        return f"⛔ Magas szintű angol elvárás ({match.strip()}) - ez alapján ki kellett volna szűrni"
    if is_listing_written_in_english(description):
        return "⛔ A hirdetés angol nyelven van írva - ez alapján ki kellett volna szűrni"
    return "✅ Nincs magas szintű angol elvárás"


def should_exclude_for_language(title: str, description: str) -> bool:
    """A helyi előszűrő ezt hívja: True, ha a hirdetést a Gemini-hívás
    ELŐTT ki kell zárni nyelvi elvárás miatt."""
    full_text = f"{title} {description}"
    if detect_high_level_english_requirement(full_text):
        return True
    return is_listing_written_in_english(description)
