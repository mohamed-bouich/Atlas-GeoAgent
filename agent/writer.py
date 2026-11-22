"""The report.

Design: numbers, verdict and limits come from CODE (always correct). The LLM only
rephrases ONE explanatory sentence, guided by a hint chosen by rules. A checker
rejects the sentence if it invents numbers, contradicts the data, truncates, or leaks
internal field names. If rejected (or if Ollama is down), the rule-based hint is used,
so the user always gets a correct interpretation."""
import json
import logging
import re
from dataclasses import dataclass

from agent import settings
from agent.llm import LLMError, chat_text
from agent.planner import Plan
from agent.prompts import narrative_system
from tools.change import ChangeSummary
from tools.climate import ClimateSummary

logger = logging.getLogger(__name__)

INDEX_LABELS = {
    "en": {"ndvi": "vegetation greenness (NDVI)", "nbr": "burn index (NBR)", "ndwi": "open-water index (NDWI)"},
    "fr": {"ndvi": "verdure de la végétation (NDVI)", "nbr": "indice de brûlure (NBR)", "ndwi": "indice d'eau libre (NDWI)"},
}
SEASON_LABELS = {
    "en": {"winter": "winter", "spring": "spring", "summer": "summer", "autumn": "autumn"},
    "fr": {"winter": "hiver", "spring": "printemps", "summer": "été", "autumn": "automne"},
}
TEXT = {
    "en": {
        "title": "**{place}: {index_label}, {before} → {after}**",
        "change": "- Mean change: {mean_change:+.3f} (changes below ±{threshold} are treated as noise).",
        "area": "- Loss: {loss_ha:.1f} ha ({loss_pct:.1f}% of the analysed land). Gain: {gain_ha:.1f} ha ({gain_pct:.1f}%).",
        "verdict_stable": "- Net balance: no significant change (gain minus loss: {net_pct:+.1f} percentage points).",
        "verdict_decline": "- Net balance: decline (gain minus loss: {net_pct:+.1f} percentage points).",
        "verdict_increase": "- Net balance: increase (gain minus loss: {net_pct:+.1f} percentage points).",
        "coverage": "- Analysed area: {analysed_pct:.0f}% of the zone (sea and clouds excluded), from {scenes_before} + {scenes_after} Sentinel-2 scenes.",
        "zone": "- Zone: {zone_km:g} × {zone_km:g} km square centred on {place}.",
        "rain": "- Rainfall in the {rain_window_months} months before: {rain_before_mm:.0f} mm, then {rain_after_mm:.0f} mm ({rain_change_pct:+.0f}%).",
        "limits": "- Limits: only two periods are compared; climate data comes from a coarse grid (about 25 km); the ±{threshold} threshold is a choice.",
    },
    "fr": {
        "title": "**{place} : {index_label}, {before} → {after}**",
        "change": "- Changement moyen : {mean_change:+.3f} (les variations inférieures à ±{threshold} sont considérées comme du bruit).",
        "area": "- Perte : {loss_ha:.1f} ha ({loss_pct:.1f}% des terres analysées). Gain : {gain_ha:.1f} ha ({gain_pct:.1f}%).",
        "verdict_stable": "- Bilan net : pas de changement significatif (gain moins perte : {net_pct:+.1f} points de pourcentage).",
        "verdict_decline": "- Bilan net : déclin (gain moins perte : {net_pct:+.1f} points de pourcentage).",
        "verdict_increase": "- Bilan net : augmentation (gain moins perte : {net_pct:+.1f} points de pourcentage).",
        "coverage": "- Surface analysée : {analysed_pct:.0f}% de la zone (mer et nuages exclus), à partir de {scenes_before} + {scenes_after} scènes Sentinel-2.",
        "zone": "- Zone : carré de {zone_km:g} × {zone_km:g} km centré sur {place}.",
        "rain": "- Pluie sur les {rain_window_months} mois précédents : {rain_before_mm:.0f} mm, puis {rain_after_mm:.0f} mm ({rain_change_pct:+.0f}%).",
        "limits": "- Limites : seulement deux périodes comparées ; données climatiques sur une grille grossière (environ 25 km) ; le seuil de ±{threshold} est un choix.",
    },
}

