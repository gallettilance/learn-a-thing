#!/usr/bin/env python3
"""Tests for lib/pipeline_progress.py."""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.pipeline_progress import PipelineProgress  # noqa: E402


class PipelineProgressTests(unittest.TestCase):
    def test_steps_increment_without_total(self) -> None:
        buf = io.StringIO()
        progress = PipelineProgress()
        with redirect_stdout(buf):
            progress.step("curator")
            progress.step("editor", detail="refinement pass 1/3 (lint gate)")
        lines = buf.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("step 1: curator", lines[0])
        self.assertIn("step 2: editor", lines[1])
        self.assertNotIn("/6", buf.getvalue())
        self.assertEqual(progress.count, 2)


if __name__ == "__main__":
    unittest.main()
