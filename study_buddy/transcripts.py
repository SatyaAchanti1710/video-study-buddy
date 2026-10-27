"""Turn a YouTube URL into a transcript, or accept a pasted transcript."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

import requests
from youtube_transcript_api import (
    AgeRestricted,
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

from .config import Settings
from .errors import TranscriptError

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOST_RE = re.compile(r"(^|\.)(youtube\.com|youtu\.be)$", re.IGNORECASE)
_USER_AGENT = "Mozilla/5.0 (compatible; VideoStudyBuddy/1.0)"


@dataclass
class Transcript:
    source: str  # "youtube", "pasted", "pdf", or "website"
    title: str
    text: str
    timed_text: str = ""
    url: str | None = None
    video_id: str | None = None
    language: str | None = None
    is_generated: bool | None = None
    duration_seconds: float = 0.0
    page_count: int = 0
    document_name: str | None = None
    word_count: int = field(init=False)
    char_count: int = field(init=False)

    def __post_init__(self) -> None:
        self.text = _normalize_text(self.text)
        self.timed_text = _normalize_text(self.timed_text) if self.timed_text else self.text
        self.word_count = len(self.text.split())
        self.char_count = len(self.text)
        if self.word_count == 0:
            raise TranscriptError("The transcript is empty, so there is nothing to study from.")


def _normalize_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def looks_like_url(raw: str) -> bool:
    text = raw.strip()
    if not text or "\n" in text or len(text) > 2000:
        return False
    return bool(re.match(r"^(https?://|www\.)", text, re.IGNORECASE))


def extract_video_id(raw: str) -> str | None:
    """Accept watch/shorts/embed/live/youtu.be links, or a bare 11-char ID."""
    text = raw.strip()
    if not text or "\n" in text or len(text) > 2000:
        return None
    if _VIDEO_ID_RE.fullmatch(text):
        return text
    if not re.search(r"(youtube\.com|youtu\.be)", text, re.IGNORECASE):
        return None

    url = text if "://" in text else f"https://{text}"
    parsed = urlparse(url)
    if not _YOUTUBE_HOST_RE.search(parsed.hostname or ""):
        return None

    candidate: str | None = None
    if (parsed.hostname or "").lower().endswith("youtu.be"):
        parts = [part for part in parsed.path.split("/") if part]
        candidate = parts[0] if parts else None
    elif parsed.path.rstrip("/") == "/watch":
        candidate = (parse_qs(parsed.query).get("v") or [None])[0]
    else:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0].lower() in {"shorts", "embed", "live", "v"}:
            candidate = parts[1]

    return candidate if candidate and _VIDEO_ID_RE.fullmatch(candidate) else None


def _format_timestamp(seconds: float) -> str:
    total = int(max(0, seconds))
    if total >= 3600:
        return f"{total // 3600}:{(total % 3600) // 60:02d}:{total % 60:02d}"
    return f"{total // 60:02d}:{total % 60:02d}"


def _build_timed_text(snippets: list) -> tuple[str, str, float]:
    plain_parts: list[str] = []
    lines: list[str] = []
    last_marker = -10_000.0
    duration = 0.0

    for snippet in snippets:
        text = re.sub(r"\s+", " ", str(getattr(snippet, "text", "") or "")).strip()
        if not text:
            continue
        start = float(getattr(snippet, "start", 0.0) or 0.0)
        length = float(getattr(snippet, "duration", 0.0) or 0.0)
        duration = max(duration, start + length)
        plain_parts.append(text)

        # A timestamp roughly every 45 seconds gives the model a sense of the
        # video's structure without bloating the prompt too much.
        if start - last_marker >= 45:
            if lines:
                lines.append("\n")
            lines.append(f"[{_format_timestamp(start)}] {text}")
            last_marker = start
        else:
            lines.append(f" {text}")

    return " ".join(plain_parts), "".join(lines).strip(), duration


def _choose_transcript(transcripts: list, preferred: tuple[str, ...]):
    for code in preferred:
        for item in transcripts:
            if item.language_code.lower() == code.lower() and not item.is_generated:
                return item
    for code in preferred:
        for item in transcripts:
            if item.language_code.lower() == code.lower():
                return item
    for item in transcripts:
        if not item.is_generated:
            return item
    return transcripts[0] if transcripts else None


def _available_languages(api: YouTubeTranscriptApi, video_id: str) -> str:
    try:
        items = list(api.list(video_id))
    except Exception:
        return ""
    names = []
    for item in items:
        label = item.language or item.language_code
        if item.is_generated:
            label = f"{label} (auto-generated)"
        names.append(label)
    return ", ".join(dict.fromkeys(names))


def fetch_video_title(video_id: str, timeout: int = 8) -> str | None:
    """Use YouTube's public oEmbed endpoint; failure is never fatal."""
    try:
        response = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            headers={"User-Agent": _USER_AGENT},
            timeout=timeout,
        )
        if response.ok:
            title = str(response.json().get("title", "")).strip()
            return title or None
    except Exception:
        return None
    return None


