"""Structured study-material models plus quality/grounding checks.

The language model is asked for JSON, but models make mistakes: missing fields,
five options instead of four, made-up quotes. These models make the expected shape
explicit, and the grounding helpers reject any card/question whose "source_quote"
cannot be found in the transcript.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

Difficulty = Literal["easy", "medium", "hard"]
CardKind = Literal["definition", "why_how", "application"]
QuestionKind = Literal["multiple_choice", "short_answer", "critical_thinking"]

_TIMESTAMP_RE = re.compile(r"\[\d{1,2}:\d{2}(?::\d{2})?\]")
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_OPTION_PREFIX_RE = re.compile(r"^\s*[\(\[]?[A-Da-d][\)\].:]\s+")


# --------------------------------------------------------------------------- #
# Notes
# --------------------------------------------------------------------------- #
def _as_text_list(value: object) -> list[str]:
    """Coerce common LLM shapes (string, dict, list) into a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"\n+|;\s*", value)
        return [p.strip(" -•\t") for p in parts if p.strip(" -•\t")]
    if isinstance(value, dict):
        return [str(v).strip() for v in value.values() if str(v).strip()]
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            if isinstance(item, dict):
                for key in ("text", "term", "name", "key_term", "value"):
                    if key in item:
                        out.append(str(item[key]).strip())
                        break
            else:
                text = str(item).strip()
                if text:
                    out.append(text)
        return out
    return [str(value).strip()]


def _coerce_bullet_list(value: object) -> object:
    """Accept ["plain string", {"text": ...}] and other common LLM shapes."""
    if isinstance(value, (str, dict)):
        value = [value]
    if not isinstance(value, list):
        return value
    cleaned: list[object] = []
    for item in value:
        if isinstance(item, str):
            cleaned.append({"text": item})
        elif isinstance(item, dict):
            item = dict(item)
            if "text" not in item:
                for alt in ("bullet", "point", "content", "text_content", "note"):
                    if alt in item:
                        item["text"] = item[alt]
                        break
            cleaned.append(item)
        else:
            cleaned.append(item)
    return cleaned


