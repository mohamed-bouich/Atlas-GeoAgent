"""Presentation only: split the report text (built by agent/writer.py) into sections.
No Streamlit import and no data is changed; if the text has another shape, we return None
and the app shows it as plain text."""
import re

_LABEL = re.compile(r"^- ([^:]+?)\s*:\s*(.+)$")
_LIMITS_PREFIX = re.compile(r"^- (Limits|Limites)\s*:\s*", re.IGNORECASE)


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


def split_report(content: str) -> dict | None:
    lines = [line.rstrip() for line in content.splitlines()]
    title = None
    findings: list[str] = []
    limits: list[str] = []
    rest: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if title is None and stripped.startswith("**") and stripped.endswith("**") and len(stripped) > 4:
            title = stripped.strip("*").strip()
        elif _LIMITS_PREFIX.match(stripped):
            body = _LIMITS_PREFIX.sub("", stripped).strip().rstrip(".")
            limits = [_capitalize(part.strip()) for part in body.split(";") if part.strip()]
        elif stripped.startswith("- "):
            match = _LABEL.match(stripped)
            findings.append(f"- **{match.group(1)}**: {match.group(2)}" if match else stripped)
        else:
            rest.append(stripped)

    if not findings:
        return None
    return {"title": title, "findings": findings, "limits": limits, "interpretation": " ".join(rest)}
