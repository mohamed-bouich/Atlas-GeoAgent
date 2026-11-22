"""Report export (pure functions, no Streamlit): attribution and a meaningful file name."""
import re
import unicodedata

from app.brand import BRAND_NAME, BRAND_SLUG
from app.i18n import t


def export_text(content: str, lang: str, date_str: str) -> str:
    """The report plus the data attribution and the generation date, for sharing."""
    return (f"{content}\n\n---\n\n{t(lang, 'export_sources')}\n\n"
            f"{t(lang, 'export_generated').format(brand=BRAND_NAME, date=date_str)}\n")


def export_filename(facts: dict | None) -> str:
    parts = [str(facts.get(k, "")) for k in ("place", "before_year", "after_year")] if facts else []
    ascii_text = unicodedata.normalize("NFKD", "-".join(parts)).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return f"{BRAND_SLUG}_{slug}.md" if slug else f"{BRAND_SLUG}_report.md"