class BulletPoint(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    text: str = Field(min_length=3)
    key_terms: list[str] = Field(default_factory=list)

    @field_validator("key_terms", mode="before")
    @classmethod
    def _terms(cls, value: object) -> list[str]:
        return [t.strip("* ") for t in _as_text_list(value) if t.strip("* ")]


class NoteSection(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    heading: str = Field(min_length=2)
    bullets: list[BulletPoint] = Field(min_length=1, max_length=7)

    @field_validator("bullets", mode="before")
    @classmethod
    def _coerce_bullets(cls, value: object) -> object:
        return _coerce_bullet_list(value)


class Notes(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    summary: str = Field(min_length=40, max_length=4000)
    sections: list[NoteSection] = Field(min_length=2, max_length=8)
    key_takeaways: list[str] = Field(min_length=3, max_length=5)

    @field_validator("key_takeaways", mode="before")
    @classmethod
    def _takeaways(cls, value: object) -> object:
        return _as_text_list(value)


# --------------------------------------------------------------------------- #
# Flashcards
# --------------------------------------------------------------------------- #
class Flashcard(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, populate_by_name=True)

    front: str = Field(
        min_length=3,
        max_length=400,
        validation_alias=AliasChoices("front", "question", "term", "prompt"),
    )
    back: str = Field(
        min_length=3,
        max_length=1500,
        validation_alias=AliasChoices("back", "answer", "definition", "explanation"),
    )
    kind: CardKind = Field(
        default="definition",
        validation_alias=AliasChoices("kind", "type", "card_type"),
    )
    source_quote: str = Field(
        min_length=8,
        max_length=800,
        validation_alias=AliasChoices("source_quote", "quote", "evidence", "source"),
    )

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, value: object) -> str:
        text = str(value or "definition").strip().lower().replace("-", "_").replace(" ", "_")
        if text in {"definition", "definitions", "term", "concept", "recall"}:
            return "definition"
        if text in {"why_how", "why", "how", "why/how", "explanation", "mechanism", "reasoning"}:
            return "why_how"
        if text in {
            "application",
            "apply",
            "applied",
            "application_question",
            "scenario",
            "example",
            "use",
        }:
            return "application"
        return text


# --------------------------------------------------------------------------- #
# Practice-test questions
# --------------------------------------------------------------------------- #
class Question(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, populate_by_name=True)

    kind: QuestionKind = Field(
        validation_alias=AliasChoices("kind", "type", "question_type")
    )
    prompt: str = Field(
        min_length=8,
        max_length=1200,
        validation_alias=AliasChoices("prompt", "question", "text"),
    )
    options: list[str] = Field(default_factory=list)
    correct_index: int | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "correct_index", "correct_option", "answer_index", "correct_answer_index"
        ),
    )
    answer: str = Field(
        default="",
        max_length=2000,
        validation_alias=AliasChoices("answer", "correct_answer", "model_answer"),
    )
    explanation: str = Field(default="", max_length=2000)
    source_quote: str = Field(
        min_length=8,
        max_length=800,
        validation_alias=AliasChoices("source_quote", "quote", "evidence", "source"),
    )

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, value: object) -> str:
        text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if text in {"mcq", "multiple_choice", "multiplechoice", "multiple_choice_question"}:
            return "multiple_choice"
        if text in {"short", "short_answer", "shortanswer", "open", "open_ended"}:
            return "short_answer"
        if text in {"critical", "critical_thinking", "criticalthinking", "thinking", "essay"}:
            return "critical_thinking"
        return text

    @field_validator("options", mode="before")
    @classmethod
    def _options(cls, value: object) -> list[str]:
        if isinstance(value, dict):
            value = [value[key] for key in sorted(value)]
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        out: list[str] = []
        for item in value:
            if isinstance(item, dict):
                for key in ("text", "option", "value", "label"):
                    if key in item:
                        item = item[key]
                        break
            text = str(item).strip()
            text = _OPTION_PREFIX_RE.sub("", text).strip()
            if text:
                out.append(text)
        return out

    @field_validator("correct_index", mode="before")
    @classmethod
    def _index(cls, value: object) -> object:
        if value is None or isinstance(value, int):
            return value
        text = str(value).strip().upper()
        if text in {"A", "B", "C", "D"}:
            return "ABCD".index(text)
        if text.isdigit():
            return int(text)
        return None

    @model_validator(mode="after")
    def _check_shape(self) -> Question:
        if self.kind == "multiple_choice":
            if len(self.options) != 4:
                raise ValueError("multiple-choice questions need exactly 4 options")
            if len({o.casefold() for o in self.options}) != 4:
                raise ValueError("multiple-choice options must be distinct")
            if self.correct_index is None and self.answer:
                # Tolerate models that return only a letter or the option text.
                letter = self.answer.strip().upper()
                if letter in {"A", "B", "C", "D"}:
                    self.correct_index = "ABCD".index(letter)
                elif self.answer in self.options:
                    self.correct_index = self.options.index(self.answer)
            if self.correct_index is None or not 0 <= self.correct_index <= 3:
                raise ValueError("multiple-choice questions need correct_index from 0 to 3")
            if not self.answer or self.answer.strip().upper() in {"A", "B", "C", "D"}:
                self.answer = self.options[self.correct_index]
        else:
            self.options = []
            self.correct_index = None
            if len(self.answer.strip()) < 5:
                raise ValueError("short-answer and critical-thinking questions need a model answer")
        if len(self.explanation.strip()) < 10:
            raise ValueError("every question needs an explanation")
        return self


def _validate_flashcard_mix(flashcards: list[Flashcard]) -> None:
    kinds = [card.kind for card in flashcards]
    for required in ("definition", "why_how", "application"):
        if kinds.count(required) < 4:
            raise ValueError(
                f"flashcards need at least 4 {required} cards "
                "(definitions, why/how, and application must all be represented)"
            )

    fronts = [_norm_dedup(card.front) for card in flashcards]
    if len(set(fronts)) != len(fronts):
        raise ValueError("flashcards must not repeat the same front")


def _validate_question_mix(questions: list[Question]) -> None:
    prompts = [_norm_dedup(question.prompt) for question in questions]
    if len(set(prompts)) != len(prompts):
        raise ValueError("practice-test questions must not repeat")

    critical = sum(1 for q in questions if q.kind == "critical_thinking")
    if not 1 <= critical <= 2:
        raise ValueError("the test needs exactly 1 or 2 critical-thinking questions")
    if sum(1 for q in questions if q.kind == "short_answer") < 2:
        raise ValueError("the test needs at least 2 short-answer questions")
    if sum(1 for q in questions if q.kind == "multiple_choice") < 4:
        raise ValueError("the test needs at least 4 multiple-choice questions")


class FlashcardsBundle(BaseModel):
    model_config = ConfigDict(extra="ignore")

    flashcards: list[Flashcard] = Field(min_length=15, max_length=25)

    @model_validator(mode="after")
    def _check_mix(self) -> FlashcardsBundle:
        _validate_flashcard_mix(self.flashcards)
        return self


class QuestionsBundle(BaseModel):
    model_config = ConfigDict(extra="ignore")

    questions: list[Question] = Field(min_length=10, max_length=15)

    @model_validator(mode="after")
    def _check_mix(self) -> QuestionsBundle:
        _validate_question_mix(self.questions)
        return self


class StudyPackPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    notes: Notes
    flashcards: list[Flashcard] = Field(min_length=15, max_length=25)
    questions: list[Question] = Field(min_length=10, max_length=15)


