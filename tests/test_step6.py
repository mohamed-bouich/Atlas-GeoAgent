"""Offline tests for step 6: map helpers, translations, agent language, and the Streamlit app
(driven with Streamlit's AppTest and a fake agent: no Ollama, no internet)."""
from pathlib import Path

import numpy as np
import pytest
from affine import Affine

import agent.graph as graph
import agent.parser as parser
import agent.writer as writer
import config
import streamlit_folium
from app.brand import BRAND_NAME
from app.i18n import TEXTS
from app.viz import bounds_latlon, change_rgba, make_map
from pipeline.caching import save_change
from pipeline.flows import ChangeRun
from tools.change import ChangeResult, ChangeSummary
from tools.climate import ClimateSummary

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")
FULL = dict(place="Al Hoceima", index="ndvi", season="summer", before_year=2023, after_year=2024)
TRANSFORM = Affine(10, 0, 500000, 0, -10, 3900000)   # UTM 30N, near Al Hoceima


def _summary():
    return ChangeSummary(
        index="ndvi", threshold=0.15, before_scenes=["a", "b", "c"], after_scenes=["d", "e", "f"],
        valid_fraction=0.3847, mean_change=-0.00065, loss_ha=49.16, gain_ha=28.37, stable_ha=3834.72,
        loss_pct=1.2566, gain_pct=0.7252,
    )


def _result() -> ChangeResult:
    delta = np.random.default_rng(1).normal(0, 0.2, (40, 50)).astype(np.float32)
    delta[:5] = np.nan
    return ChangeResult(delta=delta, classes=np.zeros(delta.shape, dtype=np.int8), transform=TRANSFORM,
                        crs="EPSG:32630", summary=_summary())


# ---------------- map helpers ----------------

def test_overlay_shows_only_meaningful_change_red_loss_green_gain():
    delta = np.array([[-0.5, 0.5], [np.nan, 0.05]], dtype=np.float32)
    rgba = change_rgba(delta, threshold=0.15)
    assert rgba[0, 0, 0] > rgba[0, 0, 1] and rgba[0, 0, 3] > 0      # loss: red
    assert rgba[0, 1, 1] > rgba[0, 1, 0] and rgba[0, 1, 3] > 0      # gain: green
    assert rgba[1, 0, 3] == 0 and rgba[1, 1, 3] == 0                # not analysed / below threshold


def test_overlay_matches_the_reported_hectares():
    """The map must colour exactly the pixels counted as loss and gain in the summary."""
    from tools.change import classify_change
    delta = _result().delta
    rgba = change_rgba(delta, 0.15)
    classes = classify_change(delta, 0.15)
    assert ((rgba[..., 3] > 0) == (classes != 0)).all()


def test_bounds_are_near_al_hoceima():
    west, south, east, north = bounds_latlon(TRANSFORM, (100, 100), "EPSG:32630")
    assert 35.0 < south < north < 35.5 and -3.2 < west < east < -2.8


def test_make_map_has_the_overlay():
    html = make_map(_result()).get_root().render()
    assert "imageOverlay" in html and "Satellite" in html and "Dark" in html


# ---------------- translations ----------------

def test_english_and_french_have_the_same_keys():
    assert set(TEXTS["en"]) == set(TEXTS["fr"])
    assert len(TEXTS["en"]["examples"]) == len(TEXTS["fr"]["examples"])


def test_every_agent_step_has_a_label_in_both_languages():
    for node in graph.STEP_LABELS:
        for lang in ("en", "fr"):
            assert f"step_{node}" in TEXTS[lang]


# ---------------- the agent answers in the requested language ----------------

def _fake_agent_tools(monkeypatch):
    run = ChangeRun(place="Fake", cache_key="k", from_cache=False, summary=_summary())
    mk = lambda mm: ClimateSummary(start="x", end="y", days_with_data=365, mean_temp_c=19.0, total_precip_mm=mm, rainy_days=40)
    geo = type("G", (), {"lat": 35.2449, "lon": -3.9313})()
    monkeypatch.setattr(parser, "chat_json", lambda *a, **k: {**FULL})
    monkeypatch.setattr(graph, "change_detection_flow", lambda **k: run)
    monkeypatch.setattr(graph, "geocode", lambda place: geo)
    monkeypatch.setattr(graph, "get_climate", lambda *a, **k: mk(172.1) if a[3].year == 2023 else mk(247.7))
    monkeypatch.setattr(writer, "chat_text", lambda *a, **k: "La verdure estivale dépend peut-être de l'irrigation.")


def test_french_report_and_french_clarification(monkeypatch):
    _fake_agent_tools(monkeypatch)
    state = graph.run_agent("q", lang="fr")
    assert "Limites" in state["answer"] and "été 2023" in state["answer"] and state["source"] == "llm"

    monkeypatch.setattr(parser, "chat_json", lambda *a, **k: {"place": "Al Hoceima"})
    assert "il me manque" in graph.run_agent("q", lang="fr")["answer"]
    assert "I still need" in graph.run_agent("q", lang="en")["answer"]


