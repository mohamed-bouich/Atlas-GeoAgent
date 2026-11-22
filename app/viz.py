"""Map helpers for the Streamlit app. No Streamlit import here, so it is easy to test."""
import folium
import numpy as np

from tools.change import ChangeResult
from tools.change import DEFAULT_THRESHOLDS
from rasterio.transform import array_bounds
from rasterio.warp import transform_bounds

LOSS_RGB = (239 / 255, 68 / 255, 68 / 255)    # #EF4444, same red as the metric cards
GAIN_RGB = (34 / 255, 197 / 255, 94 / 255)    # #22C55E, same green as the metric cards
MAX_DELTA = 0.5                               # change at which the colour is strongest
SATELLITE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
DARK_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"


def change_rgba(delta: np.ndarray, threshold: float = DEFAULT_THRESHOLDS["ndvi"]) -> np.ndarray:
    """8-bit RGBA image of the change, consistent with the reported hectares:
    red = loss, green = gain (only where |change| >= threshold), transparent elsewhere.
    Stronger change = more opaque."""
    rgba = np.zeros(delta.shape + (4,), dtype=np.float32)
    finite = np.isfinite(delta)
    loss = finite & (delta <= -threshold)
    gain = finite & (delta >= threshold)
    strength = np.clip((np.abs(np.nan_to_num(delta)) - threshold) / max(MAX_DELTA - threshold, 1e-6), 0, 1)
    alpha = 0.5 + 0.4 * strength
    for mask, color in ((loss, LOSS_RGB), (gain, GAIN_RGB)):
        rgba[mask, :3] = color
        rgba[mask, 3] = alpha[mask]
    # Folium rescales float images by their maximum, which turned red/green into cyan/pink
    # in the browser. An 8-bit image is used as is, so the colours are exact.
    return np.round(rgba * 255).astype(np.uint8)


def bounds_latlon(transform, shape: tuple[int, int], crs: str) -> tuple[float, float, float, float]:
    """(west, south, east, north) in degrees of a raster given in a projected CRS."""
    height, width = shape
    west, south, east, north = array_bounds(height, width, transform)
    return transform_bounds(crs, "EPSG:4326", west, south, east, north)


def make_map(result: ChangeResult) -> folium.Map:
    west, south, east, north = bounds_latlon(result.transform, result.delta.shape, result.crs)
    fmap = folium.Map(location=[(south + north) / 2, (west + east) / 2], zoom_start=12, tiles=None,
                      control_scale=True)
    # Base maps (switchable). Esri tiles need no API key; CartoDB tiles now do.
    folium.TileLayer(tiles=DARK_URL, attr="Tiles © Esri, DeLorme, NAVTEQ", name="Dark", max_zoom=16).add_to(fmap)
    folium.TileLayer(tiles=SATELLITE_URL, attr="Tiles © Esri, Maxar, Earthstar Geographics",
                     name="Satellite", max_zoom=19, show=False).add_to(fmap)
    folium.TileLayer("OpenStreetMap", name="Streets", show=False).add_to(fmap)
    folium.raster_layers.ImageOverlay(
        image=change_rgba(result.delta, result.summary.threshold),
        bounds=[[south, west], [north, east]],
        mercator_project=True,   # the image is in a metric grid, the web map is Web Mercator
        name="Change",
    ).add_to(fmap)
    folium.LayerControl(collapsed=True).add_to(fmap)
    return fmap
