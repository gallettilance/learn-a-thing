"""Prerequisite-aware conservative learning gate.

When the curator plans a concept/topic that requires an unmastered prerequisite,
resolve_teaching_target() recurses up the prerequisite graph until it reaches a
frontier where every dependency is already mastered (or the concept has no prereqs).
Only that frontier concept/topic should be taught tonight.

Conservative default: a concept is NOT mastered unless explicitly present in
mastered-topics.yaml (user confirmed), seeded_topics in profile.yaml, or
concept-mastery.yaml.  blind_spots are always unmastered.  true_beginner_topics
always need gentle intro (but may still be taught if their own prereqs are met).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LEARNER = ROOT / "learner"
CURRICULUM = ROOT / "curriculum"

CONCEPT_MASTERY_PATH = LEARNER / "concept-mastery.yaml"
PROFILE_PATH = LEARNER / "profile.yaml"
MASTERED_TOPICS_PATH = LEARNER / "mastered-topics.yaml"
CONCEPT_GRAPH_PATH = CURRICULUM / "concept-graph.yaml"

# Guard against infinite loops in malformed graphs
_MAX_RECURSION = 20


def load_assumed_foundations(
    profile: dict[str, Any] | None = None,
) -> tuple[set[str], set[str]]:
    """Return (concept_ids, topic_labels) always treated as mastered for gating."""
    if profile is None:
        profile = _load_yaml(PROFILE_PATH)
    block = profile.get("assumed_foundations") or {}
    concepts: set[str] = set()
    topics: set[str] = set()
    for cid in block.get("concepts") or []:
        label = str(cid).strip()
        if label:
            concepts.add(label)
    for t in block.get("topics") or []:
        label = str(t).strip()
        if label:
            topics.add(label)
    return concepts, topics


def _is_foundation(
    concept_id: str | None,
    topic_label: str | None,
    *,
    foundation_concepts: set[str],
    foundation_topics: set[str],
) -> bool:
    if concept_id and concept_id in foundation_concepts:
        return True
    if topic_label and topic_label in foundation_topics:
        return True
    return False


def _load_yaml(path: Path) -> Any:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


# ---------------------------------------------------------------------------
# Edge loading
# ---------------------------------------------------------------------------


def load_prerequisite_edges(
    graph: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return all edges with edge_type == 'prerequisite' from concept-graph.yaml."""
    if graph is None:
        graph = _load_yaml(CONCEPT_GRAPH_PATH)

    prereq_edges: list[dict[str, Any]] = []
    for edge in graph.get("seed_edges") or []:
        if isinstance(edge, dict) and edge.get("edge_type") == "prerequisite":
            prereq_edges.append(edge)
    return prereq_edges


# ---------------------------------------------------------------------------
# Mastery queries
# ---------------------------------------------------------------------------


def get_mastered_topics(
    *,
    profile: dict[str, Any] | None = None,
    mastered_entries: dict[str, Any] | None = None,
) -> set[str]:
    """Return topic labels the learner has confirmed mastery of.

    Sources (in order):
    - profile.seeded_topics  (already-taught topics)
    - mastered-topics.yaml topics where mastered=True
    Exclusions:
    - mastered-topics.yaml topics where mastered=False (explicitly reopened)
    - profile.blind_spots (always unmastered regardless of other flags)
    """
    if profile is None:
        profile = _load_yaml(PROFILE_PATH)

    mastered: set[str] = set()

    # Seeded topics are considered mastered at topic level
    for t in profile.get("seeded_topics") or []:
        label = str(t).strip()
        if label:
            mastered.add(label)

    # User-confirmed mastery from mastered-topics.yaml
    if mastered_entries is None:
        raw = _load_yaml(MASTERED_TOPICS_PATH)
        mastered_entries = raw.get("topics") or {}

    for label, entry in mastered_entries.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("mastered") is True:
            mastered.add(str(label).strip())
        elif entry.get("mastered") is False:
            mastered.discard(str(label).strip())

    # Blind spots are NEVER mastered — remove any that slipped in
    for spot in profile.get("blind_spots") or []:
        spot_label = str(spot).strip()
        # Blind spots are free-text; do a case-insensitive containment check
        to_remove = {m for m in mastered if spot_label.lower() in m.lower()}
        mastered -= to_remove

    return mastered


