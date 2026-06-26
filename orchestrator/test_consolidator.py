#!/usr/bin/env python3
"""Tests for consolidator agent integration."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.consolidator import (  # noqa: E402
    apply_consolidator_output,
    escalation_targets,
    review_passes,
    save_consolidator,
)


class TestConsolidatorApply(unittest.TestCase):
    def test_apply_agent_groups(self) -> None:
        curator = {"lessons": [{"slot": 1, "topic_label": "A", "concept": "c1"}]}
        out = {
            "phase": "plan",
            "lesson_groups": [
                {
                    "publish_slot": 1,
                    "topic_label": "A",
                    "source_slots": [1, 2],
                    "concepts": ["c1", "c2"],
                    "narrative_spine": "One arc",
                },
                {
                    "publish_slot": 2,
                    "topic_label": "B",
                    "source_slots": [3],
                    "concepts": ["c3"],
                    "narrative_spine": "Bridge",
                },
            ],
            "review_summary": {"pass": True, "escalate_to": [], "rationale": "ok"},
        }
        merged = apply_consolidator_output(curator, out)
        self.assertEqual(merged["published_lesson_count"], 2)
        self.assertTrue(merged["lesson_groups"][0]["merged"])

    def test_review_passes_blocks_on_escalation(self) -> None:
        out = {"review_summary": {"pass": True, "escalate_to": ["teacher"]}}
        self.assertFalse(review_passes(out))
        self.assertIn("teacher", escalation_targets(out))

    def test_save_consolidator_writes_dated_root_sidecar(self) -> None:
        import tempfile

        payload = {
            "date": "2026-06-26",
            "phase": "plan",
            "lesson_groups": [],
            "review_summary": {"pass": True, "escalate_to": [], "rationale": "ok"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pipe = root / "pipeline" / "2026-06-26"
            legacy = root / ".consolidator-output.json"
            legacy.write_text("{}", encoding="utf-8")
            import lib.consolidator as cons_mod

            original_root = cons_mod.ROOT
            cons_mod.ROOT = root
            try:
                save_consolidator(pipe / "consolidator-plan.json", payload, "plan")
            finally:
                cons_mod.ROOT = original_root
            dated = root / ".consolidator-output-2026-06-26.json"
            self.assertTrue(dated.is_file())
            self.assertFalse(legacy.is_file())


if __name__ == "__main__":
    unittest.main()
