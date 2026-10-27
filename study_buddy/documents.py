"""Read the text of one PDF or one web page.

Everything here returns plain text plus a little metadata. The study pipeline
never cares where the words came from, and nothing is guessed: a document with
no selectable text is refused rather than OCR'd from imagination.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

import requests
import trafilatura
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .errors import DocumentError

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
}
_MAX_BYTES = 25 * 1024 * 1024
_MAX_PAGES = 400
_MAX_REDIRECTS = 5


@dataclass(frozen=True)
class LoadedSource:
    kind: str  # "pdf" or "website"
    title: str
    text: str
    url: str | None = None
    page_count: int = 0
    document_name: str | None = None


def _normalize(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _check_url(url: str) -> str:
    candidate = (url or "").strip()
    if not re.match(r"^https?://", candidate, re.IGNORECASE):
        raise DocumentError(
            "That link needs to start with http:// or https://. Paste the address "
            "from your browser's address bar."
        )
    return candidate


def _download(url: str) -> tuple[bytes, str, str]:
    """Return (bytes, content-type, final URL), with size and error guards."""
    try:
        with requests.get(
            url,
            headers=_HEADERS,
            timeout=(8, 45),
            stream=True,
            allow_redirects=True,
        ) as response:
            if response.status_code >= 400:
                raise DocumentError(
                    f"The link returned an error (HTTP {response.status_code}). Check "
                    "that it opens in your browser without a login, then try again."
                )
            content_type = (response.headers.get("Content-Type") or "").lower()
            declared = response.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > _MAX_BYTES:
                raise DocumentError(
                    f"That file is larger than {_MAX_BYTES // (1024 * 1024)} MB. "
                    "Please use a smaller PDF."
                )
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > _MAX_BYTES:
                    raise DocumentError(
                        f"That file is larger than {_MAX_BYTES // (1024 * 1024)} MB. "
                        "Please use a smaller PDF."
                    )
                chunks.append(chunk)
            return b"".join(chunks), content_type, response.url
    except requests.Timeout as exc:
        raise DocumentError(
            "The site took too long to respond. Check your internet connection, then "
            "try again or download the file and upload it instead."
        ) from exc
    except requests.RequestException as exc:
        raise DocumentError(
            f"That link could not be opened ({type(exc).__name__}). Check the address "
            "and your internet connection, then try again."
        ) from exc


def _filename_title(filename: str) -> str:
    base = re.sub(r"\.pdf$", "", (filename or "").strip(), flags=re.IGNORECASE)
    base = re.sub(r"[_-]+", " ", base)
    base = re.sub(r"\s+", " ", base).strip(" -_")
    return base or "PDF document"


def _pdf_title(reader: PdfReader, fallback: str) -> str:
    info = reader.metadata or {}
    raw = str(info.get("/Title") or "").strip()
    if 3 <= len(raw) <= 200 and not raw.lower().endswith(".pdf"):
        return raw
    return fallback


def load_pdf(data: bytes, filename: str = "", url: str | None = None) -> LoadedSource:
    if not data.lstrip()[:5] == b"%PDF-" and b"%PDF-" not in data[:1024]:
        raise DocumentError(
            "That file doesn't look like a PDF. Choose a PDF file, or paste a link to "
            "a web page instead."
        )

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001 - pypdf raises several types
                raise DocumentError(
                    "That PDF is password-protected. Remove the password in a PDF "
                    "reader, then upload it again."
                ) from exc
        page_total = len(reader.pages)
        if page_total == 0:
            raise DocumentError("That PDF has no pages, so there is nothing to study.")
        if page_total > _MAX_PAGES:
            raise DocumentError(
                f"That PDF has {page_total} pages, which is more than this app reads at "
                f"once ({_MAX_PAGES}). Split it into chapters and upload one at a time."
            )

        pages: list[str] = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001 - one bad page should not kill the file
                pages.append("")
    except DocumentError:
        raise
    except (PdfReadError, ValueError, OSError) as exc:
        raise DocumentError(
            f"That PDF could not be read ({type(exc).__name__}). It may be damaged. "
            "Try opening it in a PDF reader and saving a fresh copy."
        ) from exc

    text = _normalize("\n\n".join(page for page in pages if page.strip()))
    if len(text.split()) < 30:
        raise DocumentError(
            "This PDF has no selectable text — it looks like a scan or photos of pages. "
            "The app will not guess at the contents. Open it in a PDF reader and run "
            "“Recognise text” (OCR), or use a text-based PDF, then try again."
        )

    fallback = _filename_title(filename)
    return LoadedSource(
        kind="pdf",
        title=_pdf_title(reader, fallback),
        text=text,
        url=url,
        page_count=page_total,
        document_name=(filename or None),
    )


def _web_title(html: bytes, url: str) -> str:
    try:
        metadata = trafilatura.extract_metadata(html, default_url=url)
    except Exception:  # noqa: BLE001 - metadata is a nicety, never fatal
        metadata = None
    title = str(getattr(metadata, "title", "") or "").strip()
    if 2 <= len(title) <= 200:
        return title
    path = Path(requests.utils.urlparse(url).path)
    return path.stem.replace("-", " ").replace("_", " ").title() or "Web page"


def _looks_like_pdf(content: bytes, content_type: str, url: str) -> bool:
    if b"%PDF-" in content[:1024]:
        return True
    if "application/pdf" in content_type:
        return True
    return requests.utils.urlparse(url).path.lower().endswith(".pdf")


def load_web_page(url: str) -> LoadedSource:
    checked = _check_url(url)
    content, content_type, final_url = _download(checked)

    if _looks_like_pdf(content, content_type, final_url):
        return load_pdf(content, Path(requests.utils.urlparse(final_url).path).name, final_url)

    if "html" not in content_type and content_type and "xml" not in content_type:
        raise DocumentError(
            f"That link is not a web page or a PDF (it returned {content_type.split(';')[0]}). "
            "Paste the address of an article page instead."
        )

    try:
        article = trafilatura.extract(
            content,
            url=final_url,
            output_format="markdown",
            include_tables=True,
            include_comments=False,
            include_images=False,
            include_links=False,
            favor_recall=True,
        )
    except Exception as exc:  # noqa: BLE001 - extraction is best-effort
        raise DocumentError(
            f"The page could not be read ({type(exc).__name__}). Try a different link, "
            "or save the page as a PDF and upload that."
        ) from exc

    text = _normalize(article or "")
    if len(text.split()) < 50:
        raise DocumentError(
            "No readable article text was found at that link. The page may need a "
            "login, be mostly images or video, or build its text with JavaScript. Try a "
            "different link, or save the page as a PDF and upload it."
        )

    return LoadedSource(
        kind="website",
        title=_web_title(content, final_url),
        text=text,
        url=final_url,
    )


def load_document(
    upload_bytes: bytes | None = None,
    upload_name: str = "",
    link: str = "",
) -> LoadedSource:
    """Read an uploaded PDF (preferred) or a pasted PDF/web link."""
    if upload_bytes:
        return load_pdf(upload_bytes, upload_name)
    checked = _check_url(link)
    return load_web_page(checked)