def get_mastered_concepts(
    *,
    concept_mastery: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
) -> set[str]:
    """Return concept IDs the learner has mastered (user-confirmed + assumed foundations).

    Topic-level mastery does NOT imply concept mastery — only explicit concept
    entries and assumed_foundations count here.
    """
    if profile is None:
        profile = _load_yaml(PROFILE_PATH)

    foundation_concepts, _ = load_assumed_foundations(profile)
    mastered: set[str] = set(foundation_concepts)

    if concept_mastery is None:
        raw = _load_yaml(CONCEPT_MASTERY_PATH)
        concept_mastery = raw.get("concepts") or {}

    for cid, entry in concept_mastery.items():
        if isinstance(entry, dict) and entry.get("mastered") is True:
            mastered.add(str(cid).strip())
        elif isinstance(entry, dict) and entry.get("mastered") is False:
            mastered.discard(str(cid).strip())

    return mastered


def get_mastered_topics_for_gate(
    *,
    profile: dict[str, Any] | None = None,
    mastered_entries: dict[str, Any] | None = None,
) -> set[str]:
    """Topics mastered for gate purposes (includes assumed foundation topics)."""
    _, foundation_topics = load_assumed_foundations(profile)
    topics = get_mastered_topics(profile=profile, mastered_entries=mastered_entries)
    return topics | foundation_topics


def is_concept_mastered(
    concept_id: str,
    *,
    mastered_concepts: set[str] | None = None,
    mastered_topics: set[str] | None = None,
    prereq_edges: list[dict[str, Any]] | None = None,
) -> bool:
    """Check if a specific concept is mastered for prerequisite gating."""
    cid = str(concept_id or "").strip()
    if not cid:
        return False

    if mastered_concepts is None:
        mastered_concepts = get_mastered_concepts()

    return cid in mastered_concepts


def is_topic_mastered_gate(
    topic_label: str,
    *,
    mastered_topics: set[str] | None = None,
) -> bool:
    """Check if a topic is mastered (gate variant — does not load profile itself)."""
    label = str(topic_label or "").strip()
    if not label:
        return False
    if mastered_topics is None:
        mastered_topics = get_mastered_topics()
    return label in mastered_topics


# ---------------------------------------------------------------------------
# Prerequisite traversal
# ---------------------------------------------------------------------------


