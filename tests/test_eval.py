"""Offline tests for the evaluation tools (step 7). No Ollama, no internet."""
from collections import Counter
from datetime import date

import numpy as np
import pytest
from affine import Affine
from rasterio.warp import transform_bounds

from agent.llm import LLMError
from agent.parser import ParseError, ParsedRequest
from eval import events, synthetic, threshold_sweep
from eval.baseline_parser import baseline_parse
from eval.parsing_benchmark import evaluate, score_fields, to_markdown
from eval.questions import QUESTIONS
from tools.change import ChangeResult, ChangeSummary, summarize_change

TODAY = date(2026, 11, 18)


# ---------------- the question set ----------------

def test_question_set_is_balanced_and_unique():
    assert len(QUESTIONS) == 47
    assert len({q["question"] for q in QUESTIONS}) == 47
    assert Counter(q["kind"] for q in QUESTIONS) == {"complete": 35, "missing": 8, "invalid": 4}
    assert sum(q["hard"] for q in QUESTIONS) == 9
    assert {q["lang"] for q in QUESTIONS} == {"en", "fr"}
    assert sum(1 for q in QUESTIONS if q["lang"] == "fr") >= 12
    assert {q["expected"]["index"] for q in QUESTIONS} == {"ndvi", "nbr", "ndwi"}


def _oracle(question: str) -> ParsedRequest:
    """A perfect parser: builds the request from the labels. If my labels contradict the planner's rules,
    this test fails, so it checks the labels themselves."""
    e = next(q for q in QUESTIONS if q["question"] == question)["expected"]
    years = e["years"] or (None, None)
    return ParsedRequest(place=e["place"], index=e["index"], season=e["season"], before_year=years[0], after_year=years[1],
                         distance_km=e["distance_km"], distance_kind=e["distance_kind"])


def test_the_labels_agree_with_the_planner_rules():
    result = evaluate(_oracle, today=TODAY)
    assert result["exact_match"] == 1.0 and result["problem_accuracy"] == 1.0
    assert result["failures"] == []


# ---------------- scoring ----------------

def test_score_fields_is_strict_but_ignores_accents_and_case():
    expected = {"place": "Fès", "season": "summer", "years": (2023, 2024), "index": "ndvi", "distance_km": None, "distance_kind": None}
    ok = ParsedRequest(place="fes", season="summer", before_year=2024, after_year=2023)       # years in any order
    assert all(score_fields(expected, ok).values())
    wrong = ParsedRequest(place="lake near Fes", season="winter", before_year=2023, after_year=2024, distance_km=3)
    scores = score_fields(expected, wrong)
    assert not scores["place"] and not scores["season"] and not scores["distance"] and scores["years"]
    assert not any(score_fields(expected, None).values())


def test_a_model_error_counts_as_a_failure_not_a_crash():
    def broken(question):
        raise ParseError("bad json")

    result = evaluate(broken, today=TODAY)
    assert result["errors"] == 47 and result["exact_match"] == 0.0 and result["problem_accuracy"] == 0.0

    def down(question):
        raise LLMError("ollama down")

    assert evaluate(down, QUESTIONS[:3], today=TODAY)["errors"] == 3


def test_the_markdown_table_compares_parsers():
    table = to_markdown({"Baseline": evaluate(baseline_parse, today=TODAY), "Oracle": evaluate(_oracle, today=TODAY)})
    assert "| Metric | Baseline | Oracle |" in table and "**Exact match (all fields)**" in table and "free phrasing (hard)" in table
    assert "| **Correct decision, all questions** |" in table


# ---------------- the regex baseline ----------------

def test_baseline_parser_reads_simple_questions_in_both_languages():
    en = baseline_parse("How did vegetation change around Al Hoceima between summer 2023 and summer 2024?")
    assert (en.place, en.season, en.before_year, en.after_year, en.index) == ("Al Hoceima", "summer", 2023, 2024, "ndvi")
    fr = baseline_parse("Comment la végétation a-t-elle évolué autour d'Agadir entre l'été 2023 et l'été 2024 ?")
    assert (fr.place, fr.season) == ("Agadir", "summer")
    assert baseline_parse("Wildfire damage near Oujda, summer 2022 compared to summer 2024.").index == "nbr"
    assert baseline_parse("Did the lakes around Ifrane gain water between spring 2023 and spring 2025?").index == "ndwi"


def test_baseline_parser_distances():
    assert baseline_parse("Dans un rayon de 2,5 km autour de Tétouan, été 2022 et été 2024.").distance_km == 2.5
    zone = baseline_parse("Analyse a 5 km zone around Nador, spring 2023 vs spring 2024.")
    assert (zone.distance_km, zone.distance_kind) == (5.0, "width")


def test_baseline_has_a_fair_score_but_not_a_perfect_one():
    """Sanity check of the benchmark itself: the baseline must be neither a strawman nor perfect."""
    result = evaluate(baseline_parse, today=TODAY)
    assert result["field_accuracy"]["years"] >= 0.9 and result["field_accuracy"]["season"] >= 0.9
    assert 0.5 <= result["exact_match"] < 0.95
    assert result["exact_match_hard"] <= 0.5      # free phrasing is where a regex parser breaks


# ---------------- threshold sweep ----------------

def test_a_higher_threshold_never_flags_more_area():
    delta = np.random.default_rng(0).normal(0, 0.15, (80, 90)).astype(np.float32)
    rows = threshold_sweep.sweep(delta, 0.01)
    losses = [r["loss_ha"] for r in rows]
    gains = [r["gain_ha"] for r in rows]
    assert losses == sorted(losses, reverse=True) and gains == sorted(gains, reverse=True)
    middle = next(r for r in rows if r["threshold"] == 0.15)
    assert middle["loss_ha"] == round(summarize_change(delta, 0.01, 0.15)["loss_ha"], 1)


