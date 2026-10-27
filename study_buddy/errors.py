"""Error types used across the app.

Every error message in this module is written for a non-programmer: it says what
went wrong and what the person running the app can do about it.
"""

from __future__ import annotations


class StudyBuddyError(Exception):
    """Base class for expected, user-facing errors."""


class ConfigError(StudyBuddyError):
    """The .env file is missing something the app needs."""


class TranscriptError(StudyBuddyError):
    """A transcript or document could not be fetched, or its text is unusable."""


class DocumentError(StudyBuddyError):
    """A PDF or web page could not be read, or contains no usable text."""


class LLMError(StudyBuddyError):
    """The language-model API rejected a request or returned unusable output."""


class ContentError(StudyBuddyError):
    """The model's answer passed the API but failed the app's quality checks."""
