"""Curator ↔ teacher ↔ editor refinement with escalation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from lib.escalation import (
    EscalationPlan,
    classify_escalation,
    escalation_from_plan_issues,
    teacher_requests_curator_revision,
    validate_teacher_plan_review,
)
from lib.lesson_consolidation import enrich_lessons_from_groups  # noqa: E402
from lib.lesson_lint import LintResult, lint_curator_plan, lint_editor_output
from lib.pipeline_progress import PipelineProgress
from lib.run_artifacts import clear_agent_sidecars

RunAgent = Callable[..., dict[str, Any]]
PostCuratorHook = Callable[[dict[str, Any]], dict[str, Any]]
PostTeacherHook = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
PreShipHook = Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], tuple[dict[str, Any], bool]]

# At least one teacher revision or curator replan is always allowed (never 0).
MIN_REFINEMENT_DEPTH = 1


# Default: 6 editor passes (attempts 0..5) before hard fail
DEFAULT_REFINEMENT_DEPTH = 5


def normalize_refinement_depth(max_depth: int) -> int:
    return max(MIN_REFINEMENT_DEPTH, int(max_depth))


def build_editor_message(
    *,
    curator: dict[str, Any],
    research: dict[str, Any],
    hypothesis: dict[str, Any] | None,
    teacher: dict[str, Any],
    teaching_style: str,
    learner_questions: str,
) -> str:
    hyp_block = ""
    if hypothesis is not None:
        hyp_block = f"Hypothesis output:\n{json.dumps(hypothesis, indent=2)}\n\n"
    return (
        f"Curator plan:\n{json.dumps(curator, indent=2)}\n\n"
        f"Research:\n{json.dumps(research, indent=2)}\n\n"
        f"{hyp_block}"
        f"Teacher drafts:\n{json.dumps(teacher, indent=2)}\n\n"
        f"Teaching style:\n{teaching_style}\n\n"
        f"Learner follow-up questions (from lesson chat — anticipate in Traps and checkpoints):\n"
        f"{learner_questions}\n\n"
        f"Revise all lessons to pass style and graph checks. Set style_pass true only when fixed.\n"
        f"If the curator plan is too dense or jargon-heavy to fix by editing alone, set "
        f"review_summary.escalate_to to include \"curator\" and fill curator_feedback. "
        f"If lesson structure must be rewritten from scratch, escalate to \"teacher\"."
    )


def build_curator_revision_message(base_msg: str, escalation: EscalationPlan) -> str:
    return (
        f"{base_msg}\n\n"
        f"---\n\n"
        f"REVISION REQUIRED — replan tonight (curator pass).\n"
        f"{escalation.curator_message()}\n\n"
        f"Split overloaded beats across nights or topic_queue; rewrite night_thread in plain "
        f"English (~40 words, no symbols). One conceptual move per core lesson.\n\n"
        f"Return full curator JSON only."
    )


def build_teacher_revision_message(
    base_msg: str,
    *,
    editor: dict[str, Any],
    lint: LintResult,
    escalation: EscalationPlan,
    iteration: int,
    curator: dict[str, Any] | None = None,
) -> str:
    n = int(curator.get("published_lesson_count") or 0) if curator else 0
    if n <= 0:
        n = len(curator.get("lesson_groups") or []) if curator else 5
    return (
        f"{base_msg}\n\n"
        f"---\n\n"
        f"REVISION REQUIRED (teacher pass {iteration + 1}).\n"
        f"Programmatic lint failed after editor pass:\n{lint.summary()}\n\n"
        f"Escalation feedback:\n{escalation.teacher_message()}\n\n"
        f"Prior editor output (fix these issues):\n"
        f"{json.dumps(editor, indent=2)[:12000]}\n\n"
        f"Return full teacher JSON with all {n} complete published lessons including "
        f"## Scene card, ## Story so far (if required), and ## Terms tonight on every lesson.\n"
        f"## Terms tonight must appear before any mechanism section (see teaching-style motivation ladder).\n"
        f"Set merged_from_slots and concepts_covered on each lesson when lesson_groups say merged.\n"
        f"Set plan_review.curator_adequate false if the curator plan still cannot support "
        f"standalone step-by-step lessons."
    )


def build_teacher_plan_review_message(base_msg: str, issues: list[str]) -> str:
    return (
        f"{base_msg}\n\n"
        f"---\n\n"
        f"REVISION REQUIRED — add plan_review before editor runs.\n"
        + "\n".join(f"- {i}" for i in issues)
        + "\n\nReturn full teacher JSON. Include plan_review with curator_adequate and proceed. "
        f"If the curator plan cannot support standalone step-by-step lessons, set "
        f"curator_adequate false and proceed false with curator_feedback."
    )


def build_teacher_message_after_curator_replan(
    base_msg: str,
    *,
    curator: dict[str, Any],
    research: dict[str, Any],
) -> str:
    return (
        f"{base_msg}\n\n"
        f"---\n\n"
        f"Curator plan was revised. Use this plan only:\n"
        f"{json.dumps(curator, indent=2)}\n\n"
        f"Research:\n{json.dumps(research, indent=2)}\n\n"
        f"Write fresh lesson drafts from the revised plan. Include plan_review."
    )


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _replan_curator_chain(
    *,
    escalation: EscalationPlan,
    curator_base_msg: str,
    teacher_base_msg: str,
    run_agent: RunAgent,
    run_research: Callable[[dict[str, Any]], dict[str, Any]],
    post_curator: PostCuratorHook,
    pipe_dir: Path,
    replan_dir: Path,
    dry_run: bool,
    use_cloud: bool,
    api_key: str | None,
    report_date: str | None,
    progress: PipelineProgress | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if progress is not None:
        progress.step("curator", detail="revision after escalation")
    curator = run_agent(
        "curator",
        build_curator_revision_message(curator_base_msg, escalation),
        dry_run=dry_run,
        use_cloud=use_cloud,
        api_key=api_key,
        pipe_dir=replan_dir,
    )
    curator = post_curator(curator)
    _save_json(pipe_dir / "curator.json", curator)
    _save_json(replan_dir / "curator.json", curator)

    research = run_research(curator)
    _save_json(pipe_dir / "research.json", research)
    _save_json(replan_dir / "research.json", research)

    if progress is not None:
        progress.step("teacher", detail="after curator replan")
    teacher = run_agent(
        "teacher",
        build_teacher_message_after_curator_replan(
            teacher_base_msg,
            curator=curator,
            research=research,
        ),
        dry_run=dry_run,
        use_cloud=use_cloud,
        api_key=api_key,
        pipe_dir=replan_dir,
        report_date=report_date,
    )
    _save_json(pipe_dir / "teacher.json", teacher)
    return curator, research, teacher


def run_content_refinement(
    *,
    curator: dict[str, Any],
    research: dict[str, Any],
    teacher: dict[str, Any] | None,
    curator_base_msg: str,
    teacher_base_msg: str,
    teaching_style: str,
    learner_questions: str,
    run_agent: RunAgent,
    run_research: Callable[[dict[str, Any]], dict[str, Any]],
    post_curator: PostCuratorHook,
    pipe_dir: Path,
    dry_run: bool,
    use_cloud: bool,
    api_key: str | None,
    max_depth: int = DEFAULT_REFINEMENT_DEPTH,
    hypothesis: dict[str, Any] | None = None,
    report_date: str | None = None,
    progress: PipelineProgress | None = None,
    post_teacher_hook: PostTeacherHook | None = None,
    pre_ship_hook: PreShipHook | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], LintResult]:
    """
    Curator → teacher → editor with mandatory back-edges.

    Guaranteed loops (when not dry-run):
    - Programmatic curator plan lint may replan curator → research → teacher.
    - Teacher plan_review may send work back to curator.
    - Editor lint / escalation may send work back to teacher or curator.

    max_depth is clamped to at least MIN_REFINEMENT_DEPTH (1).
    """
    max_depth = normalize_refinement_depth(max_depth)
    current_curator = curator
    current_research = research
    current_teacher = teacher
    last_editor: dict[str, Any] = {}
    last_lint = LintResult(passed=False, violations=["not started"])
    curator_replans = 0
    teacher_revisions = 0

    if current_teacher is None:
        if progress is not None:
            progress.step("teacher", detail="initial draft")
        current_teacher = run_agent(
            "teacher",
            teacher_base_msg,
            dry_run=dry_run,
            use_cloud=use_cloud,
            api_key=api_key,
            pipe_dir=pipe_dir,
            report_date=report_date,
        )
        current_teacher = enrich_lessons_from_groups(current_teacher, current_curator)
        _save_json(pipe_dir / "teacher.json", current_teacher)

    if post_teacher_hook is not None:
        if progress is not None:
            progress.step("consolidator", detail="draft review")
        current_teacher = post_teacher_hook(current_curator, current_teacher)
        current_teacher = enrich_lessons_from_groups(current_teacher, current_curator)
        _save_json(pipe_dir / "teacher.json", current_teacher)

    while True:
        replan_dir = pipe_dir / f"replan-{curator_replans:02d}"
        replan_dir.mkdir(parents=True, exist_ok=True)

        plan_issues = lint_curator_plan(current_curator)
        if plan_issues and not dry_run:
            if curator_replans >= max_depth:
                raise RuntimeError(
                    "Curator plan failed programmatic lint:\n" + "\n".join(plan_issues)
                )
            curator_replans += 1
            print(
                f"Curator plan gate: FAILED — replan {curator_replans}/{max_depth}\n"
                + "\n".join(plan_issues)
            )
            current_curator, current_research, current_teacher = _replan_curator_chain(
                escalation=escalation_from_plan_issues(plan_issues),
                curator_base_msg=curator_base_msg,
                teacher_base_msg=teacher_base_msg,
                run_agent=run_agent,
                run_research=run_research,
                post_curator=post_curator,
                pipe_dir=pipe_dir,
                replan_dir=pipe_dir / f"replan-{curator_replans:02d}",
                dry_run=dry_run,
                use_cloud=use_cloud,
                api_key=api_key,
                report_date=report_date,
                progress=progress,
            )
            teacher_revisions = 0
            continue

        plan_review_issues = validate_teacher_plan_review(current_teacher)
        if plan_review_issues and not dry_run:
            if teacher_revisions >= max_depth:
                raise RuntimeError(
                    "Teacher missing plan_review after retries:\n"
                    + "\n".join(plan_review_issues)
                )
            teacher_revisions += 1
            if progress is not None:
                progress.step("teacher", detail="plan_review required")
            current_teacher = run_agent(
                "teacher",
                build_teacher_plan_review_message(teacher_base_msg, plan_review_issues),
                dry_run=dry_run,
                use_cloud=use_cloud,
                api_key=api_key,
                pipe_dir=replan_dir / f"plan-review-{teacher_revisions:02d}",
                report_date=report_date,
            )
            _save_json(pipe_dir / "teacher.json", current_teacher)
            continue

        needs_curator, teacher_feedback = teacher_requests_curator_revision(current_teacher)
        if needs_curator:
            if dry_run:
                print(f"Dry-run: teacher blocked on curator plan: {teacher_feedback}")
            elif curator_replans >= max_depth:
                raise RuntimeError(
                    f"Teacher rejected curator plan after {max_depth + 1} plan(s):\n"
                    f"{teacher_feedback}"
                )
            else:
                escalation = EscalationPlan(
                    targets={"curator"},
                    curator_feedback=[f"Teacher plan_review: {teacher_feedback}"],
                )
                curator_replans += 1
                current_curator, current_research, current_teacher = _replan_curator_chain(
                    escalation=escalation,
                    curator_base_msg=curator_base_msg,
                    teacher_base_msg=teacher_base_msg,
                    run_agent=run_agent,
                    run_research=run_research,
                    post_curator=post_curator,
                    pipe_dir=pipe_dir,
                    replan_dir=pipe_dir / f"replan-{curator_replans:02d}",
                    dry_run=dry_run,
                    use_cloud=use_cloud,
                    api_key=api_key,
                    report_date=report_date,
                    progress=progress,
                )
                teacher_revisions = 0
                continue

        for attempt in range(max_depth + 1):
            iter_dir = replan_dir / f"iter-{attempt:02d}"
            iter_dir.mkdir(parents=True, exist_ok=True)

            if progress is not None:
                progress.step(
                    "editor",
                    detail=(
                        f"refinement pass {attempt + 1}/{max_depth + 1} "
                        f"(plan {curator_replans + 1}, lint gate)"
                    ),
                )

            editor_msg = build_editor_message(
                curator=current_curator,
                research=current_research,
                hypothesis=hypothesis,
                teacher=current_teacher,
                teaching_style=teaching_style,
                learner_questions=learner_questions,
            )
            if attempt > 0:
                cleared = clear_agent_sidecars(report_date=report_date)
                if cleared:
                    print(
                        f"Cleared stale sidecars before editor retry pass {attempt + 1}: "
                        f"{', '.join(cleared)}"
                    )
                editor_msg += (
                    "\n\nRevision pass — fix prior lint failures:\n"
                    f"{last_lint.summary()}\n\n"
                    "Use review_summary.escalate_to when you cannot fix alone."
                )

            last_editor = run_agent(
                "editor",
                editor_msg,
                dry_run=dry_run,
                use_cloud=use_cloud,
                api_key=api_key,
                pipe_dir=iter_dir,
                report_date=report_date,
            )
            last_editor = enrich_lessons_from_groups(last_editor, current_curator)
            _save_json(iter_dir / "editor.json", last_editor)
            _save_json(pipe_dir / "editor.json", last_editor)

            last_lint = lint_editor_output(last_editor, current_curator)
            _save_json(
                iter_dir / "lint.json",
                {
                    "passed": last_lint.passed,
                    "violations": last_lint.violations,
                    "per_lesson": last_lint.per_lesson,
                },
            )

            if last_lint.passed:
                if pre_ship_hook is not None:
                    if progress is not None:
                        progress.step("consolidator", detail="ship review")
                    last_editor, ship_ok = pre_ship_hook(
                        current_curator, current_teacher, last_editor
                    )
                    _save_json(pipe_dir / "editor.json", last_editor)
                    if not ship_ok:
                        if dry_run:
                            print("Dry-run: consolidator ship_review requested revision; re-linting.")
                        last_lint = lint_editor_output(last_editor, current_curator)
                        if last_lint.passed:
                            continue
                        # fall through to normal editor failure handling

                print(
                    f"Editor pass gate: OK (plan {curator_replans + 1}, iteration {attempt}, "
                    f"curator replans {curator_replans}, teacher revisions {teacher_revisions})"
                )
                return (
                    current_curator,
                    current_research,
                    current_teacher,
                    last_editor,
                    last_lint,
                )

            escalation = classify_escalation(
                last_lint,
                curator=current_curator,
                editor=last_editor,
                teacher=current_teacher,
            )
            print(
                f"Editor pass gate: FAILED (plan {curator_replans + 1}, iteration {attempt})\n"
                f"{last_lint.summary()}\n"
                f"Escalation targets: {sorted(escalation.targets)}"
            )

            if dry_run:
                print("Dry-run: accepting editor output despite lint failures")
                return (
                    current_curator,
                    current_research,
                    current_teacher,
                    last_editor,
                    last_lint,
                )

            if "curator" in escalation.targets:
                if curator_replans >= max_depth:
                    raise RuntimeError(
                        f"Editor/curator escalation exhausted after {max_depth + 1} plan(s):\n"
                        f"{last_lint.summary()}\n"
                        f"{escalation.curator_message()}"
                    )
                curator_replans += 1
                current_curator, current_research, current_teacher = _replan_curator_chain(
                    escalation=escalation,
                    curator_base_msg=curator_base_msg,
                    teacher_base_msg=teacher_base_msg,
                    run_agent=run_agent,
                    run_research=run_research,
                    post_curator=post_curator,
                    pipe_dir=pipe_dir,
                    replan_dir=pipe_dir / f"replan-{curator_replans:02d}",
                    dry_run=dry_run,
                    use_cloud=use_cloud,
                    api_key=api_key,
                    report_date=report_date,
                    progress=progress,
                )
                teacher_revisions = 0
                break

            if attempt >= max_depth:
                raise RuntimeError(
                    f"Editor pass gate failed after {max_depth + 1} editor pass(es):\n"
                    f"{last_lint.summary()}\n"
                    f"{escalation.teacher_message()}"
                )

            teacher_revisions += 1
            if progress is not None:
                progress.step("teacher", detail=f"revision after editor pass {attempt + 1}")
            cleared = clear_agent_sidecars(report_date=report_date)
            if cleared:
                print(f"Cleared stale sidecars before teacher retry: {', '.join(cleared)}")
            current_teacher = run_agent(
                "teacher",
                build_teacher_revision_message(
                    teacher_base_msg,
                    editor=last_editor,
                    lint=last_lint,
                    escalation=escalation,
                    iteration=attempt,
                    curator=current_curator,
                ),
                dry_run=dry_run,
                use_cloud=use_cloud,
                api_key=api_key,
                pipe_dir=iter_dir,
                report_date=report_date,
            )
            current_teacher = enrich_lessons_from_groups(current_teacher, current_curator)
            _save_json(iter_dir / "teacher.json", current_teacher)
            _save_json(pipe_dir / "teacher.json", current_teacher)
        else:
            continue


run_teacher_editor_refinement = run_content_refinement
