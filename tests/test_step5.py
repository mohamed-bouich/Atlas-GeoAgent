"""Offline tests for step 5: no Ollama, no internet, no real rasters."""
from datetime import date

import httpx
import pytest

import agent.graph as graph
import agent.llm as llm
import agent.parser as parser
import agent.writer as writer
from agent.llm import LLMError
from agent.parser import ParseError, ParsedRequest, parse_question
from agent.planner import find_problems, make_plan, season_dates, widen
from agent.writer import (
    HINTS, build_facts, check_narrative, clean_narrative, find_contradictions, hint_for, is_grounded,
    llm_view, render_template,
)
from pipeline.flows import ChangeRun
from tools.change import ChangeDetectionError, ChangeSummary
from tools.climate import ClimateSummary

TODAY = date(2026, 11, 8)
FULL = dict(place="Al Hoceima", index="ndvi", season="summer", before_year=2023, after_year=2024)


def _summary():
    return ChangeSummary(
        index="ndvi", threshold=0.15, before_scenes=["a", "b", "c"], after_scenes=["d", "e", "f"],
        valid_fraction=0.3847, mean_change=-0.00065, loss_ha=49.16, gain_ha=28.37, stable_ha=3834.72,
        loss_pct=1.2566, gain_pct=0.7252,
    )


def _climate():
    mk = lambda mm: ClimateSummary(start="x", end="y", days_with_data=365, mean_temp_c=19.0,
                                   total_precip_mm=mm, rainy_days=40)
    return mk(172.1), mk(247.7)


# ---------------- planner ----------------

def test_season_dates_including_winter_and_leap_year():
    assert season_dates("summer", 2023) == (date(2023, 6, 1), date(2023, 8, 31))
    assert season_dates("winter", 2024) == (date(2023, 12, 1), date(2024, 2, 29))


def test_find_problems():
    assert find_problems(ParsedRequest(), TODAY) == ["place", "season", "years"]
    assert find_problems(ParsedRequest(**FULL), TODAY) == []
    assert find_problems(ParsedRequest(**{**FULL, "before_year": 2017}), TODAY) == ["old_year"]
    assert find_problems(ParsedRequest(**{**FULL, "after_year": 2023}), TODAY) == ["same_year"]
    assert find_problems(ParsedRequest(**{**FULL, "after_year": 2026, "season": "winter"}), TODAY) == []
    assert find_problems(ParsedRequest(**{**FULL, "after_year": 2027}), TODAY) == ["future"]


def test_make_plan_sorts_years():
    plan = make_plan(ParsedRequest(**{**FULL, "before_year": 2024, "after_year": 2023}))
    assert (plan.before_year, plan.after_year) == (2023, 2024)


def test_widen_never_overlaps_and_never_enters_the_future():
    plan = make_plan(ParsedRequest(**{**FULL, "season": "summer", "before_year": 2025, "after_year": 2026}))
    wide = widen(plan, days=30, today=TODAY)
    assert wide.before[1] < wide.after[0]
    assert wide.after[1] < TODAY
    assert wide.before[0] < plan.before[0]


# ---------------- parser / llm ----------------

def test_parse_question_validates_model_output(monkeypatch):
    monkeypatch.setattr(parser, "chat_json", lambda *a, **k: {**FULL})
    assert parse_question("q").before_year == 2023
    monkeypatch.setattr(parser, "chat_json", lambda *a, **k: {"index": "banana"})
    with pytest.raises(ParseError):
        parse_question("q")


def test_llm_errors_are_wrapped(monkeypatch):
    class Boom:
        def chat(self, **kwargs):
            raise httpx.ConnectError("refused")

    monkeypatch.setattr(llm, "_client", lambda: Boom())
    with pytest.raises(LLMError):
        llm.chat_text("s", "u")


# ---------------- writer ----------------

def test_template_contains_the_real_numbers():
    facts = build_facts(make_plan(ParsedRequest(**FULL)), _summary(), _climate())
    text = render_template(facts, "en")
    for expected in ["49.2 ha", "28.4 ha", "1.3%", "0.7%", "38%", "-0.001", "172 mm", "248 mm", "+44%", "no significant change", "-0.5 percentage points", "Limits:"]:
        assert expected in text
    assert "été" in render_template(facts, "fr")


def test_grounding_accepts_rounding_and_rejects_invented_numbers():
    facts = build_facts(make_plan(ParsedRequest(**FULL)), _summary(), _climate())
    good = "Vegetation was stable: 49 ha lost and 28 ha gained between 2023 and 2024, while rain rose 44% from 172 mm to 248 mm over 12 months."
    assert is_grounded(good, facts) == (True, [])
    ok, bad = is_grounded("Rainfall rose by 60% and 0.02 NDVI units.", facts)
    assert not ok and set(bad) == {"60", "0.02"}


