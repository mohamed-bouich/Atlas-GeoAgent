"""LLM job #1: turn a free-text question into a small, validated structure.

The LLM extracts only simple fields (place, index, season, two years).
Dates are built by plain code in planner.py, because small models are bad at dates."""
import logging
import re
from typing import Literal

from pydantic import BaseModel, ValidationError

from agent.llm import chat_json
from agent.prompts import PARSER_SYSTEM

logger = logging.getLogger(__name__)


class ParseError(Exception):
    """The model answered, but not in the expected shape."""


class ParsedRequest(BaseModel):
    place: str | None = None
    index: Literal["ndvi", "nbr", "ndwi"] = "ndvi"
    season: Literal["winter", "spring", "summer", "autumn"] | None = None
    before_year: int | None = None
    after_year: int | None = None
    distance_km: float | None = None                       # size written by the user, e.g. 3 in "within 3 km"
    distance_kind: Literal["radius", "width"] | None = None


_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _distance_is_in_question(distance: float, question: str) -> bool:
    return any(abs(float(m.replace(",", ".")) - distance) < 1e-9 for m in _NUMBER.findall(question))


def parse_question(question: str) -> ParsedRequest:
    data = chat_json(PARSER_SYSTEM, question, ParsedRequest.model_json_schema(), max_tokens=120)
    try:
        request = ParsedRequest.model_validate(data)
    except ValidationError as exc:
        raise ParseError(f"Could not understand the question: {exc.errors()[0]['msg']}") from exc
    # A small model can invent a number. A size that is not written in the question is dropped
    # (the default size is used instead, and the report always states the zone that was analysed).
    if request.distance_km is not None and not _distance_is_in_question(request.distance_km, question):
        logger.warning("Ignoring distance %s: it is not in the question", request.distance_km)
        request = request.model_copy(update={"distance_km": None, "distance_kind": None})
    logger.info("Parsed: %s", request.model_dump())
    return request
