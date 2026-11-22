"""Offline tests: the calibration is read from STAC metadata, never guessed."""
from datetime import datetime, timezone

import pystac

from tools.search_imagery import REQUIRED_ASSETS, _to_item


def _item(raster_bands):
    item = pystac.Item(id="S2_test", geometry=None, bbox=None,
                       datetime=datetime(2021, 7, 27, tzinfo=timezone.utc),
                       properties={"eo:cloud_cover": 3.0})
    for name in REQUIRED_ASSETS:
        extra = {"raster:bands": raster_bands} if name == "red" and raster_bands is not None else {}
        item.add_asset(name, pystac.Asset(href=f"https://example.com/{name}.tif", extra_fields=extra))
    return item


def test_calibration_is_read_from_the_scene():
    scene = _to_item(_item([{"scale": 0.0001, "offset": -0.1}]))
    assert (scene.scale, scene.offset) == (0.0001, -0.1)
    older = _to_item(_item([{"scale": 0.0001, "offset": 0.0}]))
    assert older.offset == 0.0


def test_scene_without_calibration_is_skipped():
    assert _to_item(_item(None)) is None
    assert _to_item(_item([{"scale": 0.0001}])) is None
