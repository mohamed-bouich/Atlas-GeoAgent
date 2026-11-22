"""Offline tests: no network needed. Run with: pytest -q"""
import pytest
from pydantic import ValidationError

from tools.geocoding import _parse_result, bbox_around_point
from tools.schemas import BBox


def test_bbox_rejects_wrong_order():
    with pytest.raises(ValidationError):
        BBox(west=10, south=0, east=5, north=1)


def test_bbox_area_is_reasonable():
    # about 10 km x 10 km near the equator
    box = bbox_around_point(lat=0.0, lon=0.0, half_size_km=5)
    assert 95 < box.area_km2() < 105


def test_parse_nominatim_order():
    raw = {
        "display_name": "Al Hoceima, Morocco",
        "lat": "35.2517",
        "lon": "-3.9372",
        # Nominatim order: south, north, west, east
        "boundingbox": ["35.20", "35.30", "-4.00", "-3.90"],
    }
    result = _parse_result("Al Hoceima", raw)
    assert result.bbox.as_list() == [-4.0, 35.2, -3.9, 35.3]
