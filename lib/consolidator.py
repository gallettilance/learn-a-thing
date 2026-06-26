"""Consolidator agent integration — plan, draft review, ship review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from lib.lesson_consolidation import (
    MAX_PUBLISHED_LESSONS,
    MIN_PUBLISHED_LESSONS,
    _ensure_stretch_standalone,
    _stretch_planning_slots,
    build_lesson_groups,
    enforce_lesson_consolidation,
    format_consolidation_for_teacher,
    validate_lesson_groups,
    validate_stretch_preservation,
)

RunAgent = Callable[..., dict[str, Any]]

ROOT = Path(__file__).resolve().parent.parent


def _normalize_group(
    g: dict[str, Any], publish_slot: int, curator: dict[str, Any] | None = None
) -> dict[str, Any]:
    out = dict(g)
    out["publish_slot"] = int(g.get("publish_slot") or publish_slot)
    out["source_slots"] = [int(s) for s in out.get("source_slots") or []]
    out["concepts"] = [str(c).strip() for c in out.get("concepts") or [] if str(c).strip()]
    out["merged"] = len(out["source_slots"]) > 1
    if out["merged"] and not out.get("extended"):
        out["extended"] = True

    stretch = _stretch_planning_slots(curator) if curator else set()
    src = set(out["source_slots"])
    if stretch and src & stretch and not src - stretch:
        out["optional"] = True
    elif curator is not None and "optional" not in g:
        from lib.lesson_consolidation import _planning_slot_by_number

        planning = _planning_slot_by_number(curator)
        out["optional"] = any(planning.get(s, {}).get("optional") for s in out["source_slots"])

    return out


def apply_consolidator_output(curator: dict[str, Any], consolidator: dict[str, Any]) -> dict[str, Any]:
    """Merge consolidator lesson_groups onto curator plan."""
    groups_in = consolidator.get("lesson_groups")
    if isinstance(groups_in, list) and groups_in:
        groups = [_normalize_group(g, i + 1, curator) for i, g in enumerate(groups_in)]
        groups = _ensure_stretch_standalone(curator, groups)
        ok, msg = validate_lesson_groups(groups, curator)
        if not ok:
            curator, _, fallback_msg = enforce_lesson_consolidation(curator)
            curator["consolidation_fallback"] = (
                f"consolidator groups invalid ({msg}); {fallback_msg}"
            )
        else:
            for i, g in enumerate(groups, start=1):
                g["publish_slot"] = i
            curator = {**curator, "lesson_groups": groups, "published_lesson_count": len(groups)}
    else:
        curator, _, _ = enforce_lesson_consolidation(curator)

    curator["consolidation"] = {
        "phase": consolidator.get("phase"),
        "review_summary": consolidator.get("review_summary") or {},
        "omit_from_narrative": consolidator.get("omit_from_narrative") or [],
        "defer_to_topic_queue": consolidator.get("defer_to_topic_queue") or [],
        "group_assessments": consolidator.get("group_assessments") or [],
    }
    return curator


def review_passes(consolidator: dict[str, Any]) -> bool:
    review = consolidator.get("review_summary") or {}
    if review.get("pass") is not True:
        return False
    targets = review.get("escalate_to") or []
    return not targets


def escalation_targets(consolidator: dict[str, Any]) -> set[str]:
    review = consolidator.get("review_summary") or {}
    return {str(t) for t in review.get("escalate_to") or [] if t in ("curator", "teacher", "editor")}


def build_plan_message(curator: dict[str, Any], *, report_date: str) -> str:
    seed = build_lesson_groups(curator)
    return (
        f"Pipeline run date: {report_date}\n"
        f"Phase: plan\n\n"
        f"Curator plan (planning slots):\n{json.dumps(curator, indent=2)}\n\n"
        f"Programmatic merge suggestion (override if pedagogy requires):\n"
        f"{json.dumps(seed, indent=2)}\n\n"
        f"Produce lesson_groups ({MIN_PUBLISHED_LESSONS}–{MAX_PUBLISHED_LESSONS} published lessons). "
        f"Escalate to curator if slot boundaries or concept packing must change.\n\n"
        f"STRETCH RULE (hard): keep the bridge/diversity slot as its own standalone published lesson "
        f"with optional: true — never merge stretch slots into the arc core group. "
        f"Stretch slots in tonight's plan: {sorted(_stretch_planning_slots(curator)) or '(none flagged)'}"
    )


def build_draft_review_message(
    *,
    report_date: str,
    curator: dict[str, Any],
    teacher: dict[str, Any],
) -> str:
    return (
        f"Pipeline run date: {report_date}\n"
        f"Phase: draft_review\n\n"
        f"Approved lesson_groups:\n{json.dumps(curator.get('lesson_groups') or [], indent=2)}\n\n"
        f"Consolidation rationale:\n"
        f"{json.dumps(curator.get('consolidation') or {}, indent=2)}\n\n"
        f"Teacher draft:\n{json.dumps(teacher, indent=2)[:80000]}\n\n"
        f"Assess whether each published lesson is ONE cohesive narrative (not stitched slot articles). "
        f"Escalate to teacher with specific merge/omit/rewrite instructions if not."
    )


def build_ship_review_message(
    *,
    report_date: str,
    curator: dict[str, Any],
    teacher: dict[str, Any],
    editor: dict[str, Any],
) -> str:
    return (
        f"Pipeline run date: {report_date}\n"
        f"Phase: ship_review\n\n"
        f"lesson_groups:\n{json.dumps(curator.get('lesson_groups') or [], indent=2)}\n\n"
        f"Teacher draft (reference):\n{json.dumps(teacher, indent=2)[:40000]}\n\n"
        f"Editor final:\n{json.dumps(editor, indent=2)[:80000]}\n\n"
        f"Final gate: narrative cohesion across merged lessons. Escalate to editor or teacher as needed."
    )


def consolidator_feedback_suffix(consolidator: dict[str, Any], *, target: str) -> str:
    review = consolidator.get("review_summary") or {}
    field = f"{target}_feedback"
    feedback = str(review.get(field) or review.get("rationale") or "").strip()
    omit = consolidator.get("omit_from_narrative") or []
    lines = [
        f"\n\nCONSOLIDATOR — {target.upper()} REVISION REQUIRED:",
        feedback or "(see consolidator rationale)",
    ]
    if omit:
        lines.append("Omit from narrative: " + "; ".join(str(x) for x in omit))
    lines.append("Return valid JSON only.")
    return "\n".join(lines)


def save_consolidator(path: Path, data: dict[str, Any], phase: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(data, indent=2)
    path.write_text(body, encoding="utf-8")
    (path.parent / f"consolidator-{phase}.json").write_text(body, encoding="utf-8")

    report_date = str(data.get("date") or "").strip()
    if report_date:
        dated_sidecar = ROOT / f".consolidator-output-{report_date}.json"
        dated_sidecar.write_text(body, encoding="utf-8")
        legacy = ROOT / ".consolidator-output.json"
        if legacy.is_file() and legacy.resolve() != dated_sidecar.resolve():
            legacy.unlink()


def run_consolidator_plan(
    curator: dict[str, Any],
    *,
    report_date: str,
    run_agent: RunAgent,
    dry_run: bool,
    use_cloud: bool,
    api_key: str | None,
    pipe_dir: Path,
    curator_msg: str,
    max_curator_retries: int = 1,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Plan phase: consolidator sets lesson_groups; may escalate to curator."""
    msg = build_plan_message(curator, report_date=report_date)
    out = run_agent(
        "consolidator",
        msg,
        dry_run=dry_run,
        use_cloud=use_cloud,
        api_key=api_key,
        pipe_dir=pipe_dir / "consolidator-plan",
        report_date=report_date,
    )
    save_consolidator(pipe_dir / "consolidator-plan.json", out, "plan")

    retries = 0
    while not review_passes(out) and "curator" in escalation_targets(out) and retries < max_curator_retries:
        if dry_run:
            break
        retries += 1
        suffix = consolidator_feedback_suffix(out, target="curator")
        curator = run_agent(
            "curator",
            curator_msg + suffix,
            dry_run=False,
            use_cloud=use_cloud,
            api_key=api_key,
            pipe_dir=pipe_dir / f"consolidator-curator-retry-{retries}",
        )
        msg = build_plan_message(curator, report_date=report_date)
        out = run_agent(
            "consolidator",
            msg + "\n\nRe-review after curator revision.",
            dry_run=False,
            use_cloud=use_cloud,
            api_key=api_key,
            pipe_dir=pipe_dir / f"consolidator-plan-retry-{retries}",
            report_date=report_date,
        )
        save_consolidator(pipe_dir / "consolidator-plan.json", out, "plan")

    curator = apply_consolidator_output(curator, out)
    rationale = (out.get("review_summary") or {}).get("rationale") or ""
    print(
        f"Consolidator plan: {curator.get('published_lesson_count')} published lesson(s)"
        + (f" — {rationale[:120]}" if rationale else "")
    )
    return curator, out


