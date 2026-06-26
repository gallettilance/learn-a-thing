#!/usr/bin/env python3
"""Unit tests for prerequisite-aware conservative learning gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.prerequisite_gate import (  # noqa: E402
    GateResult,
    MasteredState,
    PlanGateResult,
    SlotGateResult,
    check_prerequisite_closure,
    find_unmastered_prerequisites,
    gate_curator_plan,
    get_mastered_concepts,
    get_mastered_topics,
    is_concept_mastered,
    is_topic_mastered_gate,
    load_prerequisite_edges,
    resolve_teaching_target,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MARKOV_TO_MCMC_EDGE = {
    "id": "E-markov-mcmc",
    "from_concept": "markov_chain",
    "from_topic": "Stochastic Processes",
    "to_concept": "mcmc_intuition",
    "to_topic": "Monte Carlo",
    "edge_type": "prerequisite",
}

MARKOV_TO_MCMC_DIAG_EDGE = {
    "id": "E-markov-mcmc-diag",
    "from_concept": "markov_chain",
    "from_topic": "Stochastic Processes",
    "to_concept": "mcmc_diagnostics",
    "to_topic": "Monte Carlo",
    "edge_type": "prerequisite",
}

# Transitive chain: C requires B, B requires A
A_TO_B_EDGE = {
    "id": "E-a-b",
    "from_concept": "concept_a",
    "from_topic": "Topic A",
    "to_concept": "concept_b",
    "to_topic": "Topic B",
    "edge_type": "prerequisite",
}

B_TO_C_EDGE = {
    "id": "E-b-c",
    "from_concept": "concept_b",
    "from_topic": "Topic B",
    "to_concept": "concept_c",
    "to_topic": "Topic C",
    "edge_type": "prerequisite",
}

PREREQ_EDGES = [MARKOV_TO_MCMC_EDGE, MARKOV_TO_MCMC_DIAG_EDGE, A_TO_B_EDGE, B_TO_C_EDGE]


def _state(topics: set[str], concepts: set[str] | None = None) -> MasteredState:
    return MasteredState(
        topics=topics,
        concepts=concepts or set(),
        prereq_edges=PREREQ_EDGES,
    )


def _curator_plan(concept: str, topic: str, slots: int = 5) -> dict:
    lessons = []
    for i in range(1, slots + 1):
        lessons.append({"slot": i, "concept": concept, "topic_label": topic})
    return {"night_type": "arc", "topic_label": topic, "lessons": lessons}


# ---------------------------------------------------------------------------
# load_prerequisite_edges
# ---------------------------------------------------------------------------


class TestLoadPrerequisiteEdges(unittest.TestCase):
    def test_filters_prerequisite_edge_type(self) -> None:
        graph = {
            "seed_edges": [
                {"id": "E-1", "edge_type": "prerequisite", "from_topic": "A", "to_topic": "B"},
                {"id": "E-2", "edge_type": "calibration_link", "from_topic": "C", "to_topic": "D"},
                {"id": "E-3", "edge_type": "prerequisite", "from_topic": "X", "to_topic": "Y"},
            ]
        }
        edges = load_prerequisite_edges(graph)
        self.assertEqual(len(edges), 2)
        self.assertTrue(all(e["edge_type"] == "prerequisite" for e in edges))

    def test_empty_graph_returns_empty(self) -> None:
        self.assertEqual(load_prerequisite_edges({}), [])

    def test_no_prerequisite_edges_returns_empty(self) -> None:
        graph = {"seed_edges": [{"id": "E-1", "edge_type": "generalizes"}]}
        self.assertEqual(load_prerequisite_edges(graph), [])


# ---------------------------------------------------------------------------
# get_mastered_topics
# ---------------------------------------------------------------------------


class TestGetMasteredTopics(unittest.TestCase):
    def test_seeded_topics_are_mastered(self) -> None:
        profile = {"seeded_topics": ["Naive Bayes", "KNN"], "blind_spots": []}
        with patch("lib.prerequisite_gate._load_yaml", return_value={}):
            topics = get_mastered_topics(profile=profile, mastered_entries={})
        self.assertIn("Naive Bayes", topics)
        self.assertIn("KNN", topics)

    def test_user_confirmed_mastery(self) -> None:
        profile = {"seeded_topics": [], "blind_spots": []}
        entries = {"Monte Carlo": {"mastered": True}}
        with patch("lib.prerequisite_gate._load_yaml", return_value={}):
            topics = get_mastered_topics(profile=profile, mastered_entries=entries)
        self.assertIn("Monte Carlo", topics)

    def test_explicit_unmastered_removes_seeded(self) -> None:
        profile = {"seeded_topics": ["Logistic Regression"], "blind_spots": []}
        entries = {"Logistic Regression": {"mastered": False}}
        with patch("lib.prerequisite_gate._load_yaml", return_value={}):
            topics = get_mastered_topics(profile=profile, mastered_entries=entries)
        self.assertNotIn("Logistic Regression", topics)

    def test_blind_spots_are_never_mastered(self) -> None:
        """Stochastic Processes is in blind_spots — must not appear as mastered."""
        profile = {
            "seeded_topics": [],
            "blind_spots": ["Stochastic processes (Markov structure, stationarity, ergodicity)"],
        }
        entries = {}
        with patch("lib.prerequisite_gate._load_yaml", return_value={}):
            topics = get_mastered_topics(profile=profile, mastered_entries=entries)
        self.assertNotIn("Stochastic Processes", topics)

    def test_unknown_topic_not_mastered(self) -> None:
        profile = {"seeded_topics": [], "blind_spots": []}
        with patch("lib.prerequisite_gate._load_yaml", return_value={}):
            topics = get_mastered_topics(profile=profile, mastered_entries={})
        self.assertNotIn("MCMC", topics)
        self.assertNotIn("Markov chain", topics)


# ---------------------------------------------------------------------------
# is_concept_mastered / is_topic_mastered_gate
# ---------------------------------------------------------------------------


class TestMasteryChecks(unittest.TestCase):
    def test_concept_in_mastered_set(self) -> None:
        self.assertTrue(is_concept_mastered("conjugate_pairs", mastered_concepts={"conjugate_pairs"}))

    def test_concept_not_mastered(self) -> None:
        self.assertFalse(is_concept_mastered("markov_chain", mastered_concepts=set()))

    def test_topic_mastered(self) -> None:
        self.assertTrue(is_topic_mastered_gate("Naive Bayes", mastered_topics={"Naive Bayes", "KNN"}))

    def test_topic_not_mastered(self) -> None:
        self.assertFalse(is_topic_mastered_gate("Stochastic Processes", mastered_topics={"Naive Bayes"}))

    def test_empty_concept_id_not_mastered(self) -> None:
        self.assertFalse(is_concept_mastered("", mastered_concepts={"anything"}))


# ---------------------------------------------------------------------------
# find_unmastered_prerequisites
# ---------------------------------------------------------------------------


class TestFindUnmasteredPrerequisites(unittest.TestCase):
    def test_markov_unmastered_blocks_mcmc(self) -> None:
        unmastered = find_unmastered_prerequisites(
            "mcmc_intuition",
            "Monte Carlo",
            PREREQ_EDGES,
            mastered_concepts=set(),
            mastered_topics=set(),
        )
        self.assertEqual(len(unmastered), 1)
        self.assertEqual(unmastered[0]["from_concept"], "markov_chain")

    def test_markov_mastered_unblocks_mcmc(self) -> None:
        unmastered = find_unmastered_prerequisites(
            "mcmc_intuition",
            "Monte Carlo",
            PREREQ_EDGES,
            mastered_concepts={"markov_chain"},
            mastered_topics=set(),
        )
        self.assertEqual(len(unmastered), 0)

    def test_stochastic_topic_mastered_unblocks_mcmc(self) -> None:
        unmastered = find_unmastered_prerequisites(
            "mcmc_intuition",
            "Monte Carlo",
            PREREQ_EDGES,
            mastered_concepts=set(),
            mastered_topics={"Stochastic Processes"},
        )
        self.assertEqual(len(unmastered), 0)

    def test_no_prereqs_for_unrelated_concept(self) -> None:
        unmastered = find_unmastered_prerequisites(
            "calibration",
            "Logistic Regression",
            PREREQ_EDGES,
            mastered_concepts=set(),
            mastered_topics=set(),
        )
        self.assertEqual(len(unmastered), 0)

    def test_match_by_topic_only(self) -> None:
        """Edge with no from_concept — matched by to_topic."""
        edge_topic_only = {
            "id": "E-sp-mc",
            "from_topic": "Stochastic Processes",
            "to_topic": "Monte Carlo",
            "edge_type": "prerequisite",
        }
        unmastered = find_unmastered_prerequisites(
            None,
            "Monte Carlo",
            [edge_topic_only],
            mastered_concepts=set(),
            mastered_topics=set(),
        )
        self.assertEqual(len(unmastered), 1)


# ---------------------------------------------------------------------------
# resolve_teaching_target — core recursive gate
# ---------------------------------------------------------------------------


class TestResolveTeachingTarget(unittest.TestCase):
    def test_mcmc_unmastered_markov_resolves_to_markov(self) -> None:
        """Markov unmastered → MCMC plan resolves to markov_chain/Stochastic Processes."""
        result = resolve_teaching_target(
            "mcmc_intuition",
            "Monte Carlo",
            PREREQ_EDGES,
            mastered_concepts=set(),
            mastered_topics=set(),
        )
        self.assertFalse(result.ready)
        self.assertEqual(result.effective_concept, "markov_chain")
        self.assertEqual(result.effective_topic, "Stochastic Processes")
        self.assertIn("mcmc_intuition", result.blocked_chain)
        self.assertIn("markov_chain", result.blocked_chain)

    def test_markov_mastered_mcmc_is_ready(self) -> None:
        """All mastered → original target passes through unchanged."""
        result = resolve_teaching_target(
            "mcmc_intuition",
            "Monte Carlo",
            PREREQ_EDGES,
            mastered_concepts={"markov_chain"},
            mastered_topics=set(),
        )
        self.assertTrue(result.ready)
        self.assertEqual(result.effective_concept, "mcmc_intuition")
        self.assertEqual(result.effective_topic, "Monte Carlo")
        self.assertEqual(result.blocked_chain, [])

    def test_no_prereqs_always_ready(self) -> None:
        result = resolve_teaching_target(
            "calibration",
            "Logistic Regression",
            PREREQ_EDGES,
            mastered_concepts=set(),
            mastered_topics=set(),
        )
        self.assertTrue(result.ready)

    def test_transitive_chain_a_requires_b_requires_c_only_c_unmastered(self) -> None:
        """Transitive: A requires B requires C; only C unmastered → teach C."""
        # A requires B, B requires C; mastered: A, B (but NOT C)
        result = resolve_teaching_target(
            "concept_c",
            "Topic C",
            PREREQ_EDGES,
            mastered_concepts={"concept_b"},  # B mastered, but A is the prereq of B
            mastered_topics=set(),
        )
        # B is a prerequisite of C but B is mastered → C is ready
        self.assertTrue(result.ready)
        self.assertEqual(result.effective_concept, "concept_c")

    def test_transitive_chain_c_blocked_by_unmastered_b(self) -> None:
        """C needs B (unmastered), B needs A (mastered) → teach B tonight."""
        result = resolve_teaching_target(
            "concept_c",
            "Topic C",
            PREREQ_EDGES,
            mastered_concepts={"concept_a"},  # A mastered, B not mastered
            mastered_topics=set(),
        )
        self.assertFalse(result.ready)
        # Effective target should be B (the unmastered direct prereq of C)
        self.assertEqual(result.effective_concept, "concept_b")

    def test_transitive_chain_c_blocked_to_a(self) -> None:
        """C needs B, B needs A; nothing mastered → teach A first."""
        result = resolve_teaching_target(
            "concept_c",
            "Topic C",
            PREREQ_EDGES,
            mastered_concepts=set(),
            mastered_topics=set(),
        )
        self.assertFalse(result.ready)
        # Deepest unmastered prereq is A
        self.assertEqual(result.effective_concept, "concept_a")
        # Chain goes C → B → A
        self.assertIn("concept_c", result.blocked_chain)
        self.assertIn("concept_b", result.blocked_chain)
        self.assertIn("concept_a", result.blocked_chain)

    def test_original_and_effective_preserved(self) -> None:
        result = resolve_teaching_target(
            "mcmc_intuition",
            "Monte Carlo",
            PREREQ_EDGES,
            mastered_concepts=set(),
            mastered_topics=set(),
        )
        self.assertEqual(result.original_concept, "mcmc_intuition")
        self.assertEqual(result.original_topic, "Monte Carlo")


# ---------------------------------------------------------------------------
# gate_curator_plan
# ---------------------------------------------------------------------------


class TestGateCuratorPlan(unittest.TestCase):
    def _mcmc_plan(self, concept: str = "mcmc_intuition", topic: str = "Monte Carlo") -> dict:
        return _curator_plan(concept, topic)

    def test_mcmc_plan_blocked_when_markov_unmastered(self) -> None:
        state = _state(topics=set())  # nothing mastered
        plan = self._mcmc_plan()
        result = gate_curator_plan(plan, state)
        self.assertFalse(result.all_ready)
        self.assertGreater(len(result.blocked_slots), 0)
        # Effective target for slot 1 should be markov_chain
        first = result.blocked_slots[0]
        self.assertEqual(first.gate.effective_concept, "markov_chain")

    def test_mcmc_plan_passes_when_markov_mastered(self) -> None:
        state = _state(topics={"Stochastic Processes"})
        plan = self._mcmc_plan()
        result = gate_curator_plan(plan, state)
        self.assertTrue(result.all_ready)

    def test_mcmc_plan_passes_when_markov_concept_mastered(self) -> None:
        state = _state(topics=set(), concepts={"markov_chain"})
        plan = self._mcmc_plan()
        result = gate_curator_plan(plan, state)
        self.assertTrue(result.all_ready)

    def test_unrelated_plan_always_passes(self) -> None:
        state = _state(topics=set())
        plan = _curator_plan("calibration", "Logistic Regression")
        result = gate_curator_plan(plan, state)
        self.assertTrue(result.all_ready)

    def test_replan_suggestion_contains_effective_target(self) -> None:
        state = _state(topics=set())
        plan = self._mcmc_plan()
        result = gate_curator_plan(plan, state)
        suggestion = result.replan_suggestion()
        self.assertEqual(suggestion["action"], "defer")
        self.assertEqual(suggestion["effective_concept"], "markov_chain")
        self.assertEqual(suggestion["effective_topic"], "Stochastic Processes")

    def test_empty_lessons_plan_passes(self) -> None:
        state = _state(topics=set())
        result = gate_curator_plan({"lessons": []}, state)
        self.assertTrue(result.all_ready)


# ---------------------------------------------------------------------------
# check_prerequisite_closure
# ---------------------------------------------------------------------------


class TestCheckPrerequisiteClosure(unittest.TestCase):
    def test_passes_for_mastered_prereqs(self) -> None:
        state = _state(topics={"Stochastic Processes"})
        plan = _curator_plan("mcmc_intuition", "Monte Carlo")
        ok, msg = check_prerequisite_closure(plan, state)
        self.assertTrue(ok)
        self.assertIn("ready", msg.lower())

    def test_fails_for_unmastered_prereqs(self) -> None:
        state = _state(topics=set())
        plan = _curator_plan("mcmc_intuition", "Monte Carlo")
        ok, msg = check_prerequisite_closure(plan, state)
        self.assertFalse(ok)
        self.assertIn("blocked", msg.lower())

    def test_diagnostics_blocked_when_markov_unmastered(self) -> None:
        state = _state(topics=set())
        plan = _curator_plan("mcmc_diagnostics", "Monte Carlo")
        ok, msg = check_prerequisite_closure(plan, state)
        self.assertFalse(ok)

    def test_diagnostics_passes_when_markov_mastered(self) -> None:
        state = _state(topics={"Stochastic Processes"})
        plan = _curator_plan("mcmc_diagnostics", "Monte Carlo")
        ok, msg = check_prerequisite_closure(plan, state)
        self.assertTrue(ok)


# ---------------------------------------------------------------------------
# GateResult helpers
# ---------------------------------------------------------------------------


class TestGateResultHelpers(unittest.TestCase):
    def test_ready_summary(self) -> None:
        g = GateResult(
            original_concept="markov_chain",
            original_topic="Stochastic Processes",
            effective_concept="markov_chain",
            effective_topic="Stochastic Processes",
            blocked_chain=[],
            ready=True,
        )
        self.assertIn("ready", g.summary().lower())
        self.assertFalse(g.deferred())

    def test_deferred_summary(self) -> None:
        g = GateResult(
            original_concept="mcmc_intuition",
            original_topic="Monte Carlo",
            effective_concept="markov_chain",
            effective_topic="Stochastic Processes",
            blocked_chain=["mcmc_intuition", "markov_chain"],
            ready=False,
        )
        summary = g.summary()
        self.assertIn("deferred", summary.lower())
        self.assertIn("markov_chain", summary)
        self.assertTrue(g.deferred())


# ---------------------------------------------------------------------------
# Real concept-graph.yaml integration
# ---------------------------------------------------------------------------


class TestRealConceptGraph(unittest.TestCase):
    """Smoke tests against the actual concept-graph.yaml in the repo."""

    def test_prerequisite_edges_present(self) -> None:
        edges = load_prerequisite_edges()
        ids = [e.get("id") for e in edges]
        self.assertIn("E-markov-mcmc", ids)
        self.assertIn("E-markov-mcmc-diag", ids)
        self.assertIn("E-stochastic-markov", ids)

    def test_mcmc_blocked_without_stochastic(self) -> None:
        """Integration: mcmc_intuition is blocked for a learner with no Stochastic Processes."""
        edges = load_prerequisite_edges()
        result = resolve_teaching_target(
            "mcmc_intuition",
            "Monte Carlo",
            edges,
            mastered_concepts=set(),
            mastered_topics={"Naive Bayes", "KNN"},  # seeded but no Stochastic Processes
        )
        self.assertFalse(result.ready)
        self.assertIn(result.effective_topic, ("Stochastic Processes",))

    def test_mcmc_ready_with_stochastic(self) -> None:
        edges = load_prerequisite_edges()
        result = resolve_teaching_target(
            "mcmc_intuition",
            "Monte Carlo",
            edges,
            mastered_concepts=set(),
            mastered_topics={"Stochastic Processes"},
        )
        self.assertTrue(result.ready)


class TestAssumedFoundations(unittest.TestCase):
    def test_foundation_concept_is_mastered_by_default(self) -> None:
        concepts = get_mastered_concepts()
        self.assertIn("first_order_derivatives", concepts)
        self.assertIn("basic_algebra", concepts)

    def test_foundation_stops_recursion(self) -> None:
        """Edge pointing to a foundation concept never blocks further."""
        edge_to_foundation = {
            "id": "E-to-foundation",
            "from_concept": "first_order_derivatives",
            "from_topic": "Optimization",
            "to_concept": "gradient_descent",
            "to_topic": "Neural Networks",
            "edge_type": "prerequisite",
        }
        unmastered = find_unmastered_prerequisites(
            "gradient_descent",
            "Neural Networks",
            [edge_to_foundation],
            mastered_concepts=get_mastered_concepts(),
            mastered_topics=set(),
        )
        self.assertEqual(len(unmastered), 0)

    def test_seeded_topic_does_not_master_unrelated_concept(self) -> None:
        """Optimization seeded does not unlock markov_chain without explicit concept."""
        result = resolve_teaching_target(
            "mcmc_intuition",
            "Monte Carlo",
            PREREQ_EDGES,
            mastered_concepts=set(),
            mastered_topics={"Optimization", "Neural Networks"},
        )
        self.assertFalse(result.ready)
        self.assertEqual(result.effective_concept, "markov_chain")


class TestPrerequisiteCycles(unittest.TestCase):
    def test_cycle_raises(self) -> None:
        cycle_a = {
            "id": "E-cycle-a",
            "from_concept": "concept_b",
            "to_concept": "concept_a",
            "edge_type": "prerequisite",
        }
        cycle_b = {
            "id": "E-cycle-b",
            "from_concept": "concept_a",
            "to_concept": "concept_b",
            "edge_type": "prerequisite",
        }
        with self.assertRaises(RuntimeError) as ctx:
            resolve_teaching_target(
                "concept_a",
                None,
                [cycle_a, cycle_b],
                mastered_concepts=set(),
                mastered_topics=set(),
            )
        self.assertIn("cycle", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
