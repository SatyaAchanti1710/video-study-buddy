"""Video Study Buddy — a local Streamlit app.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import hmac
import os
import traceback
import uuid
from datetime import datetime

import streamlit as st
from pydantic import ValidationError

from study_buddy.cards import flashcards_html
from study_buddy.config import Settings, get_settings
from study_buddy.documents import load_document
from study_buddy.errors import StudyBuddyError, TranscriptError
from study_buddy.formatting import (
    bold_key_terms,
    flashcards_to_csv,
    notes_to_markdown,
    slugify,
)
from study_buddy.pipeline import GenerationOptions, generate_study_pack
from study_buddy.schema import StudyPackPayload
from study_buddy.storage import delete_pack, list_packs, load_pack, save_pack
from study_buddy.subjects import DOCUMENTS, GENERAL, SUBJECTS, Subject, get_subject
from study_buddy.transcripts import (
    Transcript,
    extract_video_id,
    fetch_youtube_transcript,
    looks_like_url,
    transcript_from_text,
)

KIND_LABELS = {
    "multiple_choice": "Multiple choice",
    "short_answer": "Short answer",
    "critical_thinking": "Critical thinking",
}

SECTION_ICONS = {key: subject.icon for key, subject in SUBJECTS.items()}

SETUP_SNIPPET = """LLM_PROVIDER=openai
LLM_API_KEY=sk-your-key-goes-here
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL="""


def main() -> None:
    st.set_page_config(
        page_title="Video Study Buddy",
        page_icon="🎬",
        layout="centered",
        initial_sidebar_state="expanded",
    )
    settings = get_settings()
    _init_state()
    if not _password_gate():
        return
    _render_sections()
    subject = get_subject(st.session_state.get("section"))
    _render_sidebar(settings, subject)

    flash = st.session_state.pop("flash", None)
    if flash:
        st.success(flash)
    flash_warning = st.session_state.pop("flash_warning", None)
    if flash_warning:
        st.warning(flash_warning)

    st.title(subject.headline)
    st.markdown(subject.description)
    if subject.section_note:
        st.info(subject.section_note, icon=subject.icon)

    if not settings.is_configured:
        st.warning(
            "Add your API key to the `.env` file before generating. "
            "Open `.env`, replace the placeholder after `LLM_API_KEY=`, save, then "
            "reload this page. The README explains how to get a key."
        )
        with st.expander("Show me the exact .env lines"):
            st.code(SETUP_SNIPPET, language="bash")

    options = GenerationOptions(
        difficulty=str(st.session_state.get("difficulty", "Medium")).lower(),
        question_count=int(st.session_state.get("question_count", 12)),
        subject=subject.key,
    )

    with st.container(border=True):
        if subject.key == DOCUMENTS.key:
            upload = st.file_uploader(
                "Upload a PDF",
                type=["pdf"],
                key="document_upload",
                help=(
                    "Text-based PDFs work best. Scanned PDFs with no selectable text are "
                    "refused, because the app will not guess at their contents."
                ),
            )
            link = st.text_input(
                "…or paste a link to a PDF or web page",
                key="document_link",
                placeholder="https://…",
                help="One page or one PDF at a time. Menus and ads are stripped automatically.",
            )
            if upload is not None and (link or "").strip():
                st.caption("Both are filled in — the uploaded PDF will be used.")
            title = st.text_input(
                "Title (optional)",
                key="document_title",
                placeholder=subject.title_placeholder,
                help="Leave blank to use the PDF's own title, or the page's title.",
            )
            clicked = st.button(
                "Generate study materials",
                type="primary",
                width="stretch",
                key="generate_documents",
            )
        else:
            raw = st.text_area(
                "YouTube link or transcript",
                height=170,
                key=f"source_input_{subject.key}",
                placeholder=subject.source_placeholder,
                help=(
                    "A link is detected automatically. If the captions can't be fetched, "
                    "paste the transcript text instead."
                ),
            )
            title = st.text_input(
                "Title (optional)",
                key=f"source_title_{subject.key}",
                placeholder=subject.title_placeholder,
                help="Leave blank to use the YouTube title (or “Pasted transcript”).",
            )
            clicked = st.button(
                "Generate study materials",
                type="primary",
                width="stretch",
                key=f"generate_{subject.key}",
            )

    if clicked:
        if subject.key == DOCUMENTS.key:
            _handle_document_generate(upload, link, title, options, settings)
        else:
            _handle_generate(raw, title, options, settings)

    record = st.session_state.get("current")
    if record:
        _render_pack(record, subject)
    else:
        _render_welcome(subject)

    st.divider()
    st.caption(
        f"{subject.icon} {subject.label} section · Saved packs live in "
        f"`{settings.data_dir / 'packs'}` · The app runs on this computer; only the "
        "source text is sent to your AI provider."
    )


# --------------------------------------------------------------------------- #
# Sidebar and saved library
# --------------------------------------------------------------------------- #
def _password_gate() -> bool:
    """Require APP_PASSWORD when it is set (used by the public deployment)."""
    expected = (os.getenv("APP_PASSWORD") or "").strip()
    if not expected or st.session_state.get("authenticated"):
        return True

    st.title("🔒 Study Buddy")
    st.caption("This study app is private. Enter the password to continue.")
    with st.form("login"):
        supplied = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Enter", width="stretch", type="primary")
    if submitted:
        if hmac.compare_digest(supplied.strip().encode(), expected.encode()):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("That password is not correct.")
    return False


def _render_sections() -> None:
    """Pick the section: the same app, with prompts aimed at one subject."""
    st.session_state.setdefault("section", GENERAL.key)
    with st.container(border=True):
        st.segmented_control(
            "Section",
            options=list(SUBJECTS.keys()),
            format_func=lambda key: f"{SUBJECTS[key].icon} {SUBJECTS[key].label}",
            key="section",
            label_visibility="collapsed",
            width="stretch",
            help=(
                "General works for any video. Chemistry focuses the notes, flashcards "
                "and test on formulas, reactions, conditions, and mechanisms. Saved "
                "packs are kept per section."
            ),
        )


def _render_sidebar(settings: Settings, subject: Subject) -> None:
    with st.sidebar:
        st.caption(f"Section: **{subject.icon} {subject.label}**")
        st.header("⚙️ Settings")
        st.segmented_control(
            "Difficulty",
            ["Easy", "Medium", "Hard"],
            default="Medium",
            key="difficulty",
            help="Controls how hard the flashcards and test questions are.",
        )
        st.slider(
            "Practice-test questions",
            min_value=10,
            max_value=15,
            value=12,
            key="question_count",
            help=(
                "The test always mixes multiple choice, short answer, and 1–2 "
                "critical-thinking questions. Flashcards target 20 (15–25 accepted)."
            ),
        )

        st.divider()
        st.subheader("AI provider")
        if settings.is_configured:
            st.caption(f"**{settings.provider_label}** · `{settings.model}`")
        else:
            st.warning("No API key found yet.", icon="🔑")
        with st.expander("Change provider or model"):
            st.markdown(
                "Edit the file named `.env` in this project folder, then reload the "
                "page. Example:"
            )
            st.code(SETUP_SNIPPET, language="bash")
            st.caption("The README has copy-paste blocks for OpenAI, Anthropic, OpenRouter, Groq, and local Ollama.")

        st.divider()
        _render_library(settings, subject)


def _render_library(settings: Settings, subject: Subject) -> None:
    st.subheader(f"📚 Saved {subject.label.lower()} packs")
    try:
        all_packs = list_packs(settings.data_dir)
    except StudyBuddyError as exc:
        st.error(str(exc))
        return

    packs = [
        pack
        for pack in all_packs
        if get_subject(str(pack.get("subject") or "general")).key == subject.key
    ]

    if not packs:
        st.caption(
            "Packs you generate in this section are saved here automatically, so you "
            "can reopen them without paying again."
        )
        return

    labels = {pack["id"]: _library_label(pack) for pack in packs}
    selected = st.selectbox(
        "Open a saved pack",
        options=[pack["id"] for pack in packs],
        format_func=lambda pack_id: labels.get(pack_id, "Unknown pack"),
        key=f"library_select_{subject.key}",
    )

    open_col, delete_col = st.columns(2)
    if open_col.button("Open", width="stretch", key=f"open_saved_pack_{subject.key}"):
        try:
            record = load_pack(selected, settings.data_dir)
            StudyPackPayload.model_validate(record)
        except (StudyBuddyError, ValidationError) as exc:
            st.error(f"That saved pack could not be opened: {exc}")
        else:
            st.session_state.current = record
            st.session_state.pending_delete = None
            st.rerun()

    if delete_col.button("Delete", width="stretch", key=f"ask_delete_pack_{subject.key}"):
        st.session_state.pending_delete = selected

    pending = st.session_state.get("pending_delete")
    if pending:
        st.warning(
            f"Delete “{labels.get(pending, 'this pack')}”? The file is removed from this computer."
        )
        yes, no = st.columns(2)
        if yes.button(
            "Yes, delete",
            type="primary",
            width="stretch",
            key=f"confirm_delete_pack_{subject.key}",
        ):
            try:
                delete_pack(pending, settings.data_dir)
            except StudyBuddyError as exc:
                st.error(str(exc))
            else:
                if (st.session_state.get("current") or {}).get("id") == pending:
                    st.session_state.current = None
                st.session_state.pending_delete = None
                st.session_state.pop(f"library_select_{subject.key}", None)
                st.session_state.flash = "Saved pack deleted."
                st.rerun()
        if no.button("Cancel", width="stretch", key=f"cancel_delete_pack_{subject.key}"):
            st.session_state.pending_delete = None
            st.rerun()


def _library_label(pack: dict) -> str:
    return f"{pack.get('title', 'Untitled')[:52]} · {_short_date(pack.get('created_at', ''))}"


def _short_date(iso: str) -> str:
    try:
        moment = datetime.fromisoformat(iso)
        return f"{moment:%b} {moment.day}"
    except (TypeError, ValueError):
        return ""


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #
def _handle_generate(
    raw: str, title: str, options: GenerationOptions, settings: Settings
) -> None:
    raw = (raw or "").strip()
    title = (title or "").strip()
    if not raw:
        st.error("Paste a YouTube link or a transcript first.")
        return
    if not settings.is_configured:
        st.error(
            "No API key is configured yet, so nothing was fetched or generated. Open "
            "the `.env` file, add your key after `LLM_API_KEY=`, save, then reload the page."
        )
        return

    video_id = extract_video_id(raw)
    transcript: Transcript | None = None

    if video_id:
        with st.status("Fetching the YouTube transcript…", expanded=True) as status:
            try:
                transcript = fetch_youtube_transcript(raw, settings)
            except TranscriptError as exc:
                status.update(label="No transcript could be fetched", state="error", expanded=True)
                st.error(str(exc))
                st.info(
                    "Open the video on YouTube, expand the description, choose "
                    "**Show transcript**, copy the text, paste it into the box above, "
                    "and click Generate again."
                )
                return
            status.update(
                label=f"Transcript fetched · {transcript.word_count:,} words",
                state="complete",
                expanded=False,
            )
    elif looks_like_url(raw):
        st.error(
            "That looks like a link, but not a YouTube link. Paste a YouTube URL, or "
            "paste the transcript text itself."
        )
        return
    else:
        try:
            transcript = transcript_from_text(raw, title)
        except TranscriptError as exc:
            st.error(str(exc))
            return

    if title:
        transcript.title = title

    _generate_from_transcript(transcript, options, settings)


def _handle_document_generate(
    uploaded: object,
    link: str,
    title: str,
    options: GenerationOptions,
    settings: Settings,
) -> None:
    link = (link or "").strip()
    title = (title or "").strip()
    if uploaded is None and not link:
        st.error("Upload a PDF or paste a link first.")
        return
    if not settings.is_configured:
        st.error(
            "No API key is configured yet, so nothing was fetched or generated. Open "
            "the `.env` file, add your key after `LLM_API_KEY=`, save, then reload the page."
        )
        return

    upload_bytes = uploaded.getvalue() if uploaded is not None else None
    upload_name = getattr(uploaded, "name", "") if uploaded is not None else ""
    with st.status(
        "Reading the PDF…" if upload_bytes else "Fetching the web page…", expanded=True
    ) as status:
        try:
            source = load_document(
                upload_bytes=upload_bytes,
                upload_name=upload_name,
                link=link,
            )
        except StudyBuddyError as exc:
            status.update(
                label="That source could not be read", state="error", expanded=True
            )
            st.error(str(exc))
            return
        if source.kind == "pdf":
            pages = f"{source.page_count} page{'s' if source.page_count != 1 else ''}"
            done = f"Read {pages} of the PDF"
        else:
            done = "Read the article text"
        status.update(
            label=f"{done} · {len(source.text.split()):,} words",
            state="complete",
            expanded=False,
        )

    transcript = Transcript(
        source=source.kind,
        title=title or source.title,
        text=source.text,
        url=source.url,
        page_count=source.page_count,
        document_name=source.document_name,
    )
    _generate_from_transcript(transcript, options, settings)


def _generate_from_transcript(
    transcript: Transcript, options: GenerationOptions, settings: Settings
) -> None:
    progress_bar = st.progress(0.0)
    progress_text = st.empty()

    def progress(message: str, fraction: float) -> None:
        progress_text.caption(message)
        progress_bar.progress(min(1.0, max(0.0, fraction)))

    with st.status("Building your study pack…", expanded=True) as status:
        try:
            payload = generate_study_pack(transcript, options, settings, progress)
        except StudyBuddyError as exc:
            status.update(label="Generation stopped", state="error", expanded=True)
            progress_text.empty()
            progress_bar.empty()
            st.error(str(exc))
            with st.expander("Technical details"):
                st.code(traceback.format_exc(), language="text")
            return
        except Exception as exc:  # unexpected bug: show details, never a blank screen
            status.update(label="Generation stopped", state="error", expanded=True)
            progress_text.empty()
            progress_bar.empty()
            st.error(
                "Something unexpected went wrong, and nothing was saved. The technical "
                "details below can help you (or someone you ask) fix it."
            )
            with st.expander("Technical details"):
                st.code(
                    f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}",
                    language="text",
                )
            return
        status.update(label="Study pack ready", state="complete", expanded=False)

    progress_text.empty()
    progress_bar.empty()

    record = {
        "version": 1,
        "id": f"unsaved-{uuid.uuid4().hex[:8]}",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "title": transcript.title,
        "source": transcript.source,
        "url": transcript.url,
        "video_id": transcript.video_id,
        "language": transcript.language,
        "word_count": transcript.word_count,
        "difficulty": options.difficulty,
        "question_count": options.question_count,
        "subject": options.subject,
        "page_count": transcript.page_count,
        "document_name": transcript.document_name,
        "provider": settings.provider,
        "model": settings.model,
        **payload.model_dump(),
    }

    try:
        record = save_pack(
            payload,
            {
                "title": transcript.title,
                "source": transcript.source,
                "url": transcript.url,
                "video_id": transcript.video_id,
                "language": transcript.language,
                "word_count": transcript.word_count,
                "difficulty": options.difficulty,
                "question_count": options.question_count,
                "subject": options.subject,
                "page_count": transcript.page_count,
                "document_name": transcript.document_name,
                "provider": settings.provider,
                "model": settings.model,
            },
            settings.data_dir,
        )
        st.session_state.flash = "Study pack saved to your library."
    except StudyBuddyError as exc:
        st.session_state.flash_warning = (
            f"{exc} This pack is still available until you close the tab."
        )

    st.session_state.current = record
    st.rerun()


# --------------------------------------------------------------------------- #
# Rendering a pack
# --------------------------------------------------------------------------- #
def _render_welcome(subject: Subject) -> None:
    st.markdown("### How it works")
    columns = st.columns(3)
    if subject.key == DOCUMENTS.key:
        columns[0].markdown(
            "**1. Add a source**\n\nUpload a PDF, or paste a link to a PDF or article "
            "page. The page's menu, ads, and footer are ignored."
        )
    else:
        columns[0].markdown(
            "**1. Add a source**\n\nPaste a YouTube link and the captions are fetched "
            "for you, or paste a transcript if captions aren't available."
        )
    columns[1].markdown(
        "**2. Generate**\n\nThe source text is split into chunks, summarised, and "
        f"combined into one {subject.label.lower()} pack. Every quote is checked "
        "against the source."
    )
    columns[2].markdown(
        "**3. Study**\n\nRead the notes, flip through the flashcards, then take the "
        "test. Download the notes or an Anki-ready CSV whenever you like."
    )
    if subject.key == DOCUMENTS.key:
        st.info(
            "Long documents are handled automatically. A very long PDF or article "
            "takes longer and uses more API calls, which can cost more."
        )
    else:
        st.info(
            "Long videos are handled automatically. Very long transcripts take longer "
            "and use more API calls, which can cost more."
        )


def _render_pack(record: dict, subject: Subject) -> None:
    try:
        payload = StudyPackPayload.model_validate(record)
    except ValidationError as exc:
        st.error(f"The saved pack is damaged and can't be displayed: {exc}")
        return

    st.divider()
    title = record.get("title") or "Study pack"
    st.header(title)

    details: list[str] = []
    source_kind = str(record.get("source") or "pasted")
    source_url = record.get("url")
    if source_kind == "youtube" and source_url:
        details.append(f"[Watch on YouTube]({source_url})")
    elif source_kind == "website" and source_url:
        details.append(f"[Source page]({source_url})")
    elif source_kind == "pdf":
        document_name = record.get("document_name")
        details.append(f"PDF · `{document_name}`" if document_name else "PDF document")
    else:
        details.append("Pasted transcript")
    if record.get("page_count"):
        details.append(f"{int(record['page_count']):,} pages")
    details.append(f"{int(record.get('word_count') or 0):,} words")
    details.append(f"{len(payload.questions)} test questions")
    details.append(f"{len(payload.flashcards)} flashcards")
    pack_subject = get_subject(str(record.get("subject") or "general"))
    details.append(f"{pack_subject.icon} {pack_subject.label}")
    if record.get("difficulty"):
        details.append(f"{str(record['difficulty']).title()} difficulty")
    if record.get("created_at"):
        details.append(_short_date(str(record["created_at"])))
    if record.get("model"):
        details.append(f"`{record['model']}`")
    st.markdown(" · ".join(details))

    if str(record.get("id", "")).startswith("unsaved-"):
        st.info("This pack could not be saved to disk. Download what you need before closing the tab.")

    notes_tab, cards_tab, test_tab = st.tabs(
        ["📝 Notes", "🃏 Flashcards", f"🧪 Practice test ({len(payload.questions)})"]
    )

    with notes_tab:
        _render_notes(payload, record)

    with cards_tab:
        _render_flashcards(payload, record)

    with test_tab:
        _render_practice_test(payload, record)


def _render_notes(payload: StudyPackPayload, record: dict) -> None:
    notes = payload.notes
    file_base = slugify(str(record.get("title") or "study-notes"))

    st.markdown("#### Summary")
    st.markdown(notes.summary)

    for section in notes.sections:
        st.markdown(f"#### {section.heading}")
        bullet_markdown = "\n".join(
            f"- {bold_key_terms(bullet.text, bullet.key_terms)}" for bullet in section.bullets
        )
        st.markdown(bullet_markdown)

    st.markdown("#### Key takeaways")
    st.markdown(
        "\n".join(
            f"{index}. {takeaway}" for index, takeaway in enumerate(notes.key_takeaways, 1)
        )
    )

    st.download_button(
        "⬇️ Download notes as Markdown",
        data=notes_to_markdown(payload, record),
        file_name=f"{file_base}-notes.md",
        mime="text/markdown",
        key=f"download_notes_{record.get('id')}",
    )


def _render_flashcards(payload: StudyPackPayload, record: dict) -> None:
    st.caption(
        "Click a card to flip it. Use **Previous / Next**, the **Shuffle** button, or "
        "the arrow keys while the card is selected."
    )
    st.iframe(flashcards_html(payload.flashcards), height=470)
    st.download_button(
        "⬇️ Download flashcards as CSV (Anki-ready)",
        data=flashcards_to_csv(payload),
        file_name=f"{slugify(str(record.get('title') or 'study-cards'))}-flashcards.csv",
        mime="text/csv",
        key=f"download_cards_{record.get('id')}",
    )


def _render_practice_test(payload: StudyPackPayload, record: dict) -> None:
    pack_id = str(record.get("id") or "current")
    graded_key = f"graded::{pack_id}"
    answers_key = f"answers::{pack_id}"
    graded = bool(st.session_state.get(graded_key, False))
    answers: dict[int, str | None] = st.session_state.get(answers_key, {})
    questions = payload.questions

    if graded:
        mcq_indices = [i for i, q in enumerate(questions) if q.kind == "multiple_choice"]
        correct = 0
        answered = 0
        for index in mcq_indices:
            question = questions[index]
            choice = answers.get(index)
            if choice in question.options:
                answered += 1
                if question.options.index(choice) == question.correct_index:
                    correct += 1

        total_mcq = len(mcq_indices)
        st.markdown("#### Your score")
        score_col, percent_col, blank_col = st.columns(3)
        score_col.metric("Multiple choice", f"{correct} / {total_mcq}")
        percent_col.metric("Percent", f"{round(100 * correct / total_mcq) if total_mcq else 0}%")
        blank_col.metric("Left blank", str(total_mcq - answered))
        if total_mcq:
            st.progress(correct / total_mcq)
        st.caption(
            "Only multiple-choice questions are graded automatically. Compare your "
            "short answers and critical-thinking answers with the answer key below."
        )
        if st.button("Retake test", key=f"retake::{pack_id}"):
            st.session_state.pop(answers_key, None)
            st.session_state.pop(graded_key, None)
            st.rerun()

    if not graded:
        # A form batches all answers; on submit we copy them into plain session
        # data so the review screen doesn't depend on live widget state.
        with st.form(key=f"test_form::{pack_id}"):
            for index, question in enumerate(questions):
                with st.container(border=True):
                    st.caption(
                        f"Question {index + 1} · {KIND_LABELS.get(question.kind, question.kind)}"
                    )
                    st.markdown(f"**{question.prompt}**")
                    key = _widget_key(pack_id, index)
                    if question.kind == "multiple_choice":
                        st.radio(
                            f"Answer for question {index + 1}",
                            options=question.options,
                            index=None,
                            key=key,
                            label_visibility="collapsed",
                        )
                    else:
                        st.text_area(
                            f"Your answer to question {index + 1}",
                            key=key,
                            height=110,
                            placeholder="Write your answer here…",
                            label_visibility="collapsed",
                        )
            submitted = st.form_submit_button(
                "Submit answers",
                type="primary",
                width="stretch",
                key=f"submit::{pack_id}",
            )

        if submitted:
            st.session_state[answers_key] = {
                index: st.session_state.get(_widget_key(pack_id, index))
                for index in range(len(questions))
            }
            st.session_state[graded_key] = True
            st.rerun()
        return

    for index, question in enumerate(questions):
        with st.container(border=True):
            st.caption(f"Question {index + 1} · {KIND_LABELS.get(question.kind, question.kind)}")
            st.markdown(f"**{question.prompt}**")
            answer = (answers.get(index) or "").strip()

            if question.kind == "multiple_choice":
                chosen = question.options.index(answer) if answer in question.options else None
                st.markdown(f"**Your answer:** {answer or '_No answer_'}  ")
                if chosen == question.correct_index:
                    st.success("Correct")
                elif chosen is None:
                    st.error("No answer selected — counted as incorrect.")
                else:
                    st.error("Not quite.")
            else:
                st.markdown(f"**Your answer:** {answer or '_No answer_'}  ")
                st.info("Not auto-graded. Compare your answer with the model answer below.")

            st.markdown(f"**Correct answer:** {question.answer}")
            st.markdown(f"**Why:** {question.explanation}")
            st.caption(f"From the transcript: “{question.source_quote}”")


def _widget_key(pack_id: str, index: int) -> str:
    return f"test::{pack_id}::{index}"


def _init_state() -> None:
    st.session_state.setdefault("current", None)
    st.session_state.setdefault("pending_delete", None)


if __name__ == "__main__":
    main()
