#!/usr/bin/env python3
"""Tests for refinement depth and plan_review gates."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.escalation import validate_teacher_plan_review  # noqa: E402
from lib.refinement import (  # noqa: E402
    DEFAULT_REFINEMENT_DEPTH,
    MIN_REFINEMENT_DEPTH,
    normalize_refinement_depth,
)


class RefinementDepthTests(unittest.TestCase):
    def test_minimum_depth_is_one(self) -> None:
        self.assertEqual(MIN_REFINEMENT_DEPTH, 1)
        self.assertEqual(normalize_refinement_depth(0), 1)
        self.assertEqual(normalize_refinement_depth(2), 2)

    def test_default_depth_allows_six_editor_passes(self) -> None:
        self.assertEqual(DEFAULT_REFINEMENT_DEPTH, 5)

    def test_plan_review_required(self) -> None:
        self.assertTrue(validate_teacher_plan_review({}))
        self.assertFalse(
            validate_teacher_plan_review(
                {"plan_review": {"curator_adequate": True, "proceed": True}}
            )
        )


if __name__ == "__main__":
    unittest.main()