class DigestSection(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    heading: str = Field(min_length=2)
    bullets: list[BulletPoint] = Field(min_length=1, max_length=8)
    quotes: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("bullets", mode="before")
    @classmethod
    def _bullets(cls, value: object) -> object:
        return _coerce_bullet_list(value)

    @field_validator("quotes", mode="before")
    @classmethod
    def _quotes(cls, value: object) -> list[str]:
        return [q.strip().strip('"') for q in _as_text_list(value) if q.strip()]


class DigestTerm(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    term: str = Field(min_length=2)
    definition: str = ""
    quote: str = ""


class Digest(BaseModel):
    """A compact, fact-only brief extracted from one chunk of the transcript."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    sections: list[DigestSection] = Field(default_factory=list)
    key_terms: list[DigestTerm] = Field(default_factory=list)
    takeaways: list[str] = Field(default_factory=list)
    part: str = ""
    time_label: str = ""

    @field_validator("takeaways", mode="before")
    @classmethod
    def _takeaways(cls, value: object) -> list[str]:
        return _as_text_list(value)

    def to_prompt_json(self) -> dict:
        return {
            "sections": [
                {
                    "heading": s.heading,
                    "bullets": [{"text": b.text, "key_terms": b.key_terms} for b in s.bullets],
                    "quotes": s.quotes,
                }
                for s in self.sections
            ],
            "key_terms": [t.model_dump() for t in self.key_terms],
            "takeaways": self.takeaways,
        }


def _norm_dedup(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


# --------------------------------------------------------------------------- #
# Grounding: is a quote really in the transcript?
# --------------------------------------------------------------------------- #
def build_grounding_index(transcript: str) -> tuple[str, set[str]]:
    text = _normalize_for_match(transcript)
    tokens = {token for token in text.split() if len(token) >= 4}
    return text, tokens


def _normalize_for_match(text: str) -> str:
    text = _TIMESTAMP_RE.sub(" ", text)
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.casefold()
    text = re.sub(r"[^a-z0-9'\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def quote_is_supported(quote: str, normalized_transcript: str, transcript_tokens: set[str]) -> bool:
    """Accept a quote if it appears verbatim, or is a close word-for-word match.

    Automatic YouTube transcripts have no punctuation and use line breaks in odd
    places, so requiring an exact substring match would reject honest quotes.
    """
    quote = _MD_BOLD_RE.sub(r"\1", quote)
    normalized = _normalize_for_match(quote)
    if len(normalized) < 12:
        return False
    if normalized in normalized_transcript:
        return True
    tokens = [token for token in normalized.split() if len(token) >= 4]
    if len(tokens) < 4:
        return False
    hits = sum(1 for token in tokens if token in transcript_tokens)
    return hits / len(tokens) >= 0.8


def remove_ungrounded_cards(
    bundle: FlashcardsBundle, transcript: str
) -> tuple[FlashcardsBundle | None, list[str]]:
    """Drop unsupported cards and re-validate the remaining mix."""
    normalized, tokens = build_grounding_index(transcript)
    errors: list[str] = []
    kept: list[Flashcard] = []
    for index, card in enumerate(bundle.flashcards, start=1):
        if quote_is_supported(card.source_quote, normalized, tokens):
            kept.append(card)
        else:
            errors.append(
                f"flashcard {index} has a source_quote that does not appear in the "
                f"transcript: {card.source_quote!r}"
            )

    if errors:
        try:
            cleaned = FlashcardsBundle(flashcards=kept)
        except ValidationError as exc:
            errors.extend(format_validation_errors(exc))
            return None, errors
        return cleaned, errors
    return bundle, []


def remove_ungrounded_questions(
    bundle: QuestionsBundle, transcript: str
) -> tuple[QuestionsBundle | None, list[str]]:
    """Drop unsupported questions and re-validate the remaining mix."""
    normalized, tokens = build_grounding_index(transcript)
    errors: list[str] = []
    kept: list[Question] = []
    for index, question in enumerate(bundle.questions, start=1):
        if quote_is_supported(question.source_quote, normalized, tokens):
            kept.append(question)
        else:
            errors.append(
                f"question {index} has a source_quote that does not appear in the "
                f"transcript: {question.source_quote!r}"
            )

    if errors:
        try:
            cleaned = QuestionsBundle(questions=kept)
        except ValidationError as exc:
            errors.extend(format_validation_errors(exc))
            return None, errors
        return cleaned, errors
    return bundle, []


def format_validation_errors(exc: ValidationError, limit: int = 12) -> list[str]:
    messages: list[str] = []
    for item in exc.errors()[:limit]:
        location = ".".join(str(part) for part in item.get("loc", ())) or "response"
        messages.append(f"{location}: {item.get('msg', 'invalid value')}")
    if len(exc.errors()) > limit:
        messages.append(f"({len(exc.errors()) - limit} more errors not shown)")
    return messages
