"""Offline tests for the product polish: colours on the map, brand, export, no developer details."""
import base64
import io
import re
from pathlib import Path

import numpy as np
import pytest
from affine import Affine
from PIL import Image

import agent.graph as graph
import config
import streamlit_folium
from app import components as ui
from app.brand import BRAND_NAME, BRAND_SLUG
from app.export import export_filename, export_text
from app.i18n import TEXTS
from app.viz import make_map
from pipeline.caching import save_change
from pipeline.flows import ChangeRun
from tools.change import ChangeResult, ChangeSummary

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")


def _summary():
    return ChangeSummary(index="ndvi", threshold=0.15, before_scenes=["a"], after_scenes=["b"], valid_fraction=1.0,
                         mean_change=0.0, loss_ha=1, gain_ha=1, stable_ha=1, loss_pct=1, gain_pct=1)


def _visible_colours(result: ChangeResult) -> set[tuple]:
    """Decode the PNG that the browser receives and return its visible colours."""
    html = make_map(result).get_root().render()
    png = re.search(r"data:image/png;base64,([A-Za-z0-9+/=]+)", html).group(1)
    pixels = np.array(Image.open(io.BytesIO(base64.b64decode(png))).convert("RGBA")).reshape(-1, 4)
    return {tuple(int(v) for v in p) for p in pixels if p[3] > 100}


def test_the_browser_receives_red_for_loss_and_green_for_gain():
    """Regression: float images were rescaled by folium and showed cyan and pink."""
    delta = np.zeros((40, 50), dtype=np.float32)
    delta[5:10, 5:10] = -0.4
    delta[20:25, 20:25] = 0.4
    result = ChangeResult(delta=delta, classes=np.zeros(delta.shape, dtype=np.int8),
                          transform=Affine(10, 0, 5e5, 0, -10, 3.9e6), crs="EPSG:32630", summary=_summary())
    colours = {c[:3] for c in _visible_colours(result)}
    assert (239, 68, 68) in colours and (34, 197, 94) in colours


def test_the_brand_is_defined_once_and_used_everywhere():
    assert "Rif" not in BRAND_NAME
    assert BRAND_NAME in ui.brand_header("en") and BRAND_NAME in ui.sidebar_brand()
    assert BRAND_NAME.lower().replace(" ", "-") == BRAND_SLUG


def test_the_header_shows_no_developer_details():
    for lang in ("en", "fr"):
        header = ui.brand_header(lang)
        assert "qwen" not in header.lower() and "prefect" not in header.lower()


def test_export_adds_attribution_and_a_meaningful_file_name():
    text = export_text("**Report**", "en", "2026-11-18")
    assert text.startswith("**Report**") and "Copernicus Sentinel-2" in text and "2026-11-18" in text and BRAND_NAME in text
    assert "Copernicus Sentinel-2" in export_text("x", "fr", "2026-11-18") and "Généré par" in export_text("x", "fr", "d")
    assert export_filename({"place": "Al Hoceima", "before_year": 2023, "after_year": 2024}) == f"{BRAND_SLUG}_al-hoceima-2023-2024.md"
    assert export_filename({"place": "Tétouan", "before_year": 2022, "after_year": 2025}).endswith("tetouan-2022-2025.md")
    assert export_filename(None) == f"{BRAND_SLUG}_report.md"


def test_examples_cover_several_cities_not_only_one_place():
    for lang in ("en", "fr"):
        joined = " ".join(TEXTS[lang]["examples"])
        assert "Agadir" in joined and "Rabat" in joined


@pytest.fixture
def app(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(streamlit_folium, "st_folium", lambda fmap, **kw: None)
    delta = np.random.default_rng(1).normal(0, 0.2, (20, 20)).astype(np.float32)
    save_change("k", ChangeResult(delta=delta, classes=np.zeros(delta.shape, dtype=np.int8),
                                  transform=Affine(10, 0, 5e5, 0, -10, 3.9e6), crs="EPSG:32630", summary=_summary()))

    def run(question, on_step=None, lang=None):
        on_step("parse", {})
        facts = {"place": "Agadir", "before_year": 2023, "after_year": 2024, "index": "ndvi", "mean_change": 0.012,
                 "threshold": 0.15, "loss_ha": 53.2, "loss_pct": 0.6, "gain_ha": 159.9, "gain_pct": 1.9,
                 "net_pct": 1.3, "verdict": "increase"}
        return {"answer": "**Agadir** report", "facts": facts, "source": "rules",
                "run": ChangeRun(place="Agadir", cache_key="k", from_cache=False, summary=_summary())}

    monkeypatch.setattr(graph, "run_agent", run)
    return AppTest.from_file(APP, default_timeout=60)


def test_developer_details_are_in_the_system_expander_not_in_the_main_page(app):
    app.run()
    assert not app.exception
    main_text = " ".join(m.value for m in app.main.markdown)
    assert "Prefect" not in main_text and config.OLLAMA_MODEL not in main_text
    assert [e.label for e in app.sidebar.expander] == [TEXTS["en"]["system_title"]]
    sidebar_text = " ".join(m.value for m in app.sidebar.markdown)
    assert "Prefect" in sidebar_text and config.OLLAMA_MODEL in sidebar_text     # still available, just tucked away


def test_a_finished_answer_is_shown_for_any_place(app):
    app.run()
    app.chat_input[0].set_value("How did vegetation change around Agadir between summer 2023 and summer 2024?").run()
    assert not app.exception
    assert any("Agadir" in m.value for m in app.main.markdown)
