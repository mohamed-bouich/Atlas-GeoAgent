"""Controlled experiment: can the detector find changes we inject, and what does it falsely flag?

Synthetic NDVI scenes: a smooth landscape, per-scene noise, and a few dark outliers (clouds, shadows).
We inject loss and gain patches of a known size and compare, with the SAME code as the real pipeline
(median_composite -> difference -> classify_change), a single scene against a median of 3 scenes.

    python -m eval.synthetic
Writes eval/results/synthetic.md.  Offline, deterministic, about 10 seconds.
"""
import numpy as np

import config
from tools.change import classify_change, difference, median_composite

RESULTS_DIR = config.ROOT_DIR / "eval" / "results"
SHAPE = (300, 300)


def smooth_field(shape, rng, sigma: float = 12.0) -> np.ndarray:
    """A NDVI-like landscape (0.15 to 0.65): Gaussian-smoothed noise."""
    noise = rng.normal(size=shape)
    fy = np.fft.fftfreq(shape[0])[:, None]
    fx = np.fft.fftfreq(shape[1])[None, :]
    kernel = np.exp(-2 * (np.pi * sigma) ** 2 * (fx ** 2 + fy ** 2))
    field = np.real(np.fft.ifft2(np.fft.fft2(noise) * kernel))
    field = (field - field.min()) / (field.max() - field.min())
    return 0.15 + 0.5 * field


def make_truth(shape, rng, magnitude: float, n_patches: int = 12, size_range=(12, 30)) -> np.ndarray:
    """Change field: 0 almost everywhere, -magnitude (loss) or +magnitude (gain) in square patches."""
    change = np.zeros(shape, dtype=np.float32)
    for i in range(n_patches):
        h, w = rng.integers(*size_range, size=2)
        r, c = rng.integers(0, shape[0] - h), rng.integers(0, shape[1] - w)
        change[r:r + h, c:c + w] = -magnitude if i % 2 == 0 else magnitude
    return change


def make_period(truth_image, rng, noise_sigma: float, n_scenes: int,
                outlier_rate: float = 0.03, outlier_value: float = -0.5) -> list[np.ndarray]:
    layers = []
    for _ in range(n_scenes):
        layer = truth_image + rng.normal(0, noise_sigma, truth_image.shape)
        outliers = rng.random(truth_image.shape) < outlier_rate          # cloud shadow / residual cloud
        layer[outliers] = truth_image[outliers] + outlier_value
        layers.append(layer.astype(np.float32))
    return layers


def run_trial(magnitude: float, noise_sigma: float, n_scenes: int, threshold: float = 0.15, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    base = smooth_field(SHAPE, rng)
    change = make_truth(SHAPE, rng, magnitude)
    before = median_composite(make_period(base, rng, noise_sigma, n_scenes))
    after = median_composite(make_period(base + change, rng, noise_sigma, n_scenes))
    classes = classify_change(difference(before, after), threshold)

    loss, gain, stable = change < 0, change > 0, change == 0
    flagged = classes != 0
    correct = ((classes == -1) & loss) | ((classes == 1) & gain)
    precision = correct.sum() / flagged.sum() if flagged.any() else 1.0
    recall = (correct.sum() / (loss | gain).sum())
    return {"recall": float(recall), "false_positive_rate": float(flagged[stable].mean()),
            "precision": float(precision), "f1": float(2 * precision * recall / (precision + recall)) if precision + recall else 0.0}


def grid(magnitudes=(0.10, 0.20, 0.30, 0.50), noises=(0.03, 0.06, 0.10), scenes=(1, 3), seeds=(0, 1, 2)) -> list[dict]:
    rows = []
    for noise in noises:
        for magnitude in magnitudes:
            for n in scenes:
                trials = [run_trial(magnitude, noise, n, seed=s) for s in seeds]
                rows.append({"noise": noise, "magnitude": magnitude, "scenes": n,
                             **{k: float(np.mean([t[k] for t in trials])) for k in trials[0]}})
    return rows


def to_markdown(rows: list[dict]) -> str:
    lines = ["| Noise (σ) | True change | Scenes | Recall | False positives | Precision | F1 |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['noise']:.2f} | ±{r['magnitude']:.2f} | {'median of 3' if r['scenes'] == 3 else 'single'} | "
                     f"{100 * r['recall']:.0f}% | {100 * r['false_positive_rate']:.1f}% | {100 * r['precision']:.0f}% | {100 * r['f1']:.0f}% |")
    return "\n".join(lines)


def main() -> None:
    markdown = ("Threshold ±0.15, 3% dark outliers per scene, mean of 3 random landscapes.\n\n" + to_markdown(grid()))
    print(markdown)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "synthetic.md").write_text(markdown + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
