"""Master spine curriculum — phase-aware context for curator and grapher."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CURRICULUM = ROOT / "curriculum"
LEARNER = ROOT / "learner"
SPINE_PATH = CURRICULUM / "master-spine.yaml"
PROGRESS_PATH = LEARNER / "spine-progress.yaml"


def _load_yaml(path: Path) -> Any:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _save_yaml(path: Path, data: dict[str, Any], header: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")


def load_master_spine() -> dict[str, Any]:
    return _load_yaml(SPINE_PATH)


def get_active_phase(spine: dict[str, Any] | None = None) -> dict[str, Any]:
    spine = spine or load_master_spine()
    phases = spine.get("phases") or []
    for phase in phases:
        if isinstance(phase, dict) and phase.get("status") == "active":
            return phase
    for phase in phases:
        if isinstance(phase, dict) and phase.get("status") == "pending":
            return phase
    return phases[0] if phases else {}


def get_phase_by_id(phase_id: str, spine: dict[str, Any] | None = None) -> dict[str, Any] | None:
    spine = spine or load_master_spine()
    for phase in spine.get("phases") or []:
        if isinstance(phase, dict) and phase.get("id") == phase_id:
            return phase
    return None


def exploration_bridge_for_domain(domain: str, spine: dict[str, Any] | None = None) -> dict[str, Any] | None:
    spine = spine or load_master_spine()
    domain_l = domain.strip().lower()
    for entry in spine.get("exploration_map") or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("domain", "")).lower() == domain_l:
            return entry
    return None


def _high_priority_gaps_for_phase(phase_id: str) -> list[str]:
    gaps_data = _load_yaml(LEARNER / "gaps.yaml")
    gaps = gaps_data.get("gaps") if isinstance(gaps_data, dict) else gaps_data
    if not isinstance(gaps, list):
        return []
    out: list[str] = []
    for g in gaps:
        if not isinstance(g, dict):
            continue
        if g.get("phase_id") and g.get("phase_id") != phase_id:
            continue
        if str(g.get("priority", "")).lower() == "high":
            out.append(str(g.get("pressure", "")).strip())
    return [p for p in out if p]


def sync_spine_progress() -> dict[str, Any]:
    """Write learner/spine-progress.yaml — active phase snapshot for agents."""
    spine = load_master_spine()
    active = get_active_phase(spine)
    phase_id = str(active.get("id", ""))

    pedagogy = _load_yaml(LEARNER / "pedagogy-feedback.yaml").get("latest") or {}
    guidance = pedagogy.get("curator_guidance") or {}

    progress = {
        "synced_at": date.today().isoformat(),
        "goal": (spine.get("goal") or "").strip(),
        "active_phase_id": phase_id,
        "active_phase_name": active.get("name", ""),
        "active_phase_summary": active.get("summary", ""),
        "target_invariants": active.get("target_invariants") or [],
        "target_rung": active.get("target_rung"),
        "curriculum_topics": active.get("curriculum_topics") or [],
        "bridge_topics": active.get("bridge_topics") or [],
        "depth_budget": spine.get("depth_budget") or {},
        "high_priority_gaps": _high_priority_gaps_for_phase(phase_id),
        "last_grapher_focus": guidance.get("next_night_focus", ""),
        "pending_phases": [
            {"id": p.get("id"), "name": p.get("name"), "order": p.get("order")}
            for p in spine.get("phases") or []
            if isinstance(p, dict) and p.get("status") == "pending"
        ][:4],
    }
    _save_yaml(
        PROGRESS_PATH,
        progress,
        header="# Auto-synced from master-spine + gaps + pedagogy — do not edit by hand\n\n",
    )
    return progress


def format_spine_context() -> str:
    """Compact spine summary for agent prompts."""
    spine = load_master_spine()
    active = get_active_phase(spine)
    progress = _load_yaml(PROGRESS_PATH)
    if not progress.get("active_phase_id"):
        progress = sync_spine_progress()

    lines = [
        f"Goal: {(spine.get('goal') or '').strip()}",
        "",
        f"Active phase: {progress.get('active_phase_id')} — {progress.get('active_phase_name')}",
        f"  {progress.get('active_phase_summary', '')}",
        f"  Target invariants: {', '.join(progress.get('target_invariants') or [])}",
        f"  Target rung: {progress.get('target_rung')}",
        f"  Spine topics (depth): {', '.join(progress.get('curriculum_topics') or [])}",
        f"  Bridge topics (same anchor): {', '.join(progress.get('bridge_topics') or [])}",
        "",
        "Depth budget:",
        f"  ~{spine.get('depth_budget', {}).get('arc_and_bridge_nights_pct', 85)}% arc/bridge nights",
        f"  Defer exploration if active phase rung < {spine.get('depth_budget', {}).get('defer_exploration_if_active_phase_rung_below', 3)}",
        "",
    ]

    gaps = progress.get("high_priority_gaps") or []
    if gaps:
        lines.append("High-priority gaps (active phase):")
        for g in gaps[:5]:
            lines.append(f"  - {g}")
        lines.append("")

    if progress.get("last_grapher_focus"):
        lines.append(f"Last grapher focus: {progress['last_grapher_focus']}")
        lines.append("")

    pending = progress.get("pending_phases") or []
    if pending:
        lines.append("Next phases (pending):")
        for p in pending:
            lines.append(f"  - {p.get('id')}: {p.get('name')}")
        lines.append("")

    lines.append("Exploration rule: far-field nights must bridge home to home_invariant in master-spine exploration_map.")
    return "\n".join(lines)
