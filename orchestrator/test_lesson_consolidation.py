#!/usr/bin/env python3
"""Tests for same-topic lesson consolidation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.lesson_consolidation import (  # noqa: E402
    build_lesson_groups,
    enrich_lessons_from_groups,
    enforce_lesson_consolidation,
    validate_lesson_groups,
    validate_stretch_preservation,
)


def _plan(*topics: str, optional_slots: set[int] | None = None) -> dict:
    optional_slots = optional_slots or set()
    lessons = []
    for i, topic in enumerate(topics, start=1):
        lessons.append(
            {
                "slot": i,
                "topic_label": topic,
                "concept": f"concept_{i}",
                "pressure_question": f"Q{i}",
                "optional": i in optional_slots,
                "slot_role": "bridge" if i in optional_slots and topic != topics[0] else "deepen",
            }
        )
    return {
        "topic_label": topics[0] if topics else "",
        "night_type": "arc",
        "lessons": lessons,
    }


class TestLessonConsolidation(unittest.TestCase):
    def test_four_same_topic_plus_bridge_becomes_two_groups(self) -> None:
        curator = _plan(
            "Bayesian Inference",
            "Bayesian Inference",
            "Bayesian Inference",
            "Bayesian Inference",
            "Monte Carlo",
            optional_slots={5},
        )
        groups = build_lesson_groups(curator)
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["source_slots"], [1, 2, 3, 4])
        self.assertFalse(groups[0].get("optional"))
        self.assertTrue(groups[0]["merged"])
        self.assertEqual(groups[1]["topic_label"], "Monte Carlo")
        self.assertTrue(groups[1].get("optional"))
        ok, _ = validate_lesson_groups(groups, curator)
        self.assertTrue(ok)

    def test_stretch_not_merged_into_arc_core(self) -> None:
        curator = _plan(
            "Bayesian Inference",
            "Bayesian Inference",
            "Bayesian Inference",
            "Monte Carlo",
            optional_slots={4},
        )
        bad_groups = [
            {
                "publish_slot": 1,
                "topic_label": "Bayesian Inference",
                "source_slots": [1, 2, 3, 4],
                "optional": False,
            }
        ]
        ok, msg = validate_stretch_preservation(curator, bad_groups)
        self.assertFalse(ok)
        self.assertIn("stretch", msg.lower())

        fixed = build_lesson_groups(curator)
        self.assertTrue(validate_lesson_groups(fixed, curator)[0])
        optional = [g for g in fixed if g.get("optional")]
        self.assertEqual(len(optional), 1)
        self.assertEqual(optional[0]["source_slots"], [4])

    def test_exploration_same_topic_keeps_slot_five_stretch(self) -> None:
        curator = _plan(
            "Quantum Computing",
            "Quantum Computing",
            "Quantum Computing",
            "Quantum Computing",
            "Quantum Computing",
            optional_slots={5},
        )
        curator["night_type"] = "exploration"
        groups = build_lesson_groups(curator)
        stretch = [g for g in groups if g.get("optional")]
        self.assertEqual(len(stretch), 1)
        self.assertIn(5, stretch[0]["source_slots"])
        self.assertTrue(validate_lesson_groups(groups, curator)[0])

    def test_all_same_topic_splits_to_minimum_two(self) -> None:
        curator = _plan("Bayesian Inference", "Bayesian Inference", "Bayesian Inference", "Bayesian Inference", "Bayesian Inference")
        groups = build_lesson_groups(curator)
        self.assertGreaterEqual(len(groups), 2)
        ok, _ = validate_lesson_groups(groups)
        self.assertTrue(ok)

    def test_five_distinct_topics_stays_five(self) -> None:
        curator = _plan("A", "B", "C", "D", "E")
        groups = build_lesson_groups(curator)
        self.assertEqual(len(groups), 5)

    def test_enforce_attaches_groups(self) -> None:
        curator = _plan("Bayesian Inference", "Bayesian Inference", "Monte Carlo")
        out, invalid, msg = enforce_lesson_consolidation(curator)
        self.assertFalse(invalid)
        self.assertEqual(out["published_lesson_count"], 2)
        self.assertIn("2 published", msg)

    def test_enrich_fills_merged_metadata_from_groups(self) -> None:
        curator = _plan("Bayesian Inference", "Bayesian Inference", "Monte Carlo")
        curator, _, _ = enforce_lesson_consolidation(curator)
        teacher = {
            "lessons": [
                {"slot": 1, "markdown": "# L1", "slug": "l1", "title": "L1"},
                {"slot": 2, "markdown": "# L2", "slug": "l2", "title": "L2"},
            ]
        }
        out = enrich_lessons_from_groups(teacher, curator)
        self.assertEqual(out["lessons"][0]["merged_from_slots"], [1, 2])
        self.assertEqual(out["lessons"][1]["merged_from_slots"], [3])


if __name__ == "__main__":
    unittest.main()
