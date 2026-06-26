#!/usr/bin/env python3
"""Unit tests for extract_json in nightly.py."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "orchestrator"))

from nightly import extract_json  # noqa: E402


class ExtractJsonTests(unittest.TestCase):
    def test_bare_json(self) -> None:
        payload = {"date": "2026-06-26", "lessons": []}
        self.assertEqual(extract_json(json.dumps(payload)), payload)

    def test_json_markdown_fence(self) -> None:
        payload = {"date": "2026-06-26", "night_thread": "thread"}
        text = f"```json\n{json.dumps(payload)}\n```"
        self.assertEqual(extract_json(text), payload)

    def test_prose_then_json(self) -> None:
        payload = {"date": "2026-06-26", "slot": 1}
        text = f"Here is the teacher output you requested:\n\n{json.dumps(payload)}\n\nDone."
        self.assertEqual(extract_json(text), payload)

    def test_prose_and_fenced_json(self) -> None:
        payload = {"date": "2026-06-26", "index_md": "# Daily"}
        text = f"Output below:\n\n```json\n{json.dumps(payload)}\n```\n"
        self.assertEqual(extract_json(text), payload)

    def test_json_with_embedded_markdown_fences_in_string(self) -> None:
        payload = {
            "date": "2026-06-26",
            "lessons": [
                {
                    "slot": 1,
                    "markdown": "# Title\n\n```\ncode block\n```\n",
                }
            ],
        }
        text = json.dumps(payload)
        self.assertEqual(extract_json(text), payload)

    def test_truncated_json_repair(self) -> None:
        payload = {"date": "2026-06-26", "lessons": [{"slot": 1, "title": "x"}]}
        # Agent stopped before closing braces (not mid-string).
        truncated = json.dumps(payload)[:-3]
        result = extract_json(truncated)
        self.assertEqual(result["date"], "2026-06-26")
        self.assertEqual(len(result["lessons"]), 1)

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            extract_json("   ")

    def test_invalid_input_raises(self) -> None:
        with self.assertRaises(ValueError):
            extract_json("This is prose only with no JSON structure.")
        with self.assertRaises(ValueError):
            extract_json("```json\n{not valid json}\n```")


if __name__ == "__main__":
    unittest.main()
