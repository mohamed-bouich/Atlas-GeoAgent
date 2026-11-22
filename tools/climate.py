"""Outil climatique : récupération et synthèse des données
    de température et de précipitations depuis Open-Meteo.

Free, no API key. Data comes from the ERA5 archive, available up to ~5 days ago.
Why it matters: a vegetation drop in summer means little without knowing whether
the previous rainy season was dry.
"""
import logging
from datetime import date, timedelta
from functools import lru_cache
import requests
from pydantic import BaseModel

# Configuration du système de journalisation.
logger = logging.getLogger(__name__)

# URL de l'API Open-Meteo pour les données historiques.
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Délai estimé de disponibilité des données dans l'archive.
ARCHIVE_DELAY_DAYS = 5

# Seuil minimal de précipitations pour considérer
# une journée comme pluvieuse (en millimètres).
RAINY_DAY_MM = 1.0


class ClimateError(Exception):
    """Raised when climate data is unavailable. The agent will read this message."""


class ClimateSummary(BaseModel):
    """
        Modèle représentant le résumé climatique d'une période.
    
        Attributes:
            start: Date de début de la période.
            end: Date de fin de la période.
            days_with_data: Nombre de jours pris en compte.
            mean_temp_c: Température moyenne en degrés Celsius.
            total_precip_mm: Précipitations cumulées en millimètres.
            rainy_days: Nombre de jours ayant reçu au moins 1 mm de pluie.
        """
    start: str
    end: str
    days_with_data: int
    mean_temp_c: float | None
    total_precip_mm: float
    rainy_days: int  # days with at least 1 mm


def summarize_daily(daily: dict, start: str, end: str) -> ClimateSummary:
    """Calcule un résumé statistique à partir des données climatiques quotidiennes."""
    temps = [t for t in daily.get("temperature_2m_mean", []) if t is not None]
    rain = [p for p in daily.get("precipitation_sum", []) if p is not None]
    # Vérification de la disponibilité des données.
    if not temps and not rain:
        raise ClimateError("No climate data returned for this period.")
    return ClimateSummary(
        start=start,
        end=end,
        days_with_data=len(rain) or len(temps),
        mean_temp_c=round(sum(temps) / len(temps), 1) if temps else None,
        total_precip_mm=round(sum(rain), 1),
        rainy_days=sum(1 for p in rain if p >= RAINY_DAY_MM),
    )


@lru_cache(maxsize=64)
def get_climate(lat: float, lon: float, start: date, end: date) -> ClimateSummary:
    """Récupère les données climatiques pour une période donnée et les résume."""
    if start > end:
        raise ClimateError("Start date must be before end date.")
    if end > date.today() - timedelta(days=ARCHIVE_DELAY_DAYS):
        raise ClimateError(
            f"Climate archive is available up to {ARCHIVE_DELAY_DAYS} days ago. Use an earlier end date."
        )
    try:
        response = requests.get(
            ARCHIVE_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "daily": "temperature_2m_mean,precipitation_sum",
                "timezone": "UTC",
            },
            timeout=30,
        )
        # Vérification de la réponse HTTP.
        response.raise_for_status()
        daily = response.json()["daily"]
    except requests.RequestException as exc:
        raise ClimateError(f"Climate service failed: {exc}") from exc
    except (KeyError, ValueError) as exc:
        raise ClimateError("Unexpected response from the climate service.") from exc

    logger.info("Climate %s -> %s: %d days", start, end, len(daily.get("time", [])))
    return summarize_daily(daily, start.isoformat(), end.isoformat())
