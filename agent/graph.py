"""The LangGraph agent.

parse (LLM) -> [clarify | plan] -> change (Prefect flow) -> [climate | replan | error]
            -> climate -> write (template + LLM interpretation, grounded) -> END
"""
import logging
from datetime import timedelta
from typing import Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from agent import settings
from agent.llm import LLMError
from agent.parser import ParsedRequest, ParseError, parse_question
from agent.planner import PROBLEM_TEXT, Plan, find_problems, make_plan, widen
from agent.writer import build_facts, write_report
from pipeline.flows import ChangeRun, change_detection_flow
from tools.change import ChangeDetectionError
from tools.climate import ClimateError, get_climate
from tools.geocoding import GeocodingError, geocode

logger = logging.getLogger(__name__)

STEP_LABELS = {
    "parse": "Question understood",
    "clarify": "More information needed",
    "plan": "Plan made",
    "change": "Change analysis finished",
    "replan": "Replanned with a wider period",
    "climate": "Climate context fetched",
    "write": "Report written",
    "error": "Stopped with an error",
}

MESSAGES = {
    "en": {"clarify": "To run the analysis I still need: {items}.",
           "error": "Sorry, I could not complete this analysis: {error}"},
    "fr": {"clarify": "Pour lancer l'analyse, il me manque encore : {items}.",
           "error": "Désolé, je n'ai pas pu terminer cette analyse : {error}"},
}


class AgentState(TypedDict, total=False):
    question: str
    lang: str
    request: ParsedRequest
    problems: list[str]
    plan: Plan
    run: ChangeRun
    climate: tuple
    facts: dict
    answer: str
    grounded: bool
    rejected: str | None
    source: str
    reject_reason: str | None
    error: str | None
    retry: bool
    attempts: int


# ---------- nodes ----------

def parse_node(state: AgentState) -> dict:
    try:
        request = parse_question(state["question"])
    except (ParseError, LLMError) as exc:
        return {"error": str(exc)}
    return {"request": request, "problems": find_problems(request)}


def clarify_node(state: AgentState) -> dict:
    lang = state.get("lang") or settings.REPORT_LANGUAGE
    items = "; ".join(PROBLEM_TEXT[lang][p] for p in state["problems"])
    return {"answer": MESSAGES[lang]["clarify"].format(items=items)}


def plan_node(state: AgentState) -> dict:
    return {"plan": make_plan(state["request"])}


def change_node(state: AgentState) -> dict:
    plan = state["plan"]
    try:
        run = change_detection_flow(
            place=plan.place, before=plan.before, after=plan.after, index=plan.index,
            half_size_km=plan.half_size_km,
        )
    except (ChangeDetectionError, GeocodingError) as exc:
        can_retry = "No scene" in str(exc) and state.get("attempts", 0) < settings.MAX_REPLANS
        return {"error": str(exc), "retry": can_retry}
    return {"run": run, "error": None, "retry": False}


def replan_node(state: AgentState) -> dict:
    wider = widen(state["plan"])
    logger.info("Replanning: before=%s after=%s", wider.before, wider.after)
    return {"plan": wider, "attempts": state.get("attempts", 0) + 1, "error": None, "retry": False}


def climate_node(state: AgentState) -> dict:
    """Soft step: if climate data is unavailable, the report is still produced."""
    plan = state["plan"]
    try:
        geo = geocode(plan.place)
        lat, lon = round(geo.lat, 3), round(geo.lon, 3)
        windows = [(end - timedelta(days=364), end) for _, end in (plan.before, plan.after)]
        before, after = (get_climate(lat, lon, start, end) for start, end in windows)
    except (GeocodingError, ClimateError) as exc:
        logger.warning("Climate skipped: %s", exc)
        return {"climate": None}
    return {"climate": (before, after)}


def write_node(state: AgentState) -> dict:
    facts = build_facts(state["plan"], state["run"].summary, state.get("climate"))
    report = write_report(facts, state.get("lang"))
    return {"facts": facts, "answer": report.text, "grounded": report.grounded,
            "rejected": report.rejected, "reject_reason": report.reason, "source": report.source}


def error_node(state: AgentState) -> dict:
    lang = state.get("lang") or settings.REPORT_LANGUAGE
    return {"answer": MESSAGES[lang]["error"].format(error=state.get("error"))}


# ---------- routing ----------

def after_parse(state: AgentState) -> str:
    if state.get("error"):
        return "error"
    return "clarify" if state.get("problems") else "plan"


def after_change(state: AgentState) -> str:
    if state.get("run") is not None and not state.get("error"):
        return "climate"
    return "replan" if state.get("retry") else "error"


def build_graph():
    graph = StateGraph(AgentState)
    for name, fn in [("parse", parse_node), ("clarify", clarify_node), ("plan", plan_node),
                     ("change", change_node), ("replan", replan_node), ("climate", climate_node),
                     ("write", write_node), ("error", error_node)]:
        graph.add_node(name, fn)
    graph.add_edge(START, "parse")
    graph.add_conditional_edges("parse", after_parse, {"error": "error", "clarify": "clarify", "plan": "plan"})
    graph.add_edge("plan", "change")
    graph.add_conditional_edges("change", after_change, {"climate": "climate", "replan": "replan", "error": "error"})
    graph.add_edge("replan", "change")
    graph.add_edge("climate", "write")
    for terminal in ("write", "clarify", "error"):
        graph.add_edge(terminal, END)
    return graph.compile()


GRAPH = build_graph()


def run_agent(question: str, on_step: Callable[[str, dict], None] | None = None,
              lang: str | None = None) -> dict:
    """Run the agent. `on_step(node, update)` is called after each node (for live UI).
    `lang` ("en" or "fr") sets the language of the answer for this question only."""
    final: dict = {"question": question, "attempts": 0, "lang": lang or settings.REPORT_LANGUAGE}
    for chunk in GRAPH.stream(dict(final), stream_mode="updates"):
        for node, update in chunk.items():
            final.update(update or {})
            if on_step:
                on_step(node, update or {})
    return final
