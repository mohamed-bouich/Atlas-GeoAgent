"""Offline tests: the user can set the size of the analysed area in the question."""
from datetime import date

import pytest

import agent.graph as graph
import agent.parser as parser
import agent.writer as writer
import config
from agent.parser import ParsedRequest, parse_question
from agent.planner import MAX_SIDE_KM, MIN_SIDE_KM, find_problems, half_size_from, make_plan, widen
from agent.writer import build_facts, render_template
from pipeline.flows import ChangeRun
from tools.change import ChangeSummary
from tools.climate import ClimateSummary

TODAY = date(2026, 11, 8)
FULL = dict(place="Al Hoceima", index="ndvi", season="summer", before_year=2023, after_year=2024)


def _summary():
    return ChangeSummary(
        index="ndvi", threshold=0.15, before_scenes=["a", "b", "c"], after_scenes=["d", "e", "f"],
        valid_fraction=0.3847, mean_change=-0.00065, loss_ha=49.16, gain_ha=28.37, stable_ha=3834.72,
        loss_pct=1.2566, gain_pct=0.7252,
    )


# ---------------- parser ----------------

def test_the_distance_written_by_the_user_is_kept(monkeypatch):
    data = {**FULL, "distance_km": 3, "distance_kind": "radius"}
    monkeypatch.setattr(parser, "chat_json", lambda *a, **k: data)
    request = parse_question("How did vegetation change within 3 km of Al Hoceima between summer 2023 and 2024?")
    assert (request.distance_km, request.distance_kind) == (3.0, "radius")
    # same answer from the model, but this question does not contain "3": the distance is dropped
    assert parse_question("Dans un rayon de 2,5 km autour d'Al Hoceima, été 2023 et 2024 ?").distance_km is None


def test_an_invented_distance_is_dropped(monkeypatch):
    monkeypatch.setattr(parser, "chat_json", lambda *a, **k: {**FULL, "distance_km": 7, "distance_kind": "radius"})
    request = parse_question("How did vegetation change around Al Hoceima between summer 2023 and summer 2024?")
    assert request.distance_km is None and request.distance_kind is None
    monkeypatch.setattr(parser, "chat_json", lambda *a, **k: {**FULL, "distance_km": 2.5, "distance_kind": "radius"})
    assert parse_question("Dans un rayon de 2,5 km autour d'Al Hoceima").distance_km == 2.5


# ---------------- planner ----------------

def test_radius_and_width_become_the_distance_to_each_edge():
    assert half_size_from(ParsedRequest(**FULL)) == config.DEFAULT_HALF_SIZE_KM
    assert half_size_from(ParsedRequest(**FULL, distance_km=3, distance_kind="radius")) == 3
    assert half_size_from(ParsedRequest(**FULL, distance_km=6, distance_kind="width")) == 3
    assert half_size_from(ParsedRequest(**FULL, distance_km=4)) == 4                 # no kind: treated as a radius


def test_size_limits_are_checked_before_any_download():
    ok = lambda **kw: find_problems(ParsedRequest(**FULL, **kw), TODAY)
    assert ok(distance_km=3, distance_kind="radius") == []
    assert ok(distance_km=5, distance_kind="width") == []
    assert ok(distance_km=0.2, distance_kind="radius") == ["size"]                   # 0.4 km square: too small
    assert ok(distance_km=30, distance_kind="radius") == ["size"]                    # 60 km square: too large
    assert ok(distance_km=MAX_SIDE_KM, distance_kind="width") == []
    assert ok(distance_km=MIN_SIDE_KM, distance_kind="width") == []
    assert find_problems(ParsedRequest(place="X", distance_km=500), TODAY) == ["season", "years", "size"]


def test_the_plan_keeps_its_size_when_replanned():
    plan = make_plan(ParsedRequest(**FULL, distance_km=3, distance_kind="radius"))
    assert plan.half_size_km == 3
    assert widen(plan, today=TODAY).half_size_km == 3


# ---------------- report ----------------

def test_the_report_states_the_zone_that_was_analysed():
    plan = make_plan(ParsedRequest(**FULL, distance_km=3, distance_kind="radius"))
    facts = build_facts(plan, _summary(), None)
    assert facts["zone_km"] == 6.0
    assert "Zone: 6 × 6 km square centred on Al Hoceima." in render_template(facts, "en")
    assert "carré de 6 × 6 km centré sur Al Hoceima" in render_template(facts, "fr")


# ---------------- the agent end to end ----------------

def _run_with(monkeypatch, parsed: dict, question: str, lang="en"):
    calls = []

    def fake_flow(**kwargs):
        calls.append(kwargs)
        return ChangeRun(place="Fake", cache_key="k", from_cache=False, summary=_summary())

    mk = lambda mm: ClimateSummary(start="x", end="y", days_with_data=365, mean_temp_c=19.0, total_precip_mm=mm, rainy_days=40)
    geo = type("G", (), {"lat": 35.2449, "lon": -3.9313})()
    monkeypatch.setattr(parser, "chat_json", lambda *a, **k: parsed)
    monkeypatch.setattr(graph, "change_detection_flow", fake_flow)
    monkeypatch.setattr(graph, "geocode", lambda place: geo)
    monkeypatch.setattr(graph, "get_climate", lambda *a, **k: mk(172.1) if a[3].year == 2023 else mk(247.7))
    monkeypatch.setattr(writer, "chat_text", lambda *a, **k: "Greenness may depend on irrigation.")
    return graph.run_agent(question, lang=lang), calls


def test_the_agent_passes_the_requested_size_to_the_pipeline(monkeypatch):
    state, calls = _run_with(monkeypatch, {**FULL, "distance_km": 3, "distance_kind": "radius"},
                             "How did vegetation change within 3 km of Al Hoceima, summer 2023 vs 2024?")
    assert calls[0]["half_size_km"] == 3
    assert "Zone: 6 × 6 km" in state["answer"]

    state, calls = _run_with(monkeypatch, {**FULL, "distance_km": 5, "distance_kind": "width"},
                             "How did vegetation change in a 5 km zone around Al Hoceima, summer 2023 vs 2024?")
    assert calls[0]["half_size_km"] == 2.5
    assert "Zone: 5 × 5 km" in state["answer"]


def test_without_a_size_the_default_is_used(monkeypatch):
    state, calls = _run_with(monkeypatch, {**FULL}, "How did vegetation change around Al Hoceima?")
    assert calls[0]["half_size_km"] == config.DEFAULT_HALF_SIZE_KM


def test_a_size_out_of_range_is_a_clarification_not_a_crash(monkeypatch):
    state, calls = _run_with(monkeypatch, {**FULL, "distance_km": 40, "distance_kind": "radius"},
                             "How did vegetation change within 40 km of Al Hoceima, summer 2023 vs 2024?")
    assert calls == [] and "an area size between 1 and 20 km" in state["answer"]
    state, calls = _run_with(monkeypatch, {**FULL, "distance_km": 40, "distance_kind": "radius"},
                             "Dans un rayon de 40 km autour d'Al Hoceima, été 2023 et 2024 ?", lang="fr")
    assert "une taille de zone entre 1 et 20 km" in state["answer"]