# Domain knowledge as RULES: (verdict, rain_trend) -> cautious explanation.
# rain_trend None = no climate data. The LLM may rephrase it; it may not change its meaning.
HINTS = {
    ("stable", "wetter"): {
        "en": "Vegetation stayed stable despite more rain, so summer greenness here may depend more on irrigation or perennial vegetation than on rainfall.",
        "fr": "La végétation est restée stable malgré davantage de pluie : la verdure estivale dépend peut-être plus de l'irrigation ou de la végétation pérenne que de la pluie."},
    ("stable", "drier"): {
        "en": "Vegetation stayed stable despite less rain, which suggests irrigated crops or evergreen forest are buffering the signal.",
        "fr": "La végétation est restée stable malgré moins de pluie, ce qui suggère que les cultures irriguées ou la forêt sempervirente amortissent le signal."},
    ("stable", "similar"): {
        "en": "Vegetation and rainfall were both similar, so no meaningful change is detected.",
        "fr": "La végétation et les pluies sont restées similaires : aucun changement significatif n'est détecté."},
    ("stable", None): {
        "en": "No significant net change in vegetation was detected.",
        "fr": "Aucun changement net significatif de la végétation n'a été détecté."},
    ("increase", "wetter"): {
        "en": "Greener vegetation is consistent with the wetter conditions, although other causes such as land use change cannot be excluded.",
        "fr": "Une végétation plus verte est cohérente avec des conditions plus humides, même si d'autres causes comme le changement d'usage des sols restent possibles."},
    ("increase", "drier"): {
        "en": "Vegetation became greener although rainfall decreased, so rainfall does not explain it; irrigation, land use change or recovery after a past disturbance are possible causes.",
        "fr": "La végétation est devenue plus verte malgré une baisse des pluies : la pluie n'explique pas cette hausse ; irrigation, changement d'usage des sols ou reprise après une perturbation passée sont possibles."},
    ("increase", "similar"): {
        "en": "Vegetation became greener with similar rainfall; irrigation or land use change are possible causes.",
        "fr": "La végétation est devenue plus verte avec des pluies similaires ; irrigation ou changement d'usage des sols sont possibles."},
    ("increase", None): {
        "en": "Vegetation became greener; the cause cannot be identified without climate data.",
        "fr": "La végétation est devenue plus verte ; la cause ne peut pas être identifiée sans données climatiques."},
    ("decline", "wetter"): {
        "en": "Vegetation declined although rainfall increased, so drought does not explain it; fire, clearing, urban expansion or crop changes are possible causes.",
        "fr": "La végétation a décliné malgré une hausse des pluies : la sécheresse n'explique pas ce déclin ; incendie, défrichement, urbanisation ou changement de cultures sont possibles."},
    ("decline", "drier"): {
        "en": "The decline in vegetation is consistent with the drier conditions, which may indicate water stress.",
        "fr": "Le déclin de la végétation est cohérent avec des conditions plus sèches, ce qui peut indiquer un stress hydrique."},
    ("decline", "similar"): {
        "en": "Vegetation declined with similar rainfall; fire, clearing, urban expansion or crop changes are possible causes.",
        "fr": "La végétation a décliné avec des pluies similaires ; incendie, défrichement, urbanisation ou changement de cultures sont possibles."},
    ("decline", None): {
        "en": "Vegetation declined; the cause cannot be identified without climate data.",
        "fr": "La végétation a décliné ; la cause ne peut pas être identifiée sans données climatiques."},
}

# Decision rules computed by CODE, so the LLM never decides the direction itself.
NET_STABLE_PCT = 1.0     # |gain% - loss%| below this many percentage points = "stable"
RAIN_TREND_PCT = 10      # rain change beyond +-10% = "wetter" / "drier"


@dataclass
class Report:
    text: str
    grounded: bool                 # True if the LLM sentence passed every check
    narrative: str | None
    rejected: str | None = None    # the raw text we refused (kept for debugging and evaluation)
    reason: str | None = None
    source: str = "rules"          # "llm" or "rules": who wrote the interpretation


