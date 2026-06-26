#!/usr/bin/env python3
"""Unit tests for lesson chat persistence."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.lesson_chat import (  # noqa: E402
    append_message,
    format_for_editor,
    get_thread,
    thread_key,
)


class LessonChatTests(unittest.TestCase):
    def test_thread_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chat_path = Path(tmp) / "lesson-chat.yaml"
            with patch("lib.lesson_chat.CHAT_PATH", chat_path):
                append_message("2026-06-28", "lesson-01", role="user", content="Why calibration?", topic_label="Bayes")
                thread = get_thread("2026-06-28", "lesson-01")
                self.assertEqual(len(thread), 1)
                self.assertEqual(thread[0]["content"], "Why calibration?")
                self.assertEqual(thread[0]["topic_label"], "Bayes")

    def test_format_for_editor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chat_path = Path(tmp) / "lesson-chat.yaml"
            with patch("lib.lesson_chat.CHAT_PATH", chat_path):
                append_message("2026-06-28", "lesson-02", role="user", content="What is a posterior?", topic_label="Bayesian Inference")
                text = format_for_editor()
                self.assertIn("posterior", text)
                self.assertIn(thread_key("2026-06-28", "lesson-02"), text)


if __name__ == "__main__":
    unittest.main()
