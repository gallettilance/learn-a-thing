"""Merge same-topic planning slots into 2–5 published narrative lessons per night."""

from __future__ import annotations

from typing import Any

MIN_PUBLISHED_LESSONS = 2
MAX_PUBLISHED_LESSONS = 5
MAX_PLANNING_SLOTS = 5


def _sorted_plan_slots(curator: dict[str, Any]) -> list[dict[str, Any]]:
    lessons = list(curator.get("lessons") or [])
    return sorted(lessons, key=lambda x: int(x.get("slot") or 0))


def _planning_slot_by_number(curator: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(les["slot"]): les for les in _sorted_plan_slots(curator) if les.get("slot")}


def _stretch_planning_slots(curator: dict[str, Any]) -> set[int]:
    """Planning slots that must survive consolidation as a standalone stretch lesson."""
    slots = _sorted_plan_slots(curator)
    if not slots:
        return set()

    arc_key = _group_key(str(curator.get("topic_label") or ""))
    night_type = str(curator.get("night_type") or "arc")
    stretch: set[int] = set()

    for les in slots:
        slot = int(les.get("slot") or 0)
        if not slot:
            continue
        optional = bool(les.get("optional"))
        role = str(les.get("slot_role") or "")
        topic_key = _group_key(str(les.get("topic_label") or ""))

        if optional:
            stretch.add(slot)
        elif role == "bridge":
            stretch.add(slot)
        elif night_type != "exploration" and topic_key and arc_key and topic_key != arc_key:
            stretch.add(slot)

    if not stretch and len(slots) >= MAX_PLANNING_SLOTS:
        if night_type in ("arc", "bridge", "transfer"):
            stretch.add(MAX_PLANNING_SLOTS)
        else:
            for les in slots:
                if int(les.get("slot") or 0) == MAX_PLANNING_SLOTS:
                    stretch.add(MAX_PLANNING_SLOTS)
                    break

    return stretch


def _slice_group(g: dict[str, Any], slots: list[int], part: str = "") -> dict[str, Any]:
    idx = [g["source_slots"].index(s) for s in slots if s in g["source_slots"]]

    def pick(field: str) -> list[Any]:
        values = g.get(field) or []
        return [values[i] for i in idx if i < len(values)]

    return {
        "topic_label": g["topic_label"],
        "source_slots": slots,
        "concepts": pick("concepts"),
        "pressure_questions": pick("pressure_questions"),
        "narrative_beats": pick("narrative_beats"),
        "optional": g.get("optional", False),
        "extended": g.get("extended", False) or len(slots) >= 2,
        "intro_pacing": g.get("intro_pacing", "normal"),
        "slot_roles": g.get("slot_roles", []),
        "narrative_part": part or g.get("narrative_part"),
    }


