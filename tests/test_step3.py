"""Offline tests for step 3 (no internet, no real rasters)."""
from datetime import date, datetime, timezone

import numpy as np
import pytest
from affine import Affine

import tools.change as change
from tools.change import (
    ChangeDetectionError, classify_change, detect_change, median_composite, summarize_change,
)
from tools.indices import compute_index, water_mask
from tools.raster import BandStack
from tools.schemas import BBox, ImageryItem, SearchImageryResult


def test_nbr_and_ndwi_use_the_right_bands():
    refl = {k: np.array([v], dtype=np.float32) for k, v in
            dict(nir=0.4, red=0.1, swir22=0.2, green=0.3).items()}
    assert compute_index("nbr", refl)[0] == pytest.approx((0.4 - 0.2) / (0.4 + 0.2))
    assert compute_index("ndwi", refl)[0] == pytest.approx((0.3 - 0.4) / (0.3 + 0.4))


def test_unknown_index_raises():
    with pytest.raises(ValueError):
        compute_index("foo", {})


def test_water_mask():
    assert water_mask(np.array([6, 4], dtype=np.uint8)).tolist() == [True, False]


def test_median_composite_ignores_nan():
    layers = [np.array([1, np.nan]), np.array([3, 5]), np.array([5, np.nan])]
    assert median_composite(layers).tolist() == [3.0, 5.0]


def test_classify_change():
    delta = np.array([-0.3, 0.3, 0.0, np.nan])
    assert classify_change(delta, 0.15).tolist() == [-1, 1, 0, 0]


def test_summarize_change_areas():
    delta = np.array([[-0.3, 0.3], [0.0, np.nan]], dtype=np.float32)
    s = summarize_change(delta, pixel_area_ha=0.01, threshold=0.15)
    assert s["loss_ha"] == pytest.approx(0.01)
    assert s["gain_ha"] == pytest.approx(0.01)
    assert s["stable_ha"] == pytest.approx(0.01)
    assert s["valid_fraction"] == pytest.approx(0.75)


def _fake_tools(monkeypatch):
    bbox = BBox(west=-4, south=35, east=-3.9, north=35.1)

    def fake_search(bb, start, end, limit=10, **kw):
        prefix = "before" if start.year == 2023 else "after"
        item = ImageryItem(id=f"{prefix}_1", acquired=datetime(start.year, 7, 15, tzinfo=timezone.utc),
                           cloud_cover=0.0, assets={})
        return SearchImageryResult(bbox=bb, start=str(start), end=str(end), items=[item])

    def fake_read(item, bb, band_names):
        shape = (10, 10)
        nir_dn = 5000 if item.id.startswith("before") else 3000   # NDVI 0.60 -> 0.33
        dn = {"red": 2000, "nir": nir_dn}
        return BandStack(
            bands={n: np.full(shape, dn[n], dtype=np.uint16) for n in band_names},
            scl=np.full(shape, 4, dtype=np.uint8),
            transform=Affine(10, 0, 500000, 0, -10, 3900000), crs="EPSG:32630",
        )

    monkeypatch.setattr(change, "search_imagery", fake_search)
    monkeypatch.setattr(change, "read_bands", fake_read)
    return bbox


def test_detect_change_end_to_end(monkeypatch):
    bbox = _fake_tools(monkeypatch)
    result = detect_change(bbox, (date(2023, 7, 1), date(2023, 8, 31)),
                           (date(2024, 7, 1), date(2024, 8, 31)), index="ndvi")
    assert result.summary.loss_ha == pytest.approx(1.0)   # 100 px x 0.01 ha
    assert result.summary.gain_ha == 0.0
    assert result.summary.mean_change == pytest.approx(0.3333 - 0.6, abs=1e-3)


def test_detect_change_rejects_overlapping_periods(monkeypatch):
    bbox = _fake_tools(monkeypatch)
    with pytest.raises(ChangeDetectionError):
        detect_change(bbox, (date(2023, 7, 1), date(2024, 8, 31)), (date(2024, 7, 1), date(2024, 9, 30)))
