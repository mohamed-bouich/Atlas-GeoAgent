"""Streamlit app: ask in English or French, watch the agent work, see the numbers and the map.

Run from the project root:   streamlit run app/streamlit_app.py
The product name lives in app/brand.py.
"""
import os
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:          # Streamlit only adds app/ to the path
    sys.path.insert(0, str(ROOT))


def _prefect_server_up() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:4200/api/health", timeout=0.5):
            return True
    except OSError:
        return False


PREFECT_DEDICATED = _prefect_server_up()
if PREFECT_DEDICATED:   # must be set BEFORE prefect is imported (agent.graph imports it)
    os.environ.setdefault("PREFECT_API_URL", "http://127.0.0.1:4200/api")

import streamlit as st  # noqa: E402
from streamlit_folium import st_folium  # noqa: E402

import config  # noqa: E402
from agent.graph import run_agent  # noqa: E402
from app import components as ui  # noqa: E402
from app.brand import BRAND_NAME  # noqa: E402
from app.export import export_filename, export_text  # noqa: E402
from app.i18n import t  # noqa: E402
from app.report_view import split_report  # noqa: E402
from app.styles import CSS  # noqa: E402
from app.viz import make_map  # noqa: E402
from pipeline.caching import load_change  # noqa: E402

st.set_page_config(page_title=BRAND_NAME, page_icon="🛰️", layout="wide", initial_sidebar_state="expanded")
st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
st.session_state.setdefault("messages", [])

# ---------------- sidebar ----------------
with st.sidebar:
    st.markdown(ui.sidebar_brand(), unsafe_allow_html=True)
    choice = st.radio("Language / Langue", ["English", "Français"], horizontal=True, key="lang_choice")
    lang = "fr" if choice == "Français" else "en"

    st.markdown(ui.section_title(t(lang, "examples_title")), unsafe_allow_html=True)
    for i, example in enumerate(t(lang, "examples")):
        if st.button(example, key=f"example_{i}", use_container_width=True):
            st.session_state["pending"] = example

    st.caption(t(lang, "slow_note"))
    with st.expander(t(lang, "system_title")):
        st.markdown(ui.status_chips(lang, config.OLLAMA_MODEL, PREFECT_DEDICATED), unsafe_allow_html=True)
        if not PREFECT_DEDICATED:
            st.caption(t(lang, "prefect_temp"))
        st.caption(t(lang, "sources"))
        st.caption(t(lang, "about"))
    if st.button(t(lang, "clear"), key="clear_chat"):
        st.session_state["messages"] = []
        st.rerun()


# ---------------- rendering ----------------
def render_metrics(facts: dict, index: int) -> None:
    """Metric cards. Values come from the agent's facts; nothing is recomputed here."""
    cards = []
    if facts.get("mean_change") is not None:
        cards.append(("m_mean", t(lang, "metric_mean").format(index=str(facts.get("index", "ndvi")).upper()),
                      f"{facts['mean_change']:+.3f}", t(lang, "threshold").format(value=facts.get("threshold", ""))))
    cards.append(("m_loss", t(lang, "metric_loss"), f"{facts['loss_ha']:.1f} ha",
                  f"{facts['loss_pct']:.1f}% {t(lang, 'of_land')}"))
    cards.append(("m_gain", t(lang, "metric_gain"), f"{facts['gain_ha']:.1f} ha",
                  f"{facts['gain_pct']:.1f}% {t(lang, 'of_land')}"))
    verdict = facts.get("verdict")
    cards.append((f"m_net_{'pos' if facts['net_pct'] >= 0 else 'neg'}", t(lang, "metric_net"),
                  f"{facts['net_pct']:+.1f} {t(lang, 'pp')}", t(lang, f"verdict_{verdict}") if verdict else None))
    if "rain_change_pct" in facts:
        before, after = facts.get("rain_before_mm"), facts.get("rain_after_mm")
        cards.append(("m_rain", t(lang, "metric_rain"), f"{facts['rain_change_pct']:+d}%",
                      f"{before} → {after} mm" if before is not None and after is not None else None))

    with st.container(key=f"metrics_{index}"):
        for column, (key, label, value, delta) in zip(st.columns(len(cards)), cards):
            with column, st.container(key=f"{key}_{index}"):
                st.metric(label, value, delta, delta_color="off")


