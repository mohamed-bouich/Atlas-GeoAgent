"""Offline test of read_bands using small synthetic GeoTIFFs (no internet)."""
from datetime import datetime, timezone

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

from tools.raster import read_bands
from tools.schemas import BBox, ImageryItem

X0, Y0 = 500000.0, 3900000.0  # UTM zone 30N, near Al Hoceima


def _write(path, size, pixel, value, dtype):
    data = np.full((size, size), value, dtype=dtype)
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=1,
        dtype=dtype, crs="EPSG:32630", transform=from_origin(X0, Y0, pixel, pixel),
    ) as dst:
        dst.write(data, 1)


def test_read_bands_aligns_20m_scl_to_10m_grid(tmp_path):
    paths = {}
    for name, size, pixel, value, dtype in [
        ("red", 200, 10, 1000, "uint16"),   # 2 km x 2 km at 10 m
        ("nir", 200, 10, 3000, "uint16"),
        ("scl", 100, 20, 4, "uint8"),       # same area at 20 m
    ]:
        paths[name] = str(tmp_path / f"{name}.tif")
        _write(paths[name], size, pixel, value, dtype)

    item = ImageryItem(
        id="fake", acquired=datetime(2024, 7, 1, tzinfo=timezone.utc),
        cloud_cover=0.0, assets=paths,
    )
    # sub-area well inside the 2 km tile
    w, s, e, n = transform_bounds("EPSG:32630", "EPSG:4326", X0 + 500, Y0 - 1500, X0 + 1500, Y0 - 500)
    stack = read_bands(item, BBox(west=w, south=s, east=e, north=n))

    assert stack.bands["red"].shape == stack.bands["nir"].shape == stack.scl.shape
    assert abs(stack.bands["red"].shape[0] - 100) <= 3   # about 1 km at 10 m
    assert set(np.unique(stack.bands["red"])) == {1000}
    assert set(np.unique(stack.bands["nir"])) == {3000}
    assert set(np.unique(stack.scl)) == {4}
