"""Active learner graph + mental models from read lessons and seed hypotheses."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
LEARNER = ROOT / "learner"
CURRICULUM = ROOT / "curriculum"
REPORTS = ROOT / "reports"
ACTIVE_STATE_PATH = LEARNER / "active-state.yaml"
HYPOTHESES_PATH = LEARNER / "hypotheses.jsonl"
CONCEPT_EDGES_PATH = LEARNER / "concept-edges.jsonl"

LESSON_EVIDENCE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-lesson-(\d{2})$")
SEED_MARKERS = ("prior-teaching", "student-quiz")


def _load_yaml(path: Path) -> Any:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _save_yaml(path: Path, data: dict[str, Any], header: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(json.loads(line))
    return out


def write_jsonl(path: Path, entries: list[dict[str, Any]], header: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e, ensure_ascii=False) for e in entries]
    path.write_text(header + ("\n".join(lines) + "\n" if lines else ""), encoding="utf-8")


def report_dates() -> list[str]:
    dates: list[str] = []
    if not REPORTS.exists():
        return dates
    for d in REPORTS.iterdir():
        if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}", d.name) and (d / "index.md").exists():
            dates.append(d.name)
    return sorted(dates)


def lesson_files(report_date: str) -> list[Path]:
    d = REPORTS / report_date
    return sorted(d.glob("[0-9][0-9]-*.md")) if d.is_dir() else []


def is_seed_hypothesis(entry: dict[str, Any]) -> bool:
    source = str(entry.get("source") or "")
    if any(m in source for m in SEED_MARKERS):
        return True
    for ev in entry.get("evidence") or []:
        evs = str(ev)
        if any(evs.startswith(m) for m in SEED_MARKERS):
            return True
    return False


def parse_lesson_evidence(evidence: str) -> tuple[str, str] | None:
    m = LESSON_EVIDENCE_RE.match(evidence.strip())
    if not m:
        return None
    return m.group(1), f"lesson-{m.group(2)}"


def read_lesson_keys(engagement: dict[str, Any] | None = None) -> set[str]:
    engagement = engagement if engagement is not None else _load_yaml(LEARNER / "engagement.yaml")
    keys: set[str] = set()
    for report_date in report_dates():
        n = len(lesson_files(report_date))
        day = engagement.get(report_date, {}) if isinstance(engagement, dict) else {}
        for i in range(1, n + 1):
            key = f"lesson-{i:02d}"
            if day.get(key, {}).get("status") == "read":
                keys.add(f"{report_date}::{key}")
    return keys


def topics_from_read_lessons(
    engagement: dict[str, Any] | None = None,
) -> set[str]:
    engagement = engagement if engagement is not None else _load_yaml(LEARNER / "engagement.yaml")
    topics: set[str] = set()
    for report_date in report_dates():
        meta = _load_yaml(REPORTS / report_date / "meta.yaml")
        lessons_meta = {m["slot"]: m for m in meta.get("lessons", [])}
        n = len(lesson_files(report_date))
        day = engagement.get(report_date, {}) if isinstance(engagement, dict) else {}
        for i in range(1, n + 1):
            key = f"lesson-{i:02d}"
            if day.get(key, {}).get("status") != "read":
                continue
            m = lessons_meta.get(i, {})
            topic = m.get("topic_label") or meta.get("topic_label") or ""
            if topic:
                topics.add(str(topic))
    return topics


def hypothesis_has_read_evidence(
    entry: dict[str, Any],
    read_keys: set[str],
    valid_dates: set[str],
) -> bool:
    for ev in entry.get("evidence") or []:
        parsed = parse_lesson_evidence(str(ev))
        if not parsed:
            continue
        report_date, lesson = parsed
        if report_date not in valid_dates:
            continue
        if f"{report_date}::{lesson}" in read_keys:
            return True
    return False


def filter_active_hypotheses(
    entries: list[dict[str, Any]],
    *,
    read_keys: set[str] | None = None,
    valid_dates: set[str] | None = None,
) -> list[dict[str, Any]]:
    read_keys = read_keys if read_keys is not None else read_lesson_keys()
    valid_dates = valid_dates if valid_dates is not None else set(report_dates())

    active: list[dict[str, Any]] = []
    active_ids: set[str] = set()

    for entry in entries:
        hid = str(entry.get("id") or "")
        if is_seed_hypothesis(entry):
            active.append(entry)
            if hid:
                active_ids.add(hid)
            continue
        if hypothesis_has_read_evidence(entry, read_keys, valid_dates):
            active.append(entry)
            if hid:
                active_ids.add(hid)

    # Include depends_on targets that are seed or already active (one hop for display)
    by_id = {str(e.get("id")): e for e in entries if e.get("id")}
    expanded: list[dict[str, Any]] = list(active)
    expanded_ids = set(active_ids)
    for entry in active:
        for dep in entry.get("depends_on") or []:
            dep = str(dep)
            if dep in expanded_ids or dep not in by_id:
                continue
            dep_entry = by_id[dep]
            if is_seed_hypothesis(dep_entry) or hypothesis_has_read_evidence(dep_entry, read_keys, valid_dates):
                expanded.append(dep_entry)
                expanded_ids.add(dep)

    # Stable order: preserve original file order
    seen: set[str] = set()
    ordered: list[dict[str, Any]] = []
    for entry in entries:
        hid = str(entry.get("id") or "")
        if hid and hid in expanded_ids and hid not in seen:
            ordered.append(entry)
            seen.add(hid)
    return ordered


def active_topics(
    hypotheses: list[dict[str, Any]],
    *,
    read_topic_labels: set[str] | None = None,
) -> set[str]:
    topics = set(read_topic_labels or topics_from_read_lessons())
    for h in hypotheses:
        tl = h.get("topic_label")
        if tl:
            topics.add(str(tl))
    return topics


def filter_graph_edges(edges: list[dict[str, Any]], topics: set[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in edges:
        fr = str(e.get("from_topic") or "")
        to = str(e.get("to_topic") or "")
        if fr in topics and to in topics:
            out.append(e)
    return out


def filter_invariants(invariants: list[dict[str, Any]], topics: set[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for inv in invariants:
        inv_topics = {str(t) for t in inv.get("topics") or []}
        if inv_topics & topics:
            out.append(inv)
    return out


def build_active_graph(
    topics: set[str],
) -> dict[str, Any]:
    graph = _load_yaml(CURRICULUM / "concept-graph.yaml")
    seed_edges = [{**e, "runtime": False} for e in graph.get("seed_edges") or []]
    runtime = [{**e, "runtime": True} for e in read_jsonl(CONCEPT_EDGES_PATH)]
    all_edges = filter_graph_edges(seed_edges + runtime, topics)
    invariants = filter_invariants(graph.get("invariants") or [], topics)
    return {
        "topics": sorted(topics),
        "edges": all_edges,
        "invariants": invariants,
    }


def sync_learner_state(*, prune: bool = True) -> dict[str, Any]:
    """
    Recompute active mental models + graph from engagement, existing reports, and seeds.
    Optionally prune hypotheses.jsonl and concept-edges.jsonl to match.
    """
    engagement = _load_yaml(LEARNER / "engagement.yaml")
    valid_dates = set(report_dates())
    read_keys = read_lesson_keys(engagement)
    read_topics = topics_from_read_lessons(engagement)

    all_hyp = read_jsonl(HYPOTHESES_PATH)
    active_hyp = filter_active_hypotheses(all_hyp, read_keys=read_keys, valid_dates=valid_dates)
    topics = active_topics(active_hyp, read_topic_labels=read_topics)
    graph = build_active_graph(topics)

    if prune:
        if len(active_hyp) != len(all_hyp):
            write_jsonl(HYPOTHESES_PATH, active_hyp)
        runtime = read_jsonl(CONCEPT_EDGES_PATH)
        pruned_runtime = [
            e for e in runtime if e.get("from_topic") in topics and e.get("to_topic") in topics
        ]
        if len(pruned_runtime) != len(runtime):
            write_jsonl(
                CONCEPT_EDGES_PATH,
                pruned_runtime,
                header="# Append-only concept edges discovered or strengthened by the grapher agent.\n"
                "# Seed edges live in curriculum/concept-graph.yaml; runtime edges use ids E-100+.\n",
            )

    state = {
        "synced_at": date.today().isoformat(),
        "read_lessons": sorted(read_keys),
        "read_topics": sorted(read_topics),
        "active_topics": sorted(topics),
        "active_hypothesis_ids": [h.get("id") for h in active_hyp if h.get("id")],
        "stats": {
            "reports": len(valid_dates),
            "read_lesson_count": len(read_keys),
            "hypotheses_total_before": len(all_hyp),
            "hypotheses_active": len(active_hyp),
            "graph_nodes": len(topics),
            "graph_edges": len(graph["edges"]),
        },
        "graph": graph,
    }
    _save_yaml(
        ACTIVE_STATE_PATH,
        state,
        header="# Auto-synced from read lessons + seed mental models — do not edit by hand\n\n",
    )
    return state


def load_active_state() -> dict[str, Any]:
    state = _load_yaml(ACTIVE_STATE_PATH)
    if state.get("graph"):
        return state
    return sync_learner_state(prune=False)


def load_active_hypotheses() -> list[dict[str, Any]]:
    state = load_active_state()
    ids = set(state.get("active_hypothesis_ids") or [])
    if not ids:
        return filter_active_hypotheses(read_jsonl(HYPOTHESES_PATH))
    all_hyp = read_jsonl(HYPOTHESES_PATH)
    return [h for h in all_hyp if h.get("id") in ids]


def load_active_graph() -> dict[str, Any]:
    state = load_active_state()
    return state.get("graph") or build_active_graph(set(state.get("active_topics") or []))
