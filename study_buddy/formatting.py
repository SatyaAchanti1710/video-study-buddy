"""Formatting helpers used by the UI and the downloads."""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime

from .schema import StudyPackPayload


def bold_key_terms(text: str, key_terms: list[str]) -> str:
    """Bold the first occurrence of each key term, unless it is already bold.

    The prompt asks the model to do this itself; this is a deterministic safety
    net so the notes always satisfy the "bolded key terms" requirement.
    """
    result = text
    terms = sorted({term.strip().strip("*").strip() for term in key_terms}, key=len, reverse=True)
    for term in terms:
        if not term or f"**{term}**" in result:
            continue
        pattern = re.compile(r"(?<![\w*])" + re.escape(term) + r"(?![\w*])", re.IGNORECASE)
        updated, count = pattern.subn(lambda match: f"**{match.group(0)}**", result, count=1)
        if count:
            result = updated
    return result


def strip_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text, flags=re.MULTILINE)
    return text.strip()


def _human_datetime(value: object) -> str:
    try:
        return datetime.fromisoformat(str(value)).strftime("%b %d, %Y · %H:%M")
    except (TypeError, ValueError):
        return str(value)


def slugify(text: str, fallback: str = "study-materials") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text or "").strip("-").lower()
    return slug[:70] or fallback


def notes_to_markdown(payload: StudyPackPayload, meta: dict) -> str:
    notes = payload.notes
    title = meta.get("title") or "Study notes"
    lines: list[str] = [f"# {title}", ""]

    source = meta.get("url") or "Pasted transcript"
    lines.append(f"> **Source:** {source}  ")
    if meta.get("created_at"):
        lines.append(f"> **Generated:** {_human_datetime(meta['created_at'])}  ")
    details = []
    if meta.get("difficulty"):
        details.append(f"Difficulty: {str(meta['difficulty']).title()}")
    if meta.get("model"):
        details.append(f"Model: {meta['model']}")
    if meta.get("word_count"):
        details.append(f"Transcript: {meta['word_count']:,} words")
    if details:
        lines.append(f"> {' · '.join(details)}")
    lines.append("")

    lines.extend(["## Summary", "", notes.summary.strip(), ""])

    for section in notes.sections:
        lines.extend([f"## {section.heading.strip()}", ""])
        for bullet in section.bullets:
            lines.append(f"- {bold_key_terms(bullet.text.strip(), bullet.key_terms)}")
        lines.append("")

    lines.extend(["## Key takeaways", ""])
    for index, takeaway in enumerate(notes.key_takeaways, start=1):
        lines.append(f"{index}. {takeaway.strip()}")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def flashcards_to_csv(payload: StudyPackPayload) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Front", "Back", "Tags"])
    for card in payload.flashcards:
        writer.writerow(
            [
                strip_markdown(card.front),
                strip_markdown(card.back),
                f"video-study::{card.kind}",
            ]
        )
    return buffer.getvalue()