def test_the_language_of_one_question_does_not_leak_into_the_next(monkeypatch):
    _fake_agent_tools(monkeypatch)
    monkeypatch.setattr(writer, "chat_text", lambda *a, **k: "Greenness may depend on irrigation.")
    graph.run_agent("q", lang="fr")
    assert "Limits:" in graph.run_agent("q", lang="en")["answer"]


# ---------------- the Streamlit app ----------------

def _fake_run_agent(seen, answer="**Al Hoceima** report text", fail=False):
    def run(question, on_step=None, lang=None):
        seen.append((question, lang))
        if fail:
            raise RuntimeError("boom")
        for node in ("parse", "plan", "change", "climate", "write"):
            on_step(node, {})
        facts = {"index": "ndvi", "mean_change": -0.001, "threshold": 0.15, "loss_ha": 49.2, "loss_pct": 1.3,
                 "gain_ha": 28.4, "gain_pct": 0.7, "net_pct": -0.5, "verdict": "stable",
                 "rain_change_pct": 44, "rain_before_mm": 172, "rain_after_mm": 248}
        return {"answer": answer, "facts": facts, "source": "llm",
                "run": ChangeRun(place="Fake", cache_key="k", from_cache=False, summary=_summary())}
    return run


@pytest.fixture
def app(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    save_change("k", _result())
    maps = []
    monkeypatch.setattr(streamlit_folium, "st_folium", lambda fmap, **kw: maps.append(fmap))
    seen = []
    monkeypatch.setattr(graph, "run_agent", _fake_run_agent(seen))
    test = AppTest.from_file(APP, default_timeout=60)
    test.seen, test.maps = seen, maps
    return test


def _all_markdown(app) -> str:
    return " ".join(m.value for m in app.markdown)


def test_app_starts_with_brand_and_hero_then_switches_to_french(app):
    app.run()
    assert not app.exception
    text = _all_markdown(app)
    assert BRAND_NAME in text and "Ask about the land" in text
    app.sidebar.radio[0].set_value("Français").run()
    assert "Interrogez le territoire" in _all_markdown(app)


def test_app_answers_a_question_with_report_metrics_and_map(app):
    app.run()
    app.chat_input[0].set_value("How did vegetation change?").run()
    assert not app.exception
    assert app.seen == [("How did vegetation change?", "en")]
    texts = [m.value for m in app.markdown]
    assert any("report text" in v for v in texts)
    assert [m.label for m in app.metric] == ["Mean NDVI change", "Loss", "Gain", "Net balance", "Rainfall change"]
    assert len(app.maps) >= 1
    assert "Ask about the land" not in _all_markdown(app)       # the hero disappears once a question is asked
    assert "rg-stepper" in _all_markdown(app)                    # the progress stepper is shown


def test_app_passes_the_selected_language_to_the_agent(app):
    app.run()
    app.sidebar.radio[0].set_value("Français").run()
    app.chat_input[0].set_value("Comment la végétation a-t-elle évolué ?").run()
    assert app.seen[-1][1] == "fr"
    assert [m.label for m in app.metric][:2] == ["Variation moyenne NDVI", "Perte"]


def test_example_button_asks_the_example_question(app):
    app.run()
    app.sidebar.button[0].click().run()
    assert app.seen and app.seen[0][0] == TEXTS["en"]["examples"][0]


def test_app_shows_an_error_instead_of_crashing(app, monkeypatch):
    monkeypatch.setattr(graph, "run_agent", _fake_run_agent(app.seen, fail=True))
    app.run()
    app.chat_input[0].set_value("q").run()
    assert not app.exception and any("boom" in e.value for e in app.error)


def test_app_shows_the_report_as_structured_sections(monkeypatch, app):
    from agent.parser import ParsedRequest
    from agent.planner import make_plan
    from agent.writer import build_facts, render_template
    facts = build_facts(make_plan(ParsedRequest(**FULL)), _summary(),
                        (ClimateSummary(start="x", end="y", days_with_data=365, mean_temp_c=19.0, total_precip_mm=172.1, rainy_days=40),
                         ClimateSummary(start="x", end="y", days_with_data=365, mean_temp_c=19.0, total_precip_mm=247.7, rainy_days=40)))
    content = render_template(facts, "en") + "\n\nSummer greenness may depend on irrigation."
    monkeypatch.setattr(graph, "run_agent", _fake_run_agent(app.seen, answer=content))
    app.run()
    app.chat_input[0].set_value("q").run()
    text = _all_markdown(app)
    assert not app.exception
    for expected in ("Key findings", "Interpretation", "Limitations", "rg-insight", "Summer greenness may depend on irrigation."):
        assert expected in text
