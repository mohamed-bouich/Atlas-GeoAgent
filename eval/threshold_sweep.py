"""Threshold sensitivity: how much do the reported loss and gain depend on the ±threshold?

Uses the results already in data/cache/ (no download, no LLM). Run after a few analyses:
    python -m eval.threshold_sweep              # every cached analysis
    python -m eval.threshold_sweep <cache_key>  # one analysis
Outputs a table (eval/results/threshold_sweep.md) and a plot per analysis (PNG).
"""
import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from rasterio.transform import array_bounds
from rasterio.warp import transform_bounds

import config
from pipeline.caching import load_change
from tools.change import DEFAULT_THRESHOLDS, summarize_change

THRESHOLDS = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30)
RESULTS_DIR = config.ROOT_DIR / "eval" / "results"


def sweep(delta, pixel_area_ha: float, thresholds=THRESHOLDS) -> list[dict]:
    rows = []
    for threshold in thresholds:
        s = summarize_change(delta, pixel_area_ha, threshold)
        rows.append({"threshold": threshold, "loss_ha": round(s["loss_ha"], 1), "gain_ha": round(s["gain_ha"], 1),
                     "loss_pct": round(s["loss_pct"], 2), "gain_pct": round(s["gain_pct"], 2)})
    return rows


def _year(scene_id: str) -> str:
    match = re.search(r"_(\d{4})\d{4}_", scene_id)
    return match.group(1) if match else "?"


def centre_and_size(result) -> tuple[float, float, float, float]:
    """(lat, lon, width_km, height_km) of the analysed zone, to tell analyses apart."""
    height, width = result.delta.shape
    west, south, east, north = transform_bounds(result.crs, "EPSG:4326", *array_bounds(height, width, result.transform))
    pixel_km = abs(result.transform.a) / 1000
    return (south + north) / 2, (west + east) / 2, width * pixel_km, height * pixel_km


def label(result, key: str) -> str:
    s = result.summary
    lat, lon, w_km, h_km = centre_and_size(result)
    return (f"{s.index.upper()} {_year(s.before_scenes[0])} to {_year(s.after_scenes[0])} | "
            f"lat {lat:.2f}, lon {lon:.2f} | zone {w_km:.0f} x {h_km:.0f} km ({key[:6]})")


def signature(result) -> tuple:
    """Two cache entries with the same scenes, place and size are the same analysis."""
    s = result.summary
    lat, lon, w_km, h_km = centre_and_size(result)
    return (s.index, tuple(s.before_scenes), tuple(s.after_scenes), round(lat, 2), round(lon, 2), round(w_km), round(h_km))


def cache_keys() -> list[str]:
    if not config.CACHE_DIR.exists():
        return []
    return sorted(p.name for p in config.CACHE_DIR.iterdir() if (p / "summary.json").exists())


def to_markdown(title: str, rows: list[dict], default: float) -> str:
    lines = [f"**{title}**", "", "| Threshold | Loss (ha) | Loss (%) | Gain (ha) | Gain (%) |", "|---|---|---|---|---|"]
    for r in rows:
        mark = " (default)" if abs(r["threshold"] - default) < 1e-9 else ""
        lines.append(f"| ±{r['threshold']:.2f}{mark} | {r['loss_ha']} | {r['loss_pct']} | {r['gain_ha']} | {r['gain_pct']} |")
    return "\n".join(lines)


def main(keys: list[str]) -> None:
    keys = keys or cache_keys()
    if not keys:
        raise SystemExit(f"Nothing in {config.CACHE_DIR}. Run a few analyses first (the app or demo_step4.py).")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    sections, seen = [], set()
    for key in keys:
        result = load_change(key)
        if result is None:
            print(f"Skipping {key}: incomplete cache entry")
            continue
        if signature(result) in seen:
            print(f"Skipping {key}: same analysis as one already listed")
            continue
        seen.add(signature(result))
        area_ha = abs(result.transform.a * result.transform.e) / 10_000
        rows = sweep(result.delta, area_ha)
        default = DEFAULT_THRESHOLDS.get(result.summary.index, 0.15)
        title = label(result, key)
        sections.append(to_markdown(title, rows, default))

        fig, ax = plt.subplots(figsize=(6, 4))
        xs = [r["threshold"] for r in rows]
        ax.plot(xs, [r["loss_ha"] for r in rows], "o-", color="#EF4444", label="Loss (ha)")
        ax.plot(xs, [r["gain_ha"] for r in rows], "o-", color="#22C55E", label="Gain (ha)")
        ax.axvline(default, color="grey", linestyle="--", label=f"Default ±{default}")
        ax.set(xlabel="Threshold (±)", ylabel="Hectares", title=title)
        ax.legend()
        fig.tight_layout()
        fig.savefig(RESULTS_DIR / f"threshold_{key[:8]}.png", dpi=150)
        plt.close(fig)
    markdown = "\n\n".join(sections)
    print(markdown)
    (RESULTS_DIR / "threshold_sweep.md").write_text(markdown + "\n", encoding="utf-8")
    print(f"\nSaved to {RESULTS_DIR}")


if __name__ == "__main__":
    main(sys.argv[1:])
