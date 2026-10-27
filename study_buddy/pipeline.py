"""The map-reduce pipeline: transcript chunks -> briefs -> notes + cards + test."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from pydantic import ValidationError

from . import prompts
from .config import Settings
from .errors import ContentError, LLMError
from .llm import LLMClient
from .schema import (
    Digest,
    Difficulty,
    FlashcardsBundle,
    Notes,
    QuestionsBundle,
    StudyPackPayload,
    format_validation_errors,
    remove_ungrounded_cards,
    remove_ungrounded_questions,
)
from .subjects import get_subject
from .transcripts import Transcript, ensure_long_enough

Progress = Callable[[str, float], None]
_CARD_COUNT = 20
_TS_RE = re.compile(r"\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]")


@dataclass(frozen=True)
class GenerationOptions:
    difficulty: Difficulty = "medium"
    question_count: int = 12
    subject: str = "general"


@dataclass(frozen=True)
class Chunk:
    index: int
    total: int
    text: str
    time_label: str = ""


def question_mix(total: int) -> tuple[int, int, int]:
    """Return (multiple_choice, short_answer, critical_thinking) counts."""
    total = max(10, min(15, total))
    critical = 2 if total >= 12 else 1
    short = max(2, round(total * 0.25))
    multiple_choice = total - short - critical
    return multiple_choice, short, critical


def _noop(_message: str, _fraction: float) -> None:
    return None


# --------------------------------------------------------------------------- #
# Chunking
# --------------------------------------------------------------------------- #
def _hard_split(text: str, limit: int) -> list[str]:
    pieces: list[str] = []
    remaining = text.strip()
    while len(remaining) > limit:
        cut = remaining.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        pieces.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        pieces.append(remaining)
    return pieces


def _split_block(block: str, limit: int) -> list[str]:
    if len(block) <= limit:
        return [block]
    sentences = re.split(r"(?<=[.!?])\s+", block)
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > limit:
            if current:
                pieces.extend(_hard_split(current, limit))
                current = ""
            pieces.extend(_hard_split(sentence, limit))
            continue
        if current and len(current) + 1 + len(sentence) > limit:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def _blocks(text: str, timed: bool, limit: int) -> list[str]:
    if timed:
        raw_blocks = [line.strip() for line in text.split("\n") if line.strip()]
    else:
        raw_blocks = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if len(raw_blocks) <= 1:
            raw_blocks = _split_block(text, limit)

    blocks: list[str] = []
    for block in raw_blocks:
        blocks.extend(_split_block(block, limit))
    return blocks or [text]


def _time_label(text: str) -> str:
    stamps = [match.group(0).strip("[]") for match in _TS_RE.finditer(text)]
    if not stamps:
        return ""
    if stamps[0] != stamps[-1]:
        return f"{stamps[0]}–{stamps[-1]}"
    return stamps[0]


def make_chunks(transcript: Transcript, max_chars: int) -> list[Chunk]:
    timed = transcript.source == "youtube" and "\n" in transcript.timed_text
    text = transcript.timed_text if timed else transcript.text
    blocks = _blocks(text, timed, max_chars)

    groups: list[str] = []
    current = ""
    for block in blocks:
        candidate = f"{current}\n{block}".strip() if current else block
        if current and len(candidate) > max_chars:
            groups.append(current)
            current = block
        else:
            current = candidate
    if current:
        groups.append(current)

    # Avoid a tiny final chunk: it would cost a whole API call for a few words.
    if len(groups) >= 2 and len(groups[-1]) < max_chars * 0.2:
        groups[-2] = f"{groups[-2]}\n{groups[-1]}"
        groups.pop()

    total = len(groups)
    return [
        Chunk(index=index, total=total, text=group, time_label=_time_label(group))
        for index, group in enumerate(groups)
    ]


# --------------------------------------------------------------------------- #
# JSON helpers
# --------------------------------------------------------------------------- #
def _unwrap(key: str):
    def unwrap(data: object) -> object:
        if isinstance(data, dict) and key in data:
            return data[key]
        return data

    return unwrap


def _parse(reply: str, model_cls, unwrap=None):
    from .llm import extract_json

    data = extract_json(reply)
    if unwrap is not None:
        data = unwrap(data)
    return model_cls.model_validate(data)


def _ask_json(
    llm: LLMClient,
    user_prompt: str,
    model_cls,
    *,
    what: str,
    unwrap=None,
):
    """Get JSON from the model, allowing exactly one corrective retry."""
    reply = llm.complete(prompts.SYSTEM_PROMPT, user_prompt)
    try:
        return _parse(reply, model_cls, unwrap)
    except (ValidationError, LLMError) as exc:
        errors = (
            format_validation_errors(exc)
            if isinstance(exc, ValidationError)
            else [str(exc)]
        )

    repair_reply = llm.complete(
        prompts.SYSTEM_PROMPT,
        user_prompt + "\n\n" + prompts.repair_prompt(reply, errors),
    )
    try:
        return _parse(repair_reply, model_cls, unwrap)
    except (ValidationError, LLMError) as exc:
        details = (
            format_validation_errors(exc)[:6]
            if isinstance(exc, ValidationError)
            else [str(exc)]
        )
        raise ContentError(
            f"The AI's {what} still didn't pass the app's quality checks after a retry. "
            "This usually means the model struggles with strict JSON. Try generating "
            "again, or pick a stronger model in .env (LLM_MODEL). Details: "
            + "; ".join(details)
        ) from exc


# --------------------------------------------------------------------------- #
# Map: chunk -> digest
# --------------------------------------------------------------------------- #
def _extract_digest(llm: LLMClient, chunk: Chunk, subject: str = "general") -> Digest:
    digest = _ask_json(
        llm,
        prompts.map_prompt(
            chunk.index + 1, chunk.total, chunk.time_label, chunk.text, subject
        ),
        Digest,
        what=f"notes for part {chunk.index + 1}",
    )
    digest.part = f"{chunk.index + 1} of {chunk.total}"
    digest.time_label = chunk.time_label
    return digest


def _extract_all(
    llm: LLMClient,
    chunks: list[Chunk],
    settings: Settings,
    progress: Progress,
    subject: str = "general",
) -> list[Digest]:
    total = len(chunks)
    if total == 1:
        progress("Reading the transcript…", 0.15)
        return [_extract_digest(llm, chunks[0], subject)]

    results: list[Digest | None] = [None] * total
    workers = min(settings.max_workers, total)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_extract_digest, llm, chunk, subject): chunk.index
            for chunk in chunks
        }
        for done, future in enumerate(as_completed(futures), start=1):
            digest = future.result()
            results[futures[future]] = digest
            progress(
                f"Read part {done} of {total} (the model saw {total} chunks)",
                0.05 + 0.55 * done / total,
            )
    return [digest for digest in results if digest is not None]


# --------------------------------------------------------------------------- #
# Reduce: combine digests
# --------------------------------------------------------------------------- #
def _digests_json(digests: list[Digest]) -> str:
    parts = []
    for digest in digests:
        data = digest.to_prompt_json()
        data["part"] = digest.part
        data["video_time"] = digest.time_label
        parts.append(data)
    return json.dumps({"parts": parts}, ensure_ascii=False, indent=2)


def _group_digests(digests: list[Digest], budget: int) -> list[list[Digest]]:
    groups: list[list[Digest]] = []
    current: list[Digest] = []
    size = 0
    for digest in digests:
        item_size = len(json.dumps(digest.to_prompt_json(), ensure_ascii=False))
        if current and (size + item_size > budget or len(current) >= 4):
            groups.append(current)
            current, size = [], 0
        current.append(digest)
        size += item_size
    if current:
        groups.append(current)
    return groups


def _merge_group(llm: LLMClient, group: list[Digest]) -> Digest:
    merged = _ask_json(
        llm,
        prompts.merge_prompt(_digests_json(group)),
        Digest,
        what="combined brief",
    )
    first, last = group[0], group[-1]
    if first.part and last.part and first.part != last.part:
        merged.part = f"{first.part} to {last.part}"
    else:
        merged.part = first.part or last.part
    labels = [d.time_label for d in group if d.time_label]
    merged.time_label = f"{labels[0]}–{labels[-1]}" if len(labels) > 1 else (labels[0] if labels else "")
    return merged


def _reduce_digests(
    llm: LLMClient,
    digests: list[Digest],
    settings: Settings,
    progress: Progress,
) -> str:
    budget = settings.context_chars
    for round_number in range(3):
        text = _digests_json(digests)
        if len(text) <= budget:
            return text

        groups = _group_digests(digests, budget)
        mergeable = [group for group in groups if len(group) > 1]
        if not mergeable:
            break

        progress(
            f"Combining the notes from {len(digests)} parts (round {round_number + 1})…",
            0.63,
        )
        rebuilt: list[Digest | None] = [None] * len(groups)
        with ThreadPoolExecutor(max_workers=min(settings.max_workers, len(mergeable))) as pool:
            future_map = {
                pool.submit(_merge_group, llm, group): index
                for index, group in enumerate(groups)
                if len(group) > 1
            }
            for index, group in enumerate(groups):
                if len(group) == 1:
                    rebuilt[index] = group[0]
            for future in as_completed(future_map):
                rebuilt[future_map[future]] = future.result()

        merged_digests = [digest for digest in rebuilt if digest is not None]
        if len(merged_digests) >= len(digests):
            break
        digests = merged_digests

    text = _digests_json(digests)
    if len(text) > budget:
        progress("Condensing an unusually long set of notes…", 0.68)
        condensed = _ask_json(
            llm,
            prompts.condense_prompt(text, int(budget * 0.8)),
            Digest,
            what="condensed brief",
        )
        text = _digests_json([condensed])
    return text


# --------------------------------------------------------------------------- #
# Final generation
# --------------------------------------------------------------------------- #
def _generate_notes(
    llm: LLMClient, brief: str, difficulty: str, subject: str = "general"
) -> Notes:
    return _ask_json(
        llm,
        prompts.notes_prompt(brief, difficulty, subject),
        Notes,
        what="study notes",
        unwrap=_unwrap("notes"),
    )


def _question_count_errors(bundle: QuestionsBundle, expected: int) -> list[str]:
    if len(bundle.questions) == expected:
        return []
    return [
        f"the practice test must contain exactly {expected} questions, but the reply "
        f"contained {len(bundle.questions)}"
    ]


def _generate_flashcards(
    llm: LLMClient,
    brief: str,
    transcript: Transcript,
    subject: str = "general",
) -> FlashcardsBundle:
    user_prompt = prompts.flashcards_prompt(brief, _CARD_COUNT, subject)
    reply = llm.complete(prompts.SYSTEM_PROMPT, user_prompt)
    errors: list[str] = []

    try:
        bundle = FlashcardsBundle.model_validate(_parse(reply, FlashcardsBundle))
        cleaned, grounding_errors = remove_ungrounded_cards(bundle, transcript.text)
        if not grounding_errors:
            return bundle
        errors = grounding_errors
    except (ValidationError, LLMError) as exc:
        errors = (
            format_validation_errors(exc)
            if isinstance(exc, ValidationError)
            else [str(exc)]
        )

    repair_user = user_prompt + "\n\n" + prompts.repair_prompt(reply, errors)
    repair_reply = llm.complete(prompts.SYSTEM_PROMPT, repair_user)
    try:
        bundle = FlashcardsBundle.model_validate(_parse(repair_reply, FlashcardsBundle))
        cleaned, grounding_errors = remove_ungrounded_cards(bundle, transcript.text)
        if cleaned is not None:
            return cleaned
        errors = grounding_errors
    except (ValidationError, LLMError) as exc:
        errors = (
            format_validation_errors(exc)
            if isinstance(exc, ValidationError)
            else [str(exc)]
        )

    raise ContentError(
        "The AI produced flashcards that failed the app's quality checks twice. Nothing "
        "was saved. This usually means the model struggles with strict JSON or quotes the "
        "transcript inaccurately. Try again, use a shorter transcript, or switch "
        "LLM_MODEL in .env. Details: " + "; ".join(errors[:6])
    )


def _generate_questions(
    llm: LLMClient,
    brief: str,
    transcript: Transcript,
    options: GenerationOptions,
) -> QuestionsBundle:
    mcq, short, critical = question_mix(options.question_count)
    total_questions = mcq + short + critical
    user_prompt = prompts.questions_prompt(
        brief,
        options.difficulty,
        mcq,
        short,
        critical,
        options.subject,
    )

    reply = llm.complete(prompts.SYSTEM_PROMPT, user_prompt)
    errors: list[str] = []
    try:
        bundle = QuestionsBundle.model_validate(_parse(reply, QuestionsBundle))
        cleaned, grounding_errors = remove_ungrounded_questions(bundle, transcript.text)
        errors = _question_count_errors(bundle, total_questions) + grounding_errors
        if not errors:
            return bundle
    except (ValidationError, LLMError) as exc:
        errors = (
            format_validation_errors(exc)
            if isinstance(exc, ValidationError)
            else [str(exc)]
        )

    repair_user = user_prompt + "\n\n" + prompts.repair_prompt(reply, errors)
    repair_reply = llm.complete(prompts.SYSTEM_PROMPT, repair_user)
    try:
        bundle = QuestionsBundle.model_validate(_parse(repair_reply, QuestionsBundle))
        cleaned, grounding_errors = remove_ungrounded_questions(bundle, transcript.text)
        if cleaned is not None:
            count_errors = _question_count_errors(cleaned, total_questions)
            if not count_errors:
                return cleaned
            errors = count_errors + grounding_errors
        else:
            errors = grounding_errors or ["the repaired practice test was invalid"]
    except (ValidationError, LLMError) as exc:
        errors = (
            format_validation_errors(exc)
            if isinstance(exc, ValidationError)
            else [str(exc)]
        )

    raise ContentError(
        "The AI produced a practice test that failed the app's quality checks twice. "
        "Nothing was saved. This usually means the model struggles with strict JSON or "
        "quotes the transcript inaccurately. Try again, use a shorter transcript, or "
        "switch LLM_MODEL in .env. Details: " + "; ".join(errors[:6])
    )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def generate_study_pack(
    transcript: Transcript,
    options: GenerationOptions,
    settings: Settings,
    progress: Progress | None = None,
) -> StudyPackPayload:
    progress = progress or _noop
    options = GenerationOptions(
        difficulty=options.difficulty,
        question_count=max(10, min(15, options.question_count)),
        subject=get_subject(options.subject).key,
    )

    progress("Checking the transcript…", 0.02)
    ensure_long_enough(transcript, settings.min_transcript_words)

    chunks = make_chunks(transcript, settings.chunk_chars)
    if len(chunks) > settings.max_chunks:
        raise ContentError(
            f"This transcript is extremely long ({transcript.word_count:,} words, "
            f"{len(chunks)} chunks). The app stops at {settings.max_chunks} chunks to "
            "avoid an unexpectedly large API bill. Try a shorter video, or split the "
            "transcript into parts."
        )

    llm = LLMClient(settings)
    progress(
        f"Transcript ready ({transcript.word_count:,} words, {len(chunks)} "
        f"chunk{'s' if len(chunks) != 1 else ''}). Extracting key facts…",
        0.04,
    )

    digests = _extract_all(llm, chunks, settings, progress, options.subject)
    if not any(d.sections or d.key_terms for d in digests):
        raise ContentError(
            "The AI could not extract any factual content from this transcript. "
            "Nothing was generated, because inventing material is worse than saying so. "
            "Check that the pasted text is the actual transcript, then try again."
        )

    brief = _reduce_digests(llm, digests, settings, progress)

    progress("Writing notes…", 0.70)
    notes = _generate_notes(llm, brief, options.difficulty, options.subject)

    progress(
        f"Writing {_CARD_COUNT} flashcards and {options.question_count} test questions…",
        0.80,
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        cards_future = pool.submit(
            _generate_flashcards, llm, brief, transcript, options.subject
        )
        questions_future = pool.submit(
            _generate_questions, llm, brief, transcript, options
        )
        flashcards = cards_future.result()
        questions = questions_future.result()

    progress("Checking that every quote comes from the transcript…", 0.96)
    return StudyPackPayload(
        notes=notes,
        flashcards=flashcards.flashcards,
        questions=questions.questions,
    )