def build_facts(plan: Plan, summary: ChangeSummary,
                climate: tuple[ClimateSummary, ClimateSummary] | None) -> dict:
    """Every number the report may use. Computed here, never by the LLM."""
    facts = {
        "place": plan.place, "index": summary.index, "season": plan.season,
        "before_year": plan.before_year, "after_year": plan.after_year,
        "mean_change": round(summary.mean_change or 0.0, 3), "threshold": summary.threshold,
        "loss_ha": round(summary.loss_ha, 1), "gain_ha": round(summary.gain_ha, 1),
        "loss_pct": round(summary.loss_pct, 1), "gain_pct": round(summary.gain_pct, 1),
        "analysed_pct": round(summary.valid_fraction * 100),
        "scenes_before": len(summary.before_scenes), "scenes_after": len(summary.after_scenes),
        "periods_compared": 2,   # true by construction; lets the model say "2 periods" legitimately
        "zone_km": round(2 * plan.half_size_km, 1),
    }
    net = summary.gain_pct - summary.loss_pct
    facts["net_pct"] = round(net, 1)
    facts["verdict"] = "stable" if abs(net) < NET_STABLE_PCT else ("increase" if net > 0 else "decline")
    if climate is not None:
        before, after = climate
        facts["rain_window_months"] = 12
        facts["rain_before_mm"] = round(before.total_precip_mm)
        facts["rain_after_mm"] = round(after.total_precip_mm)
        if before.total_precip_mm > 0:
            change = 100 * (after.total_precip_mm - before.total_precip_mm) / before.total_precip_mm
            facts["rain_change_pct"] = round(change)
            facts["rain_trend"] = "wetter" if change >= RAIN_TREND_PCT else ("drier" if change <= -RAIN_TREND_PCT else "similar")
    return facts


def hint_for(facts: dict, lang: str = "en") -> str:
    return HINTS[(facts["verdict"], facts.get("rain_trend"))][lang]


def render_template(facts: dict, lang: str = "en") -> str:
    t = TEXT[lang]
    labels = dict(
        facts,
        index_label=INDEX_LABELS[lang][facts["index"]],
        before=f"{SEASON_LABELS[lang][facts['season']]} {facts['before_year']}",
        after=f"{SEASON_LABELS[lang][facts['season']]} {facts['after_year']}",
    )
    lines = [t["title"], "", t["change"], t["area"], t["verdict_" + facts["verdict"]], t["coverage"], t["zone"]]
    if "rain_change_pct" in facts:
        lines.append(t["rain"])
    lines.append(t["limits"])
    return "\n".join(lines).format(**labels)


# ---------- grounding check ----------

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _allowed_numbers(facts: dict) -> set[float]:
    allowed: set[float] = set()
    for value in facts.values():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            allowed.add(abs(float(value)))
        elif isinstance(value, str):
            allowed.update(float(m.replace(",", ".")) for m in _NUMBER.findall(value))
    return allowed


def is_grounded(text: str, facts: dict) -> tuple[bool, list[str]]:
    """Every number in `text` must match a number in `facts`, at the precision typed.
    '28' matches 28.4 (rounded), but '0.02' does not match 0.001."""
    allowed = _allowed_numbers(facts)
    bad = []
    for raw in _NUMBER.findall(text):
        number = float(raw.replace(",", "."))
        decimals = len(raw.replace(",", ".").split(".")[1]) if "." in raw.replace(",", ".") else 0
        tolerance = 0.5 * 10 ** (-decimals) + 1e-9
        if not any(abs(number - v) <= tolerance for v in allowed):
            bad.append(raw)
    return (not bad), bad


# ---------- consistency check ----------
# Grounding checks numbers, not logic. These rules catch the contradictions a small
# model makes (e.g. "a slight loss" when the verdict is stable). They cannot catch
# everything: that is why the exact numbers always come from the template.

