"""Tests for lib/spine_state.py"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.spine_state import (  # noqa: E402
    exploration_bridge_for_domain,
    format_spine_context,
    get_active_phase,
    get_phase_by_id,
    load_master_spine,
    sync_spine_progress,
)


def test_load_master_spine_has_phases():
    spine = load_master_spine()
    assert spine.get("phases")
    assert len(spine["phases"]) >= 5


def test_active_phase_is_inference():
    spine = load_master_spine()
    active = get_active_phase(spine)
    assert active.get("id") == "phase-inference"
    assert active.get("status") == "active"


def test_get_phase_by_id():
    phase = get_phase_by_id("phase-dynamics")
    assert phase is not None
    assert "Stochastic Processes" in (phase.get("curriculum_topics") or [])


def test_exploration_bridge_for_domain():
    bridge = exploration_bridge_for_domain("quantum computing")
    assert bridge is not None
    assert bridge.get("home_invariant") == "inv-basis"


def test_sync_spine_progress_writes_file():
    progress = sync_spine_progress()
    assert progress.get("active_phase_id") == "phase-inference"
    path = ROOT / "learner" / "spine-progress.yaml"
    assert path.exists()
    assert "phase-inference" in path.read_text(encoding="utf-8")


def test_format_spine_context_includes_active_phase():
    sync_spine_progress()
    text = format_spine_context()
    assert "phase-inference" in text
    assert "inv-calibration" in text
