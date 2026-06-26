"""Shared lesson title formatting."""

from __future__ import annotations

import re


def topic_prefixed_title(topic_label: str, question: str) -> str:
    """Prefix a lesson title so the topic is visible at a glance."""
    label = topic_label.strip()
    q = question.strip().rstrip("?").strip()
    if not label:
        return f"{q}?" if q else ""
    if re.match(r"^\[.+?\]", q):
        return f"{q}?"
    return f"[{label}] {q}?"


def parse_topic_from_title(title: str) -> tuple[str | None, str]:
    """Return (topic_label, question) from a prefixed title."""
    m = re.match(r"^\[(.+?)\]\s*(.+)$", title.strip())
    if m:
        return m.group(1), m.group(2)
    return None, title


def topic_slug(label: str) -> str:
    """URL-safe slug for a topic label."""
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return slug or "general"

