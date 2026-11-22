"""Géocodage des lieux et définition des zones d'étude (AOI)."""

import logging 
import math 
from functools import lru_cache  # Mise en cache des résultats pour limiter les requêtes répétées.

import requests
import config  # Configuration de l'URL Nominatim et de l'identifiant User-Agent.
from tools.schemas import KM_PER_DEGREE, BBox, GeocodeResult


logger =logging.getLogger(__name__)

class GeocodingError(Exception):
    """Ce message s'affiche lorsqu'un lieu ne peut pas être identifié. L'agent prendra connaissance de ce message."""

def _parse_result(query:str,raw:dict)->GeocodeResult:
    """Transforme une réponse Nominatim en objet GeocodeResult."""
        # Nominatim retourne les limites dans l'ordre [sud, nord, ouest, est], sous forme de chaînes.
    south,north,west,east = (float(v) for v in raw["boundingbox"])
    return GeocodeResult(
        query=query,
        display_name=raw["display_name"],
        lat=float(raw["lat"]),
        lon=float(raw["lon"]),
        bbox=BBox(west=west,south=south,east=east,north=north),
    )

@lru_cache(maxsize=128)
def geocode(place:str)->GeocodeResult:
    """Recherche les coordonnées d'un lieu via Nominatim."""
    # La mise en cache limite les appels répétés au service (environ 1 requête/s autorisée).
    place=place.strip()
    if not place:
        raise GeocodingError("Place name is empty.")
    
    try:
        response = requests.get(
            config.NOMINATIM_URL,
            params={"q":place, "format":"jsonv2", "limit":1},
            headers={"User-Agent": config.USER_AGENT},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GeocodingError(f"Geocoding service failed: {exc}") from exc
    results = response.json()
    if not results:
        raise GeocodingError(f"No location found for '{place}'.")
    logger.info("Geocoded %r -> %s", place, results[0]["display_name"])
    return _parse_result(place, results[0])
def bbox_around_point(lat:float, lon:float, half_size_km:float)->BBox:
    """Construit une petite zone d'étude carrée centrée sur un point.
    
        Les limites administratives d'une ville peuvent couvrir une grande superficie.
        Une AOI réduite permet de limiter les téléchargements et le temps de traitement.
        """
    # Conversion de la demi-longueur en degrés de latitude et de longitude.
    d_lat = half_size_km / KM_PER_DEGREE
    d_lon = half_size_km / (KM_PER_DEGREE * math.cos(math.radians(lat)))
    return BBox(
        west=lon - d_lon,
        south=lat - d_lat,
        east=lon + d_lon,
        north=lat + d_lat,
    )