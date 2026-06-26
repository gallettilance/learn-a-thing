"""Topic diversity rules for nightly curator plans."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from lib.topic_mastery import all_mastered_labels

ROOT = Path(__file__).resolve().parent.parent
LEARNER = ROOT / "learner"
CURRICULUM = ROOT / "curriculum"
REPORTS = ROOT / "reports"

MAX_SAME_TOPIC = 4
LESSON_COUNT = 5

# topic-queue concept keys → display topic labels
CONCEPT_TO_TOPIC: dict[str, str] = {
    "conjugate_pairs_beta_binomial": "Bayesian Inference",
    "variational_inference_elbo": "Bayesian Inference",
    "mcmc_diagnostics": "Monte Carlo",
    "monte_carlo_estimation": "Monte Carlo",
    "importance_sampling": "Monte Carlo",
    "prior_as_regularization": "Linear Regression",
    "stochastic_process_markov": "Stochastic Processes",
    "time_series_forecast": "Time Series",
    "quadratic_optimization_kkt": "Linear and Quadratic Optimization",
    "svm_dual_qp": "Linear and Quadratic Optimization",
    "transformer_attention": "Transformers",
    "llm_inference_scaling": "LLMs",
    "quantum_computing_basics": "Quantum Computing",
    "correlation_vs_causation": "Correlation",
    "metric_geometry": "Distance Functions",
    "gmm_soft_clustering": "GMM",
}


def _load_yaml(path: Path) -> Any:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def topic_counts(lessons: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for les in lessons:
        label = str(les.get("topic_label") or "").strip()
        if label:
            counts[label] = counts.get(label, 0) + 1
    return counts


def dominant_topic(lessons: list[dict[str, Any]]) -> tuple[str, int]:
    counts = topic_counts(lessons)
    if not counts:
        return "", 0
    label = max(counts, key=lambda k: counts[k])
    return label, counts[label]


def check_topic_diversity(
    curator: dict[str, Any],
    *,
    max_same: int = MAX_SAME_TOPIC,
) -> tuple[bool, str]:
    """Return (ok, message). Exploration nights may use one topic for all 5 slots."""
    night_type = str(curator.get("night_type") or "arc")
    if night_type == "exploration":
        return True, "exploration night — single far-field topic allowed"

    lessons = curator.get("lessons") or []
    if len(lessons) != LESSON_COUNT:
        return False, f"expected {LESSON_COUNT} lessons, got {len(lessons)}"

    _, top_count = dominant_topic(lessons)
    if top_count <= max_same:
        unique = len(topic_counts(lessons))
        return True, f"{unique} distinct topic(s); dominant count {top_count}/{LESSON_COUNT}"

    dom, _ = dominant_topic(lessons)
    return False, (
        f"all {LESSON_COUNT} lessons use '{dom}' — max {max_same}/{LESSON_COUNT} "
        f"may share the same topic_label"
    )


def _recent_diversity_topics(limit: int = 5) -> set[str]:
    """Topics used as the non-dominant slot in recent reports."""
    seen: set[str] = set()
    metas = sorted(REPORTS.glob("*/meta.yaml"), reverse=True)
    for meta_path in metas[:limit]:
        meta = _load_yaml(meta_path)
        lessons = meta.get("lessons") or []
        if len(lessons) < LESSON_COUNT:
            continue
        dom, _ = dominant_topic(lessons)
        for les in lessons:
            tl = str(les.get("topic_label") or "").strip()
            if tl and tl != dom:
                seen.add(tl)
    return seen


def _concept_to_topic(concept: str) -> str:
    key = concept.strip().lower()
    if key in CONCEPT_TO_TOPIC:
        return CONCEPT_TO_TOPIC[key]
    # fallback: snake_case → Title Case Words
    words = re.sub(r"[^a-z0-9]+", " ", key).strip().split()
    return " ".join(w.capitalize() for w in words) if words else concept


def collect_diversity_candidates(
    *,
    arc_topic: str,
    report_date: str,
    night_type: str,
) -> list[dict[str, str]]:
    """Ordered list of {topic_label, pressure, source} for a diversity slot."""
    arc_l = arc_topic.lower()
    recent = _recent_diversity_topics()
    candidates: list[dict[str, str]] = []
    seen_topics: set[str] = set()
    profile = _load_yaml(LEARNER / "profile.yaml")
    mastered = all_mastered_labels(profile=profile)

    def add(topic: str, pressure: str, source: str, *, priority: int = 0) -> None:
        t = topic.strip()
        if not t or t.lower() == arc_l or t in seen_topics:
            return
        if t in mastered or any(t.lower() == m.lower() for m in mastered):
            return
        seen_topics.add(t)
        # deprioritize topics used as diversity slots very recently
        score = priority - (10 if t in recent else 0)
        candidates.append(
            {"topic_label": t, "pressure": pressure.strip(), "source": source, "_score": str(score)}
        )

    for item in profile.get("curriculum_interests") or []:
        if not isinstance(item, dict):
            continue
        pri = {"high": 30, "medium": 20, "low": 10}.get(str(item.get("priority", "medium")), 15)
        add(str(item.get("topic", "")), str(item.get("pressure", "")), "curriculum_interests", priority=pri)

    graph = _load_yaml(CURRICULUM / "concept-graph.yaml")
    if night_type in ("bridge", "transfer", "arc"):
        for tmpl in graph.get("bridge_night_templates") or []:
            if not isinstance(tmpl, dict):
                continue
            pressure = str(tmpl.get("pressure") or "")
            for topic in tmpl.get("topics") or []:
                add(str(topic), pressure, "bridge_night_templates", priority=25)

    for edge in graph.get("seed_edges") or []:
        if not isinstance(edge, dict):
            continue
        stmt = str(edge.get("statement") or "")[:120]
        for key in ("from_topic", "to_topic"):
            add(str(edge.get(key, "")), stmt or "Connect via shared pressure invariant", "seed_edges", priority=15)

    queue = _load_yaml(LEARNER / "topic-queue.yaml")
    for item in queue.get("backlog") or []:
        if not isinstance(item, dict):
            continue
        concept = str(item.get("concept") or "")
        topic = _concept_to_topic(concept)
        pri = {"high": 22, "medium": 12, "low": 5}.get(str(item.get("priority", "medium")), 10)
        add(topic, str(item.get("pressure") or ""), "topic-queue", priority=pri)

    # Seeded topics worth revisiting at depth (not intro) — skip if user marked mastered
    for topic in profile.get("seeded_topics") or []:
        t = str(topic)
        if t in mastered or any(t.lower() == m.lower() for m in mastered):
            continue
        add(
            t,
            f"Revisit {t} with tonight's spam-filter anchor — bridge, not intro",
            "seeded_topics",
            priority=8,
        )

    if night_type == "exploration":
        exploration = _load_yaml(CURRICULUM / "exploration-topics.yaml")
        for entry in exploration.get("rotation") or []:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("topic_label") or "")
            anchors = entry.get("example_anchors") or []
            pressure = str(anchors[0]) if anchors else f"Explore {label}"
            add(label, pressure, "exploration-topics", priority=18)

    candidates.sort(key=lambda c: int(c.get("_score", "0")), reverse=True)
    for c in candidates:
        c.pop("_score", None)
    return candidates


def _pick_diversity_slot(lessons: list[dict[str, Any]], dominant: str) -> int:
    """Prefer slot 5, then 4, then last slot still on dominant topic."""
    dom_l = dominant.lower()
    for slot in (5, 4, 3, 2, 1):
        for les in lessons:
            if les.get("slot") == slot:
                tl = str(les.get("topic_label") or "").strip().lower()
                if tl == dom_l or not tl:
                    return slot
    return 5


def enforce_topic_diversity(
    curator: dict[str, Any],
    report_date: str,
    *,
    max_same: int = MAX_SAME_TOPIC,
) -> tuple[dict[str, Any], bool, str]:
    """
    Ensure at most max_same lessons share the same topic_label.
    Returns (curator, changed, message).
    """
    ok, msg = check_topic_diversity(curator, max_same=max_same)
    if ok:
        return curator, False, msg

    night_type = str(curator.get("night_type") or "arc")
    lessons: list[dict[str, Any]] = list(curator.get("lessons") or [])
    arc_topic = str(curator.get("topic_label") or "").strip()
    if not arc_topic:
        arc_topic, _ = dominant_topic(lessons)

    dom, _ = dominant_topic(lessons)
    candidates = collect_diversity_candidates(
        arc_topic=arc_topic or dom,
        report_date=report_date,
        night_type=night_type,
    )
    if not candidates:
        return curator, False, f"{msg}; no diversity candidates found"

    pick = candidates[0]
    slot_num = _pick_diversity_slot(lessons, dom)
    for i, les in enumerate(lessons):
        if les.get("slot") != slot_num:
            continue
        lessons[i] = {
            **les,
            "topic_label": pick["topic_label"],
            "pressure_question": pick["pressure"] or les.get("pressure_question", ""),
            "slot_role": "bridge",
            "optional": les.get("optional", slot_num >= 4),
            "connects_to": les.get("connects_to") or [],
            "diversity_source": pick["source"],
        }
        break

    curator = {**curator, "lessons": lessons}
    ok2, msg2 = check_topic_diversity(curator, max_same=max_same)
    if not ok2:
        return curator, True, f"partial fix: {msg2}"
    return (
        curator,
        True,
        f"slot {slot_num} → {pick['topic_label']} ({pick['source']}); {msg2}",
    )


def diversity_retry_suffix(curator: dict[str, Any], reason: str) -> str:
    """Extra instructions when re-prompting curator after diversity failure."""
    arc = str(curator.get("topic_label") or "")
    return (
        f"\n\nTOPIC DIVERSITY REQUIRED: {reason}\n"
        f"- At most {MAX_SAME_TOPIC} of {LESSON_COUNT} lessons may share the same topic_label.\n"
        f"- At least 1 lesson MUST use a different topic (from topic-queue, curriculum_interests, "
        f"bridge_night_templates, or seed_edges — not only '{arc}').\n"
        f"- Typical pattern: slots 1–4 stay on the arc; slot 5 (slot_role: bridge) contrasts a "
        f"related tool on the same anchor.\n"
        f"- Set per-lesson topic_label on every lesson.\n"
        f"Respond with valid JSON only."
    )
