"""Save generated packs as JSON files so they can be reopened without paying again."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

from .errors import StudyBuddyError
from .schema import StudyPackPayload

_PACK_ID_RE = re.compile(r"^[0-9a-f]{12}$")


def _packs_dir(data_dir: Path) -> Path:
    directory = data_dir / "packs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def save_pack(payload: StudyPackPayload, meta: dict, data_dir: Path) -> dict:
    """Write one pack atomically and return the full saved record."""
    record = {
        "version": 1,
        "id": uuid.uuid4().hex[:12],
        "created_at": _now(),
        "title": (meta.get("title") or "Untitled study pack").strip(),
        "source": meta.get("source") or "pasted",
        "url": meta.get("url"),
        "video_id": meta.get("video_id"),
        "language": meta.get("language"),
        "word_count": int(meta.get("word_count") or 0),
        "page_count": int(meta.get("page_count") or 0),
        "document_name": meta.get("document_name"),
        "difficulty": meta.get("difficulty") or "medium",
        "subject": meta.get("subject") or "general",
        "question_count": int(meta.get("question_count") or 0),
        "provider": meta.get("provider"),
        "model": meta.get("model"),
        **payload.model_dump(),
    }

    directory = _packs_dir(data_dir)
    destination = directory / f"{record['id']}.json"
    temporary = directory / f".{record['id']}.tmp"
    try:
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, destination)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise StudyBuddyError(
            f"The study pack could not be saved to {directory}. Check that the folder is "
            f"writable. ({type(exc).__name__}: {exc})"
        ) from exc
    return record


def list_packs(data_dir: Path) -> list[dict]:
    """Return lightweight summaries, newest first. Damaged files are skipped."""
    directory = _packs_dir(data_dir)
    summaries: list[dict] = []
    for path in directory.glob("*.json"):
        if path.name.startswith("."):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or not _PACK_ID_RE.fullmatch(str(data.get("id", ""))):
            continue
        summaries.append(
            {
                "id": data["id"],
                "title": data.get("title") or "Untitled study pack",
                "created_at": data.get("created_at") or "",
                "source": data.get("source") or "pasted",
                "subject": data.get("subject") or "general",
                "difficulty": data.get("difficulty") or "medium",
                "question_count": data.get("question_count") or 0,
                "word_count": data.get("word_count") or 0,
                "flashcard_count": len(data.get("flashcards") or []),
            }
        )
    return sorted(summaries, key=lambda item: item.get("created_at", ""), reverse=True)


def load_pack(pack_id: str, data_dir: Path) -> dict:
    if not _PACK_ID_RE.fullmatch(pack_id or ""):
        raise StudyBuddyError("That saved pack name looks invalid.")
    path = _packs_dir(data_dir) / f"{pack_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StudyBuddyError("That saved pack no longer exists on disk.") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise StudyBuddyError(
            f"The saved file for this pack could not be read ({type(exc).__name__})."
        ) from exc
    if not isinstance(data, dict):
        raise StudyBuddyError("The saved pack file has an unexpected format.")
    return data


def delete_pack(pack_id: str, data_dir: Path) -> None:
    if not _PACK_ID_RE.fullmatch(pack_id or ""):
        raise StudyBuddyError("That saved pack name looks invalid.")
    path = _packs_dir(data_dir) / f"{pack_id}.json"
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise StudyBuddyError(
            f"The saved pack could not be deleted ({type(exc).__name__}: {exc})."
        ) from exc
