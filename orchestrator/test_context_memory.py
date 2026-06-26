#!/usr/bin/env python3
"""Tests for context packs, pedagogy archive, run brief, memory consolidator."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.context_pack import build_role_context  # noqa: E402
from lib.memory_consolidator import consolidate_memory  # noqa: E402
from lib.pedagogy_state import (  # noqa: E402
    format_pedagogy_for_agents,
    migrate_pedagogy_history,
    persist_pedagogy_latest,
)
from lib.playbook import playbook_sections_for_role  # noqa: E402
from lib.run_brief import build_run_brief, save_run_brief  # noqa: E402


class ContextMemoryTests(unittest.TestCase):
    def test_playbook_sections_vary_by_role(self) -> None:
        curator = playbook_sections_for_role("curator")
        teacher = playbook_sections_for_role("teacher")
        self.assertIn("planning", curator)
        self.assertIn("teaching", teacher)
        self.assertNotIn("planning", teacher)

    def test_pedagogy_format_is_compact(self) -> None:
        text = format_pedagogy_for_agents()
        self.assertLess(len(text), 3000)

    def test_migrate_and_persist_pedagogy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            learner = root / "learner"
            learner.mkdir()
            archive = learner / "archive" / "pedagogy"
            ped_path = learner / "pedagogy-feedback.yaml"
            ped_path.write_text(
                "latest:\n  date: '2026-06-25'\n  summary: old\nentries:\n  - date: '2026-06-24'\n    summary: archived\n",
                encoding="utf-8",
            )

            import lib.pedagogy_state as ps

            old_ped = ps.PEDAGOGY_PATH
            old_arc = ps.ARCHIVE_DIR
            ps.PEDAGOGY_PATH = ped_path
            ps.ARCHIVE_DIR = archive
            try:
                written = migrate_pedagogy_history()
                self.assertTrue(any("2026-06-24" in w for w in written))
                self.assertFalse("entries:" in ped_path.read_text(encoding="utf-8"))

                grapher = {
                    "summary": "Tonight we learned calibration.",
                    "curator_guidance": {"next_night_focus": "prior next", "avoid": ["accuracy rerun"]},
                    "quality_scores": {"clarity": 4},
                    "lesson_feedback": [],
                }
                persist_pedagogy_latest(grapher, "2026-06-26", carry_forward=["bullet one"])
                self.assertTrue((archive / "2026-06-26.yaml").is_file())
                latest_text = ped_path.read_text(encoding="utf-8")
                self.assertIn("carry_forward", latest_text)
                self.assertNotIn("entries:", latest_text)
            finally:
                ps.PEDAGOGY_PATH = old_ped
                ps.ARCHIVE_DIR = old_arc

    def test_build_run_brief(self) -> None:
        brief = build_run_brief("2026-06-26", suggested_night_type="arc")
        self.assertEqual(brief["date"], "2026-06-26")
        self.assertIn("arc", brief)
        self.assertIn("pedagogy", brief)

    def test_role_context_under_budget(self) -> None:
        text, manifest = build_role_context("research", report_date="2026-06-26")
        self.assertIn("run-brief", text)
        self.assertLessEqual(len(text), manifest["budget"])

    def test_memory_consolidator_carry_forward(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            learner = root / "learner"
            archive = learner / "archive" / "pedagogy"
            archive.mkdir(parents=True)
            (archive / "2026-06-25.yaml").write_text(
                "date: '2026-06-25'\nsummary: We separated three memo objects on the quarantine batch.\n",
                encoding="utf-8",
            )

            import lib.pedagogy_state as ps

            ps.ARCHIVE_DIR = archive
            ps.PEDAGOGY_PATH = learner / "pedagogy-feedback.yaml"
            try:
                result = consolidate_memory(
                    {"summary": "New night summary.", "curator_guidance": {}, "lesson_feedback": []},
                    "2026-06-26",
                )
                self.assertGreaterEqual(result["carry_forward_count"], 1)
            finally:
                ps.ARCHIVE_DIR = ROOT / "learner" / "archive" / "pedagogy"
                ps.PEDAGOGY_PATH = ROOT / "learner" / "pedagogy-feedback.yaml"


if __name__ == "__main__":
    unittest.main()
