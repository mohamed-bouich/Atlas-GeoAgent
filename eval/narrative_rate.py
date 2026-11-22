"""How often does the local 7B model write an acceptable sentence?

Calls ONLY the LLM (no pipeline), N times, alternating between two real situations:
  A) your 2023 -> 2024 result (stable, wetter)
  B) your 2021 -> 2025 result (increase, drier)
Needs Ollama. About 15 s per sample.   Usage (from the project root):
    python -m eval.narrative_rate 6
"""
import json
import sys
import time

from agent.llm import chat_text
from agent.parser import ParsedRequest
from agent.planner import make_plan
from agent.prompts import narrative_system
from agent.writer import build_facts, check_narrative, clean_narrative, llm_view
from tools.change import ChangeSummary
from tools.climate import ClimateSummary


def summary(**kw) -> ChangeSummary:
    base = dict(index="ndvi", threshold=0.15, before_scenes=["a", "b", "c"], after_scenes=["d", "e", "f"],
                valid_fraction=0.3847, stable_ha=3800.0)
    return ChangeSummary(**{**base, **kw})


def climate(mm: float) -> ClimateSummary:
    return ClimateSummary(start="x", end="y", days_with_data=365, mean_temp_c=19.0, total_precip_mm=mm, rainy_days=40)


def situations() -> list[tuple[str, dict]]:
    a = build_facts(
        make_plan(ParsedRequest(place="Al Hoceima", season="summer", before_year=2023, after_year=2024)),
        summary(mean_change=-0.00065, loss_ha=49.16, gain_ha=28.37, loss_pct=1.2566, gain_pct=0.7252),
        (climate(172.1), climate(247.7)),
    )
    b = build_facts(
        make_plan(ParsedRequest(place="Al Hoceima", season="summer", before_year=2021, after_year=2025)),
        summary(mean_change=0.051, loss_ha=52.7, gain_ha=417.4, loss_pct=1.3, gain_pct=10.7),
        (climate(346.0), climate(252.0)),
    )
    return [("A stable/wetter", a), ("B increase/drier", b)]


def main(n: int) -> None:
    cases = situations()
    accepted = 0
    for i in range(1, n + 1):
        label, facts = cases[(i - 1) % 2]
        start = time.perf_counter()
        raw = chat_text(narrative_system("en"), json.dumps(llm_view(facts)), max_tokens=70)
        text = clean_narrative(raw)
        reason = check_narrative(text, facts)
        accepted += reason is None
        print(f"\n[{i}/{n}] {label} | {time.perf_counter() - start:.0f}s | {'ACCEPTED' if reason is None else 'REJECTED: ' + reason}\n{text or raw}")
    print(f"\nAccepted {accepted}/{n} ({100 * accepted / n:.0f}%). Rejected ones fall back to the rule-based sentence.")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 6)