def test_report_falls_back_to_template_when_ungrounded_or_llm_down(monkeypatch):
    facts = build_facts(make_plan(ParsedRequest(**FULL)), _summary(), _climate())
    monkeypatch.setattr(writer, "chat_text", lambda *a, **k: "Loss reached 999 ha.")
    report = writer.write_report(facts, "en")
    assert not report.grounded and "999" not in report.text and "49.2 ha" in report.text
    assert report.source == "rules" and "Vegetation stayed stable despite more rain" in report.text

    def down(*a, **k):
        raise LLMError("down")

    monkeypatch.setattr(writer, "chat_text", down)
    down_report = writer.write_report(facts, "en")
    assert not down_report.grounded and "Vegetation stayed stable" in down_report.text


def test_verdict_and_rain_trend_are_computed_by_code():
    facts = build_facts(make_plan(ParsedRequest(**FULL)), _summary(), _climate())
    assert facts["verdict"] == "stable" and facts["rain_trend"] == "wetter" and facts["net_pct"] == -0.5
    big_loss = _summary().model_copy(update={"loss_pct": 6.0, "gain_pct": 1.0})
    assert build_facts(make_plan(ParsedRequest(**FULL)), big_loss, None)["verdict"] == "decline"
    assert "rain_trend" not in build_facts(make_plan(ParsedRequest(**FULL)), _summary(), None)


def test_llm_view_is_short_and_has_no_internal_keys():
    facts = build_facts(make_plan(ParsedRequest(**FULL)), _summary(), _climate())
    view = llm_view(facts)
    assert "loss_ha" not in view and "verdict" not in view and "rain_trend" not in view
    assert view["overall_result"] == "stable" and view["rainfall_change"] == "wetter (+44%)"
    assert "explanation_hint" in view and view["years"] == "2023 to 2024"


def test_every_verdict_and_rain_trend_has_a_hint_in_both_languages():
    for verdict in ("stable", "increase", "decline"):
        for trend in ("wetter", "drier", "similar", None):
            assert set(HINTS[(verdict, trend)]) == {"en", "fr"}


def test_hint_follows_the_data_not_the_model():
    increase_drier = _summary().model_copy(update={"loss_pct": 1.3, "gain_pct": 10.7})
    dry = (ClimateSummary(start="x", end="y", days_with_data=365, mean_temp_c=19.0, total_precip_mm=346.0, rainy_days=40),
           ClimateSummary(start="x", end="y", days_with_data=365, mean_temp_c=19.0, total_precip_mm=252.0, rainy_days=40))
    facts = build_facts(make_plan(ParsedRequest(**FULL)), increase_drier, dry)
    assert (facts["verdict"], facts["rain_trend"], facts["rain_change_pct"]) == ("increase", "drier", -27)
    assert "does not explain" in hint_for(facts, "en")


def test_clean_narrative_drops_a_cut_off_tail_and_limits_length():
    assert clean_narrative("Stable. Only two periods (2023 and 20") == "Stable."
    assert clean_narrative("One. Two. Three.") == "One. Two."
    assert clean_narrative("Cut off in the first senten") == ""
    assert clean_narrative("Line one.\n\nLine two.") == "Line one. Line two."


def test_leaked_field_names_are_rejected():
    facts = build_facts(make_plan(ParsedRequest(**FULL)), _summary(), _climate())
    leaked = "A possible explanation, consistent with 'verdict' and 'rain_trend' in the data, is irrigation."
    assert check_narrative(leaked, facts) == "mentions internal field names"
    assert check_narrative("", facts) == "empty or cut off"


# The exact text produced by the 7B model in the first real run. Its numbers were all
# correct, but it called a stable result "a slight overall loss" and blamed "reduced
# rainfall" although rain increased by 44%.
REAL_BAD_NARRATIVE = (
    "The NDVI in Al Hoceima decreased by 0.001 between 2023 and 2024, indicating a slight overall loss in "
    "vegetation health. This change could be due to reduced rainfall, as the precipitation increased by 44% "
    "from 172 mm to 248 mm over a 12-month window."
)


def test_real_run_contradictions_are_caught():
    facts = build_facts(make_plan(ParsedRequest(**FULL)), _summary(), _climate())
    assert is_grounded(REAL_BAD_NARRATIVE, facts)[0]            # numbers alone look fine...
    found = find_contradictions(REAL_BAD_NARRATIVE, facts)      # ...but the logic is wrong
    assert any("overall loss" in f.lower() for f in found) and any("reduced rainfall" in f.lower() for f in found)


def test_consistent_narrative_is_accepted(monkeypatch):
    facts = build_facts(make_plan(ParsedRequest(**FULL)), _summary(), _climate())
    good = ("Greenness stayed stable, possibly because summer vegetation here depends on irrigation rather "
            "than spring rain. Only two periods are compared, so this is not a trend.")
    assert find_contradictions(good, facts) == []
    monkeypatch.setattr(writer, "chat_text", lambda *a, **k: good)
    report = writer.write_report(facts, "en")
    assert report.grounded and good in report.text and report.source == "llm"
    monkeypatch.setattr(writer, "chat_text", lambda *a, **k: REAL_BAD_NARRATIVE)
    assert not writer.write_report(facts, "en").grounded


