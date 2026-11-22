"""Parsing benchmark: how well does the LLM parser read questions, compared with a regex baseline?

Metrics (see eval/questions.py for the 47 labelled questions):
  - field accuracy on complete questions: place, season, years, index, distance
  - exact match: all five fields right
  - problem accuracy on ALL questions: does the agent ask for exactly what is missing / invalid?
    (the safety net: a wrong parse that looks complete would start a 2-minute analysis for nothing)

Usage, from the project root:
    python -m eval.parsing_benchmark                  # baseline + LLM (needs Ollama, about 15 min)
    python -m eval.parsing_benchmark --parser baseline
    python -m eval.parsing_benchmark --limit 10
"""
import argparse
import json
import re
import time
import unicodedata
from collections import defaultdict
from datetime import date

import config
from agent.llm import LLMError
from agent.parser import ParseError, ParsedRequest
from agent.planner import find_problems
from eval.baseline_parser import baseline_parse
from eval.questions import QUESTIONS

RESULTS_DIR = config.ROOT_DIR / "eval" / "results"
FIELDS = ("place", "season", "years", "index", "distance")


def _norm(text: str | None) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[-'’]", " ", text)).strip()


def score_fields(expected: dict, request: ParsedRequest | None) -> dict[str, bool]:
    if request is None:
        return {field: False for field in FIELDS}
    exp_years = sorted(expected["years"]) if expected["years"] else None
    got_years = (sorted([request.before_year, request.after_year])
                 if request.before_year is not None and request.after_year is not None else None)
    distance_ok = (request.distance_km is None if expected["distance_km"] is None
                   else request.distance_km == expected["distance_km"]
                   and (request.distance_kind or "radius") == expected["distance_kind"])
    return {
        "place": _norm(request.place) == _norm(expected["place"]),
        "season": request.season == expected["season"],
        "years": got_years == exp_years,
        "index": request.index == expected["index"],
        "distance": distance_ok,
    }


def evaluate(parse_fn, cases=QUESTIONS, today: date | None = None) -> dict:
    """Run `parse_fn(question) -> ParsedRequest` on every case and score it."""
    field_hits = defaultdict(int)
    complete = exact = errors = 0
    problem_hits = defaultdict(lambda: [0, 0])      # kind -> [correct, total]
    lang_exact = defaultdict(lambda: [0, 0])
    hard = [0, 0]                                   # exact matches on the "hard" subset
    seconds, failures = [], []

    for item in cases:
        start = time.perf_counter()
        try:
            request = parse_fn(item["question"])
        except (ParseError, LLMError):
            request, errors = None, errors + 1
        seconds.append(time.perf_counter() - start)

        problems = sorted(find_problems(request, today)) if request is not None else ["parse_error"]
        problem_ok = problems == sorted(item["problems"])
        problem_hits[item["kind"]][0] += problem_ok
        problem_hits[item["kind"]][1] += 1

        fields = score_fields(item["expected"], request)
        if item["kind"] == "complete":
            complete += 1
            for name, ok in fields.items():
                field_hits[name] += ok
            all_ok = all(fields.values())
            exact += all_ok
            lang_exact[item["lang"]][0] += all_ok
            lang_exact[item["lang"]][1] += 1
            if item.get("hard"):
                hard[0] += all_ok
                hard[1] += 1
        if not problem_ok or (item["kind"] == "complete" and not all(fields.values())):
            failures.append({"question": item["question"], "kind": item["kind"],
                             "wrong_fields": [n for n, ok in fields.items() if not ok] if item["kind"] == "complete" else [],
                             "expected_problems": item["problems"], "got_problems": problems,
                             "got": request.model_dump() if request else None})

    total_problem = sum(v[1] for v in problem_hits.values())
    return {
        "n": len(cases), "complete_n": complete, "errors": errors,
        "field_accuracy": {f: field_hits[f] / complete for f in FIELDS} if complete else {},
        "exact_match": exact / complete if complete else 0.0,
        "exact_match_by_lang": {k: v[0] / v[1] for k, v in lang_exact.items()},
        "exact_match_hard": hard[0] / hard[1] if hard[1] else 0.0, "hard_n": hard[1],
        "problem_accuracy": sum(v[0] for v in problem_hits.values()) / total_problem if total_problem else 0.0,
        "problem_accuracy_by_kind": {k: v[0] / v[1] for k, v in problem_hits.items()},
        "seconds_mean": sum(seconds) / len(seconds) if seconds else 0.0,
        "failures": failures,
    }


def to_markdown(results: dict[str, dict]) -> str:
    names = list(results)
    pct = lambda x: f"{100 * x:.0f}%"
    rows = [("Questions (complete, of which hard / all)", lambda r: f"{r['complete_n']}, {r['hard_n']} / {r['n']}")]
    rows += [(f"Accuracy: {f}", lambda r, f=f: pct(r["field_accuracy"][f])) for f in FIELDS]
    rows += [
        ("**Exact match (all fields)**", lambda r: f"**{pct(r['exact_match'])}**"),
        ("Exact match, free phrasing (hard)", lambda r: pct(r["exact_match_hard"])),
        ("Exact match, English", lambda r: pct(r["exact_match_by_lang"].get("en", 0))),
        ("Exact match, French", lambda r: pct(r["exact_match_by_lang"].get("fr", 0))),
        ("Asks for the right missing info (missing)", lambda r: pct(r["problem_accuracy_by_kind"].get("missing", 0))),
        ("Rejects invalid requests (invalid)", lambda r: pct(r["problem_accuracy_by_kind"].get("invalid", 0))),
        ("**Correct decision, all questions**", lambda r: f"**{pct(r['problem_accuracy'])}**"),
        ("Model errors", lambda r: str(r["errors"])),
        ("Mean time per question", lambda r: f"{r['seconds_mean']:.2f} s"),
    ]
    lines = ["| Metric | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    lines += [f"| {label} | " + " | ".join(fn(results[n]) for n in names) + " |" for label, fn in rows]
    return "\n".join(lines)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parser", choices=("llm", "baseline", "both"), default="both")
    ap.add_argument("--limit", type=int, default=None, help="only the first N questions")
    args = ap.parse_args(argv)
    cases = QUESTIONS[: args.limit] if args.limit else QUESTIONS

    results = {}
    if args.parser in ("baseline", "both"):
        results["Regex baseline"] = evaluate(baseline_parse, cases)
    if args.parser in ("llm", "both"):
        from agent.parser import parse_question
        print(f"Running the LLM parser on {len(cases)} questions (about 15 s each)...")
        try:
            results[f"LLM ({config.OLLAMA_MODEL})"] = evaluate(parse_question, cases)
        except LLMError as exc:
            raise SystemExit(f"Cannot reach the local LLM: {exc}")

    markdown = to_markdown(results)
    print("\n" + markdown)
    for name, res in results.items():
        shown = res["failures"][:8]
        if shown:
            print(f"\nFirst {len(shown)} failures of {name} ({len(res['failures'])} in total):")
            for f in shown:
                print(f"  [{f['kind']}] {f['question']}\n      wrong={f['wrong_fields']} expected_problems={f['expected_problems']} "
                      f"got_problems={f['got_problems']}\n      got={f['got']}")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "parsing_benchmark.md").write_text(markdown + "\n", encoding="utf-8")
    (RESULTS_DIR / "parsing_benchmark.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to {RESULTS_DIR}")


if __name__ == "__main__":
    main()
