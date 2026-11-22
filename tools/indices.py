"""Fonctions NumPy pour la conversion en réflectance, les masques et les indices spectraux.

Aucun accès réseau ou fichier : fonctions indépendantes et facilement testables.
"""
import numpy as np

# Sentinel-2 L2A reflectance = DN * scale + offset.
# Since processing baseline 04.00 (25 Jan 2022) ESA adds +1000 to every DN, which
# means an offset of -0.1 once scaled. Defaults below; real values come from STAC.
SCALE = 0.0001
BOA_OFFSET = -0.1

# Scene Classification Layer (SCL) classes we must NOT use for analysis:
# 0 no data, 1 saturated, 3 cloud shadow, 8 cloud medium, 9 cloud high,
# 10 thin cirrus, 11 snow/ice
SCL_INVALID = (0, 1, 3, 8, 9, 10, 11)
SCL_WATER = 6

# index name -> (band a, band b), index = (a - b) / (a + b)
INDEX_BANDS = {
    "ndvi": ("nir", "red"),      # vegetation greenness
    "nbr": ("nir", "swir22"),    # burn severity (dNBR)
    "ndwi": ("green", "nir"),    # open water
}


def to_reflectance(dn: np.ndarray, scale: float = SCALE, offset: float = BOA_OFFSET) -> np.ndarray:
    """Convert raw digital numbers to surface reflectance (float32).

    scale and offset come from each scene's STAC metadata (item.scale, item.offset),
    so every processing baseline is handled correctly. Defaults match baseline >= 04.00."""
    reflectance = dn.astype(np.float32) * scale + offset
    return np.clip(reflectance, 0.0, None)


def cloud_mask(scl: np.ndarray) -> np.ndarray:
    """Boolean array: True where the pixel is usable (clear land or water)."""
    return ~np.isin(scl, SCL_INVALID)


def water_mask(scl: np.ndarray) -> np.ndarray:
    """Boolean array: True where the SCL says water."""
    return scl == SCL_WATER


def normalized_difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """(a - b) / (a + b). The building block of NDVI, NBR, NDWI..."""
    a = a.astype(np.float32)
    b = b.astype(np.float32)
    denom = a + b
    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.where(denom != 0, (a - b) / denom, np.nan)
    return result.astype(np.float32)


def compute_index(name: str, reflectance: dict[str, np.ndarray]) -> np.ndarray:
    """Compute an index by name from a dict of reflectance bands."""
    if name not in INDEX_BANDS:
        raise ValueError(f"Unknown index '{name}'. Choose from {sorted(INDEX_BANDS)}.")
    band_a, band_b = INDEX_BANDS[name]
    return normalized_difference(reflectance[band_a], reflectance[band_b])


def ndvi(nir: np.ndarray, red: np.ndarray, valid: np.ndarray | None = None) -> np.ndarray:
    """Vegetation index. Masked pixels become NaN."""
    result = normalized_difference(nir, red)
    if valid is not None:
        result = np.where(valid, result, np.nan).astype(np.float32)
    return result


def summarize(index: np.ndarray) -> dict[str, float | None]:
    """Small JSON-friendly summary. This is what the LLM will read later,
    never the raw pixels."""
    finite = np.isfinite(index)
    if not finite.any():
        return {"mean": None, "std": None, "p10": None, "p90": None, "valid_fraction": 0.0}
    values = index[finite]
    return {
        "mean": float(values.mean()),
        "std": float(values.std()),
        "p10": float(np.percentile(values, 10)),
        "p90": float(np.percentile(values, 90)),
        "valid_fraction": float(finite.mean()),
    }
