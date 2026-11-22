"""HTML snippets for the redesigned UI. No Streamlit import: every function returns a string.

Safety rule: only fixed text from i18n.py and escaped values go into the HTML.
Text coming from the user or the LLM is always passed through html.escape.
Strings are built without leading spaces, because indented lines become code blocks in Markdown."""
import html

from app.brand import BRAND_MARK, BRAND_NAME
from app.i18n import t

STAGES = ("parse", "plan", "change", "climate", "write")


def _esc(value) -> str:
    return html.escape(str(value))


def _chip(dot: str, label: str, value: str) -> str:
    return (f'<span class="rg-chip"><span class="rg-dot rg-dot-{dot}"></span>'
            f'{_esc(label)} <b>{_esc(value)}</b></span>')


def status_chips(lang: str, model: str, prefect_ok: bool) -> str:
    prefect = t(lang, "status_connected") if prefect_ok else t(lang, "status_temporary")
    return ('<div class="rg-chips">'
            + _chip("info", t(lang, "status_model"), model)
            + _chip("ok" if prefect_ok else "warn", "Prefect", prefect)
            + "</div>")


def brand_header(lang: str) -> str:
    """Brand bar. Only things a user cares about: the data and that the AI runs locally."""
    return ('<div class="rg-header"><div class="rg-brand">'
            f'<div class="rg-logo">{_esc(BRAND_MARK)}</div><div>'
            f'<div class="rg-title">{_esc(BRAND_NAME)}</div>'
            f'<div class="rg-tagline">{_esc(t(lang, "tagline"))}</div></div></div>'
            '<div class="rg-chips">'
            '<span class="rg-chip"><span class="rg-dot rg-dot-info"></span><b>Sentinel-2</b> · 10 m</span>'
            f'<span class="rg-chip"><span class="rg-dot rg-dot-ok"></span>{_esc(t(lang, "chip_private"))}</span>'
            "</div></div>")


def sidebar_brand() -> str:
    return ('<div class="rg-side-brand">'
            f'<div class="rg-logo rg-logo-sm">{_esc(BRAND_MARK)}</div>'
            f'<div class="rg-title rg-title-sm">{_esc(BRAND_NAME)}</div></div>')


def section_title(text: str) -> str:
    return f'<div class="rg-section">{_esc(text)}</div>'


def hero(lang: str) -> str:
    tiles = "".join(
        f'<div class="rg-tile rg-tile-{kind}"><div class="rg-tile-title">{_esc(t(lang, f"tile_{kind}_title"))}</div>'
        f'<div class="rg-tile-text">{_esc(t(lang, f"tile_{kind}_text"))}</div></div>'
        for kind in ("veg", "burn", "water")
    )
    return ('<div class="rg-hero">'
            f'<div class="rg-hero-title">{_esc(t(lang, "hero_title"))}</div>'
            f'<div class="rg-hero-text">{_esc(t(lang, "hero_text"))}</div>'
            f'<div class="rg-tiles">{tiles}</div>'
            f'<div class="rg-hero-note">{_esc(t(lang, "slow_note"))}</div></div>')


def stepper(lang: str, done: list[str], failed: bool = False, note: str = "", running: bool = True) -> str:
    """Pipeline progress. `done` = graph nodes finished so far. While `running`, the first
    unfinished stage pulses; when the run is over, it is shown as stopped (or red if failed)."""
    finished = set(done)
    active = next((s for s in STAGES if s not in finished), None)
    items = []
    for number, stage in enumerate(STAGES, 1):
        if stage in finished:
            state, mark = "done", "✓"
        elif stage == active and failed:
            state, mark = "failed", "!"
        elif stage == active and running:
            state, mark = "active", str(number)
        else:
            state, mark = "pending", str(number)
        items.append(f'<div class="rg-step {state}"><span class="rg-dotn">{mark}</span>'
                     f'<span class="rg-steplabel">{_esc(t(lang, "stage_" + stage))}</span></div>')
    note_html = f'<div class="rg-stepnote">{_esc(note)}</div>' if note else ""
    return f'<div class="rg-stepcard"><div class="rg-stepper">{"".join(items)}</div>{note_html}</div>'


def report_title(text: str) -> str:
    return f'<div class="rg-report-title">{_esc(text)}</div>'


def insight(text: str) -> str:
    return f'<div class="rg-insight">{_esc(text)}</div>'


def limits_list(items: list[str]) -> str:
    return '<ul class="rg-limits">' + "".join(f"<li>{_esc(i)}</li>" for i in items) + "</ul>"


def legend(lang: str) -> str:
    return ('<div class="rg-legend">'
            f'<span><i class="rg-sw rg-sw-loss"></i>{_esc(t(lang, "legend_loss"))}</span>'
            f'<span><i class="rg-sw rg-sw-gain"></i>{_esc(t(lang, "legend_gain"))}</span>'
            f'<span><i class="rg-sw rg-sw-none"></i>{_esc(t(lang, "legend_none"))}</span></div>')


def footer_chips(lang: str, source: str | None, elapsed: float | None) -> str:
    chips = []
    if source:
        key = "source_llm" if source == "llm" else "source_rules"
        chips.append(f'<span class="rg-chip"><span class="rg-dot rg-dot-{"ok" if source == "llm" else "info"}"></span>'
                     f'{_esc(t(lang, key))}</span>')
    if elapsed:
        chips.append(f'<span class="rg-chip">{_esc(t(lang, "elapsed"))} <b>{elapsed:.0f} s</b></span>')
    return f'<div class="rg-chips rg-footer">{"".join(chips)}</div>' if chips else ""
