"""Read settings from the project's .env file (and from real environment vars)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .errors import ConfigError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

# Values shipped in .env.example. Treat them as "not filled in yet" so the app
# can show helpful setup instructions instead of making a doomed API call.
_PLACEHOLDER_KEYS = {
    "",
    "sk-paste-your-key-here",
    "paste-your-key-here",
    "your-api-key",
    "changeme",
}


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    provider: str
    api_key: str
    model: str
    base_url: str
    temperature: float
    max_output_tokens: int
    timeout_seconds: int
    json_mode: bool
    chunk_chars: int
    context_chars: int
    max_chunks: int
    max_workers: int
    min_transcript_words: int
    transcript_languages: tuple[str, ...]
    data_dir: Path

    @property
    def is_configured(self) -> bool:
        """True when there is an API key (or a local endpoint that needs none)."""
        if self.api_key.strip().lower() not in _PLACEHOLDER_KEYS:
            return True
        return _is_local_url(self.base_url)

    @property
    def provider_label(self) -> str:
        names = {
            "openai": "OpenAI-compatible API",
            "anthropic": "Anthropic",
            "ollama": "OpenAI-compatible API",
        }
        return names.get(self.provider, self.provider)


def _is_local_url(url: str) -> bool:
    lowered = url.lower()
    return any(
        marker in lowered
        for marker in ("://localhost", "://127.0.0.1", "://0.0.0.0", "://host.docker.internal")
    )


def _apply_streamlit_secrets() -> None:
    """Expose Streamlit Cloud secrets as environment variables.

    Locally there is no secrets file, and the `.env` values already loaded win
    because this only fills in names that are not set yet.
    """
    try:
        import streamlit as st

        for name, value in st.secrets.items():
            if isinstance(value, str) and value.strip():
                os.environ.setdefault(name, value.strip())
    except Exception:  # noqa: BLE001 - no secrets file, or not running in Streamlit
        return


def get_settings() -> Settings:
    """Build Settings, re-reading .env each time so edits take effect on rerun."""
    # override=True means changing a key in .env is picked up by the next rerun,
    # not only after restarting the terminal command.
    load_dotenv(ENV_FILE, override=True)
    _apply_streamlit_secrets()

    provider = (_env("LLM_PROVIDER", "openai") or "openai").lower()
    if provider in {"claude"}:
        provider = "anthropic"
    if provider in {"openai-compatible", "openai_compatible"}:
        provider = "openai"

    default_model = "claude-sonnet-4-5" if provider == "anthropic" else "gpt-4o-mini"
    default_base = "https://api.anthropic.com" if provider == "anthropic" else "https://api.openai.com/v1"

    languages = tuple(
        part.strip()
        for part in _env("TRANSCRIPT_LANGUAGES", "en,en-US,en-GB").split(",")
        if part.strip()
    )

    data_dir = Path(_env("STUDY_DATA_DIR", str(PROJECT_ROOT / "data"))).expanduser()
    if not data_dir.is_absolute():
        data_dir = PROJECT_ROOT / data_dir

    return Settings(
        provider=provider,
        api_key=_env("LLM_API_KEY"),
        model=_env("LLM_MODEL", default_model) or default_model,
        base_url=(_env("LLM_BASE_URL") or default_base).rstrip("/"),
        temperature=min(1.0, max(0.0, _env_float("LLM_TEMPERATURE", 0.2))),
        max_output_tokens=max(512, _env_int("LLM_MAX_OUTPUT_TOKENS", 8000)),
        timeout_seconds=max(10, _env_int("LLM_TIMEOUT", 180)),
        json_mode=_env_bool("LLM_JSON_MODE", True),
        chunk_chars=max(2500, _env_int("TRANSCRIPT_CHUNK_CHARS", 9000)),
        context_chars=max(6000, _env_int("LLM_CONTEXT_CHARS", 24000)),
        max_chunks=max(1, _env_int("MAX_TRANSCRIPT_CHUNKS", 30)),
        max_workers=min(6, max(1, _env_int("LLM_MAX_WORKERS", 3))),
        min_transcript_words=max(20, _env_int("MIN_TRANSCRIPT_WORDS", 150)),
        transcript_languages=languages or ("en",),
        data_dir=data_dir,
    )


def require_api_key(settings: Settings) -> None:
    """Raise a friendly error when the user hasn't added a key yet."""
    if settings.is_configured:
        return
    raise ConfigError(
        "No API key was found. Open the file named .env in this project folder, "
        "replace the placeholder after LLM_API_KEY= with your key, save the file, "
        "then try again. The README explains how to get a key."
    )