_DIRECTION = r"(loss|decline|decrease|increase|gain|perte|déclin|baisse|diminution|augmentation|hausse)"
_QUALIFIER = r"(slight|overall|net|significant|substantial|légère|globale|nette|significative)"
RULES = {
    "stable": [rf"\b{_QUALIFIER}(\s+\w+)?\s+{_DIRECTION}\b"],
    "decline": [r"\b(overall|net|global\w*)\s+(gain|increase|improvement|augmentation|hausse)\b"],
    "increase": [r"\b(overall|net|global\w*)\s+(loss|decline|decrease|perte|déclin|baisse)\b"],
}
RAIN_RULES = {
    "wetter": [r"\b(reduced|lower|less|decreased|declining|drier)\s+(rainfall|rain|precipitation)", r"\bdrought\b",
               r"sécheresse", r"moins de pluie", r"baisse des précipitations"],
    "drier": [r"\b(increased|higher|more|heavier|wetter)\s+(rainfall|rain|precipitation)", r"\bwetter\b",
              r"plus de pluie", r"hausse des précipitations"],
}
# Words that only exist in our prompt: if they appear, the model is quoting its instructions.
LEAK = re.compile(r"verdict|rain_trend|periods_compared|overall_result|rainfall_change|explanation_hint|\bhint\b", re.I)


def find_contradictions(text: str, facts: dict) -> list[str]:
    patterns = RULES.get(facts.get("verdict", ""), []) + RAIN_RULES.get(facts.get("rain_trend", ""), [])
    found = []
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            found.append(match.group(0))
    return found


# ---------- cleaning and checking the LLM sentence ----------

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def clean_narrative(text: str, max_sentences: int = 2) -> str:
    """One line, whole sentences only (a cut-off tail is dropped), at most `max_sentences`.
    Real run: the token limit cut '2023 and 2024' to '2023 and 20', which then looked like
    an invented number."""
    text = " ".join(text.split())
    if not text:
        return ""
    parts = _SENTENCE_END.split(text)
    if not re.search(r"[.!?][\"')\]]*$", parts[-1]):
        parts = parts[:-1]
    return " ".join(parts[:max_sentences])


def check_narrative(text: str, facts: dict) -> str | None:
    """None if the text is acceptable, otherwise the reason it was rejected."""
    if not text:
        return "empty or cut off"
    if LEAK.search(text):
        return "mentions internal field names"
    ok, bad = is_grounded(text, facts)
    if not ok:
        return f"ungrounded numbers: {bad}"
    contradictions = find_contradictions(text, facts)
    if contradictions:
        return f"contradicts the data: {contradictions}"
    return None


LLM_NUMBERS = ("rain_change_pct",)


def llm_view(facts: dict, lang: str = "en") -> dict:
    """Only what the model needs, with natural field values: a short prompt is a fast prompt."""
    view = {
        "place": facts["place"],
        "season": facts["season"],
        "years": f"{facts['before_year']} to {facts['after_year']}",
        "overall_result": facts["verdict"],
        "explanation_hint": hint_for(facts, lang),
    }
    if "rain_trend" in facts:
        view["rainfall_change"] = f"{facts['rain_trend']} ({facts['rain_change_pct']:+d}%)"
    return view


def write_report(facts: dict, lang: str | None = None) -> Report:
    lang = lang or settings.REPORT_LANGUAGE
    base = render_template(facts, lang)
    fallback = f"{base}\n\n{hint_for(facts, lang)}"       # rule-based interpretation
    try:
        raw = chat_text(narrative_system(lang), json.dumps(llm_view(facts, lang), ensure_ascii=False), max_tokens=70)
    except LLMError as exc:
        logger.warning("No LLM sentence (%s). Using the rule-based interpretation.", exc)
        return Report(fallback, False, None, source="rules")

    narrative = clean_narrative(raw)
    reason = check_narrative(narrative, facts)
    if reason:
        logger.warning("LLM sentence rejected (%s): %r", reason, raw)
        return Report(fallback, False, None, rejected=raw, reason=reason, source="rules")
    return Report(f"{base}\n\n{narrative}", True, narrative, source="llm")
