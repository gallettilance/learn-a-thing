#!/usr/bin/env python3
"""Unit tests for active learner state sync."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import active_state as ast  # noqa: E402


class ActiveStateTests(unittest.TestCase):
    def test_seed_hypothesis_always_active(self) -> None:
        entry = {
            "id": "H-003",
            "source": "prior-teaching/logistic-regression",
            "evidence": ["prior-teaching/logistic-regression"],
            "topic_label": "Logistic Regression",
        }
        self.assertTrue(ast.is_seed_hypothesis(entry))
        active = ast.filter_active_hypotheses(
            [entry],
            read_keys=set(),
            valid_dates=set(),
        )
        self.assertEqual(len(active), 1)

    def test_pipeline_hypothesis_requires_read_evidence(self) -> None:
        entry = {
            "id": "H-001",
            "evidence": ["2026-06-26-lesson-01"],
        }
        self.assertFalse(ast.is_seed_hypothesis(entry))
        inactive = ast.filter_active_hypotheses(
            [entry],
            read_keys=set(),
            valid_dates={"2026-06-26"},
        )
        self.assertEqual(len(inactive), 0)
        active = ast.filter_active_hypotheses(
            [entry],
            read_keys={"2026-06-26::lesson-01"},
            valid_dates={"2026-06-26"},
        )
        self.assertEqual(len(active), 1)

    def test_graph_filters_edges_by_active_topics(self) -> None:
        topics = {"Bayesian Inference", "Logistic Regression"}
        edges = [
            {"from_topic": "Bayesian Inference", "to_topic": "Logistic Regression", "id": "E-1"},
            {"from_topic": "Bayesian Inference", "to_topic": "Quantum Physics", "id": "E-2"},
        ]
        filtered = ast.filter_graph_edges(edges, topics)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["id"], "E-1")

    def test_sync_prunes_when_report_gone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            learner = root / "learner"
            reports = root / "reports"
            curriculum = root / "curriculum"
            learner.mkdir()
            reports.mkdir()
            curriculum.mkdir()

            hyp_path = learner / "hypotheses.jsonl"
            hyp_path.write_text(
                json.dumps({"id": "H-900", "evidence": ["2099-01-01-lesson-01"]}) + "\n"
                + json.dumps(
                    {
                        "id": "H-003",
                        "source": "prior-teaching/x",
                        "evidence": ["prior-teaching/x"],
                        "topic_label": "Logistic Regression",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (curriculum / "concept-graph.yaml").write_text(
                "invariants: []\nseed_edges: []\n",
                encoding="utf-8",
            )
            (learner / "engagement.yaml").write_text("{}", encoding="utf-8")

            with mock.patch.object(ast, "ROOT", root), mock.patch.object(
                ast, "LEARNER", learner
            ), mock.patch.object(ast, "REPORTS", reports), mock.patch.object(
                ast, "CURRICULUM", curriculum
            ), mock.patch.object(
                ast, "HYPOTHESES_PATH", hyp_path
            ), mock.patch.object(
                ast, "ACTIVE_STATE_PATH", learner / "active-state.yaml"
            ), mock.patch.object(
                ast, "CONCEPT_EDGES_PATH", learner / "concept-edges.jsonl"
            ), mock.patch.object(
                ast, "report_dates", return_value=[]
            ):
                state = ast.sync_learner_state(prune=True)
                remaining = ast.read_jsonl(hyp_path)
                ids = {h["id"] for h in remaining}
                self.assertIn("H-003", ids)
                self.assertNotIn("H-900", ids)
                self.assertEqual(state["stats"]["hypotheses_active"], 1)


if __name__ == "__main__":
    unittest.main()
