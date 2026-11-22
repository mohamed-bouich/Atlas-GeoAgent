
"""Détection des changements d'un indice spectral (NDVI, NBR, NDWI) entre deux périodes.

Pipeline : sélection des meilleures scènes sans nuages -> calcul de l'indice
par scène -> composite médian (réduction des nuages résiduels et du bruit)
-> différence entre les périodes -> classification des changements.

Le traitement est divisé en trois étapes publiques afin de permettre au
workflow Prefect d'exécuter les deux périodes en parallèle :
validate_request -> period_composite (x2) -> build_change_result.
"""
import logging  
import warnings  # Gestion des avertissements NumPy lors du calcul des composites
from dataclasses import dataclass
from datetime import date
import numpy as np
from affine import Affine  # Conservation de la référence spatiale des résultats raster
from pydantic import BaseModel  # Validation et structuration du résumé destiné à l'agent.
from tools.indices import (
    INDEX_BANDS, cloud_mask, compute_index, to_reflectance, water_mask,)
from tools.raster import RasterReadError, read_bands
from tools.search_imagery import ImagerySearchError, search_imagery
from tools.schemas import BBox

logger = logging.getLogger(__name__)

# Variation absolue minimale considérée comme un changement significatif.
# Ces seuils doivent être justifiés dans le rapport et ajustés lors de l'évaluation .
DEFAULT_THRESHOLDS = {"ndvi": 0.15, "nbr": 0.10, "ndwi": 0.15}


class ChangeDetectionError(Exception):
    """Erreur levée lorsqu'un changement ne peut pas être calculé."""


class ChangeSummary(BaseModel):
    """Résumé statistique destiné au LLM, sans transmission des pixels bruts."""

    index: str
    threshold: float
    before_scenes: list[str]
    after_scenes: list[str]
    valid_fraction: float
    mean_change: float | None
    loss_ha: float
    gain_ha: float
    stable_ha: float
    loss_pct: float    # Pourcentage de la surface valide, calculé ici et non par le LLM.
    gain_pct: float


@dataclass
class PeriodResult:
    """Médiane composite sur une période."""
   

    image: np.ndarray  
    scene_ids: list[str]    
    transform: Affine
    crs: str


@dataclass
class ChangeResult:
    """Résultat spatial et statistique de la détection des changements."""
    delta: np.ndarray     # Différence après - avant, avec NaN pour les pixels invalides.
    classes: np.ndarray    # -1 : perte, 0 : stable ou invalide, +1 : gain.
    transform: Affine
    crs: str
    summary: ChangeSummary


# ---------- Fonctions pures (testées unitairement, sans accès réseau ni fichiers) ----------

def median_composite(layers: list[np.ndarray]) -> np.ndarray:
    """Per-pixel median over scenes, ignoring NaN."""
    stack = np.stack(layers)
    with warnings.catch_warnings():
        # Les avertissements liés aux pixels entièrement NaN sont attendus.
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN pixels are expected
        return np.nanmedian(stack, axis=0).astype(np.float32)


