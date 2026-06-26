"""Learner topic mastery — skip intro and diversity slots for owned topics."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
LEARNER = ROOT / "learner"
MASTERED_PATH = LEARNER / "mastered-topics.yaml"


def _load_yaml(path: Path) -> Any:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _save_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "# User-confirmed topic mastery — curator skips intro; diversity slots avoid these\n\n"
    path.write_text(header + yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")


def load_profile() -> dict[str, Any]:
    return _load_yaml(LEARNER / "profile.yaml")


def load_mastery_entries() -> dict[str, dict[str, Any]]:
    raw = _load_yaml(MASTERED_PATH)
    topics = raw.get("topics") or {}
    if not isinstance(topics, dict):
        return {}
    return {str(k): (v if isinstance(v, dict) else {}) for k, v in topics.items()}


def needs_gentle_intro(topic_label: str, *, profile: dict[str, Any] | None = None) -> bool:
    """True when the learner has not mastered this topic via seeds or site confirmation."""
    return not is_topic_mastered(topic_label, profile=profile)


def is_topic_mastered(topic_label: str, *, profile: dict[str, Any] | None = None) -> bool:
    label = str(topic_label or "").strip()
    if not label:
        return False

    entries = load_mastery_entries()
    entry = entries.get(label)
    if isinstance(entry, dict) and entry.get("mastered") is False:
        return False
    if isinstance(entry, dict) and entry.get("mastered") is True:
        return True

    prof = profile if profile is not None else load_profile()
    seeded = prof.get("seeded_topics") or []
    return label in seeded


def all_mastered_labels(*, profile: dict[str, Any] | None = None) -> set[str]:
    prof = profile if profile is not None else load_profile()
    labels: set[str] = {str(t).strip() for t in prof.get("seeded_topics") or [] if str(t).strip()}

    for label, entry in load_mastery_entries().items():
        if not isinstance(entry, dict):
            continue
        if entry.get("mastered") is False:
            labels.discard(label)
        elif entry.get("mastered") is True:
            labels.add(label)

    return labels


def set_topic_mastered(
    topic_label: str,
    mastered: bool,
    *,
    note: str = "",
    source: str = "user",
) -> dict[str, Any]:
    label = str(topic_label or "").strip()
    if not label:
        raise ValueError("topic_label required")

    raw = _load_yaml(MASTERED_PATH)
    if not isinstance(raw, dict):
        raw = {}
    topics = raw.setdefault("topics", {})
    if not isinstance(topics, dict):
        topics = {}
        raw["topics"] = topics

    if mastered:
        entry: dict[str, Any] = {
            "mastered": True,
            "mastered_at": date.today().isoformat(),
            "source": source,
        }
        if note.strip():
            entry["note"] = note.strip()
        topics[label] = entry
    else:
        prof = load_profile()
        if label in (prof.get("seeded_topics") or []):
            topics[label] = {"mastered": False, "reopened_at": date.today().isoformat()}
        elif label in topics:
            del topics[label]

    _save_yaml(MASTERED_PATH, raw)
    return {"topic_label": label, "mastered": mastered}
