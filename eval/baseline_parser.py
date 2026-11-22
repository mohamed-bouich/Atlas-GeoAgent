"""Parseur de référence basé sur des expressions régulières, utilisé pour comparer
les performances du parseur LLM.

Il couvre plusieurs cas courants : prépositions, noms de lieux avec majuscules,
mots-clés liés aux saisons et aux indices, ainsi que les distances en kilomètres.
Ses limites sont réelles : il ne détecte pas un lieu sans préposition introductive
et ne comprend pas les dates relatives comme « last summer ».
"""
import re

from agent.parser import ParsedRequest

# Correspondance entre les noms de saisons en anglais et en français.
SEASON_WORDS = {
    "summer": "summer", "été": "summer", "ete": "summer", "winter": "winter", "hiver": "winter",
    "spring": "spring", "printemps": "spring", "autumn": "autumn", "fall": "autumn", "automne": "autumn",
}
# Mots-clés orientant la sélection de l'indice spectral.
NBR_WORDS = ("fire", "burn", "wildfire", "incendie", "brûl", "brul")
NDWI_WORDS = ("water", "lake", "flood", "reservoir", "dam ", "lac ", "lacs", "inond", "barrage")

# Détection des noms de lieux composés de mots commençant par une majuscule.
_CAP = r"[A-ZÉÈÀ][\w’'\-éèêàçôû]+(?:\s+[A-ZÉÈÀ][\w’'\-éèêàçôû]+)*"
# Prépositions utilisées pour repérer le nom du lieu dans la question.
_PREP = r"(?:\b(?:around|near|in|at|of|for)\s+|autour d['’]\s*|autour de\s+|près d['’]\s*|près de\s+|\bà\s+|\bde\s+|\bd['’])"
_PLACE = re.compile(_PREP + "(" + _CAP + ")")
# Saisons à exclure des candidats détectés comme noms de lieux.
_NOT_A_PLACE = {"summer", "winter", "spring", "autumn", "été", "hiver", "printemps", "automne"}
# Extraction d'une distance exprimée en kilomètres.
_KM = re.compile(r"(\d+(?:[.,]\d+)?)\s*km", re.IGNORECASE)


def _place(question: str) -> str | None:
    """Extrait le premier nom de lieu détecté après une préposition."""
    for match in _PLACE.finditer(question):
        candidate = match.group(1).strip()
        if candidate.split()[0].lower() not in _NOT_A_PLACE:
            return candidate
    return None


def _season(text: str) -> str | None:
    """Identifie la première saison reconnue dans le texte."""
    for match in re.finditer(r"\b(\w+)\b", text.lower()):
        if match.group(1) in SEASON_WORDS:
            return SEASON_WORDS[match.group(1)]
    return None


def _index(text: str) -> str:
    """Sélectionne l'indice spectral selon les mots-clés présents dans la question."""
    lowered = text.lower() + " "
    if any(word in lowered for word in NBR_WORDS):
        return "nbr"
    if any(word in lowered for word in NDWI_WORDS):
        return "ndwi"
    return "ndvi"


def _distance(question: str) -> tuple[float | None, str | None]:
    """Extrait la distance et détermine si elle représente un rayon ou une largeur."""
    match = _KM.search(question)
    if not match:
        return None, None
    before = question[max(0, match.start() - 25):match.start()].lower()
    around = question[max(0, match.start() - 25):match.end() + 25].lower()
    if re.search(r"within|radius|rayon|moins de|around|autour", before):
        kind = "radius"
    elif re.search(r"zone|area|square|carré|carre|wide|large", around):
        kind = "width"
    else:
        kind = "radius"
    return float(match.group(1).replace(",", ".")), kind


def baseline_parse(question: str) -> ParsedRequest:
    """Transforme une question en requête structurée à l'aide de règles prédéfinies."""
    years = sorted(dict.fromkeys(int(y) for y in re.findall(r"\b(20\d\d)\b", question)))
    distance, kind = _distance(question)
    return ParsedRequest(
        place=_place(question), index=_index(question), season=_season(question),
        before_year=years[0] if years else None, after_year=years[1] if len(years) > 1 else None,
        distance_km=distance, distance_kind=kind,
    )
