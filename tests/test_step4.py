"""Offline tests for step 4: cache, retry rules, and the Prefect flow."""
import time
from datetime import date, datetime, timezone

import numpy as np
import pytest
import rasterio
import requests
from affine import Affine
from rasterio.transform import from_origin

import config
from pipeline.caching import load_change, make_key, save_change
from tools.change import (
    ChangeDetectionError, ChangeResult, ChangeSummary, PeriodResult, summarize_change,
)
from tools.raster import read_bands
from tools.schemas import BBox, GeocodeResult, ImageryItem


def _result(loss=1.0) -> ChangeResult:
    delta = np.array([[-0.3, 0.0], [0.0, np.nan]], dtype=np.float32)
    classes = np.array([[-1, 0], [0, 0]], dtype=np.int8)
    summary = ChangeSummary(
        index="ndvi", threshold=0.15, before_scenes=["a"], after_scenes=["b"],
        valid_fraction=0.75, mean_change=-0.1, loss_ha=loss, gain_ha=0.0, stable_ha=2.0,
        loss_pct=33.3, gain_pct=0.0,
    )
    return ChangeResult(delta=delta, classes=classes, transform=Affine(10, 0, 5e5, 0, -10, 3.9e6),
                        crs="EPSG:32630", summary=summary)


def test_key_is_order_independent_and_sensitive():
    assert make_key("c", a=1, b=2) == make_key("c", b=2, a=1)
    assert make_key("c", a=1) != make_key("c", a=2)


def test_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    save_change("k1", _result())
    loaded = load_change("k1")
    assert loaded.summary.loss_ha == 1.0
    assert loaded.transform == Affine(10, 0, 5e5, 0, -10, 3.9e6)
    assert np.isnan(loaded.delta[1, 1]) and loaded.delta[0, 0] == pytest.approx(-0.3)


def test_incomplete_cache_is_a_miss(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    (tmp_path / "k2").mkdir()
    np.savez_compressed(tmp_path / "k2" / "delta.npz", delta=np.zeros(1), classes=np.zeros(1))
    assert load_change("k2") is None   # no summary.json -> not complete


def test_percentages_come_from_code():
    delta = np.array([-0.3, 0.3, 0.0, np.nan], dtype=np.float32)
    s = summarize_change(delta, pixel_area_ha=0.01, threshold=0.15)
    assert s["loss_pct"] == pytest.approx(100 / 3)
    assert s["gain_pct"] == pytest.approx(100 / 3)


def test_probe_reads_only_scl(tmp_path):
    from rasterio.warp import transform_bounds
    X0, Y0 = 500000.0, 3900000.0
    paths = {}
    for name, size, pixel, value, dtype in [("red", 200, 10, 1000, "uint16"), ("scl", 100, 20, 4, "uint8")]:
        paths[name] = str(tmp_path / f"{name}.tif")
        with rasterio.open(paths[name], "w", driver="GTiff", height=size, width=size, count=1, dtype=dtype,
                           crs="EPSG:32630", transform=from_origin(X0, Y0, pixel, pixel)) as dst:
            dst.write(np.full((size, size), value, dtype=dtype), 1)
    item = ImageryItem(id="f", acquired=datetime(2024, 7, 1, tzinfo=timezone.utc), cloud_cover=0, assets=paths)
    w, s, e, n = transform_bounds("EPSG:32630", "EPSG:4326", X0 + 500, Y0 - 1500, X0 + 1500, Y0 - 500)
    probe = read_bands(item, BBox(west=w, south=s, east=e, north=n), ())
    assert probe.bands == {} and set(np.unique(probe.scl)) == {4}


# ---------------- Prefect ----------------
prefect = pytest.importorskip("prefect")
from prefect import flow, task  # noqa: E402
from prefect.cache_policies import NO_CACHE  # noqa: E402
from prefect.testing.utilities import prefect_test_harness  # noqa: E402

import pipeline.flows as flows  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def prefect_harness():
    with prefect_test_harness():
        yield


def test_is_transient_walks_the_cause_chain():
    try:
        try:
            raise requests.ConnectionError("down")
        except requests.ConnectionError as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as outer:
        assert flows._is_transient(outer)
    assert not flows._is_transient(ValueError("no scene found"))


ARGS = dict(place="x", before=(date(2023, 7, 1), date(2023, 8, 31)),
            after=(date(2024, 7, 1), date(2024, 8, 31)))


def _period(value, ids):
    return PeriodResult(image=np.full((2, 2), value, dtype=np.float32), scene_ids=ids,
                        transform=Affine(10, 0, 5e5, 0, -10, 3.9e6), crs="EPSG:32630")


def _fake_geocode(place):
    return GeocodeResult(query=place, display_name="Fake", lat=35.2, lon=-3.9,
                         bbox=BBox(west=-4, south=35, east=-3.8, north=35.4))


def test_flow_uses_cache_on_second_run(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    calls = {"n": 0}

    def fake_period(bbox, period, index, max_scenes=3, min_coverage=0.9):
        calls["n"] += 1
        return _period(0.6 if period[0].year == 2023 else 0.3, [f"s{period[0].year}"])

    monkeypatch.setattr(flows, "geocode", _fake_geocode)
    monkeypatch.setattr(flows, "period_composite", fake_period)

    first = flows.change_detection_flow(**ARGS)
    second = flows.change_detection_flow(**ARGS)
    third = flows.change_detection_flow(**ARGS, threshold=0.15)   # same as the default -> same key

    assert (first.from_cache, second.from_cache, third.from_cache) == (False, True, True)
    assert calls["n"] == 2                                  # one call per period, first run only
    assert first.summary.loss_ha == pytest.approx(0.04)     # 4 px x 0.01 ha, delta = -0.3
    assert first.cache_key == second.cache_key == third.cache_key


def test_periods_run_in_parallel(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    spans = []

    def slow_period(bbox, period, index, max_scenes=3, min_coverage=0.9):
        start = time.perf_counter()
        time.sleep(0.6)
        spans.append((start, time.perf_counter()))
        return _period(0.5, ["x"])

    monkeypatch.setattr(flows, "geocode", _fake_geocode)
    monkeypatch.setattr(flows, "period_composite", slow_period)
    flows.change_detection_flow(**ARGS, use_cache=False)

    assert len(spans) == 2
    assert max(s for s, _ in spans) < min(e for _, e in spans)   # the two periods overlapped


def test_flow_fails_fast_on_bad_request(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)

    def must_not_run(*a, **k):
        raise AssertionError("no download should start for an invalid request")

    monkeypatch.setattr(flows, "geocode", must_not_run)
    monkeypatch.setattr(flows, "period_composite", must_not_run)
    with pytest.raises(ChangeDetectionError):
        flows.change_detection_flow(place="x", before=(date(2024, 7, 1), date(2024, 8, 31)),
                                    after=(date(2023, 7, 1), date(2023, 8, 31)))


@pytest.mark.parametrize("error, expected_calls", [
    (requests.ConnectionError("down"), 2),   # transient -> retried once
    (ValueError("no scene found"), 1),       # domain error -> not retried
])
def test_retry_only_on_transient_errors(error, expected_calls):
    calls = {"n": 0}

    @task(retries=1, retry_delay_seconds=0, retry_condition_fn=flows._retry_if_transient, cache_policy=NO_CACHE)
    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise error
        return "ok"

    @flow
    def run():
        return flaky(return_state=True).is_completed()   # a failed task must not crash the test

    completed = run()
    assert calls["n"] == expected_calls
    assert completed == (expected_calls == 2)
