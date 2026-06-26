"""Role-specific agent context packs with size budgets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from lib.anchor_primer import format_anchor_for_agents
from lib.pedagogy_state import format_pedagogy_for_agents, migrate_pedagogy_history
from lib.playbook import format_playbook_for_role
from lib.run_brief import format_run_brief_yaml, load_run_brief
from lib.spine_state import format_spine_context

ROOT = Path(__file__).resolve().parent.parent
LEARNER = ROOT / "learner"
CURRICULUM = ROOT / "curriculum"
REPORTS = ROOT / "reports"

ROLE_BUDGETS: dict[str, int] = {
    "curator": 45_000,
    "consolidator": 20_000,
    "teacher": 28_000,
    "editor": 22_000,
    "research": 18_000,
    "hypothesis": 20_000,
    "grapher": 25_000,
}


def _read(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {}


def _section(title: str, body: str) -> str:
    body = (body or "").strip()
    if not body:
        return ""
    return f"=== {title} ===\n{body}"


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 40] + "\n\n… (context truncated to budget)"


def active_arc_slice() -> str:
    arc = _load_yaml(CURRICULUM / "narrative-arc.yaml")
    active = arc.get("active_arc") or {}
    day = int(active.get("current_day") or 1)
    beat = next(
        (
            p
            for p in active.get("planned_beats") or []
            if isinstance(p, dict) and int(p.get("day") or 0) == day
        ),
        {},
    )
    slice_data = {
        "active_arc": {
            "id": active.get("id"),
            "topic_label": active.get("topic_label"),
            "current_day": day,
            "beat": beat.get("beat") if isinstance(beat, dict) else "",
            "night_lessons": beat.get("night_lessons") if isinstance(beat, dict) else [],
        }
    }
    return yaml.dump(slice_data, default_flow_style=False, sort_keys=False)


def concept_graph_slice() -> str:
    graph = _load_yaml(CURRICULUM / "concept-graph.yaml")
    slim = {
        "invariants": graph.get("invariants"),
        "night_types": graph.get("night_types"),
        "weekly_schedule": graph.get("weekly_schedule"),
        "mastery_rungs": graph.get("mastery_rungs"),
        "bridge_night_templates": graph.get("bridge_night_templates"),
    }
    seed = graph.get("seed_edges") or []
    slim["seed_edges"] = seed[:40] if len(seed) > 40 else seed
    return yaml.dump(slim, default_flow_style=False, sort_keys=False)


def recent_meta_compact(*, limit: int = 2) -> str:
    metas = sorted(REPORTS.glob("*/meta.yaml"), reverse=True)[:limit]
    lines: list[str] = []
    for m in metas:
        meta = _load_yaml(m)
        lines.append(
            f"- {meta.get('date')}: {meta.get('topic_label')} day {meta.get('narrative_day')} — "
            f"{str(meta.get('night_thread') or meta.get('pedagogy_summary') or '')[:120]}"
        )
    return "\n".join(lines) if lines else "(no prior reports)"


def build_role_context(
    role: str,
    *,
    report_date: str | None = None,
    topic_label: str | None = None,
    max_hypotheses: int = 20,
    curator: dict[str, Any] | None = None,
    format_hypotheses_fn: Any | None = None,
    format_engagement_fn: Any | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Build role-specific context string and a manifest of included sections.

    format_hypotheses_fn / format_engagement_fn injected from nightly to avoid circular imports.
    """
    migrate_pedagogy_history()

    arc = _load_yaml(CURRICULUM / "narrative-arc.yaml")
    arc_id = (arc.get("active_arc") or {}).get("id", "spam-filter-bayes")
    if topic_label is None:
        topic_label = (arc.get("active_arc") or {}).get("topic_label", "")

    parts: list[str] = []
    manifest: dict[str, Any] = {"role": role, "sections": []}

    def add(name: str, content: str) -> None:
        block = _section(name, content)
        if block:
            parts.append(block)
            manifest["sections"].append({"name": name, "chars": len(block)})

    brief_yaml = format_run_brief_yaml()
    add("learner/run-brief.yaml", brief_yaml)
    add(f"playbook ({role})", format_playbook_for_role(role))
    add("pedagogy (latest)", format_pedagogy_for_agents())

    if role in ("curator", "research", "hypothesis", "grapher"):
        add("master spine summary", format_spine_context())
        add("learner/spine-progress.yaml", _read(LEARNER / "spine-progress.yaml"))
        add("curriculum/narrative-arc (active beat)", active_arc_slice())
        add("curriculum/concept-graph (slice)", concept_graph_slice())
        add("learner/profile.yaml", _read(LEARNER / "profile.yaml"))
        add("learner/topic-queue.yaml", _read(LEARNER / "topic-queue.yaml"))
        add("learner/engagement.yaml", _read(LEARNER / "engagement.yaml"))
        add("learner/mastered-topics.yaml", _read(LEARNER / "mastered-topics.yaml"))
        add("curriculum/exploration-topics.yaml", _read(CURRICULUM / "exploration-topics.yaml"))
        add("anchor primer summary", format_anchor_for_agents(arc_id, report_date=report_date))
        if format_hypotheses_fn is not None:
            add("learner/hypotheses.jsonl (filtered)", format_hypotheses_fn(topic_label=topic_label, max_entries=max_hypotheses))
        edges_path = LEARNER / "concept-edges.jsonl"
        if edges_path.is_file():
            lines = edges_path.read_text(encoding="utf-8").strip().splitlines()
            if len(lines) > 30:
                lines = lines[-30:]
            add("learner/concept-edges.jsonl (recent)", "\n".join(lines))
        gaps = _read(LEARNER / "gaps.yaml")
        if gaps:
            add("learner/gaps.yaml", gaps)
        add("recent reports (compact)", recent_meta_compact())

    elif role == "teacher":
        add("anchor primer summary", format_anchor_for_agents(arc_id, report_date=report_date))
        add("learner/profile.yaml (blind_spots)", yaml.dump(
            {"blind_spots": _load_yaml(LEARNER / "profile.yaml").get("blind_spots")},
            default_flow_style=False,
        ))
        if format_hypotheses_fn is not None:
            add("learner/hypotheses.jsonl (filtered)", format_hypotheses_fn(topic_label=topic_label, max_entries=15))

    elif role == "editor":
        from lib.lesson_chat import format_for_editor

        chat = format_for_editor()
        if chat.strip():
            add("learner lesson follow-ups", chat)

    elif role == "consolidator":
        if curator is not None:
            add("curator plan (lesson_groups)", yaml.dump(
                {
                    "lesson_groups": curator.get("lesson_groups"),
                    "published_lesson_count": curator.get("published_lesson_count"),
                    "lessons": curator.get("lessons"),
                },
                default_flow_style=False,
                sort_keys=False,
            ))

    elif role == "research":
        pass  # brief + playbook + pedagogy + curator plan in user message

    text = "\n\n".join(parts)
    budget = ROLE_BUDGETS.get(role, 30_000)
    truncated = len(text) > budget
    final = _truncate(text, budget)
    manifest["total_chars"] = len(text)
    manifest["final_chars"] = len(final)
    manifest["budget"] = budget
    manifest["truncated"] = truncated
    return final, manifest


def save_context_manifest(pipe_dir: Path, role: str, manifest: dict[str, Any]) -> None:
    path = pipe_dir / f"context-manifest-{role}.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
