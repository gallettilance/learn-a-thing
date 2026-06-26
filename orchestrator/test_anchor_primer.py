#!/usr/bin/env python3
"""Tests for lib/anchor_primer.py"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.anchor_primer import format_anchor_for_agents, get_anchor_primer, html_reference_panel  # noqa: E402


class AnchorPrimerTests(unittest.TestCase):
    def test_primer_loads(self) -> None:
        p = get_anchor_primer("spam-filter-bayes")
        self.assertEqual(p.get("id"), "spam-filter-bayes")
        self.assertIn("TF-IDF", format_anchor_for_agents("spam-filter-bayes"))

    def test_html_panel(self) -> None:
        html = html_reference_panel("spam-filter-bayes", report_date="2026-06-26", narrative_day=4)
        self.assertIn("anchor-ref-panel", html)
        self.assertIn("148", html)


if __name__ == "__main__":
    unittest.main()
