#!/usr/bin/env python3
"""Unit tests for topic diversity enforcement."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.topic_diversity import (  # noqa: E402
    check_topic_diversity,
    collect_diversity_candidates,
    enforce_topic_diversity,
    topic_counts,
)


def _five_same(topic: str = "Bayesian Inference") -> list[dict]:
    return [{"slot": i, "topic_label": topic} for i in range(1, 6)]


def _four_plus_one(arc: str = "Bayesian Inference", other: str = "Naive Bayes") -> list[dict]:
    lessons = _five_same(arc)[:4]
    lessons.append({"slot": 5, "topic_label": other})
    return lessons


class TopicDiversityTests(unittest.TestCase):
    def test_all_same_fails(self) -> None:
        curator = {"night_type": "arc", "topic_label": "Bayesian Inference", "lessons": _five_same()}
        ok, msg = check_topic_diversity(curator)
        self.assertFalse(ok)
        self.assertIn("Bayesian Inference", msg)

    def test_four_plus_one_passes(self) -> None:
        curator = {"night_type": "arc", "topic_label": "Bayesian Inference", "lessons": _four_plus_one()}
        ok, _ = check_topic_diversity(curator)
        self.assertTrue(ok)

    def test_exploration_all_same_allowed(self) -> None:
        curator = {
            "night_type": "exploration",
            "topic_label": "Quantum Physics",
            "lessons": _five_same("Quantum Physics"),
        }
        ok, msg = check_topic_diversity(curator)
        self.assertTrue(ok)
        self.assertIn("exploration", msg)

    def test_enforce_fixes_homogeneous_arc_night(self) -> None:
        curator = {
            "night_type": "arc",
            "topic_label": "Bayesian Inference",
            "lessons": [
                {
                    "slot": i,
                    "topic_label": "Bayesian Inference",
                    "pressure_question": f"p{i}",
                    "slot_role": "deepen",
                }
                for i in range(1, 6)
            ],
        }
        fixed, changed, msg = enforce_topic_diversity(curator, "2099-06-01")
        self.assertTrue(changed, msg)
        ok, _ = check_topic_diversity(fixed)
        self.assertTrue(ok)
        labels = [l["topic_label"] for l in fixed["lessons"]]
        self.assertEqual(sum(1 for t in labels if t == "Bayesian Inference"), 4)
        self.assertEqual(len(set(labels)), 2)

    def test_candidates_exclude_arc_topic(self) -> None:
        candidates = collect_diversity_candidates(
            arc_topic="Bayesian Inference",
            report_date="2099-06-01",
            night_type="arc",
        )
        self.assertTrue(candidates)
        for c in candidates:
            self.assertNotEqual(c["topic_label"].lower(), "bayesian inference")

    def test_candidates_exclude_mastered_topics(self) -> None:
        with patch(
            "lib.topic_diversity.all_mastered_labels",
            return_value={"Naive Bayes", "Monte Carlo"},
        ):
            candidates = collect_diversity_candidates(
                arc_topic="Bayesian Inference",
                report_date="2099-06-01",
                night_type="arc",
            )
        labels = {c["topic_label"] for c in candidates}
        self.assertNotIn("Naive Bayes", labels)
        self.assertNotIn("Monte Carlo", labels)

    def test_topic_counts(self) -> None:
        counts = topic_counts(_four_plus_one())
        self.assertEqual(counts["Bayesian Inference"], 4)
        self.assertEqual(counts["Naive Bayes"], 1)


if __name__ == "__main__":
    unittest.main()
