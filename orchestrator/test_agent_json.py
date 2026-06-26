#!/usr/bin/env python3
"""Tests for lib/agent_json.py teacher recovery."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.agent_json import (  # noqa: E402
    find_teacher_sidecar_path,
    is_valid_teacher_payload,
    load_teacher_response,
    recover_teacher_json,
)


def _sample_teacher() -> dict:
    md = "# [Bayesian Inference] Test?\n\n" + ("word " * 600)
    return {
        "date": "2026-06-26",
        "night_thread": "thread",
        "index_md": "# Daily\n",
        "lessons": [
            {
                "slot": i,
                "slug": f"lesson-{i}",
                "topic_label": "Bayesian Inference",
                "title": f"[Bayesian Inference] Q{i}?",
                "estimated_minutes": 15,
                "word_count": 1800,
                "markdown": md,
            }
            for i in range(1, 6)
        ],
    }


class AgentJsonTests(unittest.TestCase):
    def test_valid_teacher_payload(self) -> None:
        self.assertTrue(is_valid_teacher_payload(_sample_teacher()))

    def test_rejects_stub_lessons(self) -> None:
        stub = {"date": "2026-06-26", "index_md": "# x", "lessons": ["... see file ..."]}
        self.assertFalse(is_valid_teacher_payload(stub))

    def test_recovers_from_sidecar_pointer(self) -> None:
        payload = _sample_teacher()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sidecar = root / ".teacher-output-2026-06-26.json"
            sidecar.write_text(json.dumps(payload), encoding="utf-8")
            raw = f"Full output is in `{sidecar.name}` (60KB). Pasting would exceed the limit."
            found = find_teacher_sidecar_path(raw, root=root)
            self.assertEqual(found, sidecar)
            recovered = recover_teacher_json(raw, {"lessons": ["stub"]}, root=root)
            self.assertEqual(len(recovered["lessons"]), 5)

    def test_recovers_with_date_mismatch(self) -> None:
        payload = _sample_teacher()
        payload["date"] = "2026-06-27"
        recovered = recover_teacher_json("", payload, report_date="2026-06-26")
        self.assertEqual(recovered["date"], "2026-06-26")
        self.assertEqual(len(recovered["lessons"]), 5)

    def test_raises_with_clear_validation_message(self) -> None:
        bad = _sample_teacher()
        bad["lessons"][0]["markdown"] = "too short"
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as ctx:
                recover_teacher_json("", bad, report_date="2026-06-26", root=Path(tmp))
            self.assertIn("markdown too short", str(ctx.exception))

    def test_recovers_from_prose_sidecar_pointer(self) -> None:
        payload = _sample_teacher()
        raw = (
            "The full teacher JSON (66,798 bytes, validated) is in "
            "`.teacher-output-2026-06-26.json`. Word counts: 1743, 2136.\n\n"
            "The response is too large to embed inline here (~67k characters)."
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sidecar = root / ".teacher-output-2026-06-26.json"
            sidecar.write_text(json.dumps(payload), encoding="utf-8")
            recovered = recover_teacher_json(raw, None, report_date="2026-06-26", root=root)
            self.assertEqual(len(recovered["lessons"]), 5)

    def test_recovers_from_absolute_path_in_prose(self) -> None:
        payload = _sample_teacher()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sidecar = root / ".teacher_output.json"
            sidecar.write_text(json.dumps(payload), encoding="utf-8")
            raw = f"Run: cat {sidecar}\nToo large to embed inline."
            recovered = recover_teacher_json(raw, None, report_date="2026-06-26", root=root)
            self.assertEqual(recovered["date"], "2026-06-26")

    def test_standard_sidecar_without_prose_markers(self) -> None:
        payload = _sample_teacher()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sidecar = root / ".teacher_output.json"
            sidecar.write_text(json.dumps(payload), encoding="utf-8")
            recovered = load_teacher_response(
                "Summary only — no paths in prose.",
                report_date="2026-06-26",
                root=root,
            )
            self.assertEqual(len(recovered["lessons"]), 5)

    def test_editor_recovers_from_prose_sidecar(self) -> None:
        md = "# Lesson\n\n" + ("word " * 600)
        payload = {
            "date": "2026-06-26",
            "index_md": "# Daily\n",
            "lessons": [
                {
                    "slot": i,
                    "slug": f"lesson-{i}",
                    "markdown": md,
                    "word_count": 1800,
                    "style_pass": True,
                    "style_violations": [],
                }
                for i in range(1, 6)
            ],
            "review_summary": {"all_pass": True, "notes": "ok", "graph_ready_for_grapher": True},
        }
        raw = (
            "Validated editor output is in `.editor-output-2026-06-26.json`. "
            "Lessons array is ~62KB — too large to embed inline."
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sidecar = root / ".editor-output-2026-06-26.json"
            sidecar.write_text(json.dumps(payload), encoding="utf-8")
            from lib.agent_json import load_editor_response

            recovered = load_editor_response(raw, report_date="2026-06-26", root=root)
            self.assertEqual(len(recovered["lessons"]), 5)

    def test_accepts_two_lesson_consolidated_payload(self) -> None:
        base = _sample_teacher()
        base["lessons"] = base["lessons"][:2]
        base["lessons"][0]["slot"] = 1
        base["lessons"][1]["slot"] = 2
        self.assertTrue(is_valid_teacher_payload(base))

    def test_recovers_two_lesson_sidecar(self) -> None:
        payload = _sample_teacher()
        payload["lessons"] = payload["lessons"][:2]
        payload["lessons"][0]["slot"] = 1
        payload["lessons"][1]["slot"] = 2
        raw = "Full output is in `.teacher-output-2026-06-26.json`."
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sidecar = root / ".teacher-output-2026-06-26.json"
            sidecar.write_text(json.dumps(payload), encoding="utf-8")
            recovered = load_teacher_response(raw, report_date="2026-06-26", root=root)
            self.assertEqual(len(recovered["lessons"]), 2)

    def test_consolidator_recovers_from_dated_sidecar(self) -> None:
        payload = {
            "date": "2026-06-26",
            "phase": "plan",
            "published_lesson_count": 2,
            "lesson_groups": [
                {"publish_slot": 1, "source_slots": [1, 2], "topic_label": "A"},
                {"publish_slot": 2, "source_slots": [3], "topic_label": "B"},
            ],
            "review_summary": {"pass": True, "escalate_to": [], "rationale": "ok"},
        }
        raw = "Full consolidator JSON is in `.consolidator-output-2026-06-26.json`."
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sidecar = root / ".consolidator-output-2026-06-26.json"
            sidecar.write_text(json.dumps(payload), encoding="utf-8")
            from lib.agent_json import load_consolidator_response

            recovered = load_consolidator_response(raw, report_date="2026-06-26", root=root)
            self.assertEqual(recovered["phase"], "plan")
            self.assertEqual(recovered["published_lesson_count"], 2)

    def test_consolidator_recovers_legacy_undated_sidecar(self) -> None:
        payload = {
            "date": "2026-06-26",
            "phase": "draft_review",
            "review_summary": {"pass": False, "escalate_to": ["teacher"], "rationale": "fix"},
            "group_assessments": [{"publish_slot": 1, "pass": False, "issues": ["stitched"]}],
        }
        raw = "Output is in `.consolidator-output.json` — too large to embed."
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sidecar = root / ".consolidator-output.json"
            sidecar.write_text(json.dumps(payload), encoding="utf-8")
            from lib.agent_json import load_consolidator_response

            recovered = load_consolidator_response(raw, report_date="2026-06-26", root=root)
            self.assertEqual(recovered["phase"], "draft_review")

    def test_raises_without_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                recover_teacher_json("no json here", {"lessons": ["stub"]}, root=Path(tmp))


if __name__ == "__main__":
    unittest.main()
