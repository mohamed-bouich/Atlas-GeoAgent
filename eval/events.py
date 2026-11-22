
"""Évaluation sur des événements réels : le pipeline détecte-t-il un changement
dont l'occurrence est connue ?

Les événements doivent être vérifiés au préalable à partir d'une source fiable :
article de presse, données EFFIS ou comparaison des images satellites dans
la couche Satellite de l'application.

Pour chaque événement, deux emprises géographiques sont définies en degrés :
  - affected_box : zone où le changement a réellement eu lieu
  - control_box  : zone proche, située dans la même zone analysée, sans changement

L'évaluation compare la proportion de pixels classés en perte ou en gain
dans les deux emprises.

Exécution :
    python -m eval.events

Règle PASS (constantes définies ci-dessous et à préciser dans le rapport) :
la proportion de pixels détectés dans la direction attendue doit atteindre
MIN_SHARE dans la zone affectée et être au moins MIN_RATIO fois supérieure
à celle de la zone témoin.
"""
import json
import math
from datetime import date

import numpy as np
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

import config
from tools.change import ChangeResult

RESULTS_DIR = config.ROOT_DIR / "eval" / "results"
# Seuils de validation : proportion minimale et rapport avec la zone témoin.
MIN_SHARE = 0.20
MIN_RATIO = 2.0

# Structure de référence uniquement. À remplacer par des événements vérifiés,
# puis à supprimer avant l'évaluation finale
EXAMPLE_EVENT = {
    "name": "EXAMPLE (replace me): what happened, where, when",
    "place": "Al Hoceima",
    "index": "ndvi",                                  # NDVI : végétation, NBR : brûlis, NDWI : eau
    "before": (date(2023, 6, 1), date(2023, 8, 31)),
    "after": (date(2024, 6, 1), date(2024, 8, 31)),
    "half_size_km": 5.0,
    "affected_box": (-3.95, 35.24, -3.94, 35.25),
    "control_box": (-3.92, 35.22, -3.91, 35.23),
    "expected": "loss",                               # "loss" or "gain"
}
EVENTS: list[dict] = []


def box_stats(result: ChangeResult, box: tuple[float, float, float, float]) -> dict | None:
    """Calcule le changement moyen et les proportions de perte/gain dans une emprise géographique.

    Retourne None si l'emprise est hors de la zone analysée ou ne contient
    aucun pixel valide.
    """
    left, bottom, right, top = transform_bounds("EPSG:4326", result.crs, *box)
    # Conversion de l'emprise géographique WGS84 vers le système de coordonnées du raster.
    window = from_bounds(left, bottom, right, top, transform=result.transform)
    height, width = result.delta.shape
    # Limitation de la fenêtre aux dimensions du raster.
    r0, r1 = max(0, math.floor(window.row_off)), min(height, math.ceil(window.row_off + window.height))
    c0, c1 = max(0, math.floor(window.col_off)), min(width, math.ceil(window.col_off + window.width))
    if r1 <= r0 or c1 <= c0:
        return None
    # Exclusion des valeurs invalides avant le calcul des statistiques.
    values = result.delta[r0:r1, c0:c1]
    values = values[np.isfinite(values)]
    if values.size == 0:
        return None
    threshold = result.summary.threshold
    return {"pixels": int(values.size), "mean_delta": float(values.mean()),
            "share_loss": float((values <= -threshold).mean()), "share_gain": float((values >= threshold).mean())}


def judge(expected: str, affected: dict | None, control: dict | None) -> tuple[bool, str]:
    """Applique les critères PASS/FAIL à partir des proportions de changement."""
    if affected is None or control is None:
        return False, "a box is outside the analysed zone (or has no valid pixels)"
    # Sélection de la proportion correspondant au changement attendu.
    key = "share_loss" if expected == "loss" else "share_gain"
    # La zone affectée doit atteindre la proportion minimale de pixels détectés.
    a, c = affected[key], control[key]
    if a < MIN_SHARE:
        return False, f"only {100 * a:.0f}% of the affected box is flagged (needs {100 * MIN_SHARE:.0f}%)"
    # Le changement détecté doit être suffisamment supérieur à celui de la zone témoin.
    if a < MIN_RATIO * max(c, 0.01):
        return False, f"affected {100 * a:.0f}% vs control {100 * c:.0f}%: not {MIN_RATIO:g}x more"
    return True, f"affected {100 * a:.0f}% vs control {100 * c:.0f}%"


def evaluate_event(event: dict, run_flow=None) -> dict:
    """Exécute le pipeline et évalue un événement réel."""
    
        # Import différé pour permettre aux tests de fonctionner sans dépendre de Prefect.
    if run_flow is None:                      
        from pipeline.flows import change_detection_flow as run_flow
    from pipeline.caching import load_change
    run = run_flow(place=event["place"], before=event["before"], after=event["after"],
                   index=event["index"], half_size_km=event.get("half_size_km", config.DEFAULT_HALF_SIZE_KM))
    # Récupération des tableaux raster sauvegardés par le pipeline.
    result = load_change(run.cache_key)
    affected, control = box_stats(result, event["affected_box"]), box_stats(result, event["control_box"])
    passed, reason = judge(event["expected"], affected, control)
    return {"name": event["name"], "expected": event["expected"], "affected": affected, "control": control,
            "passed": passed, "reason": reason, "from_cache": run.from_cache}


def to_markdown(rows: list[dict]) -> str:
    """Convertit les résultats de l'évaluation en tableau Markdown."""
    lines = ["| Event | Expected | Affected box | Control box | Result |", "|---|---|---|---|---|"]
    for r in rows:
        share = "share_loss" if r["expected"] == "loss" else "share_gain"
        a = f"{100 * r['affected'][share]:.0f}%" if r["affected"] else "n/a"
        c = f"{100 * r['control'][share]:.0f}%" if r["control"] else "n/a"
        lines.append(f"| {r['name']} | {r['expected']} | {a} flagged | {c} flagged | {'PASS' if r['passed'] else 'FAIL'}: {r['reason']} |")
    return "\n".join(lines)


def main() -> None:
    """Exécute l'évaluation et enregistre les résultats au format Markdown et JSON."""
    if not EVENTS:
        raise SystemExit("EVENTS is empty. Open eval/events.py, copy EXAMPLE_EVENT, and fill in 2 or 3 verified events.")
    rows = []
    for event in EVENTS:
        print(f"Running: {event['name']} ...")
        rows.append(evaluate_event(event))
    markdown = to_markdown(rows)
    print("\n" + markdown)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "events.md").write_text(markdown + "\n", encoding="utf-8")
    (RESULTS_DIR / "events.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
