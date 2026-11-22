"""Deterministic planning: validation, seasons -> dates, and replanning.

No LLM here. Dates and rules are code, so they are always correct and testable."""
import calendar
import math
from dataclasses import dataclass, replace
from datetime import date, timedelta

import config
from agent import settings
from agent.parser import ParsedRequest


@dataclass(frozen=True)
class Plan:
    place: str
    index: str
    season: str
    before_year: int
    after_year: int
    before: tuple[date, date]
    after: tuple[date, date]
    half_size_km: float = 5.0     # distance from the place to each edge of the square zone


MIN_SIDE_KM = 1.0
MAX_SIDE_KM = math.sqrt(config.MAX_AOI_KM2)    # same limit as the imagery search (20 km for 400 km2)

PROBLEM_TEXT = {
    "en": {
        "place": "which place (for example: Al Hoceima)",
        "season": "which season (winter, spring, summer or autumn)",
        "years": "the two years to compare (for example: 2023 and 2024)",
        "old_year": f"years from {settings.MIN_YEAR} onwards (Sentinel-2 L2A coverage starts around then)",
        "same_year": "two different years",
        "future": "periods that are already finished",
        "size": f"an area size between {MIN_SIDE_KM:g} and {MAX_SIDE_KM:g} km (for example: within 3 km of the place)",
    },
    "fr": {
        "place": "quel lieu (par exemple : Al Hoceima)",
        "season": "quelle saison (hiver, printemps, été ou automne)",
        "years": "les deux années à comparer (par exemple : 2023 et 2024)",
        "old_year": f"des années à partir de {settings.MIN_YEAR} (la couverture Sentinel-2 L2A commence vers cette date)",
        "same_year": "deux années différentes",
        "future": "des périodes déjà terminées",
        "size": f"une taille de zone entre {MIN_SIDE_KM:g} et {MAX_SIDE_KM:g} km (par exemple : dans un rayon de 3 km)",
    },
}


def season_dates(season: str, year: int) -> tuple[date, date]:
    """Meteorological seasons. Winter of year Y = Dec (Y-1) to Feb Y."""
    if season == "winter":
        return date(year - 1, 12, 1), date(year, 2, calendar.monthrange(year, 2)[1])
    months = {"spring": (3, 5), "summer": (6, 8), "autumn": (9, 11)}[season]
    return date(year, months[0], 1), date(year, months[1], calendar.monthrange(year, months[1])[1])


def half_size_from(req: ParsedRequest) -> float:
    """Distance from the place to each edge of the zone, in km.
    'within 3 km' (radius) -> 3. 'a 6 km zone' (width) -> 3. No size given -> the default."""
    if req.distance_km is None:
        return config.DEFAULT_HALF_SIZE_KM
    return req.distance_km / 2 if req.distance_kind == "width" else req.distance_km


def find_problems(req: ParsedRequest, today: date | None = None) -> list[str]:
    """Return problem codes. Empty list = the request is complete and valid."""
    today = today or date.today()
    problems = []
    if not req.place or not req.place.strip():
        problems.append("place")
    if req.season is None:
        problems.append("season")
    if req.before_year is None or req.after_year is None:
        problems.append("years")
    if not problems:
        first, second = sorted((req.before_year, req.after_year))
        if first < settings.MIN_YEAR:
            problems.append("old_year")
        elif first == second:
            problems.append("same_year")
        elif season_dates(req.season, second)[1] >= today:
            problems.append("future")
    if req.distance_km is not None and not (MIN_SIDE_KM <= 2 * half_size_from(req) <= MAX_SIDE_KM):
        problems.append("size")
    return problems


def make_plan(req: ParsedRequest) -> Plan:
    first, second = sorted((req.before_year, req.after_year))
    return Plan(
        place=req.place.strip(), index=req.index, season=req.season,
        before_year=first, after_year=second,
        before=season_dates(req.season, first), after=season_dates(req.season, second),
        half_size_km=half_size_from(req),
    )


def widen(plan: Plan, days: int = 30, today: date | None = None) -> Plan:
    """Replan after 'no clear scene': extend both periods by `days`, without overlapping."""
    today = today or date.today()
    b0, b1 = plan.before
    a0, a1 = plan.after
    b0 = b0 - timedelta(days=days)
    b1 = min(b1 + timedelta(days=days), a0 - timedelta(days=1))
    a0 = max(a0 - timedelta(days=days), b1 + timedelta(days=1))
    a1 = min(a1 + timedelta(days=days), today - timedelta(days=1))
    return replace(plan, before=(b0, b1), after=(a0, a1))
