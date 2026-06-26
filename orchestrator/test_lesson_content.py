#!/usr/bin/env python3
"""Tests for lesson markdown validation and site lesson rendering."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.lesson_content import is_lesson_markdown_stub, validate_lesson_markdown  # noqa: E402
from lib.topic_mastery import needs_gentle_intro  # noqa: E402


class LessonContentTests(unittest.TestCase):
    def test_detects_word_count_stub(self) -> None:
        self.assertTrue(is_lesson_markdown_stub("...(1917 words)..."))
        self.assertTrue(is_lesson_markdown_stub("...(1917 words — see reports/2026-06-27/editor.json)..."))

    def test_accepts_real_lesson_opening(self) -> None:
        md = "# [Bayesian Inference] Why?\n\n## The situation\n\nStory here."
        self.assertFalse(is_lesson_markdown_stub(md))
        validate_lesson_markdown(md)

    def test_validate_raises_on_stub(self) -> None:
        with self.assertRaises(ValueError):
            validate_lesson_markdown("...(500 words)...", source="test.md")

    def test_needs_gentle_intro(self) -> None:
        profile = {"seeded_topics": ["Logistic Regression", "KNN"]}
        self.assertTrue(needs_gentle_intro("Bayesian Inference", profile=profile))
        self.assertTrue(needs_gentle_intro("Monte Carlo", profile=profile))
        self.assertFalse(needs_gentle_intro("Logistic Regression", profile=profile))


class SiteLessonBuildTests(unittest.TestCase):
    def test_lesson_html_renders_body_not_stub(self) -> None:
        import importlib.util

        build_path = ROOT / "site" / "build.py"
        spec = importlib.util.spec_from_file_location("learning_site_build", build_path)
        assert spec and spec.loader
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)

        report_date = "2026-06-26"
        src_dir = ROOT / "reports" / report_date
        if not src_dir.exists():
            self.skipTest("fixture report missing")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            reports = tmp_root / "reports"
            shutil.copytree(src_dir, reports / report_date)
            public = tmp_root / "site" / "public"
            public.mkdir(parents=True)

            with patch.object(build, "ROOT", tmp_root), patch.object(build, "PUBLIC", public), patch.object(
                build, "REPORTS", reports
            ), patch.object(build, "sync_learner_state"), patch.object(build, "sync_spine_progress"), patch.object(
                build, "collect_all_lessons", return_value=[]
            ):
                (public / "reports" / report_date).mkdir(parents=True, exist_ok=True)
                build.build_lesson_pages(report_date, [])

            html = (public / "reports" / report_date / "lesson-01.html").read_text(encoding="utf-8")
            self.assertIn("The situation", html)
            self.assertNotIn("words — see reports", html)
            self.assertNotIn("...(1917 words)", html)


if __name__ == "__main__":
    unittest.main()
