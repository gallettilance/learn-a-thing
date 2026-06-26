"""Programmatic teaching-style checks for editor output."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from lib.lesson_content import is_lesson_markdown_stub, validate_lesson_markdown
from lib.lesson_consolidation import merged_word_limits, slot_metadata_from_groups

REQUIRED_HEADINGS = {
    "scene": re.compile(r"^##\s+Scene card\s*$", re.MULTILINE | re.IGNORECASE),
    "terms": re.compile(r"^##\s+Terms tonight\s*$", re.MULTILINE | re.IGNORECASE),
    "story": re.compile(r"^##\s+Story so far\s*$", re.MULTILINE | re.IGNORECASE),
}

MECHANISM_HEADINGS = re.compile(
    r"^##\s+(Building the mechanism|The formal tool arrives|Why the obvious approach breaks)\s*$",
    re.MULTILINE | re.IGNORECASE,
)

BANNED_OPENERS = (
    re.compile(r"you inherited this mess three nights ago", re.IGNORECASE),
    re.compile(r"last night you shipped", re.IGNORECASE),
    re.compile(r"^same characters,\s*same queue", re.IGNORECASE | re.MULTILINE),
)

PRE_TERMS_JARGON = (
    re.compile(r"P\s*\([^)]*\|"),
    re.compile(r"[βθ]|\\beta|\\theta"),
    re.compile(r"\bESS\b|\bMCMC\b|\bMAP\b|\bELBO\b"),
    re.compile(r"R[\s-]?hat|R̂", re.IGNORECASE),
    re.compile(r"\b\d+k?\s*[-–]?\s*D\b", re.IGNORECASE),
)

SUMMARY_JARGON = PRE_TERMS_JARGON + (
    re.compile(r"P\s*\(\s*β\s*\|\s*D\s*\)", re.IGNORECASE),
    re.compile(r"μ\s*\(\s*β\s*\)"),
)

CORE_WORD_MIN = 1200
CORE_WORD_MAX = 3200
CORE_EXTENDED_WORD_MAX = 4500
STRETCH_WORD_MIN = 800
STRETCH_WORD_MAX = 1800
NIGHT_SUMMARY_MAX_WORDS = 45


@dataclass
class LintResult:
    passed: bool
    violations: list[str] = field(default_factory=list)
    per_lesson: dict[int, list[str]] = field(default_factory=dict)

    def summary(self) -> str:
        lines = list(self.violations)
        for slot, items in sorted(self.per_lesson.items()):
            for item in items:
                lines.append(f"slot {slot}: {item}")
        return "\n".join(lines) if lines else "ok"


def lint_night_summary(text: str, *, label: str = "summary") -> list[str]:
    """Plain-English checks for night_thread, Thread line, carry forward."""
    issues: list[str] = []
    stripped = (text or "").strip()
    if not stripped:
        issues.append(f"{label} is empty")
        return issues

    words = len(stripped.split())
    if words > NIGHT_SUMMARY_MAX_WORDS:
        issues.append(f"{label} too long ({words} words; max {NIGHT_SUMMARY_MAX_WORDS})")

    if stripped.count(";") >= 2:
        issues.append(f"{label} is semicolon soup (split or simplify)")

    for pattern in SUMMARY_JARGON:
        if pattern.search(stripped):
            issues.append(f"{label} uses notation/jargon before reader has context")

    return issues


def lint_index_md(index_md: str) -> list[str]:
    """Lint nightly index markdown (Thread, carry forward)."""
    issues: list[str] = []
    md = index_md or ""

    thread_match = re.search(r"^\*\*Thread:\*\*\s*(.+)$", md, re.MULTILINE)
    if thread_match:
        issues.extend(lint_night_summary(thread_match.group(1).strip(), label="index Thread"))

    carry_match = re.search(
        r"^##\s+Carry forward\s*\n+(.+?)(?:\n##|\Z)",
        md,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if carry_match:
        issues.extend(lint_night_summary(carry_match.group(1).strip(), label="carry forward"))

    return issues


def _optional_slots(curator: dict[str, Any]) -> set[int]:
    optional: set[int] = set()
    for les in curator.get("lessons") or []:
        if isinstance(les, dict) and les.get("optional"):
            optional.add(int(les.get("slot", 0)))
    return optional


def _extended_slots(curator: dict[str, Any]) -> set[int]:
    extended: set[int] = set()
    for les in curator.get("lessons") or []:
        if isinstance(les, dict) and les.get("extended"):
            extended.add(int(les.get("slot", 0)))
    return extended


def _section_before_terms(md: str) -> str:
    parts = re.split(r"^##\s+Terms tonight\s*$", md, maxsplit=1, flags=re.MULTILINE | re.IGNORECASE)
    return parts[0] if parts else md


def lint_lesson_markdown(
    markdown: str,
    *,
    slot: int,
    narrative_day: int,
    optional: bool,
    extended: bool = False,
    gentle_intro: bool = False,
    word_min: int | None = None,
    word_max: int | None = None,
) -> list[str]:
    issues: list[str] = []
    md = markdown or ""

    try:
        validate_lesson_markdown(md, source=f"lesson slot {slot}")
    except ValueError as exc:
        issues.append(str(exc))

    if not REQUIRED_HEADINGS["scene"].search(md):
        issues.append("missing ## Scene card")
    if not REQUIRED_HEADINGS["terms"].search(md):
        issues.append("missing ## Terms tonight")
    if (narrative_day > 1 or slot > 1) and not REQUIRED_HEADINGS["story"].search(md):
        issues.append("missing ## Story so far (required when arc day > 1 or slot > 1)")

    terms_match = REQUIRED_HEADINGS["terms"].search(md)
    mechanism_match = MECHANISM_HEADINGS.search(md)
    if terms_match and mechanism_match and mechanism_match.start() < terms_match.start():
        issues.append("## Terms tonight must appear before mechanism sections")

    pre_terms = _section_before_terms(md)
    for pattern in PRE_TERMS_JARGON:
        if pattern.search(pre_terms):
            issues.append("notation or acronym before ## Terms tonight — motivate in English first")
            break

    intro = md[:1200]
    for pattern in BANNED_OPENERS:
        if pattern.search(intro):
            issues.append(f"banned assumed-prior-night phrase: {pattern.pattern}")

    words = len(md.split())
    if optional:
        if words < STRETCH_WORD_MIN:
            issues.append(f"word count {words} below stretch minimum {STRETCH_WORD_MIN}")
        stretch_max = word_max if word_max is not None else STRETCH_WORD_MAX
        if words > stretch_max:
            issues.append(f"word count {words} above stretch maximum {stretch_max}")
    else:
        core_min = word_min if word_min is not None else CORE_WORD_MIN
        core_max = word_max if word_max is not None else (CORE_EXTENDED_WORD_MAX if extended else CORE_WORD_MAX)
        if words < core_min:
            issues.append(f"word count {words} below core minimum {core_min}")
        if words > core_max:
            issues.append(f"word count {words} above core maximum {core_max}")

    if gentle_intro and not optional:
        mechanism_sections = len(MECHANISM_HEADINGS.findall(md))
        if mechanism_sections > 0 and terms_match:
            body_after_terms = md[terms_match.end() :]
            new_acronym_hits = sum(
                1 for p in PRE_TERMS_JARGON if p.search(body_after_terms)
            )
            if new_acronym_hits > 4:
                issues.append(
                    "gentle intro lesson introduces too many symbols/acronyms — split or mark extended"
                )

    if is_lesson_markdown_stub(md):
        issues.append("markdown is a stub placeholder")

    return issues


def _gentle_intro_slots(curator: dict[str, Any]) -> set[int]:
    gentle: set[int] = set()
    for les in curator.get("lessons") or []:
        if isinstance(les, dict) and les.get("intro_pacing") == "gentle":
            gentle.add(int(les.get("slot", 0)))
    return gentle


def lint_curator_plan(curator: dict[str, Any]) -> list[str]:
    """Plan-level checks: complexity budget and plain-English summaries."""
    issues: list[str] = []
    issues.extend(lint_night_summary(str(curator.get("night_thread") or ""), label="night_thread"))

    core_concepts = 0
    for les in curator.get("lessons") or []:
        if not isinstance(les, dict):
            continue
        slot = int(les.get("slot", 0))
        concept = str(les.get("concept") or "")
        optional = bool(les.get("optional"))
        gentle = les.get("intro_pacing") == "gentle"
        pressure = str(les.get("pressure_question") or "")

        if gentle and not optional:
            for pattern in SUMMARY_JARGON:
                if pattern.search(pressure):
                    issues.append(
                        f"slot {slot}: pressure_question uses notation before lesson setup"
                    )
                    break
            if re.search(r"\band\b.*\band\b", concept, re.IGNORECASE) or ";" in concept:
                issues.append(
                    f"slot {slot}: concept packs multiple moves — split across nights or mark extended"
                )
            core_concepts += 1

        if not optional and not concept.strip():
            issues.append(f"slot {slot}: missing concept (one move per core lesson required)")

    if core_concepts > 4:
        issues.append("too many gentle-intro core slots in one night — defer beats to topic_queue")

    return issues


def lint_editor_output(editor: dict[str, Any], curator: dict[str, Any]) -> LintResult:
    """Return violations for editor JSON + lesson bodies."""
    violations: list[str] = []
    per_lesson: dict[int, list[str]] = {}

    review = editor.get("review_summary") or {}
    if not review.get("all_pass"):
        violations.append("review_summary.all_pass is not true")

    narrative_day = int(curator.get("narrative_day") or 1)
    slot_meta = slot_metadata_from_groups(curator)
    lessons = editor.get("lessons") or []
    pub_count = len(lessons)

    if pub_count < 2 or pub_count > 5:
        violations.append(f"expected 2–5 published lessons, got {pub_count}")

    violations.extend(lint_index_md(str(editor.get("index_md") or "")))

    for les in lessons:
        if not isinstance(les, dict):
            violations.append("lesson entry is not an object")
            continue
        slot = int(les.get("slot", 0))
        flags = slot_meta.get(slot, {})
        optional = bool(flags.get("optional"))
        extended = bool(flags.get("extended"))
        gentle = bool(flags.get("gentle_intro"))
        group_stub = {
            "optional": optional,
            "extended": extended,
            "source_slots": flags.get("source_slots") or [slot],
        }
        wmin, wmax = merged_word_limits(group_stub)
        if not les.get("style_pass"):
            per_lesson.setdefault(slot, []).append("style_pass is false")
        for v in les.get("style_violations") or []:
            per_lesson.setdefault(slot, []).append(f"editor flagged: {v}")
        slot_issues = lint_lesson_markdown(
            str(les.get("markdown") or ""),
            slot=slot,
            narrative_day=narrative_day,
            optional=optional,
            extended=extended,
            gentle_intro=gentle,
            word_min=wmin,
            word_max=wmax,
        )
        if slot_issues:
            per_lesson.setdefault(slot, []).extend(slot_issues)
        if flags.get("merged") and not les.get("merged_from_slots"):
            per_lesson.setdefault(slot, []).append("merged lesson missing merged_from_slots metadata")

    passed = not violations and not any(per_lesson.values())
    return LintResult(passed=passed, violations=violations, per_lesson=per_lesson)
