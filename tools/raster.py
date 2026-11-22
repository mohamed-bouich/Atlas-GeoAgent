"""Raster I/O: lecture d'une petite fenêtre de bandes Sentinel-2 à partir de fichiers COG distants..

Le format COG (Cloud Optimized GeoTIFF) permet de récupérer uniquement les
pixels correspondant à notre zone d'étude (AOI), grâce aux requêtes HTTP Range,
sans télécharger toute la tuile satellite de 100 km × 100 km.
"""

import logging
import math
from dataclasses import dataclass  # Regroupement des bandes et métadonnées dans une structure unique.
import numpy as np
import rasterio   # Lecture des rasters géospatiaux, y compris les fichiers COG distants
from affine import Affine  # Transformation entre les coordonnées des pixels et celles de la carte.
from rasterio.enums import Resampling  # Méthodes de rééchantillonnage des bandes raster.
from rasterio.errors import RasterioError
from rasterio.warp import transform_bounds  # Conversion des limites géographiques entre systèmes de coordonnées.
from rasterio.windows import Window, bounds as window_bounds, from_bounds
from tools.schemas import BBox, ImageryItem

logger = logging.getLogger(__name__)

REFERENCE_BAND = "red"  # Bande de référence à 10 m pour définir la grille spatiale commune.

# Options GDAL pour optimiser l'accès HTTP aux fichiers COG distants.
GDAL_OPTIONS = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff",
    "GDAL_HTTP_MAX_RETRY": "3",
    "GDAL_HTTP_RETRY_DELAY": "1",
}

class RasterReadError(Exception):
    """Ce message s'affiche lorsque les bandes ne peuvent pas être lues. L'agent lira ce message."""


@dataclass
class BandStack:
    bands: dict[str, np.ndarray]  # Valeurs numériques brutes (uint16), de même dimension.
    scl: np.ndarray               # Classification SCL (uint8), alignée sur les bandes.
    transform: Affine             # Transformation des pixels vers les coordonnées géographiques.
    crs: str                      # Système de référence spatial, par exemple EPSG:32630


def _integer_window(window: Window) -> Window:
    """Ajuste les limites de la fenêtre aux dimensions entières des pixels."""
    return Window(
        col_off=math.floor(window.col_off),
        row_off=math.floor(window.row_off),
        width=math.ceil(window.width),
        height=math.ceil(window.height),
    )


def _read_aligned(url: str, bounds: tuple, shape: tuple[int, int], resampling: Resampling) -> np.ndarray:
    """Lire une bande au-delà des « limites », rééchantillonnée sur la grille de référence « shape »."""
    with rasterio.open(url) as ds:
        window = from_bounds(*bounds, transform=ds.transform)
        return ds.read(
            1, window=window, out_shape=shape,
            resampling=resampling, boundless=True, fill_value=0,
        )


def read_bands(item: ImageryItem, bbox: BBox, band_names: tuple[str, ...] = ("red", "nir")) -> BandStack:
    """Lit les bandes demandées et la couche SCL sur une grille commune de 10 m."""
    try:
        with rasterio.Env(**GDAL_OPTIONS):
            with rasterio.open(item.assets[REFERENCE_BAND]) as ref:
                 # Conversion de l'AOI depuis WGS84 vers le système de coordonnées du raster.
                left, bottom, right, top = transform_bounds("EPSG:4326", ref.crs, *bbox.as_list())
                # Définition de la fenêtre de lecture à partir de la grille de la bande de référence.
                window = _integer_window(from_bounds(left, bottom, right, top, transform=ref.transform))
                bounds = window_bounds(window, ref.transform)
                transform = ref.window_transform(window)
                crs = ref.crs.to_string()
                shape = (int(window.height), int(window.width))
             # Interpolation bilinéaire adaptée aux bandes spectrales continues.
            bands = {
                name: _read_aligned(item.assets[name], bounds, shape, Resampling.bilinear)
                for name in band_names
            }
             # Plus proche voisin pour préserver les classes catégorielles de la couche SCL.
            scl = _read_aligned(item.assets["scl"], bounds, shape, Resampling.nearest)
    except KeyError as exc:
        raise RasterReadError(f"Scene {item.id} has no asset {exc}.") from exc
    except RasterioError as exc:
        raise RasterReadError(f"Could not read scene {item.id}: {exc}") from exc

    logger.info("Read %s bands %s, shape %s", item.id, band_names, shape)
    return BandStack(bands=bands, scl=scl, transform=transform, crs=crs)
