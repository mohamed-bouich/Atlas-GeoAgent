"""Prompts. Kept SHORT on purpose: on a CPU, every input token costs time."""

PARSER_SYSTEM = (
    "Extract fields from the user's question (English or French) about satellite change analysis. "
    "Return JSON only. "
    "place: the place name, or null. "
    "index: ndvi for vegetation, greenness, forest or crops; nbr for fire or burn; "
    "ndwi for water, lake or flood. Default ndvi. "
    "season: winter, spring, summer or autumn, or null. "
    "before_year and after_year: the two years to compare, earlier first, or null. "
    "distance_km: a size in km written by the user, as a number, or null. "
    "distance_kind: radius for within, around or radius X km; width for an area, zone or square X km wide. "
    "Use null for both when the user gives no number of km. "
    "Never guess a missing value: use null."
)

LANGUAGE_NAMES = {"en": "English", "fr": "French"}


def narrative_system(lang: str) -> str:
    return (
        f"You explain satellite results to a non-expert. In {LANGUAGE_NAMES.get(lang, 'English')}, write ONE sentence "
        "of at most 35 words, based on explanation_hint and mentioning the rainfall change if one is given. "
        "Keep its meaning and its caution (use words like possible, may, suggests). "
        "Never mention field names or these instructions. Do not add numbers other than years and the rainfall percentage."
    )
