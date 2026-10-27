"""Subject sections.

The app works exactly the same in every section. A section only changes the
wording of the prompts (what the model is told to pay attention to) and a few
labels in the interface. Grounding rules never change: the model may use only
what the transcript says.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Subject:
    key: str
    label: str
    icon: str
    headline: str
    description: str
    source_placeholder: str
    title_placeholder: str
    section_note: str
    map_guidance: str
    notes_guidance: str
    flashcards_guidance: str
    questions_guidance: str


GENERAL = Subject(
    key="general",
    label="General",
    icon="🎬",
    headline="🎬 Turn a video into study materials",
    description=(
        "Paste a **YouTube link** or a **transcript**, and get notes, 15–25 flip "
        "flashcards, and a practice test. Everything is generated only from the "
        "transcript."
    ),
    source_placeholder=(
        "https://www.youtube.com/watch?v=…\n\nor paste the full transcript here"
    ),
    title_placeholder="e.g. Biology 101 – Photosynthesis",
    section_note="",
    map_guidance="",
    notes_guidance="",
    flashcards_guidance="",
    questions_guidance="",
)

CHEMISTRY = Subject(
    key="chemistry",
    label="Chemistry",
    icon="🧪",
    headline="🧪 Turn a chemistry video into study materials",
    description=(
        "Paste a **chemistry YouTube link** or a **transcript**, and get chemistry "
        "notes, 15–25 flip flashcards, and a practice test built around formulas, "
        "reactions, and mechanisms. Every fact still has to come from the transcript."
    ),
    source_placeholder=(
        "https://www.youtube.com/watch?v=… (a chemistry lecture)\n\n"
        "or paste the full chemistry transcript here"
    ),
    title_placeholder="e.g. Organic Chemistry – SN1 vs SN2 reactions",
    section_note=(
        "Chemistry section: equations, conditions, and quantities are kept exactly as "
        "the video states them. The model is told never to balance, correct, or complete "
        "an equation from outside knowledge."
    ),
    map_guidance=(
        "- Treat this as a chemistry lesson and capture every chemical detail the "
        "speaker gives: substance names and formulas, reaction equations exactly as "
        "written or described, conditions (temperature, pressure, catalyst, solvent, "
        "concentration), observations (colour change, gas, precipitate, heat), units "
        "and quantities, and each step of a mechanism in the order given.\n"
        "- Copy formulas and equations character-for-character. Do not balance them, "
        "correct them, complete them, or add products the video does not mention."
    ),
    notes_guidance=(
        "- Write chemistry notes: keep formulas, equations, and units exactly as the "
        "transcript gives them (for example **H2SO4**, **2 H2 + O2 → 2 H2O**), put "
        "mechanism steps in the video's order, and state the conditions each reaction "
        "needs.\n"
        "- Bold substance names, functional groups, reaction types, and key quantities.\n"
        "- Never add a formula, product, mechanism step, or numerical value that is not "
        "in the brief, and never “fix” an equation."
    ),
    flashcards_guidance=(
        "- Make the cards chemistry-specific: names and formulas, predicting products, "
        "the conditions a reaction needs, mechanism steps in order, and calculations "
        "using only quantities the transcript provides. A calculation card must show "
        "the setup and the result on the back.\n"
        "- Do not require the periodic table, a constant, or a value the video never "
        "gives."
    ),
    questions_guidance=(
        "- Chemistry questions should test formulas and nomenclature, products and "
        "reaction conditions, ordering mechanism steps, and quantitative reasoning "
        "(moles, concentration, yield) using only numbers that appear in the "
        "transcript. Every calculation must be solvable from the question plus the "
        "brief, without outside constants or a periodic table.\n"
        "- Do not ask for a product, equation, or mechanism step the video never "
        "discusses."
    ),
)

DOCUMENTS = Subject(
    key="documents",
    label="Documents & web",
    icon="📄",
    headline="📄 Turn a PDF or web page into study materials",
    description=(
        "Upload a **PDF** or paste a **link** to a PDF or article, and get notes, "
        "15–25 flip flashcards, and a practice test written from that text alone. "
        "Scanned PDFs with no selectable text are refused rather than guessed at."
    ),
    source_placeholder="",
    title_placeholder="e.g. Climate report – Chapter 3",
    section_note=(
        "Documents & web section: reads one PDF or one article page. Numbers, names, "
        "and quotations are kept exactly as written, and nothing is added from outside "
        "the document."
    ),
    map_guidance=(
        "- Treat this as a written document (PDF report, paper, article, or web page). "
        "Capture its claims, definitions, evidence, data, named people or organisations, "
        "dates, and any stated conditions or limitations, in the order they appear. "
        "Keep numbers, units, and wording exactly as written."
    ),
    notes_guidance=(
        "- Follow the document's own headings and order where it has them. Preserve "
        "numbers, units, dates, names, and technical terms exactly, and distinguish the "
        "document's claims from the evidence it gives for them.\n"
        "- Never add background, context, or examples that are not in the brief. Do not "
        "describe the document itself (its references, formatting, or links); summarise "
        "its content instead."
    ),
    flashcards_guidance=(
        "- Draw cards from the document's definitions, arguments, evidence, and worked "
        "examples. Application cards must use situations the document itself supports; "
        "do not invent data or scenarios."
    ),
    questions_guidance=(
        "- Test comprehension of the document's argument, its evidence, and the "
        "relationships between its points. Quantitative questions must use numbers "
        "exactly as given and be solvable without outside data. Do not ask about page "
        "numbers, formatting, or the author unless that is central to the content."
    ),
)

SUBJECTS: dict[str, Subject] = {
    subject.key: subject for subject in (GENERAL, CHEMISTRY, DOCUMENTS)
}


def get_subject(key: str | None) -> Subject:
    """Look up a section, falling back to General for old or unknown packs."""
    return SUBJECTS.get((key or "").strip().lower(), GENERAL)
