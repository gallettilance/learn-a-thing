"""Nightly memory consolidation — archive pedagogy, update carry_forward, stage playbook rules."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from lib.pedagogy_state import (
    load_pedagogy_carry_forward,
    persist_pedagogy_latest,
    recent_archive_summaries,
)
from lib.playbook import append_proposed_rule
from lib.run_brief import save_run_brief, update_run_brief_carry_forward

ROOT = Path(__file__).resolve().parent.parent


def _normalize_issue(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _extract_carry_forward_bullets(summaries: list[dict[str, Any]], *, limit: int = 8) -> list[str]:
    """Distill recent night summaries into short carry-forward bullets."""
    bullets: list[str] = []
    seen: set[str] = set()

    for entry in summaries:
        summary = str(entry.get("summary") or "").strip()
        if not summary or summary.lower().startswith("dry-run"):
            continue
        # First sentence or first ~120 chars
        sentence = summary.split(". ")[0].strip()
        if len(sentence) > 140:
            sentence = sentence[:137] + "..."
        key = _normalize_issue(sentence)
        if key and key not in seen:
            seen.add(key)
            bullets.append(sentence)

        guidance = entry.get("curator_guidance") or {}
        focus = str(guidance.get("next_night_focus") or "").strip()
        if focus:
            fk = _normalize_issue(focus)
            if fk not in seen:
                seen.add(fk)
                bullets.append(f"Next: {focus[:120]}")

        if len(bullets) >= limit:
            break

    return bullets[:limit]


def _collect_repeated_lesson_issues(archives: list[dict[str, Any]], *, min_count: int = 3) -> list[str]:
    """Find lesson_feedback issues that repeat across archived nights."""
    counter: Counter[str] = Counter()
    for entry in archives:
        for lf in entry.get("lesson_feedback") or []:
            if not isinstance(lf, dict):
                continue
            for issue in lf.get("issues") or []:
                text = str(issue).strip()
                if len(text) >= 25:
                    counter[_normalize_issue(text)] += 1

    repeated: list[str] = []
    for norm, count in counter.most_common():
        if count >= min_count:
            # recover original casing from first match — use norm as fallback
            repeated.append(norm)
    return repeated[:5]


def consolidate_memory(
    grapher: dict[str, Any],
    report_date: str,
    *,
    run_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Phase 4 memory consolidator — run after grapher, before next night's brief.

    Returns summary dict for logging.
    """
    archives = recent_archive_summaries(limit=5)
    carry = _extract_carry_forward_bullets(archives)
    summary = str(grapher.get("summary") or "").strip()
    if summary and not summary.lower().startswith("dry-run"):
        lead = summary.split(". ")[0].strip()
        if lead and lead not in carry:
            carry = [lead[:140]] + carry
    if not carry:
        carry = load_pedagogy_carry_forward()

    persist_pedagogy_latest(grapher, report_date, carry_forward=carry)
    update_run_brief_carry_forward(carry)

    proposed: list[str] = []
    for issue in _collect_repeated_lesson_issues(archives):
        rule = f"Repeated lesson issue — address in planning/teaching: {issue[:200]}"
        if append_proposed_rule(rule):
            proposed.append(rule)

    result = {
        "report_date": report_date,
        "carry_forward_count": len(carry),
        "proposed_rules_added": len(proposed),
        "archives_considered": len(archives),
    }

    if run_brief is not None:
        run_brief["carry_forward"] = carry[:8]
        save_run_brief(run_brief)

    return result
