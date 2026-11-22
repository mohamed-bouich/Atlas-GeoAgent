"""Outil de recherche des scènes Sentinel-2 via l'API STAC."""
import logging
from datetime import date

import requests
from pystac_client import Client   # Client STAC pour rechercher et parcourir les catalogues d'images.
from pystac_client.exceptions import APIError   # Gestion des erreurs retournées par l'API STAC.
import config
from tools.schemas import BBox, ImageryItem, SearchImageryResult

logger = logging.getLogger(__name__)

# Bandes requises pour les étapes suivantes : RVB, NIR (NDVI), SWIR (NBR/NDWI), SCL (masque de nuages)

REQUIRED_ASSETS = ("red", "green", "blue", "nir", "swir16", "swir22", "scl")


class ImagerySearchError(Exception):
    """Erreur levée en cas de paramètres invalides ou d'échec de la recherche STAC."""


def _calibration(stac_item) -> tuple[float, float] | None:
    """Récupère les paramètres de calibration (scale, offset) depuis les métadonnées STAC.
        Les bandes optiques d'une même scène Sentinel-2 partagent les mêmes paramètres
        de calibration.
        """
    # Lecture des métadonnées de calibration associées à la bande rouge.
    bands = stac_item.assets["red"].extra_fields.get("raster:bands") or []
    if not bands or "scale" not in bands[0] or "offset" not in bands[0]:
        return None
    return float(bands[0]["scale"]), float(bands[0]["offset"])


def _to_item(stac_item) -> ImageryItem | None:
    """Convertir un élément pystac. Renvoyer `None` s'il manque une bande ou si son étalonnage est manquant :
    nous ignorons ces scènes plutôt que de deviner le décalage."""
    if stac_item.datetime is None:
        return None
    if any(name not in stac_item.assets for name in REQUIRED_ASSETS):
        return None
    calibration = _calibration(stac_item)
    if calibration is None:
        logger.debug("Skipping %s: no scale/offset metadata", stac_item.id)
        return None
    scale, offset = calibration
    return ImageryItem(
        scale=scale,
        offset=offset,
        id=stac_item.id,
        acquired=stac_item.datetime,
        cloud_cover=float(stac_item.properties.get("eo:cloud_cover", 100.0)),
        assets={name: stac_item.assets[name].href for name in REQUIRED_ASSETS},
    )


def search_imagery(
    bbox: BBox,
    start: date,
    end: date,
    max_cloud_cover: float = config.MAX_CLOUD_COVER,
    limit: int = 10,
) -> SearchImageryResult:
    """Recherche les scènes les moins nuageuses couvrant l'AOI pendant la période demandée."""
    if start > end:
        raise ImagerySearchError("Start date must be before end date.")
    # Limite la superficie de recherche afin de maîtriser les volumes de données à traiter.
    if bbox.area_km2() > config.MAX_AOI_KM2:
        raise ImagerySearchError(
            f"Area is {bbox.area_km2():.0f} km2, above the {config.MAX_AOI_KM2:.0f} km2 limit. "
            "Use a smaller area."
        )

    try:
        # Connexion au catalogue STAC et recherche des scènes correspondant aux critères.
        client = Client.open(config.STAC_URL)
        search = client.search(
            collections=[config.STAC_COLLECTION],
            bbox=bbox.as_list(),
            datetime=f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
            query={"eo:cloud_cover": {"lt": max_cloud_cover}},
            max_items=200,
        )
        raw_items = list(search.items())
    except (APIError, requests.RequestException) as exc:
        raise ImagerySearchError(f"STAC search failed: {exc}") from exc
    
    # Conversion des résultats STAC et exclusion des scènes incomplètes ou non calibrées.
    items = [i for i in (_to_item(r) for r in raw_items) if i is not None]

    # Classement par couverture nuageuse croissante.
    items.sort(key=lambda i: i.cloud_cover)
    logger.info("STAC returned %d usable scenes (keeping %d)", len(items), limit)

    return SearchImageryResult(
        bbox=bbox, start=start.isoformat(), end=end.isoformat(), items=items[:limit]
    )
