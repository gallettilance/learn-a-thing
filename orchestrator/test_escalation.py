#!/usr/bin/env python3
"""Tests for lib/escalation.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.escalation import (  # noqa: E402
    classify_escalation,
    teacher_requests_curator_revision,
)
from lib.lesson_lint import LintResult, lint_curator_plan


class EscalationTests(unittest.TestCase):
    def test_teacher_blocks_inadequate_plan(self) -> None:
        teacher = {
            "plan_review": {
                "curator_adequate": False,
                "curator_feedback": "Split MCMC across two nights.",
                "proceed": False,
            }
        }
        blocked, msg = teacher_requests_curator_revision(teacher)
        self.assertTrue(blocked)
        self.assertIn("Split MCMC", msg)

    def test_editor_escalates_to_curator(self) -> None:
        editor = {
            "review_summary": {
                "all_pass": False,
                "escalate_to": ["curator"],
                "curator_feedback": "Slot 3 concept packs two moves.",
            },
            "lessons": [],
            "index_md": "# Daily\n",
        }
        lint = LintResult(passed=False, violations=["review_summary.all_pass is not true"])
        curator = {"night_thread": "ok", "lessons": [{"slot": 1, "concept": "one"}]}
        plan = classify_escalation(lint, curator=curator, editor=editor)
        self.assertIn("curator", plan.targets)

    def test_lint_curator_flags_jargon_thread(self) -> None:
        curator = {
            "night_thread": "P(β|D) and R-hat ESS MCMC tonight on the queue.",
            "lessons": [
                {
                    "slot": 1,
                    "concept": "reject sampling and MH and diagnostics",
                    "intro_pacing": "gentle",
                    "optional": False,
                    "pressure_question": "Why?",
                }
            ],
        }
        issues = lint_curator_plan(curator)
        self.assertTrue(any("night_thread" in i for i in issues))
        self.assertTrue(any("multiple moves" in i for i in issues))


if __name__ == "__main__":
    unittest.main()
