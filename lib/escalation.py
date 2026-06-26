"""Route refinement failures back to curator, teacher, or editor."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from lib.lesson_lint import LintResult, lint_curator_plan, lint_night_summary


@dataclass
class EscalationPlan:
    """Who must redo work before the pipeline can ship."""

    targets: set[str] = field(default_factory=set)
    curator_feedback: list[str] = field(default_factory=list)
    teacher_feedback: list[str] = field(default_factory=list)
    editor_feedback: list[str] = field(default_factory=list)

    def merge(self, other: EscalationPlan) -> None:
        self.targets |= other.targets
        self.curator_feedback.extend(other.curator_feedback)
        self.teacher_feedback.extend(other.teacher_feedback)
        self.editor_feedback.extend(other.editor_feedback)

    def curator_message(self) -> str:
        lines = ["The nightly plan must be revised before lessons can ship."]
        for item in self.curator_feedback:
            lines.append(f"- {item}")
        return "\n".join(lines)

    def teacher_message(self) -> str:
        lines = ["Lesson drafts must be revised."]
        for item in self.teacher_feedback:
            lines.append(f"- {item}")
        return "\n".join(lines)


def teacher_requests_curator_revision(teacher: dict[str, Any]) -> tuple[bool, str]:
    review = teacher.get("plan_review") or {}
    if review.get("curator_adequate") is False:
        return True, str(review.get("curator_feedback") or "Curator plan inadequate.")
    if review.get("proceed") is False:
        return True, str(review.get("curator_feedback") or "Teacher blocked on curator plan.")
    return False, ""


def validate_teacher_plan_review(teacher: dict[str, Any]) -> list[str]:
    """Teacher must evaluate the curator plan before editor runs."""
    review = teacher.get("plan_review")
    if not isinstance(review, dict):
        return ["missing plan_review — teacher must approve or reject curator plan before lessons ship"]
    if "curator_adequate" not in review:
        return ["plan_review.curator_adequate is required (true or false)"]
    if "proceed" not in review:
        return ["plan_review.proceed is required (true when writing lessons)"]
    return []


def escalation_from_plan_issues(issues: list[str]) -> EscalationPlan:
    plan = EscalationPlan(targets={"curator"})
    plan.curator_feedback.extend(issues)
    return plan


def escalation_from_editor(editor: dict[str, Any]) -> EscalationPlan:
    plan = EscalationPlan()
    review = editor.get("review_summary") or {}
    for target in review.get("escalate_to") or []:
        if target in ("curator", "teacher", "editor"):
            plan.targets.add(target)
    if review.get("curator_feedback"):
        plan.curator_feedback.append(str(review["curator_feedback"]))
    if review.get("teacher_feedback"):
        plan.teacher_feedback.append(str(review["teacher_feedback"]))
    if review.get("editor_feedback"):
        plan.editor_feedback.append(str(review["editor_feedback"]))
    return plan


def escalation_from_lint(lint: LintResult, curator: dict[str, Any]) -> EscalationPlan:
    plan = EscalationPlan()

    for issue in lint.violations:
        if _is_curator_issue(issue):
            plan.targets.add("curator")
            plan.curator_feedback.append(issue)
        elif _is_teacher_issue(issue):
            plan.targets.add("teacher")
            plan.teacher_feedback.append(issue)
        elif _is_editor_issue(issue):
            plan.targets.add("editor")
            plan.editor_feedback.append(issue)

    for slot, issues in lint.per_lesson.items():
        for issue in issues:
            tagged = f"slot {slot}: {issue}"
            if _is_curator_issue(issue):
                plan.targets.add("curator")
                plan.curator_feedback.append(tagged)
            elif _is_teacher_issue(issue):
                plan.targets.add("teacher")
                plan.teacher_feedback.append(tagged)
            else:
                plan.targets.add("editor")
                plan.editor_feedback.append(tagged)

    for issue in lint_curator_plan(curator):
        plan.targets.add("curator")
        plan.curator_feedback.append(issue)

    return plan


def classify_escalation(
    lint: LintResult,
    *,
    curator: dict[str, Any],
    editor: dict[str, Any],
    teacher: dict[str, Any] | None = None,
) -> EscalationPlan:
    plan = escalation_from_lint(lint, curator)
    plan.merge(escalation_from_editor(editor))
    if teacher:
        needs_curator, feedback = teacher_requests_curator_revision(teacher)
        if needs_curator:
            plan.targets.add("curator")
            if feedback:
                plan.curator_feedback.append(f"Teacher plan_review: {feedback}")
    if not plan.targets and not lint.passed:
        plan.targets.add("teacher")
        plan.teacher_feedback.append("Lint failed; default escalation to teacher rewrite.")
    return plan


def _is_curator_issue(issue: str) -> bool:
    lower = issue.lower()
    return any(
        needle in lower
        for needle in (
            "night_thread",
            "complexity",
            "concept packs",
            "split or defer",
            "too many concepts",
            "curator plan",
            "defer sub-beats",
        )
    )


def _is_teacher_issue(issue: str) -> bool:
    lower = issue.lower()
    if _is_curator_issue(issue):
        return False
    return any(
        needle in lower
        for needle in (
            "terms tonight",
            "scene card",
            "story so far",
            "before ## terms",
            "notation or acronym",
            "motivation",
            "gentle intro",
            "index thread",
            "carry forward",
            "semicolon soup",
            "word count",
            "stub",
            "style_pass",
        )
    )


def _is_editor_issue(issue: str) -> bool:
    return not (_is_curator_issue(issue) or _is_teacher_issue(issue))


def curator_plan_needs_revision(curator: dict[str, Any]) -> tuple[bool, list[str]]:
    issues = lint_curator_plan(curator)
    issues.extend(lint_night_summary(str(curator.get("night_thread") or ""), label="night_thread"))
    return bool(issues), issues
