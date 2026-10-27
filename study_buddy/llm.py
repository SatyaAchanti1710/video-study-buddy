"""A tiny, dependency-light client for two kinds of LLM APIs.

* ``openai``  -> OpenAI's Chat Completions API and every compatible clone
  (OpenRouter, Groq, DeepSeek, Together, local Ollama, ...).
* ``anthropic`` -> Claude's Messages API.

Swapping providers is a .env change; no app code needs to change.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import requests
from requests import Response

from .config import Settings, require_api_key
from .errors import LLMError

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_ATTEMPTS = 3


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        require_api_key(settings)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def complete(self, system: str, user: str, *, max_tokens: int | None = None) -> str:
        if self.settings.provider == "anthropic":
            return self._complete_anthropic(system, user, max_tokens)
        return self._complete_openai(system, user, max_tokens)

    # ------------------------------------------------------------------ #
    # OpenAI-compatible chat completions
    # ------------------------------------------------------------------ #
    def _complete_openai(self, system: str, user: str, max_tokens: int | None) -> str:
        url = f"{self.settings.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.settings.temperature,
            "max_tokens": max_tokens or self.settings.max_output_tokens,
        }
        if self.settings.json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"

        # Some providers/models reject response_format, max_tokens, or temperature.
        # Retry without the offending parameter instead of failing outright.
        for _ in range(4):
            response = self._post(url, headers, payload)
            if response.ok:
                return self._parse_openai(response)
            body = response.text[:1000]
            if response.status_code == 400:
                if "response_format" in payload and "response_format" in body:
                    payload.pop("response_format", None)
                    continue
                if "max_tokens" in payload and "max_tokens" in body:
                    payload["max_completion_tokens"] = payload.pop("max_tokens")
                    continue
                if "temperature" in payload and "temperature" in body:
                    payload.pop("temperature", None)
                    continue
            raise self._http_error(response)
        raise self._http_error(response)

    def _parse_openai(self, response: Response) -> str:
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMError(
                "The AI provider returned a response that isn't JSON. "
                "Check that LLM_BASE_URL points at an OpenAI-compatible API."
            ) from exc

        if isinstance(data, dict) and data.get("error"):
            raise LLMError(f"The AI provider returned an error: {data['error']}")

        choices = data.get("choices") or []
        if not choices:
            raise LLMError("The AI provider returned no answer. Check your model name and credits.")
        choice = choices[0]
        message = choice.get("message") or {}
        content = message.get("content")

        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        if not isinstance(content, str) or not content.strip():
            raise LLMError("The AI provider returned an empty answer. Try again.")

        if choice.get("finish_reason") == "length":
            raise LLMError(
                "The AI's answer was cut off before it finished. Increase "
                f"LLM_MAX_OUTPUT_TOKENS in .env (currently {self.settings.max_output_tokens}) "
                "and try again."
            )
        return content

    # ------------------------------------------------------------------ #
    # Anthropic Messages API
    # ------------------------------------------------------------------ #
    def _complete_anthropic(self, system: str, user: str, max_tokens: int | None) -> str:
        base = self.settings.base_url.rstrip("/")
        url = f"{base}/messages" if base.endswith("/v1") else f"{base}/v1/messages"
        payload = {
            "model": self.settings.model,
            "max_tokens": max_tokens or self.settings.max_output_tokens,
            "temperature": self.settings.temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.settings.api_key,
            "anthropic-version": "2023-06-01",
        }

        response = self._post(url, headers, payload)
        if not response.ok:
            raise self._http_error(response)

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMError("The AI provider returned a response that isn't JSON.") from exc

        blocks = data.get("content") or []
        text = "".join(
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        )
        if not text.strip():
            raise LLMError("The AI provider returned an empty answer. Try again.")
        if data.get("stop_reason") == "max_tokens":
            raise LLMError(
                "The AI's answer was cut off before it finished. Increase "
                f"LLM_MAX_OUTPUT_TOKENS in .env (currently {self.settings.max_output_tokens}) "
                "and try again."
            )
        return text

    # ------------------------------------------------------------------ #
    # HTTP helpers
    # ------------------------------------------------------------------ #
    def _post(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> Response:
        last_error: Exception | None = None
        response: Response | None = None

        for attempt in range(_ATTEMPTS):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=(10, self.settings.timeout_seconds),
                )
            except requests.Timeout as exc:
                last_error = exc
                if attempt < _ATTEMPTS - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise LLMError(
                    f"The AI provider did not answer within {self.settings.timeout_seconds} "
                    "seconds. Try again, use a shorter transcript, or raise LLM_TIMEOUT in .env."
                ) from exc
            except requests.RequestException as exc:
                last_error = exc
                if attempt < _ATTEMPTS - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise LLMError(
                    f"Could not reach the AI provider ({type(exc).__name__}). Check your "
                    "internet connection and LLM_BASE_URL in .env."
                ) from exc

            if response.status_code in _RETRYABLE_STATUS and attempt < _ATTEMPTS - 1:
                time.sleep(self._retry_delay(response, attempt))
                continue
            return response

        if response is not None:
            return response
        raise LLMError(f"Could not reach the AI provider ({last_error}).")

    @staticmethod
    def _retry_delay(response: Response, attempt: int) -> float:
        header = response.headers.get("Retry-After", "")
        try:
            seconds = float(header)
        except ValueError:
            seconds = 0.0
        return min(seconds, 10.0) if seconds > 0 else 2.0 * (attempt + 1)

    def _http_error(self, response: Response) -> LLMError:
        body = re.sub(r"\s+", " ", (response.text or ""))[:700]
        code = response.status_code
        provider = self.settings.provider_label

        if code in {401, 403}:
            message = (
                f"{provider} rejected the API key (HTTP {code}). Check LLM_API_KEY in .env: "
                "make sure it is the full key with no spaces or quotes."
            )
        elif code == 404:
            message = (
                f"{provider} could not find the model “{self.settings.model}” (HTTP 404). "
                "Check LLM_MODEL and LLM_BASE_URL in .env."
            )
        elif code == 429:
            message = (
                f"{provider} is rate-limiting this key or the account is out of credits "
                "(HTTP 429). Wait a minute and try again, or check your provider's billing page."
            )
        elif code == 400:
            message = (
                f"{provider} rejected the request (HTTP 400). The model may not support "
                f"this request style. Provider said: {body}"
            )
        else:
            message = f"{provider} returned an error (HTTP {code}). {body}"

        return LLMError(message)


def extract_json(text: str) -> Any:
    """Parse JSON from a model reply, tolerating code fences and stray prose."""
    cleaned = (text or "").strip().lstrip("\ufeff")
    fence = re.match(r"^```(?:json|JSON)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()

    candidates = [cleaned]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        candidates.append(cleaned[start : end + 1])

    for candidate in candidates:
        variants = (candidate, re.sub(r",\s*([}\]])", r"\1", candidate))
        for variant in variants:
            try:
                return json.loads(variant)
            except json.JSONDecodeError:
                continue

    snippet = re.sub(r"\s+", " ", cleaned)[:300]
    raise LLMError(
        "The AI returned text that isn't valid JSON, so it can't be displayed. Try "
        f"generating again or switch LLM_MODEL in .env. The reply began with: “{snippet}”"
    )