def test_counting_the_two_periods_is_not_a_hallucination():
    """Real run 2: the model wrote 'only 2 periods are compared' and was rejected by mistake."""
    facts = build_facts(make_plan(ParsedRequest(**FULL)), _summary(), _climate())
    text = "Stable greenness may reflect irrigation. Only 2 periods are compared, so this is no trend."
    assert check_narrative(text, facts) is None
    assert "ungrounded" in check_narrative("Only 7 periods and 60 ha lost.", facts)
    assert "contradicts" in check_narrative(REAL_BAD_NARRATIVE, facts)


def test_rejected_text_and_reason_are_kept(monkeypatch):
    facts = build_facts(make_plan(ParsedRequest(**FULL)), _summary(), _climate())
    monkeypatch.setattr(writer, "chat_text", lambda *a, **k: "Loss was 999 ha.")
    report = writer.write_report(facts, "en")
    assert report.rejected == "Loss was 999 ha." and "999" in report.reason


# ---------------- graph ----------------

def _install_fakes(monkeypatch, flow, narrative="Greenness was stable, with 49 ha lost and 28 ha gained."):
    monkeypatch.setattr(parser, "chat_json", lambda *a, **k: {**FULL})
    monkeypatch.setattr(graph, "change_detection_flow", flow)
    geo = type("G", (), {"lat": 35.2449, "lon": -3.9313})()
    monkeypatch.setattr(graph, "geocode", lambda place: geo)
    monkeypatch.setattr(graph, "get_climate", lambda *a, **k: _climate()[0 if a[3].year == 2023 else 1])
    monkeypatch.setattr(writer, "chat_text", lambda *a, **k: narrative)


def _ok_run():
    return ChangeRun(place="Fake", cache_key="k", from_cache=False, summary=_summary())


def test_graph_happy_path(monkeypatch):
    _install_fakes(monkeypatch, lambda **k: _ok_run())
    steps = []
    state = graph.run_agent("q", on_step=lambda node, update: steps.append(node))
    assert steps == ["parse", "plan", "change", "climate", "write"]
    assert state["grounded"] is True and state["source"] == "llm"
    assert "49.2 ha" in state["answer"] and "+44%" in state["answer"]


def test_graph_asks_for_missing_info_without_running_the_pipeline(monkeypatch):
    def must_not_run(**k):
        raise AssertionError("pipeline must not start")

    _install_fakes(monkeypatch, must_not_run)
    monkeypatch.setattr(parser, "chat_json", lambda *a, **k: {"place": "Al Hoceima"})
    steps = []
    state = graph.run_agent("q", on_step=lambda node, update: steps.append(node))
    assert steps == ["parse", "clarify"]
    assert "season" in state["answer"] and "years" in state["answer"]


def test_graph_replans_once_when_no_scene(monkeypatch):
    calls = []

    def flaky_flow(**k):
        calls.append(k["before"])
        if len(calls) == 1:
            raise ChangeDetectionError("No scene between 2023-06-01 and 2023-08-31 covers the area well enough.")
        return _ok_run()

    _install_fakes(monkeypatch, flaky_flow)
    steps = []
    state = graph.run_agent("q", on_step=lambda node, update: steps.append(node))
    assert steps == ["parse", "plan", "change", "replan", "change", "climate", "write"]
    assert calls[1][0] < calls[0][0]            # the second attempt used a wider period
    assert state["attempts"] == 1


def test_graph_stops_after_one_replan(monkeypatch):
    def always_fails(**k):
        raise ChangeDetectionError("No scene between a and b covers the area well enough.")

    _install_fakes(monkeypatch, always_fails)
    steps = []
    state = graph.run_agent("q", on_step=lambda node, update: steps.append(node))
    assert steps.count("change") == 2 and steps[-1] == "error"
    assert "Sorry" in state["answer"]


def test_graph_reports_other_errors_without_retry(monkeypatch):
    def bad(**k):
        raise ChangeDetectionError("Area is 900 km2, above the limit.")

    _install_fakes(monkeypatch, bad)
    steps = []
    state = graph.run_agent("q", on_step=lambda node, update: steps.append(node))
    assert steps == ["parse", "plan", "change", "error"]
    assert "900 km2" in state["answer"]


def test_graph_survives_llm_down_at_parse_time(monkeypatch):
    def down(*a, **k):
        raise LLMError("Local LLM unavailable")

    monkeypatch.setattr(parser, "chat_json", down)
    state = graph.run_agent("q")
    assert "Local LLM unavailable" in state["answer"]
