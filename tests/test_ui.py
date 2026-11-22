"""Offline tests for the UI helpers (no Streamlit server needed)."""
import pytest

from app import components as ui
from app.brand import BRAND_NAME
from app.i18n import TEXTS
from app.report_view import split_report
from app.styles import CSS

REPORT_EN = """**Al Hoceima: vegetation greenness (NDVI), summer 2023 → summer 2024**

- Mean change: -0.001 (changes below ±0.15 are treated as noise).
- Loss: 49.2 ha (1.3% of the analysed land). Gain: 28.4 ha (0.7%).
- Net balance: no significant change (gain minus loss: -0.5 percentage points).
- Analysed area: 38% of the zone (sea and clouds excluded), from 3 + 3 Sentinel-2 scenes.
- Rainfall in the 12 months before: 172 mm, then 248 mm (+44%).
- Limits: only two periods are compared; climate data comes from a coarse grid (about 25 km); the ±0.15 threshold is a choice.

Vegetation stayed stable despite more rain."""

REPORT_FR = """**Al Hoceima : verdure de la végétation (NDVI), été 2023 → été 2024**

- Changement moyen : -0.001 (les variations inférieures à ±0.15 sont considérées comme du bruit).
- Perte : 49.2 ha (1.3% des terres analysées). Gain : 28.4 ha (0.7%).
- Limites : seulement deux périodes comparées ; données climatiques sur une grille grossière (environ 25 km) ; le seuil de ±0.15 est un choix.

La végétation est restée stable."""


def test_split_report_english():
    parts = split_report(REPORT_EN)
    assert parts["title"].startswith("Al Hoceima: vegetation greenness")
    assert len(parts["findings"]) == 5 and parts["findings"][0].startswith("- **Mean change**: -0.001")
    assert parts["limits"] == ["Only two periods are compared", "Climate data comes from a coarse grid (about 25 km)",
                               "The ±0.15 threshold is a choice"]
    assert parts["interpretation"] == "Vegetation stayed stable despite more rain."


def test_split_report_french():
    parts = split_report(REPORT_FR)
    assert parts["findings"][0].startswith("- **Changement moyen**")
    assert len(parts["limits"]) == 3 and parts["interpretation"] == "La végétation est restée stable."


def test_split_report_returns_none_for_messages_without_findings():
    assert split_report("To run the analysis I still need: which season.") is None
    assert split_report("Sorry, I could not complete this analysis: boom") is None


def test_stepper_marks_done_active_and_pending():
    html = ui.stepper("en", ["parse"])
    assert html.count("rg-step done") == 1 and html.count("rg-step active") == 1 and html.count("rg-step pending") == 3
    assert "Understand" in html and "Analyse imagery" in html


def test_stepper_when_the_run_is_over_nothing_pulses():
    assert "active" not in ui.stepper("en", ["parse", "clarify"], running=False).replace("rg-stepper", "")
    assert "rg-step failed" in ui.stepper("en", ["parse", "plan", "error"], failed=True, running=False)


def test_user_and_llm_text_is_escaped():
    assert "<script>" not in ui.stepper("en", [], note="<script>alert(1)</script>")
    assert "<script>" not in ui.insight("<script>alert(1)</script>")
    assert "<b>" not in ui.limits_list(["<b>bold</b>"])
    assert "<img" not in ui.report_title("<img src=x onerror=alert(1)>")


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_every_component_renders_in_both_languages(lang):
    outputs = [
        ui.brand_header(lang), ui.hero(lang), ui.legend(lang),
        ui.footer_chips(lang, "llm", 63.7), ui.footer_chips(lang, "rules", None), ui.status_chips(lang, "m", False),
        ui.stepper(lang, ["parse", "plan"]), ui.section_title(TEXTS[lang]["section_findings"]),
    ]
    assert all(outputs) and BRAND_NAME in outputs[0]
    assert outputs[1].count("rg-tile ") == 3


def test_html_snippets_have_no_indented_lines():
    """Indented lines would be rendered as a Markdown code block."""
    for html in (ui.brand_header("en"), ui.hero("en"), ui.stepper("en", []), ui.legend("en")):
        assert "\n" not in html


def test_css_uses_the_requested_palette_and_key_hooks():
    for token in ("#0B1220", "#172338", "#14B8A6", "#22C55E", "#EF4444", "#E5E7EB", "#94A3B8",
                  'data-testid="stMetric"', 'data-testid="stChatInput"', 'st-key-report_', 'st-key-map_card_'):
        assert token in CSS
