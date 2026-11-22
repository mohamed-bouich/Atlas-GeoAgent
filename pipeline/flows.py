"""Flows Prefect : orchestration, nouvelles tentatives et cache autour des outils.

Les outils restent de simples fonctions Python. Prefect apporte les mécanismes
nécessaires au pipeline : nouvelles tentatives en cas de problèmes réseau,
journaux structurés et historique des exécutions consultable.
"""

from datetime import date
import requests
from prefect import flow,get_run_logger,task
from prefect.cache_policies import NO_CACHE
from pydantic import BaseModel
from pystac_client.exceptions import APIError
from rasterio.errors import RasterioError
import config
from pipeline.caching import load_change,make_key,save_change
from tools.change import (
    DEFAULT_THRESHOLDS, ChangeResult, ChangeSummary, PeriodResult,
    build_change_result, period_composite, validate_request,
)
from tools.geocoding import bbox_around_point,geocode
from tools.schemas import BBox,GeocodeResult

# Exceptions considérées comme temporaires et pouvant justifier une nouvelle tentative.
TRANSIENT= (requests.RequestException,APIError,RasterioError)

def _is_transient(exc: BaseException | None) -> bool:
    """Vrai si l'erreur, ou l'une de ses causes, est un problème réseau ou d'E/S.

    Nos outils encapsulent les erreurs de bas niveau (raise ... from exc), nous remontons donc la chaîne.
    Le message « Aucune scène trouvée » n'a pas de cause de ce type, il n'est donc PAS réessayé (cela échouerait à nouveau).
    """
    while exc is not None:
        if isinstance(exc, TRANSIENT):
            return True
        exc = exc.__cause__
    return False


def _retry_if_transient(task, task_run, state) -> bool:
    """Déclenche une nouvelle tentative uniquement pour les erreurs temporaires."""
    return _is_transient(state.result(raise_on_failure=False))


@task(name="geocode", retries=2, retry_delay_seconds=2,
      retry_condition_fn=_retry_if_transient, cache_policy=NO_CACHE)
def geocode_task(place: str) -> GeocodeResult:
    return geocode(place)


@task(name="period-composite", task_run_name="period-{label}", retries=2, retry_delay_seconds=5,
      retry_condition_fn=_retry_if_transient, cache_policy=NO_CACHE)
def period_task(bbox: BBox, period: tuple[date, date], index: str, label: str) -> PeriodResult:
    return period_composite(bbox, period, index)


@task(name="combine-change", cache_policy=NO_CACHE)
def combine_task(before: PeriodResult, after: PeriodResult, index: str,
                 threshold: float | None) -> ChangeResult:
    return build_change_result(before, after, index, threshold)


class ChangeRun(BaseModel):
    """Résultat transmis à l'agent : résumé des changements et emplacement des fichiers."""

    place: str
    cache_key: str      # Les fichiers sont stockés dans data/cache/<cache_key>/
    from_cache: bool
    summary: ChangeSummary


@flow(name="change-detection")
def change_detection_flow(
    place: str,
    before: tuple[date, date],
    after: tuple[date, date],
    index: str = "ndvi",
    threshold: float | None = None,
    half_size_km: float = config.DEFAULT_HALF_SIZE_KM,
    use_cache: bool = True,
) -> ChangeRun:
    logger = get_run_logger()
    # Validation anticipée : arrêter le traitement avant tout téléchargement
    # si les paramètres de la demande ne sont pas valides.
    validate_request(index, before, after)   

    geo = geocode_task(place)
    bbox = bbox_around_point(geo.lat, geo.lon, half_size_km)

    if threshold is None:
        # Résoudre le seuil avant de générer la clé pour obtenir la même clé
        # qu'un appel utilisant explicitement la valeur par défaut.
        threshold = DEFAULT_THRESHOLDS.get(index)  # resolve first: None and 0.15 must share a key
    key = make_key(
        "change",
        bbox=[round(v, 5) for v in bbox.as_list()],
        before=[d.isoformat() for d in before],
        after=[d.isoformat() for d in after],
        index=index,
        threshold=threshold,
    )

    if use_cache and (cached := load_change(key)) is not None:
        logger.info("Cache hit %s", key)
        return ChangeRun(place=geo.display_name, cache_key=key, from_cache=True, summary=cached.summary)

    logger.info("Cache miss %s: computing both periods in parallel", key)

     # .submit() lance chaque tâche dans un thread de travail et retourne
     # immédiatement un objet Future. Les deux périodes sont ainsi traitées
    # en parallèle, car les téléchargements constituent l'essentiel du travail.
    before_future = period_task.submit(bbox, before, index, label="before")
    after_future = period_task.submit(bbox, after, index, label="after")
    before_result, after_result = before_future.result(), after_future.result()

    result = combine_task(before_result, after_result, index, threshold)
    save_change(key, result)
    return ChangeRun(place=geo.display_name, cache_key=key, from_cache=False, summary=result.summary)