def find_unmastered_prerequisites(
    target_concept: str | None,
    target_topic: str | None,
    prereq_edges: list[dict[str, Any]],
    *,
    mastered_concepts: set[str],
    mastered_topics: set[str],
    foundation_concepts: set[str] | None = None,
    foundation_topics: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return direct prerequisite edges for target whose source is NOT yet mastered.

    Each returned edge is a raw dict from concept-graph.yaml with at minimum
    from_concept/from_topic and to_concept/to_topic fields.
    """
    if foundation_concepts is None:
        foundation_concepts, foundation_topics = load_assumed_foundations()
    if foundation_topics is None:
        _, foundation_topics = load_assumed_foundations()

    unmastered: list[dict[str, Any]] = []

    for edge in prereq_edges:
        # Match by concept first, then by topic
        to_concept = str(edge.get("to_concept") or "").strip()
        to_topic = str(edge.get("to_topic") or "").strip()
        from_concept = str(edge.get("from_concept") or "").strip()
        from_topic = str(edge.get("from_topic") or "").strip()

        matches = False
        if to_concept:
            # Concept-specific edge: match only when caller's concept matches exactly.
            # A different concept in the same topic does NOT trigger this edge.
            matches = target_concept is not None and target_concept == to_concept
        elif to_topic:
            # Topic-level edge (no to_concept): fires for any lesson in that topic.
            matches = target_topic is not None and target_topic == to_topic

        if not matches:
            continue

        # Foundation floor — never block on assumed basics
        if _is_foundation(from_concept or None, from_topic or None, foundation_concepts=foundation_concepts, foundation_topics=foundation_topics):
            continue

        # Check if the prerequisite (from_*) is already mastered
        prereq_mastered = False
        if from_concept:
            if from_concept in mastered_concepts:
                prereq_mastered = True
            # Whole-topic claim unlocks all concepts in that topic for this edge
            elif from_topic and from_topic in mastered_topics:
                prereq_mastered = True
        elif from_topic and from_topic in mastered_topics:
            prereq_mastered = True

        if not prereq_mastered:
            unmastered.append(edge)

    return unmastered


@dataclass
class GateResult:
    """Result of resolve_teaching_target()."""

    original_concept: str | None
    original_topic: str | None
    effective_concept: str | None
    effective_topic: str | None
    blocked_chain: list[str] = field(default_factory=list)
    ready: bool = True

    def deferred(self) -> bool:
        return not self.ready

    def summary(self) -> str:
        if self.ready:
            orig = self.original_concept or self.original_topic or ""
            return f"Ready to teach: {orig}"
        orig = self.original_concept or self.original_topic or ""
        eff = self.effective_concept or self.effective_topic or ""
        chain = " → ".join(self.blocked_chain)
        return f"Deferred: {orig} blocked by [{chain}] → teach {eff} tonight"


def resolve_teaching_target(
    planned_concept: str | None,
    planned_topic: str | None,
    prereq_edges: list[dict[str, Any]],
    *,
    mastered_concepts: set[str],
    mastered_topics: set[str],
    _depth: int = 0,
    _visited: frozenset[tuple[str | None, str | None]] | None = None,
    foundation_concepts: set[str] | None = None,
    foundation_topics: set[str] | None = None,
) -> GateResult:
    """Recursively walk prerequisites until we reach a teachable frontier.

    Stops when:
    - All direct prerequisites are mastered (or absent from the graph).
    - The target hits assumed_foundations (basic math, literacy, etc.).
    - A cycle is detected in the prerequisite graph.
    - _MAX_RECURSION depth is exceeded (malformed graph safety valve).
    """
    if foundation_concepts is None or foundation_topics is None:
        foundation_concepts, foundation_topics = load_assumed_foundations()

    key = (planned_concept, planned_topic)
    visited = _visited or frozenset()
    if key in visited:
        raise RuntimeError(
            f"Prerequisite cycle detected at concept={planned_concept!r} topic={planned_topic!r}"
        )

    if _is_foundation(planned_concept, planned_topic, foundation_concepts=foundation_concepts, foundation_topics=foundation_topics):
        return GateResult(
            original_concept=planned_concept,
            original_topic=planned_topic,
            effective_concept=planned_concept,
            effective_topic=planned_topic,
            blocked_chain=[],
            ready=True,
        )

    if _depth > _MAX_RECURSION:
        raise RuntimeError(
            f"Prerequisite chain exceeded depth {_MAX_RECURSION} at "
            f"concept={planned_concept!r} topic={planned_topic!r} — check concept-graph for cycles"
        )

    unmastered = find_unmastered_prerequisites(
        planned_concept,
        planned_topic,
        prereq_edges,
        mastered_concepts=mastered_concepts,
        mastered_topics=mastered_topics,
        foundation_concepts=foundation_concepts,
        foundation_topics=foundation_topics,
    )

    if not unmastered:
        # All prerequisites satisfied — this concept/topic is teachable
        return GateResult(
            original_concept=planned_concept,
            original_topic=planned_topic,
            effective_concept=planned_concept,
            effective_topic=planned_topic,
            blocked_chain=[],
            ready=True,
        )

    # Pick the first blocking prerequisite and recurse
    blocking_edge = unmastered[0]
    prereq_concept = str(blocking_edge.get("from_concept") or "").strip() or None
    prereq_topic = str(blocking_edge.get("from_topic") or "").strip() or None

    # Recurse into the prerequisite
    child = resolve_teaching_target(
        prereq_concept,
        prereq_topic,
        prereq_edges,
        mastered_concepts=mastered_concepts,
        mastered_topics=mastered_topics,
        _depth=_depth + 1,
        _visited=visited | {key},
        foundation_concepts=foundation_concepts,
        foundation_topics=foundation_topics,
    )

    # Build the blocked chain: current target is blocked by its prereq chain
    current_label = planned_concept or planned_topic or ""
    child_blocked = child.blocked_chain or []

    if child.ready:
        # The prereq itself has no further blockers — chain ends here
        prereq_label = prereq_concept or prereq_topic or ""
        blocked_chain = [current_label, prereq_label]
    else:
        # Deeper chain: propagate
        blocked_chain = [current_label] + child_blocked

    return GateResult(
        original_concept=planned_concept,
        original_topic=planned_topic,
        effective_concept=child.effective_concept,
        effective_topic=child.effective_topic,
        blocked_chain=blocked_chain,
        ready=False,
    )


# ---------------------------------------------------------------------------
# MasteredState helper
# ---------------------------------------------------------------------------


@dataclass
class MasteredState:
    """Snapshot of what the learner has mastered at gate-check time."""

    topics: set[str]
    concepts: set[str]
    prereq_edges: list[dict[str, Any]]
    foundation_concepts: set[str] = field(default_factory=set)
    foundation_topics: set[str] = field(default_factory=set)

    @classmethod
    def load(cls) -> "MasteredState":
        profile = _load_yaml(PROFILE_PATH)
        graph = _load_yaml(CONCEPT_GRAPH_PATH)
        edges = load_prerequisite_edges(graph)
        foundation_concepts, foundation_topics = load_assumed_foundations(profile)
        return cls(
            topics=get_mastered_topics_for_gate(profile=profile),
            concepts=get_mastered_concepts(profile=profile),
            prereq_edges=edges,
            foundation_concepts=foundation_concepts,
            foundation_topics=foundation_topics,
        )


# ---------------------------------------------------------------------------
# Curator plan gating
# ---------------------------------------------------------------------------


@dataclass
class SlotGateResult:
    slot: int
    concept: str | None
    topic: str | None
    gate: GateResult


@dataclass
class PlanGateResult:
    """Result of gate_curator_plan()."""

    slots: list[SlotGateResult] = field(default_factory=list)

    @property
    def all_ready(self) -> bool:
        return all(s.gate.ready for s in self.slots)

    @property
    def blocked_slots(self) -> list[SlotGateResult]:
        return [s for s in self.slots if not s.gate.ready]

    def summary(self) -> str:
        if self.all_ready:
            return "All planned concepts/topics are prerequisite-gated and ready."
        lines = ["Prerequisite gate blocked the following slots:"]
        for s in self.blocked_slots:
            lines.append(f"  slot {s.slot}: {s.gate.summary()}")
        return "\n".join(lines)

    def replan_suggestion(self) -> dict[str, Any]:
        """Return a dict describing the recommended plan adjustment."""
        if self.all_ready:
            return {"action": "proceed"}

        first = self.blocked_slots[0]
        return {
            "action": "defer",
            "blocked_concept": first.gate.original_concept,
            "blocked_topic": first.gate.original_topic,
            "effective_concept": first.gate.effective_concept,
            "effective_topic": first.gate.effective_topic,
            "blocked_chain": first.gate.blocked_chain,
            "message": first.gate.summary(),
        }


def gate_curator_plan(
    curator: dict[str, Any],
    mastered_state: MasteredState | None = None,
) -> PlanGateResult:
    """Check all planned lesson concepts/topics against prerequisite graph.

    For each lesson slot, run resolve_teaching_target(). Return a PlanGateResult
    describing which slots are ready and which need deferral.
    """
    if mastered_state is None:
        mastered_state = MasteredState.load()

    lessons = curator.get("lessons") or []
    results: list[SlotGateResult] = []

    for lesson in lessons:
        slot = int(lesson.get("slot") or 0)
        concept = str(lesson.get("concept") or "").strip() or None
        topic = str(lesson.get("topic_label") or "").strip() or None

        gate = resolve_teaching_target(
            concept,
            topic,
            mastered_state.prereq_edges,
            mastered_concepts=mastered_state.concepts,
            mastered_topics=mastered_state.topics,
            foundation_concepts=mastered_state.foundation_concepts,
            foundation_topics=mastered_state.foundation_topics,
        )
        results.append(SlotGateResult(slot=slot, concept=concept, topic=topic, gate=gate))

    return PlanGateResult(slots=results)


# ---------------------------------------------------------------------------
# Convenience: check_prerequisite_closure
# ---------------------------------------------------------------------------


def check_prerequisite_closure(
    curator: dict[str, Any],
    mastered_state: MasteredState | None = None,
) -> tuple[bool, str]:
    """Return (ok, message) — pass gate for orchestrator validation hook.

    Returns True when all planned concepts/topics have their prerequisites met.
    """
    result = gate_curator_plan(curator, mastered_state)
    return result.all_ready, result.summary()