def render_report(content: str, index: int) -> None:
    parts = split_report(content)
    with st.container(key=f"report_{index}"):
        if parts is None:          # clarification questions and error messages
            st.markdown(content)
            return
        if parts["title"]:
            st.markdown(ui.report_title(parts["title"]), unsafe_allow_html=True)
        st.markdown(ui.section_title(t(lang, "section_findings")), unsafe_allow_html=True)
        st.markdown("\n".join(parts["findings"]))
        if parts["interpretation"]:
            st.markdown(ui.section_title(t(lang, "section_interpretation")), unsafe_allow_html=True)
            st.markdown(ui.insight(parts["interpretation"]), unsafe_allow_html=True)
        if parts["limits"]:
            st.markdown(ui.section_title(t(lang, "section_limits")), unsafe_allow_html=True)
            st.markdown(ui.limits_list(parts["limits"]), unsafe_allow_html=True)


def render_map(key: str, index: int) -> None:
    result = load_change(key)
    if result is None:
        return
    with st.container(key=f"map_card_{index}"):
        st.markdown(ui.section_title(t(lang, "map_title")), unsafe_allow_html=True)
        try:
            st_folium(make_map(result), height=560, use_container_width=True,
                      returned_objects=[], key=f"map_{index}")
        except Exception:  # noqa: BLE001  UI boundary: a map problem must not hide the report
            st.warning(t(lang, "map_failed"))
        st.markdown(ui.legend(lang), unsafe_allow_html=True)


def render_extras(message: dict, index: int) -> None:
    """Everything below the progress stepper: metrics, report, map, footer."""
    if message.get("facts"):
        render_metrics(message["facts"], index)
    render_report(message["content"], index)
    if message.get("cache_key"):
        render_map(message["cache_key"], index)
    footer = ui.footer_chips(lang, message.get("source"), message.get("elapsed"))
    if footer:
        st.markdown(footer, unsafe_allow_html=True)
    st.download_button(
        t(lang, "download"),
        export_text(message["content"], message.get("lang", lang), date.today().isoformat()),
        file_name=export_filename(message.get("facts")), mime="text/markdown", key=f"download_{index}",
    )


def answer(question: str) -> None:
    start = time.perf_counter()
    with st.chat_message("assistant"):
        steps_slot = st.empty()
        done: list[str] = []

        def paint(note: str = "", failed: bool = False, running: bool = True) -> str:
            html_steps = ui.stepper(lang, done, failed=failed, note=note, running=running)
            steps_slot.markdown(html_steps, unsafe_allow_html=True)
            return html_steps

        paint()

        def on_step(node: str, update: dict) -> None:
            done.append(node)
            paint(f"{t(lang, 'step_' + node)} · {time.perf_counter() - start:.0f} s")

        try:
            state = run_agent(question, on_step=on_step, lang=lang)
        except Exception as exc:  # noqa: BLE001  UI boundary: never show a stack trace to the user
            paint(t(lang, "crashed"), failed=True, running=False)
            st.error(str(exc))
            return

        elapsed = time.perf_counter() - start
        if "error" in done:
            steps_html = paint(t(lang, "step_error"), failed=True, running=False)
        elif "clarify" in done:
            steps_html = paint(t(lang, "step_clarify"), running=False)
        else:
            steps_html = paint(f"{t(lang, 'done')} · {elapsed:.0f} s", running=False)

        run = state.get("run")
        message = {
            "role": "assistant", "content": state.get("answer", ""), "facts": state.get("facts"),
            "cache_key": run.cache_key if run else None,
            "source": state.get("source") if state.get("facts") else None,
            "elapsed": elapsed, "steps_html": steps_html, "lang": lang,
        }
        render_extras(message, len(st.session_state["messages"]))
        st.session_state["messages"].append(message)


# ---------------- page ----------------
st.markdown(ui.brand_header(lang), unsafe_allow_html=True)
hero_slot = st.empty()

for index, message in enumerate(st.session_state["messages"]):
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            if message.get("steps_html"):
                st.markdown(message["steps_html"], unsafe_allow_html=True)
            render_extras(message, index)
        else:
            st.markdown(message["content"])

question = st.chat_input(t(lang, "input")) or st.session_state.pop("pending", None)
if question:
    st.session_state["messages"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    answer(question)
elif not st.session_state["messages"]:
    hero_slot.markdown(ui.hero(lang), unsafe_allow_html=True)
