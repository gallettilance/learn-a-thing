"""Compact per-run brief — tonight's distilled working memory for agents."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from lib.lesson_consolidation import MAX_PLANNING_SLOTS, _stretch_planning_slots
from lib.pedagogy_state import load_pedagogy_carry_forward, load_pedagogy_latest
from lib.spine_state import sync_spine_progress

ROOT = Path(__file__).resolve().parent.parent
LEARNER = ROOT / "learner"
CURRICULUM = ROOT / "curriculum"
RUN_BRIEF_PATH = LEARNER / "run-brief.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {}


def _dump_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")


def active_arc_brief(arc: dict[str, Any]) -> dict[str, Any]:
    active = arc.get("active_arc") or {}
    day = int(active.get("current_day") or 1)
    beat = ""
    for planned in active.get("planned_beats") or []:
        if isinstance(planned, dict) and int(planned.get("day") or 0) == day:
            beat = str(planned.get("beat") or "")
            break
    return {
        "id": active.get("id", ""),
        "topic_label": active.get("topic_label", ""),
        "title": active.get("title", ""),
        "current_day": day,
        "beat": beat,
    }


def top_gaps(*, limit: int = 5) -> list[str]:
    data = _load_yaml(LEARNER / "gaps.yaml")
    gaps = data.get("gaps") or []
    out: list[str] = []
    for g in gaps:
        if not isinstance(g, dict):
            continue
        pressure = str(g.get("pressure") or g.get("description") or "").strip()
        if pressure:
            out.append(pressure)
        if len(out) >= limit:
            break
    return out


def mastered_topic_labels() -> list[str]:
    data = _load_yaml(LEARNER / "mastered-topics.yaml")
    topics = data.get("topics") or {}
    return sorted(label for label, entry in topics.items() if isinstance(entry, dict) and entry.get("mastered"))


def build_run_brief(
    report_date: str,
    *,
    engagement_summary: dict[str, Any] | None = None,
    suggested_night_type: str | None = None,
    carry_forward: list[str] | None = None,
) -> dict[str, Any]:
    if not (LEARNER / "spine-progress.yaml").is_file():
        sync_spine_progress()

    arc = _load_yaml(CURRICULUM / "narrative-arc.yaml")
    profile = _load_yaml(LEARNER / "profile.yaml")
    progress = _load_yaml(LEARNER / "spine-progress.yaml")
    pedagogy_latest = load_pedagogy_latest()
    guidance = pedagogy_latest.get("curator_guidance") or {}

    carry = carry_forward if carry_forward is not None else load_pedagogy_carry_forward()

    arc_brief = active_arc_brief(arc)
    night_type = suggested_night_type or "arc"
    stretch_curator = {
        "topic_label": arc_brief.get("topic_label"),
        "night_type": night_type,
        "lessons": [{"slot": i} for i in range(1, MAX_PLANNING_SLOTS + 1)],
    }

    brief: dict[str, Any] = {
        "date": report_date,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "arc": arc_brief,
        "spine": {
            "phase_id": progress.get("active_phase_id") or guidance.get("spine_phase_focus"),
            "phase_summary": progress.get("active_phase_summary", ""),
            "mastery_rung": progress.get("mastery_rung"),
            "pressure_invariant": guidance.get("pressure_invariant") or progress.get("pressure_invariant"),
        },
        "pedagogy": {
            "next_night_focus": guidance.get("next_night_focus", ""),
            "avoid": list(guidance.get("avoid") or [])[:5],
            "emphasize_edges": list(guidance.get("emphasize_edges") or [])[:6],
            "recommended_night_type": guidance.get("recommended_night_type"),
        },
        "learner": {
            "true_beginner_topics": list(profile.get("true_beginner_topics") or [])[:8],
            "mastered_topics": mastered_topic_labels()[:12],
            "blind_spots": list(profile.get("blind_spots") or [])[:8],
        },
        "consolidation": {
            "published_range": [2, 5],
            "stretch_slots": sorted(_stretch_planning_slots(stretch_curator)),
        },
        "carry_forward": carry[:8],
        "open_gaps": top_gaps(),
    }

    if suggested_night_type:
        brief["suggested_night_type"] = suggested_night_type
    if engagement_summary:
        brief["engagement"] = {
            "recommended_mode": engagement_summary.get("recommended_mode"),
            "last_night_unread": engagement_summary.get("last_night_unread"),
        }

    return brief


def save_run_brief(brief: dict[str, Any]) -> Path:
    _dump_yaml(RUN_BRIEF_PATH, brief)
    return RUN_BRIEF_PATH


def load_run_brief() -> dict[str, Any]:
    return _load_yaml(RUN_BRIEF_PATH)


def format_run_brief_yaml(brief: dict[str, Any] | None = None) -> str:
    data = brief if brief is not None else load_run_brief()
    if not data:
        return "(run brief not built yet)"
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


def update_run_brief_carry_forward(items: list[str]) -> None:
    brief = load_run_brief()
    if not brief:
        return
    brief["carry_forward"] = items[:8]
    save_run_brief(brief)
