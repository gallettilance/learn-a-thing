"""Anchor primer — standalone story context for lessons and site."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CURRICULUM = ROOT / "curriculum"
REPORTS = ROOT / "reports"
PRIMER_PATH = CURRICULUM / "anchor-primer.yaml"


def _load_yaml(path: Path) -> Any:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_anchor_primers() -> dict[str, Any]:
    data = _load_yaml(PRIMER_PATH)
    return data.get("anchors") or {}


def get_anchor_primer(arc_id: str) -> dict[str, Any]:
    return load_anchor_primers().get(arc_id) or {}


def list_arc_report_dates(arc_id: str, *, before: str | None = None) -> list[str]:
    dates = []
    for d in sorted(REPORTS.iterdir()):
        if not d.is_dir() or not (d / "index.md").exists():
            continue
        meta = _load_yaml(d / "meta.yaml")
        if meta.get("arc_id") == arc_id:
            if before is None or d.name < before:
                dates.append(d.name)
    return dates


def prior_night_links(arc_id: str, report_date: str) -> list[dict[str, str]]:
    links = []
    for d in list_arc_report_dates(arc_id, before=report_date):
        meta = _load_yaml(REPORTS / d / "meta.yaml")
        day = meta.get("narrative_day")
        label = f"Night {d}" + (f" (arc day {day})" if day else "")
        links.append({"date": d, "label": label, "url": f"/reports/{d}/index.html"})
    return links


def all_arc_report_links(arc_id: str) -> list[dict[str, str]]:
    links = []
    for d in list_arc_report_dates(arc_id, before=None):
        meta = _load_yaml(REPORTS / d / "meta.yaml")
        day = meta.get("narrative_day")
        label = f"Night {d}" + (f" (arc day {day})" if day else "")
        links.append({"date": d, "label": label, "url": f"/reports/{d}/index.html"})
    return links


def format_anchor_for_agents(arc_id: str, *, report_date: str | None = None) -> str:
    primer = get_anchor_primer(arc_id)
    if not primer:
        return f"(no anchor primer for {arc_id})"

    fd = primer.get("fixed_anchor_data") or {}
    lines = [
        f"Anchor: {primer.get('id')} — {primer.get('one_line', '')}",
        "",
        f"Setting: {str(primer.get('setting', '')).strip()}",
        "",
        "Characters:",
    ]
    for ch in primer.get("characters") or []:
        if isinstance(ch, dict):
            lines.append(f"  - {ch.get('name')}: {ch.get('role')}")

    lines.extend(
        [
            "",
            "Fixed numbers (use these exact anchors unless curator changes them):",
            f"  - {fd.get('queue_name')}: {fd.get('labeled_batch_size')} labeled emails",
            f"  - Labels: {fd.get('spam_labels')} spam, {fd.get('ham_labels')} ham (rate {fd.get('label_rate')})",
            f"  - Auto-quarantine threshold: {fd.get('auto_quarantine_threshold')}",
            f"  - Classifier: {fd.get('classifier')}",
            f"  - Features: {str(fd.get('feature_spec', '')).strip()}",
            "",
            "Story beats (write Story so far from these — do NOT assume reader saw prior nights):",
        ]
    )
    for beat in primer.get("story_beats") or []:
        if isinstance(beat, dict):
            lines.append(f"  Day {beat.get('day')}: {str(beat.get('summary', '')).strip()}")

    lines.append("")
    lines.append("Glossary (use plain language in lessons; link Terms tonight to these):")
    for t in primer.get("terms") or []:
        if isinstance(t, dict):
            lines.append(f"  - {t.get('term')}: {str(t.get('plain', '')).strip()}")

    lines.append("")
    lines.append("Precision rules:")
    for rule in primer.get("precision_rules") or []:
        lines.append(f"  - {rule}")

    if report_date:
        prior = prior_night_links(arc_id, report_date)
        if prior:
            lines.append("")
            lines.append("Prior published nights (link in Story so far when relevant):")
            for p in prior:
                lines.append(f"  - {p['label']}: {p['url']}")

    return "\n".join(lines)


def html_reference_panel(
    arc_id: str,
    *,
    report_date: str,
    narrative_day: int | None = None,
) -> str:
    """Sidebar-style reference block for lesson HTML pages."""
    primer = get_anchor_primer(arc_id)
    if not primer:
        return ""

    fd = primer.get("fixed_anchor_data") or {}
    anchor_url = f"/anchor/{arc_id}.html"

    prior_links = prior_night_links(arc_id, report_date)
    prior_html = ""
    if prior_links:
        items = "".join(f'<li><a href="{p["url"]}">{p["label"]}</a></li>' for p in prior_links)
        prior_html = f"<p><strong>Prior nights</strong></p><ul class='anchor-ref-list'>{items}</ul>"

    beat = None
    if narrative_day:
        for b in primer.get("story_beats") or []:
            if isinstance(b, dict) and b.get("day") == narrative_day:
                beat = b
                break
    beat_html = ""
    if beat:
        beat_html = f"<p class='anchor-ref-beat'><strong>Arc day {narrative_day}:</strong> {beat.get('summary', '')}</p>"

    refs = primer.get("reference_pages") or []
    ref_items = "".join(
        f'<li><a href="{r.get("path", "#")}">{r.get("label", "")}</a></li>' for r in refs if isinstance(r, dict)
    )

    return f"""
    <aside class="anchor-ref-panel" aria-label="Story context and references">
      <p class="anchor-ref-eyebrow">Standalone context</p>
      <p><strong>{primer.get('title', arc_id)}</strong> — {fd.get('labeled_batch_size')} emails ({fd.get('spam_labels')} spam / {fd.get('ham_labels')} ham). <a href="{anchor_url}">Full primer →</a></p>
      {beat_html}
      {prior_html}
      <p><strong>Quick links</strong></p>
      <ul class="anchor-ref-list">{ref_items}</ul>
    </aside>"""