def test_threshold_table_marks_the_default():
    rows = threshold_sweep.sweep(np.zeros((10, 10), dtype=np.float32), 0.01)
    assert "±0.15 (default)" in threshold_sweep.to_markdown("t", rows, 0.15)


# ---------------- synthetic experiment ----------------

def test_the_median_of_three_scenes_cuts_false_positives():
    single = synthetic.run_trial(0.3, 0.06, 1, seed=1)
    median = synthetic.run_trial(0.3, 0.06, 3, seed=1)
    assert median["false_positive_rate"] < single["false_positive_rate"] / 3
    assert median["precision"] > single["precision"]


def test_large_changes_are_found_and_changes_below_the_threshold_are_not():
    large = synthetic.run_trial(0.5, 0.03, 3, seed=2)
    assert large["recall"] > 0.95 and large["false_positive_rate"] < 0.02
    below = synthetic.run_trial(0.10, 0.03, 3, seed=2)
    assert below["recall"] < 0.2          # by design: the threshold is the smallest change we claim to see


def test_the_experiment_is_reproducible():
    assert synthetic.run_trial(0.2, 0.06, 3, seed=5) == synthetic.run_trial(0.2, 0.06, 3, seed=5)


# ---------------- real-event check ----------------

def _result_with_a_loss_patch() -> ChangeResult:
    delta = np.zeros((100, 100), dtype=np.float32)
    delta[10:30, 10:30] = -0.4                                    # the "event"
    summary = ChangeSummary(index="ndvi", threshold=0.15, before_scenes=["a"], after_scenes=["b"], valid_fraction=1.0,
                            mean_change=0.0, loss_ha=1, gain_ha=0, stable_ha=1, loss_pct=1, gain_pct=0)
    return ChangeResult(delta=delta, classes=np.zeros(delta.shape, dtype=np.int8),
                        transform=Affine(10, 0, 500000, 0, -10, 3900000), crs="EPSG:32630", summary=summary)


def _box(x0, y0, x1, y1):
    """lon/lat box from pixel coordinates of the test raster (10 m pixels, origin 500000, 3900000)."""
    return transform_bounds("EPSG:32630", "EPSG:4326", 500000 + x0 * 10, 3900000 - y1 * 10, 500000 + x1 * 10, 3900000 - y0 * 10)


def test_box_stats_and_judgement():
    result = _result_with_a_loss_patch()
    affected = events.box_stats(result, _box(12, 12, 28, 28))
    control = events.box_stats(result, _box(60, 60, 90, 90))
    assert affected["share_loss"] == pytest.approx(1.0, abs=0.05) and affected["mean_delta"] < -0.35
    assert control["share_loss"] == 0.0
    assert events.judge("loss", affected, control)[0] is True
    assert events.judge("gain", affected, control)[0] is False                 # wrong direction
    assert events.judge("loss", control, affected)[0] is False                 # boxes swapped
    assert events.judge("loss", None, control)[0] is False


def test_a_box_outside_the_zone_is_reported_not_crashed():
    assert events.box_stats(_result_with_a_loss_patch(), (10.0, 10.0, 10.1, 10.1)) is None


def test_event_runner_uses_the_pipeline_result(tmp_path, monkeypatch):
    import config
    from pipeline.caching import save_change
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    save_change("k", _result_with_a_loss_patch())
    run = type("Run", (), {"cache_key": "k", "from_cache": True})()
    event = {**events.EXAMPLE_EVENT, "name": "patch", "affected_box": _box(12, 12, 28, 28), "control_box": _box(60, 60, 90, 90)}
    row = events.evaluate_event(event, run_flow=lambda **kw: run)
    assert row["passed"] and "PASS" in events.to_markdown([row])


# ---------------- threshold sweep: readable labels, no duplicates ----------------

def test_sweep_labels_tell_analyses_apart_and_duplicates_are_skipped(tmp_path, monkeypatch):
    import config
    from pipeline.caching import save_change

    def entry(scenes_after, side_px):
        delta = np.random.default_rng(0).normal(0, 0.1, (side_px, side_px)).astype(np.float32)
        summary = ChangeSummary(index="ndvi", threshold=0.15, before_scenes=["S2B_30SVE_20230811_0_L2A"],
                                after_scenes=[scenes_after], valid_fraction=1.0, mean_change=0.0, loss_ha=1, gain_ha=1,
                                stable_ha=1, loss_pct=1, gain_pct=1)
        return ChangeResult(delta=delta, classes=np.zeros(delta.shape, dtype=np.int8),
                            transform=Affine(10, 0, 500000, 0, -10, 3900000), crs="EPSG:32630", summary=summary)

    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(threshold_sweep, "RESULTS_DIR", tmp_path / "results")
    a = entry("S2B_30SVE_20240726_0_L2A", 500)          # 5 km zone
    save_change("aaaaaa111111", a)
    save_change("bbbbbb222222", a)                       # same analysis cached under another key
    save_change("cccccc333333", entry("S2B_30SVE_20240726_0_L2A", 1000))   # 10 km zone
    threshold_sweep.main([])
    text = (tmp_path / "results" / "threshold_sweep.md").read_text(encoding="utf-8")
    assert text.count("**NDVI") == 2                     # the duplicate is gone
    assert "zone 5 x 5 km" in text and "zone 10 x 10 km" in text and "lat 35." in text
