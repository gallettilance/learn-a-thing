"""Pedagogy feedback: latest-only working file + dated archive."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
LEARNER = ROOT / "learner"
PEDAGOGY_PATH = LEARNER / "pedagogy-feedback.yaml"
ARCHIVE_DIR = LEARNER / "archive" / "pedagogy"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {}


def _dump_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")


def archive_path_for_date(report_date: str) -> Path:
    return ARCHIVE_DIR / f"{report_date}.yaml"


def archive_pedagogy_entry(entry: dict[str, Any], report_date: str) -> Path:
    """Write one night's full grapher feedback to archive."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    path = archive_path_for_date(report_date)
    payload = dict(entry)
    payload.setdefault("date", report_date)
    _dump_yaml(path, payload)
    return path


def load_pedagogy_latest() -> dict[str, Any]:
    data = _load_yaml(PEDAGOGY_PATH)
    latest = data.get("latest")
    return dict(latest) if isinstance(latest, dict) else {}


def load_pedagogy_carry_forward() -> list[str]:
    data = _load_yaml(PEDAGOGY_PATH)
    items = data.get("carry_forward") or []
    return [str(x).strip() for x in items if str(x).strip()]


def migrate_pedagogy_history(*, dry_run: bool = False) -> list[str]:
    """
    Move pedagogy-feedback entries[] to learner/archive/pedagogy/ and slim the working file.

    Returns archive paths written.
    """
    data = _load_yaml(PEDAGOGY_PATH)
    if not data:
        return []

    written: list[str] = []
    latest = data.get("latest")
    entries = list(data.get("entries") or [])

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        date = str(entry.get("date") or "").strip()
        if not date:
            continue
        dest = archive_path_for_date(date)
        if dest.is_file():
            continue
        if not dry_run:
            archive_pedagogy_entry(entry, date)
        try:
            written.append(str(dest.relative_to(ROOT)))
        except ValueError:
            written.append(str(dest))

    if not dry_run and (entries or "entries" in data):
        slim: dict[str, Any] = {}
        if isinstance(latest, dict):
            slim["latest"] = latest
        if data.get("carry_forward"):
            slim["carry_forward"] = data["carry_forward"]
        _dump_yaml(PEDAGOGY_PATH, slim)

    return written


def persist_pedagogy_latest(
    grapher: dict[str, Any],
    report_date: str,
    *,
    carry_forward: list[str] | None = None,
) -> None:
    """Archive tonight's entry and update pedagogy-feedback.yaml (latest only)."""
    migrate_pedagogy_history()

    entry = {
        "date": report_date,
        "quality_scores": grapher.get("quality_scores"),
        "curator_guidance": grapher.get("curator_guidance"),
        "summary": grapher.get("summary"),
        "lesson_feedback": grapher.get("lesson_feedback"),
        "hypothesis_audit": grapher.get("hypothesis_audit"),
        "edges_strengthened": grapher.get("edges_strengthened"),
        "new_edge_count": len(grapher.get("new_edges") or []),
    }
    archive_pedagogy_entry(entry, report_date)

    payload: dict[str, Any] = {"latest": entry}
    if carry_forward:
        payload["carry_forward"] = carry_forward[:8]
    elif load_pedagogy_carry_forward():
        payload["carry_forward"] = load_pedagogy_carry_forward()

    _dump_yaml(PEDAGOGY_PATH, payload)


def format_pedagogy_for_agents(*, max_avoid: int = 5, max_summary_chars: int = 600) -> str:
    """Compact pedagogy block for agent context (~30 lines)."""
    latest = load_pedagogy_latest()
    if not latest:
        return "(no pedagogy feedback yet)"

    lines: list[str] = [f"date: {latest.get('date', '?')}"]
    guidance = latest.get("curator_guidance") or {}
    if guidance.get("next_night_focus"):
        lines.append(f"next_night_focus: {guidance['next_night_focus']}")
    avoid = [str(a) for a in guidance.get("avoid") or [] if str(a).strip()]
    if avoid:
        lines.append("avoid:")
        for item in avoid[:max_avoid]:
            lines.append(f"  - {item}")
    edges = guidance.get("emphasize_edges") or []
    if edges:
        lines.append(f"emphasize_edges: {', '.join(str(e) for e in edges)}")
    for key in ("recommended_night_type", "pressure_invariant", "spine_phase_focus", "mastery_rung_target"):
        if guidance.get(key) is not None:
            lines.append(f"{key}: {guidance[key]}")

    summary = str(latest.get("summary") or "").strip()
    if summary:
        if len(summary) > max_summary_chars:
            summary = summary[: max_summary_chars - 3] + "..."
        lines.append(f"summary: {summary}")

    carry = load_pedagogy_carry_forward()
    if carry:
        lines.append("carry_forward:")
        for item in carry[:6]:
            lines.append(f"  - {item}")

    return "\n".join(lines)


def recent_archive_summaries(*, limit: int = 3) -> list[dict[str, Any]]:
    """Most recent archived pedagogy entries (newest first)."""
    if not ARCHIVE_DIR.is_dir():
        return []
    paths = sorted(ARCHIVE_DIR.glob("*.yaml"), reverse=True)[:limit]
    out: list[dict[str, Any]] = []
    for path in paths:
        data = _load_yaml(path)
        if data:
            out.append(data)
    return out
