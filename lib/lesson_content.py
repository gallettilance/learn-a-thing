"""Validate lesson markdown written by the editor pipeline."""

from __future__ import annotations

import re

LESSON_STUB_RE = re.compile(
    r"^\.\.\.\(\s*\d+\s+words(?:\s+—[^)]*)?\)\.\.\.\s*$",
    re.DOTALL,
)


def is_lesson_markdown_stub(markdown: str) -> bool:
    """True when markdown is a placeholder stub instead of full lesson body."""
    text = (markdown or "").strip()
    if not text:
        return True
    if LESSON_STUB_RE.fullmatch(text):
        return True
    if text.startswith("...(") and "words" in text and len(text) < 120:
        return True
    return False


def validate_lesson_markdown(markdown: str, *, source: str = "lesson") -> None:
    """Raise ValueError if markdown is missing or a word-count stub."""
    if is_lesson_markdown_stub(markdown):
        raise ValueError(
            f"{source} contains stub markdown (word-count placeholder only). "
            "Full lesson body is required for reports and site build."
        )
