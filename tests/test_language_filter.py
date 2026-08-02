from tools.language_filter import (
    detect_high_level_english_requirement,
    is_listing_written_in_english,
    language_requirement_label,
    should_exclude_for_language,
)

# Élesben, valós hirdetésekben látott, HIBÁSAN ÁTMENT (nem kiszűrt) szövegek -
# ezek adták a regresszió bizonyítékát.
REAL_BAD_EXAMPLES = [
    "Tárgyalóképes szakmai angol nyelvtudás",
    "Angol felsőfok",
    "Angol anyanyelvi szint",
    "kommunikációs szintű angol nyelvtudás",
    "Magabiztos, tárgyalási szintű angol nyelvtudással",
]


def test_detects_all_real_confirmed_bad_examples():
    for text in REAL_BAD_EXAMPLES:
        assert detect_high_level_english_requirement(text) is not None, (
            f"nem ismerte fel a magas szintű angol elvárást ebben: {text!r}"
        )


def test_allows_basic_and_intermediate_english():
    """A persona.md szerint az alap-/középfokú angol elvárás RENDBEN van,
    csak a kifejezetten magas szintű a kizáró ok."""
    allowed = [
        "Angol középfok",
        "jó angoltudás előny",
        "alapfokú angol nyelvtudás",
        "Angol nyelvtudás előny",
    ]
    for text in allowed:
        assert detect_high_level_english_requirement(text) is None, (
            f"tévesen kizárta ezt, pedig alap-/középfokú: {text!r}"
        )


def test_should_exclude_for_language_matches_bad_examples():
    for text in REAL_BAD_EXAMPLES:
        assert should_exclude_for_language("IT vezető", text) is True


def test_hungarian_listing_not_flagged_as_english():
    hu_description = (
        "A Ganz Transzformátor- és Villamos Forgógépgyártó Zrt. IT projektmenedzsert "
        "keres Budapesten. Székesfehérvár környéki jelentkezőket is várnak. A pozíció "
        "célja a vállalati informatikai fejlesztési projektek végigvitele, a beszállítói "
        "kapcsolatok kezelése és a csapat szakmai irányítása."
    )
    assert is_listing_written_in_english(hu_description) is False


def test_english_listing_is_detected():
    en_description = (
        "We are looking for an experienced IT Project Manager to join our growing team "
        "in Budapest. The successful candidate will lead cross functional projects, "
        "manage vendor relationships and coordinate with international stakeholders "
        "across multiple time zones and business units."
    )
    assert is_listing_written_in_english(en_description) is True


def test_short_text_never_flagged_as_english():
    """Egy pár szavas angol CÍM ('Head of IT') még nem jelenti, hogy a teljes
    hirdetés angol nyelvű - a rövid szöveget nem szabad ez alapján kizárni."""
    assert is_listing_written_in_english("Head of IT") is False
    assert is_listing_written_in_english("") is False


def test_language_requirement_label_visible_for_excluded_case():
    label = language_requirement_label("IT vezető", "Angol felsőfok szükséges.")
    assert "⛔" in label
    assert "felsőfok" in label.lower()


def test_language_requirement_label_visible_for_allowed_case():
    label = language_requirement_label("IT vezető", "Középfokú angol nyelvtudás előny.")
    assert "✅" in label