def run_consolidator_draft_review(
    *,
    report_date: str,
    curator: dict[str, Any],
    teacher: dict[str, Any],
    run_agent: RunAgent,
    dry_run: bool,
    use_cloud: bool,
    api_key: str | None,
    pipe_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Draft review: returns (teacher, consolidator_out, needs_teacher_retry)."""
    msg = build_draft_review_message(report_date=report_date, curator=curator, teacher=teacher)
    out = run_agent(
        "consolidator",
        msg,
        dry_run=dry_run,
        use_cloud=use_cloud,
        api_key=api_key,
        pipe_dir=pipe_dir / "consolidator-draft",
        report_date=report_date,
    )
    save_consolidator(pipe_dir / "consolidator-draft.json", out, "draft")
    needs_retry = not review_passes(out) and "teacher" in escalation_targets(out)
    if needs_retry:
        print("Consolidator draft_review: teacher revision required")
    elif review_passes(out):
        print("Consolidator draft_review: pass")
    return teacher, out, needs_retry and not dry_run


def run_consolidator_ship_review(
    *,
    report_date: str,
    curator: dict[str, Any],
    teacher: dict[str, Any],
    editor: dict[str, Any],
    run_agent: RunAgent,
    dry_run: bool,
    use_cloud: bool,
    api_key: str | None,
    pipe_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any], set[str]]:
    """Ship review: returns (editor, consolidator_out, escalation_targets)."""
    msg = build_ship_review_message(
        report_date=report_date, curator=curator, teacher=teacher, editor=editor
    )
    out = run_agent(
        "consolidator",
        msg,
        dry_run=dry_run,
        use_cloud=use_cloud,
        api_key=api_key,
        pipe_dir=pipe_dir / "consolidator-ship",
        report_date=report_date,
    )
    save_consolidator(pipe_dir / "consolidator-ship.json", out, "ship")
    if review_passes(out):
        print("Consolidator ship_review: pass")
        return editor, out, set()
    targets = escalation_targets(out)
    print(f"Consolidator ship_review: FAILED — escalate to {sorted(targets)}")
    return editor, out, targets
