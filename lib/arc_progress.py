"""Narrative arc day validation against published reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
CURRICULUM = ROOT / "curriculum"


def published_report_dates(*, before: str | None = None) -> list[str]:
    dates = [
        d.name
        for d in REPORTS.iterdir()
        if d.is_dir() and (d / "index.md").exists()
    ]
    dates = sorted(dates)
    if before:
        dates = [d for d in dates if d < before]
    return dates


def max_narrative_day_for_run(report_date: str) -> int:
    """Next allowed arc day: one step per published night before this date."""
    return len(published_report_dates(before=report_date)) + 1


def validate_curator_arc(curator: dict[str, Any], report_date: str) -> dict[str, Any]:
    """
    Clamp curator narrative_day and narrative_arc_patch.current_day to published progress.
    Mutates and returns curator.
    """
    max_day = max_narrative_day_for_run(report_date)
    proposed = int(curator.get("narrative_day") or max_day)
    if proposed > max_day:
        print(
            f"Arc validation: clamping narrative_day {proposed} → {max_day} "
            f"({len(published_report_dates(before=report_date))} published night(s) before {report_date})"
        )
        proposed = max_day
    curator["narrative_day"] = proposed

    patch = curator.get("narrative_arc_patch")
    if isinstance(patch, dict) and "current_day" in patch:
        patch_day = int(patch["current_day"])
        if patch_day > max_day:
            print(f"Arc validation: clamping narrative_arc_patch.current_day {patch_day} → {max_day}")
            patch_day = max_day
        patch["current_day"] = patch_day
        curator["narrative_arc_patch"] = patch
    elif patch is None and proposed:
        curator["narrative_arc_patch"] = {"current_day": proposed}

    return curator


def sync_arc_yaml_to_published(*, dry_run: bool = False) -> int:
    """
    If narrative-arc current_day exceeds published progress, clamp YAML to match.
    Returns clamped current_day.
    """
    path = CURRICULUM / "narrative-arc.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    arc = data.setdefault("active_arc", {})
    current = int(arc.get("current_day") or 1)
    # Published count without a specific report_date → use all reports
    max_day = len(published_report_dates()) or 1
    if current > max_day:
        print(f"Arc sync: narrative-arc.yaml current_day {current} → {max_day} (published nights)")
        arc["current_day"] = max_day
        if not dry_run:
            path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")
        return max_day
    return current