def difference(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """Calcule la différence après - avant en conservant les valeurs NaN."""
    return (after - before).astype(np.float32)


def classify_change(delta: np.ndarray, threshold: float) -> np.ndarray:
    """Classe les pixels selon le seuil : -1 (perte), 0 (stable), +1 (gain)."""
    classes = np.zeros(delta.shape, dtype=np.int8)
    classes[delta <= -threshold] = -1   # Les comparaisons avec NaN retournent False.
    classes[delta >= threshold] = 1
    return classes


def summarize_change(delta: np.ndarray, pixel_area_ha: float, threshold: float) -> dict[str, float | None]:
    """Calcule les statistiques de changement et les surfaces correspondantes en hectares."""
    finite = np.isfinite(delta)
    classes = classify_change(delta, threshold)
    valid_ha = float(finite.sum() * pixel_area_ha)
    loss_ha = float((classes == -1).sum() * pixel_area_ha)
    gain_ha = float((classes == 1).sum() * pixel_area_ha)
    return {
        "valid_fraction": float(finite.mean()),
        "mean_change": float(delta[finite].mean()) if finite.any() else None,
        "loss_ha": loss_ha,
        "gain_ha": gain_ha,
        "stable_ha": float(((classes == 0) & finite).sum() * pixel_area_ha),
        "loss_pct": 100 * loss_ha / valid_ha if valid_ha else 0.0,
        "gain_pct": 100 * gain_ha / valid_ha if valid_ha else 0.0,
    }


def validate_request(index: str, before: tuple[date, date], after: tuple[date, date]) -> None:
    """Échouer rapidement : vérifiez la requête AVANT de passer plusieurs minutes à la télécharger."""
    if index not in INDEX_BANDS:
        raise ChangeDetectionError(f"Unknown index '{index}'. Choose from {sorted(INDEX_BANDS)}.")
    if before[0] > before[1] or after[0] > after[1]:
        raise ChangeDetectionError("Each period must start before it ends.")
    if before[1] >= after[0]:
        raise ChangeDetectionError("The 'before' period must end before the 'after' period starts.")


def build_change_result(before: PeriodResult, after: PeriodResult, index: str, threshold: float | None) -> ChangeResult:
    """Combine les composites des deux périodes pour produire le résultat final."""
    if before.image.shape != after.image.shape:
        raise ChangeDetectionError("Before and after images are on different grids.")
    threshold = DEFAULT_THRESHOLDS[index] if threshold is None else threshold

    delta = difference(before.image, after.image)
    # Surface d'un pixel en hectares (UTM : coordonnées exprimées en mètres).
    pixel_area_ha = abs(before.transform.a * before.transform.e) / 10_000  # m2 -> hectares (UTM = metres)
    summary = ChangeSummary(
        index=index, threshold=threshold,
        before_scenes=before.scene_ids, after_scenes=after.scene_ids,
        **summarize_change(delta, pixel_area_ha, threshold),
    )
    return ChangeResult(delta=delta, classes=classify_change(delta, threshold),
                        transform=before.transform, crs=before.crs, summary=summary)


# ---------- Accès aux données et traitement des scènes ----------

def period_composite(bbox: BBox, period: tuple[date, date], index: str,
                     max_scenes: int = 3, min_coverage: float = 0.9) -> PeriodResult:
    """Construit le composite médian des meilleures scènes d'une période (avec accès réseau)."""
    start, end = period
    try:
        found = search_imagery(bbox, start, end, limit=10)
        band_names = tuple(sorted(set(INDEX_BANDS[index])))

        layers: list[np.ndarray] = []
        ids: list[str] = []
        transform, crs = None, None

        for item in found.items:
            # Vérification préalable : lecture de la seule couche SCL pour évaluer la couverture.
            # Les scènes insuffisamment couvertes sont écartées avant le téléchargement des bandes.
            # La couverture correspond aux pixels non nuageux et non NoData.
            # L'eau est traitée séparément, car une AOI côtière peut être majoritairement maritime.
            probe = read_bands(item, bbox, ())
            usable = cloud_mask(probe.scl)
            if usable.mean() < min_coverage:
                continue
            if layers and usable.shape != layers[0].shape:
                logger.warning("Skipping %s: grid differs from the first scene", item.id)
                continue

            stack = read_bands(item, bbox, band_names)
            # L'eau est conservée pour le NDWI, mais exclue des analyses NDVI et NBR.
            valid = usable if index == "ndwi" else usable & ~water_mask(stack.scl)
            # Conversion des bandes brutes en réflectance à partir des métadonnées de chaque
            reflectance = {n: to_reflectance(stack.bands[n], item.scale, item.offset) for n in band_names}
            layer = compute_index(index, reflectance)
            layers.append(np.where(valid, layer, np.nan).astype(np.float32))
            ids.append(item.id)
            if transform is None:
                transform, crs = stack.transform, stack.crs
            if len(layers) >= max_scenes:
                break
    except (ImagerySearchError, RasterReadError) as exc:
        # Préserve la chaîne d'exceptions pour permettre la gestion des tentatives de reprise.
        raise ChangeDetectionError(str(exc)) from exc   

    if not layers:
        raise ChangeDetectionError(
            f"No scene between {start} and {end} covers the area well enough. "
            "Try a longer period."
        )
    return PeriodResult(image=median_composite(layers), scene_ids=ids, transform=transform, crs=crs)


def detect_change(
    bbox: BBox,
    before: tuple[date, date],
    after: tuple[date, date],
    index: str = "ndvi",
    threshold: float | None = None,
    max_scenes: int = 3,
    min_coverage: float = 0.9,
) -> ChangeResult:
    """Version séquentielle (simple, utilisée dans les tests et les scripts). Le flux Prefect
    exécute quant à lui les deux appels à `period_composite` en parallèle."""
    validate_request(index, before, after)
    b = period_composite(bbox, before, index, max_scenes, min_coverage)
    a = period_composite(bbox, after, index, max_scenes, min_coverage)
    return build_change_result(b, a, index, threshold)
