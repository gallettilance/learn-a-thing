"""Load role-specific playbook sections for agent context packs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
PLAYBOOK_PATH = ROOT / "learner" / "playbook.yaml"

ROLE_SECTIONS: dict[str, tuple[str, ...]] = {
    "curator": ("planning", "consolidation"),
    "consolidator": ("consolidation", "teaching"),
    "teacher": ("teaching", "consolidation"),
    "editor": ("teaching", "quality"),
    "research": ("planning",),
    "hypothesis": ("planning", "teaching"),
    "grapher": ("planning", "quality", "teaching"),
}


def load_playbook() -> dict[str, Any]:
    if not PLAYBOOK_PATH.is_file():
        return {}
    return yaml.safe_load(PLAYBOOK_PATH.read_text(encoding="utf-8")) or {}


def playbook_sections_for_role(role: str) -> dict[str, Any]:
    """Return only the playbook sections an agent role needs."""
    data = load_playbook()
    keys = ROLE_SECTIONS.get(role, ())
    out: dict[str, Any] = {"version": data.get("version", 1)}
    for key in keys:
        if key in data:
            out[key] = data[key]
    proposed = data.get("proposed_rules") or []
    if proposed and role in ("curator", "editor", "grapher"):
        out["proposed_rules"] = proposed[-5:]
    return out


def format_playbook_for_role(role: str) -> str:
    sections = playbook_sections_for_role(role)
    if not sections:
        return "(playbook unavailable)"
    return yaml.dump(sections, default_flow_style=False, sort_keys=False, allow_unicode=True)


def append_proposed_rule(rule: str, *, min_chars: int = 20) -> bool:
    """Append a durable rule candidate to playbook staging (deduped)."""
    text = str(rule or "").strip()
    if len(text) < min_chars:
        return False
    data = load_playbook()
    rules = list(data.get("proposed_rules") or [])
    if any(text.lower() == str(r).lower() for r in rules):
        return False
    rules.append(text)
    data["proposed_rules"] = rules[-20:]
    PLAYBOOK_PATH.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return True
