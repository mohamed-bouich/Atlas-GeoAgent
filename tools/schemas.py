"""Contrats de données typés partagés par tous les outils.

Pourquoi est-ce important: Par la suite, le LLM appellera des outils avec des arguments JSON.
Les modèles Pydantic valident les données reçues, notamment les arguments JSON
transmis aux outils, afin de détecter les erreurs avant le traitement.
"""
import math
from datetime import datetime

from pydantic import BaseModel, Field, model_validator  # Modèles et validation des données.

# Facteur approximatif de conversion des degrés en kilomètres.
KM_PER_DEGREE = 111.32


class BBox(BaseModel):
    """Boîte géographique WGS84 au format STAC : ouest, sud, est, nord."""

    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)

    @model_validator(mode="after")
    def _check_order(self) -> "BBox":
        """Vérifie que les limites géographiques sont dans le bon ordre."""
        if self.west >= self.east or self.south >= self.north:
            raise ValueError("Invalid bbox: need west < east and south < north.")
        return self

    def as_list(self) -> list[float]:
        """Retourne les coordonnées dans l'ordre attendu par STAC."""
        return [self.west, self.south, self.east, self.north]

    def area_km2(self) -> float:
        """Surface approximative (suffisante pour établir une limite de sécurité)."""
        mid_lat = math.radians((self.south + self.north) / 2)
        height = (self.north - self.south) * KM_PER_DEGREE
        width = (self.east - self.west) * KM_PER_DEGREE * math.cos(mid_lat)
        return height * width


class GeocodeResult(BaseModel):
    """Résultat du géocodage d'un lieu."""
    query: str
    display_name: str
    lat: float
    lon: float
    bbox: BBox


class ImageryItem(BaseModel):
    """Métadonnées d'une scène satellite et références de ses bandes."""

    id: str
    acquired: datetime
    cloud_cover: float
    assets: dict[str, str]  # nom de la bande -> URL du fichier COG
    # reflectance = DN * scale + offset, read from the scene's own STAC metadata
    scale: float = 0.0001
    offset: float = -0.1


class SearchImageryResult(BaseModel):
    """Résultat d'une recherche d'images satellite pour une zone et une période."""
    bbox: BBox
    start: str
    end: str
    items: list[ImageryItem]
