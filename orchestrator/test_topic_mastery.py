#!/usr/bin/env python3
"""Unit tests for topic mastery."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.topic_mastery import (  # noqa: E402
    all_mastered_labels,
    is_topic_mastered,
    set_topic_mastered,
)


class TopicMasteryTests(unittest.TestCase):
    def test_seeded_topic_is_mastered(self) -> None:
        profile = {"seeded_topics": ["Naive Bayes", "KNN"]}
        self.assertTrue(is_topic_mastered("Naive Bayes", profile=profile))
        self.assertFalse(is_topic_mastered("Monte Carlo", profile=profile))

    def test_user_mark_and_unmark(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            learner = Path(tmp) / "learner"
            learner.mkdir()
            mastered_path = learner / "mastered-topics.yaml"
            profile_path = learner / "profile.yaml"
            profile_path.write_text("seeded_topics: []\n", encoding="utf-8")

            with patch("lib.topic_mastery.MASTERED_PATH", mastered_path), patch(
                "lib.topic_mastery.LEARNER", learner
            ), patch("lib.topic_mastery.load_profile", return_value={"seeded_topics": []}):
                set_topic_mastered("Monte Carlo", True)
                self.assertTrue(is_topic_mastered("Monte Carlo"))
                set_topic_mastered("Monte Carlo", False)
                self.assertFalse(is_topic_mastered("Monte Carlo"))

    def test_all_mastered_merges_seeded_and_user(self) -> None:
        profile = {"seeded_topics": ["KNN"]}
        with patch(
            "lib.topic_mastery.load_mastery_entries",
            return_value={"Monte Carlo": {"mastered": True}},
        ):
            labels = all_mastered_labels(profile=profile)
        self.assertIn("KNN", labels)
        self.assertIn("Monte Carlo", labels)


if __name__ == "__main__":
    unittest.main()