def _ensure_stretch_standalone(
    curator: dict[str, Any], groups: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Peel stretch/bridge slots out of merged core groups; mark stretch groups optional."""
    stretch = _stretch_planning_slots(curator)
    if not stretch:
        return groups

    planning = _planning_slot_by_number(curator)
    out: list[dict[str, Any]] = []

    for g in groups:
        src = list(g.get("source_slots") or [])
        stretch_src = [s for s in src if s in stretch]
        core_src = [s for s in src if s not in stretch]

        if stretch_src and core_src:
            core_g = _slice_group(g, core_src)
            core_g["optional"] = False
            stretch_g = _slice_group(g, stretch_src)
            stretch_g["optional"] = True
            if len(stretch_src) == 1:
                slot = stretch_src[0]
                stretch_g["topic_label"] = str(
                    planning.get(slot, {}).get("topic_label") or stretch_g.get("topic_label") or ""
                )
            out.extend([core_g, stretch_g])
        elif stretch_src:
            g = dict(g)
            g["optional"] = True
            if len(stretch_src) == 1:
                slot = stretch_src[0]
                g["topic_label"] = str(
                    planning.get(slot, {}).get("topic_label") or g.get("topic_label") or ""
                )
            out.append(g)
        else:
            g = dict(g)
            g["optional"] = bool(g.get("optional"))
            out.append(g)

    covered = {s for g in out for s in g.get("source_slots") or []}
    missing = sorted(stretch - covered)
    if missing:
        for slot in missing:
            les = planning.get(slot) or {}
            out.append(
                {
                    "topic_label": str(les.get("topic_label") or curator.get("topic_label") or ""),
                    "source_slots": [slot],
                    "concepts": [str(les.get("concept") or "").strip()],
                    "pressure_questions": [str(les.get("pressure_question") or "").strip()],
                    "narrative_beats": [str(les.get("narrative_beat") or "").strip()],
                    "optional": True,
                    "extended": False,
                    "intro_pacing": str(les.get("intro_pacing") or "normal"),
                    "slot_roles": [str(les.get("slot_role") or "")] if les.get("slot_role") else [],
                }
            )

    out.sort(key=lambda g: min(g["source_slots"]))
    return out


def validate_stretch_preservation(
    curator: dict[str, Any], groups: list[dict[str, Any]]
) -> tuple[bool, str]:
    """Require at least one standalone stretch lesson when the plan includes stretch slots."""
    stretch = _stretch_planning_slots(curator)
    if not stretch:
        return True, ""

    optional_groups = [g for g in groups if g.get("optional")]
    if not optional_groups:
        return False, "missing stretch lesson — at least one lesson_group must have optional: true"

    for g in optional_groups:
        src = set(g.get("source_slots") or [])
        if not src:
            continue
        if src <= stretch:
            return True, "stretch lesson preserved as standalone optional group"
        non_stretch = src - stretch
        if non_stretch:
            return False, (
                f"stretch lesson must stand alone — publish group {g.get('publish_slot')} "
                f"merges stretch slots {sorted(src & stretch)} with core slots {sorted(non_stretch)}"
            )

    return False, f"stretch planning slots {sorted(stretch)} not covered by any optional lesson_group"


def _group_key(topic_label: str) -> str:
    return str(topic_label or "").strip().lower()


def build_lesson_groups(curator: dict[str, Any]) -> list[dict[str, Any]]:
    """Group planning slots by topic_label into publishable lesson groups.

    Same topic on multiple slots → one group with a multi-move narrative spine.
    Ensures at least MIN and at most MAX published lessons.
    """
    slots = _sorted_plan_slots(curator)
    if not slots:
        return []

    # Preserve slot order; merge consecutive runs of the same topic
    groups: list[dict[str, Any]] = []
    for les in slots:
        topic = str(les.get("topic_label") or curator.get("topic_label") or "").strip()
        role = str(les.get("slot_role") or "").strip()
        key = _group_key(topic)
        if groups and _group_key(str(groups[-1].get("topic_label") or "")) == key:
            if bool(les.get("optional")) != bool(groups[-1].get("optional")):
                groups.append(
                    {
                        "topic_label": topic,
                        "source_slots": [int(les["slot"])],
                        "concepts": [str(les.get("concept") or "").strip()],
                        "pressure_questions": [str(les.get("pressure_question") or "").strip()],
                        "narrative_beats": [str(les.get("narrative_beat") or "").strip()],
                        "optional": bool(les.get("optional")),
                        "extended": bool(les.get("extended")),
                        "intro_pacing": str(les.get("intro_pacing") or "normal"),
                        "slot_roles": [role] if role else [],
                    }
                )
                continue
            g = groups[-1]
            g["source_slots"].append(int(les["slot"]))
            g["concepts"].append(str(les.get("concept") or "").strip())
            g["pressure_questions"].append(str(les.get("pressure_question") or "").strip())
            g["narrative_beats"].append(str(les.get("narrative_beat") or "").strip())
            if les.get("optional"):
                g["optional"] = True
            if les.get("extended"):
                g["extended"] = True
            if str(les.get("intro_pacing") or "") == "gentle":
                g["intro_pacing"] = "gentle"
        else:
            groups.append(
                {
                    "topic_label": topic,
                    "source_slots": [int(les["slot"])],
                    "concepts": [str(les.get("concept") or "").strip()],
                    "pressure_questions": [str(les.get("pressure_question") or "").strip()],
                    "narrative_beats": [str(les.get("narrative_beat") or "").strip()],
                    "optional": bool(les.get("optional")),
                    "extended": bool(les.get("extended")),
                    "intro_pacing": str(les.get("intro_pacing") or "normal"),
                    "slot_roles": [role] if role else [],
                }
            )

    # Re-merge non-consecutive same topic (e.g. slots 1,2,4 same topic with bridge in 3)
    merged: list[dict[str, Any]] = []
    for g in groups:
        key = _group_key(g["topic_label"])
        hit = next((m for m in merged if _group_key(m["topic_label"]) == key), None)
        if hit is None:
            merged.append({**g})
        elif bool(hit.get("optional")) != bool(g.get("optional")):
            merged.append({**g})
        else:
            hit["source_slots"].extend(g["source_slots"])
            hit["concepts"].extend(g["concepts"])
            hit["pressure_questions"].extend(g["pressure_questions"])
            hit["narrative_beats"].extend(g["narrative_beats"])
            hit["slot_roles"].extend(r for r in g["slot_roles"] if r not in hit["slot_roles"])
            hit["optional"] = bool(hit.get("optional") or g.get("optional"))
            hit["extended"] = hit.get("extended") or g.get("extended")
            if g.get("intro_pacing") == "gentle":
                hit["intro_pacing"] = "gentle"

    groups = merged
    groups = _ensure_stretch_standalone(curator, groups)

    # Too few published lessons — split the largest group into two narrative parts
    while len(groups) < MIN_PUBLISHED_LESSONS and groups:
        largest = max(groups, key=lambda g: len(g["source_slots"]))
        if len(largest["source_slots"]) < 2:
            break
        mid = len(largest["source_slots"]) // 2
        left_slots = largest["source_slots"][:mid]
        right_slots = largest["source_slots"][mid:]

        groups.remove(largest)
        groups.append(_slice_group(largest, left_slots, "part_1"))
        groups.append(_slice_group(largest, right_slots, "part_2"))
        groups.sort(key=lambda g: min(g["source_slots"]))
        groups = _ensure_stretch_standalone(curator, groups)

    # Too many — cannot merge further without dropping beats; curator must defer
    if len(groups) > MAX_PUBLISHED_LESSONS:
        return groups  # validation will fail

    for i, g in enumerate(groups, start=1):
        g["publish_slot"] = i
        g["merged"] = len(g["source_slots"]) > 1
        g["narrative_spine"] = _default_narrative_spine(g)

    return groups


def _default_narrative_spine(group: dict[str, Any]) -> str:
    topic = group.get("topic_label") or "Tonight's topic"
    concepts = [c for c in group.get("concepts") or [] if c]
    part = group.get("narrative_part")
    if len(concepts) <= 1:
        base = f"One end-to-end lesson on {topic}: {concepts[0] if concepts else 'core beat'}."
    else:
        chain = " → ".join(concepts)
        base = (
            f"Single narrative on {topic} weaving {len(concepts)} moves in order: {chain}. "
            f"Drop repeated Scene-card cold opens and any digression that does not serve this arc."
        )
    if part:
        base += f" ({part.replace('_', ' ')})"
    return base


def validate_lesson_groups(
    groups: list[dict[str, Any]],
    curator: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    n = len(groups)
    if n < MIN_PUBLISHED_LESSONS:
        return False, f"expected at least {MIN_PUBLISHED_LESSONS} published lessons, got {n}"
    if n > MAX_PUBLISHED_LESSONS:
        return False, f"expected at most {MAX_PUBLISHED_LESSONS} published lessons, got {n}"
    for g in groups:
        if not g.get("source_slots"):
            return False, "lesson group missing source_slots"
        if not str(g.get("topic_label") or "").strip():
            return False, "lesson group missing topic_label"
    if curator is not None:
        stretch_ok, stretch_msg = validate_stretch_preservation(curator, groups)
        if not stretch_ok:
            return False, stretch_msg
    return True, f"{n} published lesson(s) from planning slots"


def enforce_lesson_consolidation(curator: dict[str, Any]) -> tuple[dict[str, Any], bool, str]:
    """Attach lesson_groups to curator plan; build from lessons if missing."""
    existing = curator.get("lesson_groups")
    if isinstance(existing, list) and existing:
        groups = existing
    else:
        groups = build_lesson_groups(curator)

    ok, msg = validate_lesson_groups(groups, curator)
    curator = {**curator, "lesson_groups": groups, "published_lesson_count": len(groups)}
    return curator, not ok, msg if ok else f"lesson consolidation invalid: {msg}"


def planning_slot_count(curator: dict[str, Any]) -> int:
    return len(curator.get("lessons") or [])


def published_lesson_count(curator: dict[str, Any]) -> int:
    groups = curator.get("lesson_groups") or []
    return len(groups) if groups else 0


def group_for_publish_slot(curator: dict[str, Any], publish_slot: int) -> dict[str, Any] | None:
    for g in curator.get("lesson_groups") or []:
        if int(g.get("publish_slot") or 0) == publish_slot:
            return g
    return None


def merged_word_limits(group: dict[str, Any]) -> tuple[int, int]:
    """Return (min_words, max_words) for a published lesson."""
    n = max(1, len(group.get("source_slots") or [1]))
    if group.get("optional"):
        return 1200, 1800
    if group.get("extended") or n >= 2:
        lo = 2000 + 700 * (n - 1)
        hi = min(5500, lo + 1500)
        return lo, hi
    return 1500, 2500


def format_consolidation_for_teacher(curator: dict[str, Any]) -> str:
    groups = curator.get("lesson_groups") or build_lesson_groups(curator)
    n = len(groups)
    lines = [
        f"\n\nLESSON CONSOLIDATION (required — write {n} published lessons, not {MAX_PLANNING_SLOTS}):",
        "When multiple planning slots share the same topic_label, merge them into ONE pedagogical article.",
        "Do NOT concatenate slot drafts — build one narrative arc; omit material that does not serve the story.",
        "",
    ]
    for g in groups:
        ps = g.get("publish_slot")
        src = g.get("source_slots") or []
        concepts = [c for c in g.get("concepts") or [] if c]
        lo, hi = merged_word_limits(g)
        lines.append(f"Published lesson {ps} (topic: {g.get('topic_label')}):")
        lines.append(f"  - Merges planning slots: {src}")
        lines.append(f"  - Concept moves (in order): {', '.join(concepts) or '(see pressure questions)'}")
        lines.append(f"  - Narrative spine: {g.get('narrative_spine') or _default_narrative_spine(g)}")
        lines.append(f"  - Target length: {lo}–{hi} words; optional={g.get('optional')}; extended={g.get('extended') or len(src) >= 2}")
        if g.get("optional"):
            lines.append(
                "  - STRETCH lesson: standalone article on the bridge/diversity topic "
                "(do not merge into arc core); label [stretch] in index_md"
            )
        lines.append("  - One Scene card + one Terms tonight block for the merged lesson")
        lines.append("")
    lines.append(
        f'Output exactly {n} entries in lessons[] with slot = publish_slot (1..{n}). '
        f'Include "merged_from_slots" and "concepts_covered" on each lesson.'
    )
    return "\n".join(lines)


def slot_metadata_from_groups(curator: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Map publish_slot → flags for lint (optional, extended, gentle)."""
    out: dict[int, dict[str, Any]] = {}
    for g in curator.get("lesson_groups") or []:
        ps = int(g.get("publish_slot") or 0)
        if not ps:
            continue
        out[ps] = {
            "optional": bool(g.get("optional")),
            "extended": bool(g.get("extended")) or len(g.get("source_slots") or []) >= 2,
            "gentle_intro": str(g.get("intro_pacing") or "") == "gentle",
            "merged": bool(g.get("merged")),
            "source_slots": list(g.get("source_slots") or []),
        }
    return out


def enrich_lessons_from_groups(
    payload: dict[str, Any],
    curator: dict[str, Any],
) -> dict[str, Any]:
    """Fill merged_from_slots / concepts_covered from curator lesson_groups when agents omit them."""
    groups_by_slot = {
        int(g.get("publish_slot") or 0): g
        for g in curator.get("lesson_groups") or []
        if int(g.get("publish_slot") or 0)
    }
    lessons = payload.get("lessons")
    if not isinstance(lessons, list):
        return payload

    payload = dict(payload)
    enriched: list[Any] = []
    for les in lessons:
        if not isinstance(les, dict):
            enriched.append(les)
            continue
        les = dict(les)
        slot = int(les.get("slot") or 0)
        group = groups_by_slot.get(slot)
        if group:
            if not les.get("merged_from_slots"):
                les["merged_from_slots"] = list(group.get("source_slots") or [])
            if not les.get("concepts_covered"):
                les["concepts_covered"] = [
                    c for c in group.get("concepts") or [] if str(c).strip()
                ]
            if group.get("optional") is True:
                les["optional"] = True
            if group.get("topic_label") and not les.get("topic_label"):
                les["topic_label"] = group["topic_label"]
        enriched.append(les)
    payload["lessons"] = enriched
    return payload

