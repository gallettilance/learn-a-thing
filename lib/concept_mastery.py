"""Per-concept mastery — finer-grained than topic or lesson labels.

Lesson mastery marks ONE concept (the lesson's `concept` field). Topic mastery
(skipped intro / bridge slots) does NOT imply all concepts in that topic are
mastered for prerequisite gating.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONCEPT_MASTERY_PATH = ROOT / "learner" / "concept-mastery.yaml"


def _load_yaml(path: Path) -> Any:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _save_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Concept-level mastery — prerequisite gate uses these, not whole-topic flags.\n"
        "# Format: concept_id -> {mastered, mastered_at, source, note, lesson_ref?}\n\n"
    )
    path.write_text(header + yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")


def load_concept_entries() -> dict[str, dict[str, Any]]:
    raw = _load_yaml(CONCEPT_MASTERY_PATH)
    concepts = raw.get("concepts") or {}
    if not isinstance(concepts, dict):
        return {}
    return {str(k): (v if isinstance(v, dict) else {}) for k, v in concepts.items()}


def is_concept_mastered_user(concept_id: str) -> bool:
    cid = str(concept_id or "").strip()
    if not cid:
        return False
    entry = load_concept_entries().get(cid)
    if not isinstance(entry, dict):
        return False
    if entry.get("mastered") is False:
        return False
    return entry.get("mastered") is True


def set_concept_mastered(
    concept_id: str,
    mastered: bool,
    *,
    note: str = "",
    source: str = "user",
    lesson_ref: str = "",
    topic_label: str = "",
) -> dict[str, Any]:
    cid = str(concept_id or "").strip()
    if not cid:
        raise ValueError("concept_id required")

    raw = _load_yaml(CONCEPT_MASTERY_PATH)
    if not isinstance(raw, dict):
        raw = {}
    concepts = raw.setdefault("concepts", {})
    if not isinstance(concepts, dict):
        concepts = {}
        raw["concepts"] = concepts

    if mastered:
        entry: dict[str, Any] = {
            "mastered": True,
            "mastered_at": date.today().isoformat(),
            "source": source,
        }
        if note.strip():
            entry["note"] = note.strip()
        if lesson_ref.strip():
            entry["lesson_ref"] = lesson_ref.strip()
        if topic_label.strip():
            entry["topic_label"] = topic_label.strip()
        concepts[cid] = entry
    elif cid in concepts:
        del concepts[cid]

    _save_yaml(CONCEPT_MASTERY_PATH, raw)
    return {"concept_id": cid, "mastered": mastered}
