#!/usr/bin/env python3
"""Tests for lib/run_artifacts.py."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.run_artifacts import cleanup_run_artifacts, clear_agent_sidecars  # noqa: E402


class RunArtifactsTests(unittest.TestCase):
    def test_removes_sidecars_and_dated_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".teacher-output-2026-06-26.json").write_text("{}", encoding="utf-8")
            (root / ".editor-output-2026-06-26.json").write_text("{}", encoding="utf-8")
            (root / ".teacher-gen-full.py").write_text("# scratch", encoding="utf-8")
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "nightly-local.sh").write_text("#!/bin/sh", encoding="utf-8")
            (scripts / "editor_output_2026_06_26.py").write_text("# old", encoding="utf-8")
            (scripts / "_teacher_drafts.json").write_text("{}", encoding="utf-8")

            removed = cleanup_run_artifacts(root=root)
            self.assertIn(".teacher-output-2026-06-26.json", removed)
            self.assertIn(".editor-output-2026-06-26.json", removed)
            self.assertIn(".teacher-gen-full.py", removed)
            self.assertIn("scripts/editor_output_2026_06_26.py", removed)
            self.assertTrue((scripts / "nightly-local.sh").is_file())
            self.assertFalse((root / ".teacher-output-2026-06-26.json").exists())

    def test_empty_when_nothing_to_remove(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            self.assertEqual(cleanup_run_artifacts(root=root), [])

    def test_clear_agent_sidecars_includes_pipeline_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pipe = root / "pipeline" / "2026-06-26"
            pipe.mkdir(parents=True)
            (root / ".editor-output-2026-06-26.json").write_text("{}", encoding="utf-8")
            (pipe / "editor.json").write_text("{}", encoding="utf-8")
            (pipe / "teacher.json").write_text("{}", encoding="utf-8")
            (pipe / "consolidator-plan.json").write_text("{}", encoding="utf-8")

            removed = clear_agent_sidecars(report_date="2026-06-26", root=root)
            self.assertIn(".editor-output-2026-06-26.json", removed)
            self.assertIn("pipeline/2026-06-26/editor.json", removed)
            self.assertIn("pipeline/2026-06-26/teacher.json", removed)
            self.assertIn("pipeline/2026-06-26/consolidator-plan.json", removed)
            self.assertFalse((pipe / "editor.json").exists())


if __name__ == "__main__":
    unittest.main()
