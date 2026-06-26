#!/usr/bin/env python3
"""Tests for lib/lesson_lint.py and lib/arc_progress.py"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.arc_progress import max_narrative_day_for_run, validate_curator_arc  # noqa: E402
from lib.lesson_lint import lint_editor_output, lint_lesson_markdown  # noqa: E402

GOOD_MD = """
# [Bayesian Inference] Test?

## Scene card
You are the ML engineer. Priya and Marcus. 200 emails, 148 spam, 52 ham.

## Story so far
- Prior beat one.

## Terms tonight
- **θ** — folder spam rate.

## The situation
Body text here.
""" + ("word " * 1300)


class LessonLintTests(unittest.TestCase):
    def test_missing_scene_card_fails(self) -> None:
        md = "## Terms tonight\n\nx\n" + ("word " * 1300)
        issues = lint_lesson_markdown(md, slot=1, narrative_day=1, optional=False)
        self.assertTrue(any("Scene card" in i for i in issues))

    def test_good_lesson_passes_headings(self) -> None:
        issues = lint_lesson_markdown(GOOD_MD, slot=2, narrative_day=2, optional=False)
        self.assertFalse(any("Scene card" in i for i in issues))
        self.assertFalse(any("Story so far" in i for i in issues))

    def test_editor_all_pass_required(self) -> None:
        editor = {
            "review_summary": {"all_pass": False},
            "lessons": [
                {
                    "slot": i,
                    "style_pass": True,
                    "markdown": GOOD_MD,
                }
                for i in range(1, 6)
            ],
        }
        curator = {"narrative_day": 2, "lessons": [{"slot": i} for i in range(1, 6)]}
        result = lint_editor_output(editor, curator)
        self.assertFalse(result.passed)

    def test_jargon_thread_fails_index_lint(self) -> None:
        from lib.lesson_lint import lint_index_md, lint_night_summary

        bad = (
            "Marcus won't sign until draws target P(β|D), reject sampling dies in 10k-D, "
            "R-hat/ESS pass, and Platt routing separates from MCMC integral footnotes."
        )
        self.assertTrue(lint_night_summary(bad))
        index = f"# Daily\n\n**Thread:** {bad}\n"
        self.assertTrue(lint_index_md(index))

    def test_pre_terms_jargon_fails(self) -> None:
        md = """
# [Bayesian Inference] Test?

## Scene card
Draws must target P(β|D) before Marcus signs.

## Terms tonight
- **β** — weights.

## The situation
Body.
""" + ("word " * 1300)
        issues = lint_lesson_markdown(md, slot=1, narrative_day=1, optional=False)
        self.assertTrue(any("before ## Terms tonight" in i for i in issues))


class ArcProgressTests(unittest.TestCase):
    def test_max_day_with_one_report(self) -> None:
        # 2026-06-26 exists in repo
        self.assertEqual(max_narrative_day_for_run("2026-06-27"), 2)

    def test_clamp_narrative_day(self) -> None:
        curator = {"narrative_day": 99, "narrative_arc_patch": {"current_day": 99}}
        validate_curator_arc(curator, "2026-06-27")
        self.assertLessEqual(curator["narrative_day"], 2)
        self.assertLessEqual(curator["narrative_arc_patch"]["current_day"], 2)


if __name__ == "__main__":
    unittest.main()