def fetch_youtube_transcript(raw_url: str, settings: Settings) -> Transcript:
    video_id = extract_video_id(raw_url)
    if not video_id:
        raise TranscriptError(
            "That doesn't look like a YouTube link. Links usually look like "
            "https://www.youtube.com/watch?v=XXXXXXXXXXX or https://youtu.be/XXXXXXXXXXX. "
            "You can also paste the transcript text instead."
        )

    api = YouTubeTranscriptApi()
    preferred = tuple(settings.transcript_languages)

    try:
        fetched = api.fetch(video_id, languages=list(preferred))
    except NoTranscriptFound:
        try:
            available = list(api.list(video_id))
            chosen = _choose_transcript(available, preferred)
            if chosen is None:
                raise TranscriptError(
                    "This video has no captions available. Open the video on YouTube, "
                    "use “Show transcript” under the description, and paste the text here."
                )
            fetched = chosen.fetch()
        except TranscriptError:
            raise
        except TranscriptsDisabled:
            raise TranscriptError(
                "The video owner turned off captions for this video, so no transcript "
                "can be downloaded. You can paste a transcript manually instead."
            )
        except (RequestBlocked, IpBlocked):
            raise TranscriptError(
                "YouTube is temporarily blocking transcript requests from this computer. "
                "Wait a few minutes and try again, or paste the transcript manually."
            )
        except Exception as exc:
            languages = _available_languages(api, video_id)
            detail = f" Available languages: {languages}." if languages else ""
            raise TranscriptError(
                f"No transcript could be downloaded for this video "
                f"({type(exc).__name__}).{detail} Paste the transcript manually instead."
            ) from exc
    except TranscriptsDisabled as exc:
        raise TranscriptError(
            "The video owner turned off captions for this video, so no transcript can "
            "be downloaded. You can paste a transcript manually instead."
        ) from exc
    except VideoUnavailable as exc:
        raise TranscriptError(
            "YouTube says this video is unavailable. It may be private, removed, or "
            "blocked in your region. Check the link, or paste the transcript manually."
        ) from exc
    except AgeRestricted as exc:
        raise TranscriptError(
            "This video is age-restricted, so YouTube will not share its transcript. "
            "Paste the transcript manually instead."
        ) from exc
    except (RequestBlocked, IpBlocked) as exc:
        raise TranscriptError(
            "YouTube is temporarily blocking transcript requests from this computer. "
            "Wait a few minutes and try again, or paste the transcript manually."
        ) from exc
    except TranscriptError:
        raise
    except Exception as exc:
        raise TranscriptError(
            f"YouTube did not return a transcript ({type(exc).__name__}: {exc}). "
            "Check your internet connection, then try again or paste the transcript manually."
        ) from exc

    snippets = list(fetched)
    plain, timed, duration = _build_timed_text(snippets)
    if not plain.strip():
        raise TranscriptError(
            "YouTube returned an empty transcript, so nothing was generated. Paste the "
            "transcript manually instead."
        )

    title = fetch_video_title(video_id) or f"YouTube video {video_id}"
    return Transcript(
        source="youtube",
        title=title,
        text=plain,
        timed_text=timed,
        url=f"https://www.youtube.com/watch?v={video_id}",
        video_id=video_id,
        language=getattr(fetched, "language", None),
        is_generated=getattr(fetched, "is_generated", None),
        duration_seconds=duration,
    )


def transcript_from_text(raw_text: str, title: str = "") -> Transcript:
    text = (raw_text or "").strip()
    if not text:
        raise TranscriptError("Paste a transcript or a YouTube link first.")
    return Transcript(source="pasted", title=title.strip() or "Pasted transcript", text=text)


def ensure_long_enough(transcript: Transcript, minimum_words: int) -> None:
    """Refuse to generate from too little text, rather than inventing content."""
    if transcript.word_count < minimum_words:
        raise TranscriptError(
            f"The source text is only {transcript.word_count} words long. At least "
            f"{minimum_words} words are needed; with less, the study materials would be "
            "mostly guesswork. Nothing was generated. Add the rest of the text and "
            "try again. (You can lower MIN_TRANSCRIPT_WORDS in .env, but the results will "
            "be less reliable.)"
        )
