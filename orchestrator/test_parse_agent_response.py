#!/usr/bin/env python3
"""Tests for parse_agent_response (teacher sidecar before retry)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "orchestrator"))
sys.path.insert(0, str(ROOT))


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


class ParseAgentResponseTests(unittest.TestCase):
    def test_teacher_prose_sidecar_skips_retry_path(self) -> None:
        from nightly import parse_agent_response  # noqa: E402

        payload = _sample_teacher()
        raw = (
            "Validated JSON is in `.teacher-output-2026-06-26.json`. "
            "Too large to embed inline."
        )
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / ".teacher-output-2026-06-26.json"
            sidecar.write_text(json.dumps(payload), encoding="utf-8")
            from lib.agent_json import load_agent_response
            from nightly import extract_json  # noqa: E402

            result = load_agent_response(
                "teacher",
                raw,
                report_date="2026-06-26",
                root=Path(tmp),
                extract_json_fn=extract_json,
            )
            self.assertEqual(len(result["lessons"]), 5)

    def test_editor_prose_sidecar(self) -> None:
        from nightly import parse_agent_response  # noqa: E402
        from pathlib import Path

        raw_path = ROOT / "pipeline" / "2026-06-26" / "iter-00" / "editor-raw.txt"
        if not raw_path.is_file():
            self.skipTest("no saved editor-raw.txt")
        raw = raw_path.read_text(encoding="utf-8")
        sidecar = ROOT / ".editor-output-2026-06-26.json"
        if not sidecar.is_file():
            self.skipTest("no editor sidecar on disk")
        result = parse_agent_response("editor", raw, report_date="2026-06-26")
        self.assertEqual(len(result["lessons"]), 5)

    def test_non_teacher_still_requires_inline_json(self) -> None:
        from nightly import parse_agent_response  # noqa: E402

        with self.assertRaises(ValueError):
            parse_agent_response("curator", "prose only, no json")


if __name__ == "__main__":
    unittest.main()
