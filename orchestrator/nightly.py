#!/usr/bin/env python3
"""Nightly multi-agent learning pipeline orchestrator."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.active_state import load_active_hypotheses, sync_learner_state  # noqa: E402
from lib.context_pack import build_role_context, recent_meta_compact, save_context_manifest  # noqa: E402
from lib.memory_consolidator import consolidate_memory  # noqa: E402
from lib.pedagogy_state import format_pedagogy_for_agents, load_pedagogy_latest, migrate_pedagogy_history  # noqa: E402
from lib.playbook import format_playbook_for_role  # noqa: E402
from lib.run_brief import build_run_brief, save_run_brief  # noqa: E402
from lib.arc_progress import sync_arc_yaml_to_published, validate_curator_arc  # noqa: E402
from lib.lesson_lint import lint_editor_output, lint_night_summary  # noqa: E402
from lib.pipeline_progress import PipelineProgress  # noqa: E402
from lib.refinement import (  # noqa: E402
    DEFAULT_REFINEMENT_DEPTH,
    normalize_refinement_depth,
    run_content_refinement,
)
from lib.run_artifacts import cleanup_run_artifacts, clear_agent_sidecars  # noqa: E402
from lib.spine_state import format_spine_context, sync_spine_progress  # noqa: E402
from lib.titles import topic_prefixed_title  # noqa: E402
from lib.agent_json import load_agent_response  # noqa: E402
from lib.lesson_content import validate_lesson_markdown  # noqa: E402
from lib.topic_diversity import (  # noqa: E402
    check_topic_diversity,
    diversity_retry_suffix,
    enforce_topic_diversity,
)
from lib.consolidator import (  # noqa: E402
    consolidator_feedback_suffix,
    review_passes,
    run_consolidator_draft_review,
    run_consolidator_plan,
    run_consolidator_ship_review,
)
from lib.lesson_consolidation import (  # noqa: E402
    MAX_PLANNING_SLOTS,
    MAX_PUBLISHED_LESSONS,
    MIN_PUBLISHED_LESSONS,
    build_lesson_groups,
    enrich_lessons_from_groups,
    enforce_lesson_consolidation,
    format_consolidation_for_teacher,
)
from lib.prerequisite_gate import (  # noqa: E402
    MasteredState,
    PlanGateResult,
    check_prerequisite_closure,
    gate_curator_plan,
)

PROMPTS = ROOT / "prompts"
LEARNER = ROOT / "learner"
CURRICULUM = ROOT / "curriculum"
REPORTS = ROOT / "reports"
PIPELINE = ROOT / "pipeline"

MODEL = os.environ.get("LEARNING_MODEL", "composer-2.5")

JSON_RETRY_SUFFIX = (
    "\n\nRespond with valid JSON only. No markdown fences. No prose before or after. "
    "Never write output to a file or say content is in another path — embed the full JSON in your reply."
)

TEACHER_JSON_RETRY_SUFFIX = (
    JSON_RETRY_SUFFIX
    + " Write 2–5 published lessons per lesson_groups (not 5 separate articles when topics merge). "
    "Each lessons[].markdown must be the complete merged narrative (see word targets in prompt), "
    "not a summary or pointer. Set top-level \"date\" to the pipeline run date given in the prompt."
)

EDITOR_JSON_RETRY_SUFFIX = (
    JSON_RETRY_SUFFIX
    + " Write 2–5 published lessons with review_summary.all_pass true when fixed. "
    "Set top-level \"date\" to the pipeline run date given in the prompt."
)

CONSOLIDATOR_JSON_RETRY_SUFFIX = (
    JSON_RETRY_SUFFIX
    + " Set top-level \"date\" to the pipeline run date given in the prompt. "
    "If you must use a sidecar, name it `.consolidator-output-YYYY-MM-DD.json` (dated), not "
    "`.consolidator-output.json`."
)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").strip().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            entries.append(json.loads(line))
    return entries


def load_yaml(path: Path) -> Any:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def dump_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")


def sanitize_slug(raw: str, slot: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    slug = slug[:48] or f"lesson-{slot:02d}"
    return f"lesson-{slot:02d}-{slug}" if not slug.startswith(f"lesson-{slot:02d}") else slug


def _strip_markdown_fences(text: str) -> str:
    """Remove surrounding ```json / ``` fences from agent output."""
    stripped = text.strip()
    stripped = re.sub(r"^```(?:json)?\s*\n?", "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\n?```\s*$", "", stripped)
    return stripped.strip()


def _extract_fenced_json_blocks(text: str) -> list[str]:
    """Return contents of ```json ... ``` or ``` ... ``` blocks."""
    return [
        block.strip()
        for block in re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
        if block.strip()
    ]


def _find_balanced_json_object(text: str, start: int = 0) -> str | None:
    """Locate outermost {...} using brace matching that respects JSON strings."""
    idx = text.find("{", start)
    if idx < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(idx, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[idx : i + 1]
    return None


def _repair_truncated_json(fragment: str) -> str | None:
    """Best-effort repair when agent output ends mid-object."""
    candidate = fragment.strip()
    if not candidate.startswith("{"):
        start = candidate.find("{")
        if start < 0:
            return None
        candidate = candidate[start:]

    stack: list[str] = []
    in_string = False
    escape = False
    for ch in candidate:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]" and stack and stack[-1] == ch:
            stack.pop()

    suffix = ""
    if in_string:
        suffix += '"'
    suffix += "".join(reversed(stack))
    if not suffix:
        return None

    repaired = candidate + suffix
    try:
        json.loads(repaired)
    except json.JSONDecodeError:
        return None
    return repaired


def _json_parse_candidates(text: str) -> list[str]:
    """Build ordered list of strings to attempt json.loads on."""
    candidates: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        piece = raw.strip()
        if piece and piece not in seen:
            seen.add(piece)
            candidates.append(piece)

    add(text)
    unfenced = _strip_markdown_fences(text)
    add(unfenced)
    for block in _extract_fenced_json_blocks(text):
        add(block)
        add(_strip_markdown_fences(block))

    for source in (text, unfenced):
        pos = 0
        while True:
            obj = _find_balanced_json_object(source, pos)
            if obj is None:
                break
            add(obj)
            pos = source.find(obj, pos) + max(len(obj), 1)

    # Greedy outermost {...} fallback (may fail on nested prose but cheap to try)
    for source in (text, unfenced):
        match = re.search(r"\{[\s\S]*\}", source)
        if match:
            add(match.group(0))

    for source in (text, unfenced):
        start = source.find("{")
        if start >= 0:
            add(source[start:])
            repaired = _repair_truncated_json(source[start:])
            if repaired:
                add(repaired)

    return candidates


def extract_json(text: str) -> dict[str, Any]:
    """Extract JSON object from agent response (fences, prose, truncation)."""
    if not text or not text.strip():
        raise ValueError("No JSON object found in agent response")

    last_error: json.JSONDecodeError | None = None
    for candidate in _json_parse_candidates(text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(parsed, dict):
            return parsed

    if last_error is not None:
        raise ValueError(f"No JSON object found in agent response: {last_error}") from last_error
    raise ValueError("No JSON object found in agent response")


def _save_raw_response(pipe_dir: Path | None, role: str, raw: str) -> Path | None:
    if pipe_dir is None:
        return None
    pipe_dir.mkdir(parents=True, exist_ok=True)
    path = pipe_dir / f"{role}-raw.txt"
    path.write_text(raw, encoding="utf-8")
    return path


def _format_json_parse_error(role: str, raw: str, raw_path: Path | None, cause: Exception) -> str:
    preview = (raw or "")[:500]
    lines = [
        f"{role} agent returned non-JSON response",
        f"Parse error: {cause}",
        f"Response preview (first 500 chars):\n{preview}",
    ]
    if raw_path is not None:
        lines.append(f"Full raw response saved to: {raw_path}")
    return "\n".join(lines)


def report_dates_before(report_date: str) -> list[str]:
    dates = [
        d.name
        for d in REPORTS.iterdir()
        if d.is_dir() and (d / "index.md").exists()
    ]
    return sorted(d for d in dates if d < report_date)


def compute_engagement_summary(report_date: str) -> dict[str, Any]:
    """Summarize engagement for adaptive pacing (full | light | recap)."""
    engagement = load_yaml(LEARNER / "engagement.yaml")
    prior_dates = report_dates_before(report_date)
    last_night = prior_dates[-1] if prior_dates else None

    last_night_unread = 0
    if last_night:
        day = engagement.get(last_night, {})
        if isinstance(day, dict):
            for i in range(1, 6):
                key = f"lesson-{i:02d}"
                if day.get(key, {}).get("status", "unread") == "unread":
                    last_night_unread += 1

    today = date.fromisoformat(report_date)
    window_start = (today - timedelta(days=7)).isoformat()
    skipped = too_deep = too_shallow = 0
    for d, lessons in engagement.items():
        if not isinstance(lessons, dict) or not (window_start <= d < report_date):
            continue
        for entry in lessons.values():
            if not isinstance(entry, dict):
                continue
            if entry.get("status") == "skipped":
                skipped += 1
            depth = entry.get("depth", "")
            if depth == "too_deep":
                too_deep += 1
            elif depth == "too_shallow":
                too_shallow += 1

    if last_night_unread >= 4:
        mode = "recap"
    elif last_night_unread > 0 or skipped >= 2 or too_deep >= 2:
        mode = "light"
    else:
        mode = "full"

    return {
        "last_night_date": last_night,
        "last_night_unread": last_night_unread,
        "skipped_7d": skipped,
        "too_deep_7d": too_deep,
        "too_shallow_7d": too_shallow,
        "recommended_mode": mode,
    }


def _hypothesis_matches_blind_spot(entry: dict[str, Any], blind_spots: list[str]) -> bool:
    if entry.get("confidence") != "low":
        return False
    haystack = " ".join(
        str(entry.get(k, "")) for k in ("topic_label", "statement", "narrative_beat")
    ).lower()
    for spot in blind_spots:
        tokens = [t for t in re.split(r"[^a-z0-9]+", spot.lower()) if len(t) > 3]
        if any(t in haystack for t in tokens):
            return True
    return False


def filter_hypotheses_for_context(
    entries: list[dict[str, Any]],
    topic_label: str,
    blind_spots: list[str],
    max_entries: int = 30,
) -> list[dict[str, Any]]:
    """Subset hypotheses for agent context; full file stays on disk."""
    by_id = {e["id"]: e for e in entries if e.get("id")}
    selected_ids: set[str] = set()
    topic_l = topic_label.lower()

    for entry in entries:
        hid = entry.get("id")
        if not hid:
            continue
        tl = str(entry.get("topic_label", "")).lower()
        if topic_l and tl and (topic_l in tl or tl in topic_l):
            selected_ids.add(hid)

    for entry in entries:
        hid = entry.get("id")
        if hid and _hypothesis_matches_blind_spot(entry, blind_spots):
            selected_ids.add(hid)

    changed = True
    while changed:
        changed = False
        for hid in list(selected_ids):
            entry = by_id.get(hid, {})
            for dep in entry.get("depends_on") or []:
                if dep in by_id and dep not in selected_ids:
                    selected_ids.add(dep)
                    changed = True
            for other in entries:
                oid = other.get("id")
                if oid and hid in (other.get("depends_on") or []) and oid not in selected_ids:
                    selected_ids.add(oid)
                    changed = True

    if len(selected_ids) < max_entries:
        for entry in entries:
            hid = entry.get("id")
            if not hid or hid in selected_ids:
                continue
            if entry.get("confidence") == "low" and entry.get("narrative_beat"):
                selected_ids.add(hid)
            if len(selected_ids) >= max_entries:
                break

    selected = [by_id[hid] for hid in sorted(selected_ids) if hid in by_id]
    return selected[:max_entries]


def format_hypotheses_context(
    *,
    topic_label: str | None = None,
    max_entries: int = 30,
) -> str:
    profile = load_yaml(LEARNER / "profile.yaml")
    if topic_label is None:
        arc = load_yaml(CURRICULUM / "narrative-arc.yaml")
        topic_label = arc.get("active_arc", {}).get("topic_label", "")

    all_hyp = load_active_hypotheses()
    blind_spots = profile.get("blind_spots") or []
    filtered = filter_hypotheses_for_context(all_hyp, topic_label or "", blind_spots, max_entries)
    lines = [json.dumps(e, ensure_ascii=False) for e in filtered]
    header = f"# {len(filtered)} of {len(all_hyp)} hypotheses (topic + blind spots + depends_on closure)\n"
    return header + "\n".join(lines)


def build_context_files(*, topic_label: str | None = None, max_hypotheses: int = 30, report_date: str | None = None) -> str:
    """Backward-compatible wrapper — prefer build_role_context(role=...) per agent."""
    text, _ = build_role_context(
        "curator",
        report_date=report_date,
        topic_label=topic_label,
        max_hypotheses=max_hypotheses,
        format_hypotheses_fn=format_hypotheses_context,
    )
    return text


def agent_context(
    role: str,
    *,
    report_date: str | None = None,
    topic_label: str | None = None,
    max_hypotheses: int = 20,
    curator: dict[str, Any] | None = None,
    pipe_dir: Path | None = None,
) -> str:
    text, manifest = build_role_context(
        role,
        report_date=report_date,
        topic_label=topic_label,
        max_hypotheses=max_hypotheses,
        curator=curator,
        format_hypotheses_fn=format_hypotheses_context,
    )
    if pipe_dir is not None:
        save_context_manifest(pipe_dir, role, manifest)
    return text


def suggest_night_type(report_date: str) -> str:
    """Suggest night_type from weekly_schedule + pedagogy feedback."""
    graph = load_yaml(CURRICULUM / "concept-graph.yaml")
    schedule = graph.get("weekly_schedule") or {}
    d = datetime.strptime(report_date, "%Y-%m-%d")
    weekday = d.weekday()
    suggested = schedule.get(weekday) or schedule.get(str(weekday)) or "arc"

    if suggested == "transfer" and d.isocalendar()[1] % 2 == 0:
        suggested = "arc"

    pedagogy = load_pedagogy_latest()
    scores = pedagogy.get("quality_scores") or {}
    guidance = pedagogy.get("curator_guidance") or {}
    if scores.get("graph_integration", 5) <= 2 and guidance.get("recommended_night_type"):
        suggested = guidance["recommended_night_type"]

    return str(suggested)


def recent_meta() -> str:
    metas = sorted(REPORTS.glob("*/meta.yaml"), reverse=True)[:3]
    chunks = []
    for m in metas:
        chunks.append(f"=== {m.relative_to(ROOT)} ===\n{m.read_text(encoding='utf-8')}")
    return "\n\n".join(chunks) if chunks else "(no prior reports)"


def parse_agent_response(
    role: str, raw: str, *, report_date: str | None = None
) -> dict[str, Any]:
    """Parse agent output; teacher/editor/consolidator may point at a JSON sidecar when too large."""
    if role in ("teacher", "editor", "consolidator"):
        return load_agent_response(role, raw, report_date=report_date, extract_json_fn=extract_json)
    return extract_json(raw)


def run_agent(
    role: str,
    user_message: str,
    *,
    dry_run: bool,
    use_cloud: bool,
    api_key: str | None,
    pipe_dir: Path | None = None,
    report_date: str | None = None,
) -> dict[str, Any]:
    system = read_text(PROMPTS / f"{role}.md")
    full_prompt = f"{system}\n\n---\n\n{user_message}"

    if dry_run:
        return dry_run_response(role, user_message)

    from cursor_sdk import Agent, AgentOptions, CloudAgentOptions, LocalAgentOptions

    repo_url = os.environ.get("LEARNING_REPO_URL", "")
    if use_cloud:
        cloud_opts: dict[str, Any] = {}
        if repo_url:
            cloud_opts["repos"] = [repo_url]
        opts = AgentOptions(
            api_key=api_key or os.environ["CURSOR_API_KEY"],
            model=MODEL,
            cloud=CloudAgentOptions(**cloud_opts),
        )
    else:
        opts = AgentOptions(
            api_key=api_key or os.environ["CURSOR_API_KEY"],
            model=MODEL,
            local=LocalAgentOptions(cwd=str(ROOT)),
        )

    prompt = full_prompt
    for attempt in range(2):
        result = Agent.prompt(prompt, opts)
        if result.status == "error":
            raise RuntimeError(f"{role} agent failed: {result.result}")

        raw = result.result or ""
        try:
            return parse_agent_response(role, raw, report_date=report_date)
        except ValueError as exc:
            raw_path = _save_raw_response(pipe_dir, role, raw)
            if attempt == 0:
                if role in ("teacher", "editor", "consolidator"):
                    print(
                        f"Warning: {role} response has no usable inline JSON or sidecar; "
                        f"retrying once (raw saved to {raw_path or 'n/a'})..."
                    )
                else:
                    print(
                        f"Warning: {role} response was not valid JSON; retrying once "
                        f"(raw saved to {raw_path or 'n/a'})..."
                    )
                if role == "teacher":
                    retry_suffix = TEACHER_JSON_RETRY_SUFFIX
                elif role == "editor":
                    retry_suffix = EDITOR_JSON_RETRY_SUFFIX
                elif role == "consolidator":
                    retry_suffix = CONSOLIDATOR_JSON_RETRY_SUFFIX
                else:
                    retry_suffix = JSON_RETRY_SUFFIX
                prompt = full_prompt + retry_suffix
                continue
            raise ValueError(
                _format_json_parse_error(role, raw, raw_path, exc)
            ) from exc

    raise RuntimeError(f"{role} agent: unreachable retry state")


def apply_prerequisite_gate(
    curator: dict[str, Any],
    report_date: str,
    *,
    dry_run: bool,
    use_cloud: bool,
    api_key: str | None,
    pipe_dir: Path | None,
    curator_msg: str,
    progress: "PipelineProgress | None" = None,
) -> dict[str, Any]:
    """Run prerequisite gate on curator plan; auto-rewrite if blocked.

    If any lesson slot references a concept/topic whose prerequisites the learner
    has not yet mastered, rewrite the plan to teach the unmastered prerequisite
    instead.  On dry_run only warns.
    """
    mastered_state = MasteredState.load()
    ok, msg = check_prerequisite_closure(curator, mastered_state)
    if ok:
        return curator

    max_replans = 5
    for replan_attempt in range(max_replans):
        plan_result = gate_curator_plan(curator, mastered_state)
        _print_prerequisite_side_quests(plan_result, report_date, replan_attempt + 1, dry_run=dry_run)
        _log_prerequisite_side_quests(
            plan_result,
            report_date,
            pipe_dir=pipe_dir,
            replan_attempt=replan_attempt + 1,
            dry_run=dry_run,
        )

        if dry_run:
            print("Warning: dry-run — prerequisite gate would replan but skipping.")
            return curator

        suggestion = plan_result.replan_suggestion()
        chain_str = " → ".join(suggestion.get("blocked_chain") or [])
        eff_concept = suggestion.get("effective_concept") or ""
        eff_topic = suggestion.get("effective_topic") or ""
        eff_label = eff_concept or eff_topic or "(unknown)"
        orig_label = suggestion.get("blocked_concept") or suggestion.get("blocked_topic") or "(unknown)"

        prereq_suffix = (
            f"\n\nPREREQUISITE GATE — REPLAN REQUIRED:\n"
            f"The plan references '{orig_label}' but the learner has NOT mastered its prerequisites.\n"
            f"Blocked prerequisite chain: {chain_str}\n"
            f"Teach '{eff_label}' tonight instead.\n"
            f"Update all affected lesson slots to use topic_label and concept for '{eff_label}'.\n"
            f"Set prerequisite_check.deferred=true and prerequisite_check.chain={suggestion.get('blocked_chain')!r} "
            f"in the top-level JSON.\n"
            f"Respond with valid JSON only."
        )

        print(
            f"Prerequisite gate: re-running curator to teach '{eff_label}' "
            f"instead of '{orig_label}'..."
        )
        if progress is not None:
            progress.step("curator", detail=f"prerequisite gate replan {replan_attempt + 1}")

        curator = run_agent(
            "curator",
            curator_msg + prereq_suffix,
            dry_run=False,
            use_cloud=use_cloud,
            api_key=api_key,
            pipe_dir=pipe_dir,
        )

        _log_deferred_beat(suggestion, report_date)

        ok2, msg2 = check_prerequisite_closure(curator, mastered_state)
        if ok2:
            print("Prerequisite gate: replan passed.")
            return curator
        print(f"Prerequisite gate: still blocked after replan {replan_attempt + 1}: {msg2}")

    raise RuntimeError(
        f"Prerequisite gate failed after {max_replans} curator replans:\n{msg2}"
    )


def _print_prerequisite_side_quests(
    plan_result: PlanGateResult,
    report_date: str,
    attempt: int,
    *,
    dry_run: bool,
) -> None:
    """Console log: prerequisite side quests (deferred beats)."""
    if plan_result.all_ready:
        return
    mode = "would replan (dry-run)" if dry_run else "replanning curator"
    print(f"\n{'=' * 60}")
    print(f"PREREQUISITE SIDE QUESTS · {report_date} · attempt {attempt} · {mode}")
    print(f"{'=' * 60}")
    for slot in plan_result.blocked_slots:
        g = slot.gate
        orig = g.original_concept or g.original_topic or "?"
        eff = g.effective_concept or g.effective_topic or "?"
        chain = " → ".join(g.blocked_chain) if g.blocked_chain else orig
        print(f"  slot {slot.slot:02d}: teach {eff} tonight")
        print(f"           blocked: {orig}")
        print(f"           chain:   {chain}")
    print(f"{'=' * 60}\n")


def _log_prerequisite_side_quests(
    plan_result: PlanGateResult,
    report_date: str,
    *,
    pipe_dir: Path | None,
    replan_attempt: int,
    dry_run: bool,
) -> None:
    """Persist side quests to learner YAML and pipeline JSON."""
    if plan_result.all_ready:
        return

    entries = []
    for slot in plan_result.blocked_slots:
        g = slot.gate
        entries.append({
            "slot": slot.slot,
            "blocked_concept": g.original_concept,
            "blocked_topic": g.original_topic,
            "effective_concept": g.effective_concept,
            "effective_topic": g.effective_topic,
            "blocked_chain": g.blocked_chain,
            "summary": g.summary(),
        })

    record = {
        "date": report_date,
        "replan_attempt": replan_attempt,
        "dry_run": dry_run,
        "side_quests": entries,
    }

    path = LEARNER / "prerequisite-side-quests.yaml"
    raw: dict[str, Any]
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        raw = {}
    log = list(raw.get("log") or [])
    log.append(record)
    raw["log"] = log
    raw["last_updated"] = report_date
    header = (
        "# Prerequisite side quests — beats deferred until dependencies are mastered.\n"
        "# Also printed to console during nightly runs.\n\n"
    )
    path.write_text(header + yaml.dump(raw, default_flow_style=False, sort_keys=False), encoding="utf-8")

    if pipe_dir is not None:
        pipe_dir.mkdir(parents=True, exist_ok=True)
        (pipe_dir / "prerequisite-side-quests.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8"
        )


def _log_deferred_beat(suggestion: dict[str, Any], report_date: str) -> None:
    """Append a deferred-beat entry to learner/deferred-beats.yaml."""
    path = LEARNER / "deferred-beats.yaml"
    import yaml as _yaml  # already imported at module level but guard for clarity

    raw: dict[str, Any]
    if path.exists():
        raw = _yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        raw = {}

    deferred: list[dict[str, Any]] = list(raw.get("deferred") or [])
    deferred.append({
        "date": report_date,
        "blocked_concept": suggestion.get("blocked_concept"),
        "blocked_topic": suggestion.get("blocked_topic"),
        "effective_concept": suggestion.get("effective_concept"),
        "effective_topic": suggestion.get("effective_topic"),
        "blocked_chain": suggestion.get("blocked_chain") or [],
        "message": suggestion.get("message"),
    })
    raw["deferred"] = deferred
    raw["last_updated"] = report_date
    path.write_text(_yaml.dump(raw, default_flow_style=False, sort_keys=False), encoding="utf-8")


def _warn_curator_summary(curator: dict[str, Any]) -> None:
    issues = lint_night_summary(str(curator.get("night_thread") or ""), label="night_thread")
    if issues:
        print("Curator summary warning (plain English required):\n" + "\n".join(f"  - {i}" for i in issues))


def ensure_curator_lesson_consolidation(
    curator: dict[str, Any],
    *,
    report_date: str,
    dry_run: bool,
    use_cloud: bool,
    api_key: str | None,
    pipe_dir: Path,
    curator_msg: str,
    progress: PipelineProgress | None = None,
) -> dict[str, Any]:
    """Consolidator agent plans lesson_groups; programmatic fallback on invalid output."""
    if progress is not None:
        progress.step("consolidator", detail="plan")
    curator, _ = run_consolidator_plan(
        curator,
        report_date=report_date,
        run_agent=run_agent,
        dry_run=dry_run,
        use_cloud=use_cloud,
        api_key=api_key,
        pipe_dir=pipe_dir,
        curator_msg=curator_msg,
    )
    return curator


def ensure_curator_topic_diversity(
    curator: dict[str, Any],
    report_date: str,
    *,
    dry_run: bool,
    use_cloud: bool,
    api_key: str | None,
    pipe_dir: Path | None,
    curator_msg: str,
    progress: PipelineProgress | None = None,
) -> dict[str, Any]:
    """Validate curator plan; enforce or retry until diversity rules pass."""
    curator, changed, msg = enforce_topic_diversity(curator, report_date)
    if changed:
        print(f"Topic diversity (programmatic): {msg}")

    ok, check_msg = check_topic_diversity(curator)
    if ok:
        return curator

    if dry_run:
        print(f"Warning: dry-run curator still fails diversity check: {check_msg}")
        return curator

    print(f"Topic diversity check failed ({check_msg}); retrying curator once...")
    if progress is not None:
        progress.step("curator", detail="diversity retry")
    retry_msg = curator_msg + diversity_retry_suffix(curator, check_msg)
    curator = run_agent(
        "curator",
        retry_msg,
        dry_run=False,
        use_cloud=use_cloud,
        api_key=api_key,
        pipe_dir=pipe_dir,
    )
    curator, changed, msg = enforce_topic_diversity(curator, report_date)
    if changed:
        print(f"Topic diversity after retry (programmatic): {msg}")

    ok, check_msg = check_topic_diversity(curator)
    if not ok:
        raise ValueError(f"Curator plan violates topic diversity after retry: {check_msg}")
    return curator


def lesson_markdown(
    slot: int, slug: str, title: str, pressure: str, beat: str, topic_label: str = ""
) -> str:
    """Generate dry-run lesson following teaching-style structure."""
    topic_line = f"**Topic**: {topic_label} | " if topic_label else ""
    story_block = ""
    if slot > 1:
        story_block = """
## Story so far

- You inherited a legacy keyword spam filter; leadership wants calibrated risk, not just labels.
- Priya (product) needs confidence before auto-quarantine; Legal (Marcus) wants defensible audit numbers.
- Tonight continues the spam-filter arc on the same quarantine email queue.

"""
    return f"""# {title}
**Time**: ~15 min | {topic_line}**Pressure**: {pressure}

## Scene card

You are the ML engineer on a corporate email product. **Priya** owns product decisions; **Marcus** from Legal signs audit memos. A **quarantine folder** holds emails pulled aside for review — tonight's labeled batch has **200 emails** (**148 spam**, **52 ham**). The team uses **logistic regression** on **TF-IDF word scores** (~10,000 sparse features per email, not an embedding) with **auto-quarantine at threshold 0.9**.

## Terms tonight

- **Quarantine folder** — emails held for review before release or block.
- **TF-IDF** — sparse word importance scores per email fed to logistic regression.
- **Calibration** — predicted spam rates should match observed rates in score bins.

{story_block}## The situation

You inherited the company's legacy spam filter — a brittle keyword list that fires on "winner" and "urgent" but misses sophisticated phishing. The product owner, Priya, stops you in the hallway. She's not asking for better accuracy on yesterday's batch. She's holding up two quarantine reports.

"We auto-deleted 400 messages last night," she says. "Legal wants to know how many were probably wrong. I can't tell them 'the model said so.' What can you give me?"

This is lesson {slot} of tonight's thread: *{beat}*.

## Why the obvious approach breaks

Your first instinct: pull yesterday's accuracy from the dashboard. 94% on the holdout set. Priya's face doesn't change.

"That's not what I asked. Two emails — same score from your system, both labeled spam. One was a newsletter the user actually reads every week. One was credential theft. Your dashboard treats them identically."

Accuracy answers *how often we were right*. Priya needs to know *how much to trust each decision before acting* — especially when the action is irreversible (delete) or expensive (human review).

{"Why not just threshold harder? You tried that last month — recall collapsed and phishing spiked." if slot > 1 else "Why not just report accuracy? Because a 51% spam score and a 99% spam score currently trigger the same workflow."}

## Building the mechanism

Start with a single email. Before your model sees it, you have some background rate — in this company, roughly 40% of inbound mail is unwanted. That's not a precise number; it's the **baseline you'd act on if you had nothing else**.

Now the model assigns a score. The question Priya is really asking: **given this score, what should we believe about this specific message?**

```
Prior gut feel:     ~40% of mail is spam (before reading this one)
Evidence (model):   score = 0.87
Question:           What should quarantine confidence be?
```

You don't need Bayes notation yet. You need a story where **the same label can carry different stakes depending on how sure you are**.

| Model score | Old action | Priya wants |
|-------------|------------|-------------|
| 0.52 | Quarantine | "Maybe — send to human review" |
| 0.87 | Quarantine | "Probably — auto-quarantine OK" |
| 0.99 | Delete | "Very confident — but show me why" |

The mechanism: **decisions consume uncertainty**. A mental model that only stores "spam/not spam" throws away the information Priya needs to choose an action.

## The formal tool arrives (if needed)

{"We don't need new symbols tonight — the pressure is the point." if slot <= 2 else "When you're ready to be precise: call the baseline belief P(spam) your **prior**, the model output the **likelihood evidence**, and what Priya wants the **posterior** — but only after the hallway conversation makes each piece necessary."}

## What we can now do that we couldn't before

Instead of defending accuracy, you can propose **calibrated actions**: different thresholds for delete, quarantine, and pass-through — tied to how much error each action tolerates. Priya can take this to Legal.

## Traps you would have fallen into

1. **"Our AUC is 0.96"** — Priya doesn't care about ranking quality in abstract; she cares about what to do with *this* email.
2. **"We'll just use a higher threshold"** — fixes false positives by hiding false negatives; the phishing team will notice.
3. **"Confidence equals model score"** — only valid if the model is calibrated; that's a fight for another lesson.
{"4. **Jumping to Bayes' formula** before feeling why point labels fail — notation without pressure is lecture, not learning." if slot <= 3 else ""}

## Mental model checkpoint

**Reconstruct this:** Priya rejected accuracy because decisions need **graded trust**, not binary labels. The legacy filter collapses "a little spammy" and "almost certainly malicious" into the same action. A useful mental model tracks **how much to believe** before choosing irreversible actions — not just whether we were right on average yesterday.

**Self-check:**
1. Why didn't 94% accuracy satisfy Priya?
2. What information gets thrown away when you only store spam/not-spam?
3. How would you explain "confidence" to Legal without mentioning AUC?
"""


def dry_run_response(role: str, user_message: str) -> dict[str, Any]:
    today = date.today().isoformat()
    arc = load_yaml(CURRICULUM / "narrative-arc.yaml")
    beats = arc.get("active_arc", {}).get("planned_beats", [])
    day1 = beats[0] if beats else {}
    night_lessons = day1.get("night_lessons", [])

    if role == "curator":
        topic_label = arc.get("active_arc", {}).get("topic_label", "Statistics")
        profile = load_yaml(LEARNER / "profile.yaml")
        interests = profile.get("curriculum_interests") or []
        diversity_pick = next(
            (
                i
                for i in interests
                if str(i.get("topic", "")).strip()
                and str(i.get("topic")).lower() != topic_label.lower()
            ),
            {"topic": "Monte Carlo", "pressure": "When closed-form posteriors fail, what does simulation buy us?"},
        )
        diversity_topic = str(diversity_pick.get("topic", "Monte Carlo"))
        diversity_pressure = str(
            diversity_pick.get("pressure", "Connect a related tool on the same spam-filter anchor")
        )
        lessons = []
        for i, nl in enumerate(night_lessons[:5], start=1):
            pressure = nl.get("pressure", f"Pressure for lesson {i}")
            is_diversity_slot = i == 5
            slot_topic = diversity_topic if is_diversity_slot else topic_label
            lessons.append(
                {
                    "slot": i,
                    "slug": sanitize_slug(pressure[:40], i),
                    "topic_label": slot_topic,
                    "pressure_question": diversity_pressure if is_diversity_slot else nl.get("pressure", f"Pressure for lesson {i}"),
                    "narrative_beat": day1.get("beat", "Narrative beat"),
                    "concept": day1.get("concepts", ["uncertainty"])[min(i - 1, len(day1.get("concepts", [])) - 1)],
                    "formalism_needed": i >= 3 and not is_diversity_slot,
                    "formalism_what": "Light notation only after mechanism" if i >= 3 and not is_diversity_slot else "",
                    "connects_to": [],
                    "slot_role": "bridge" if is_diversity_slot else nl.get("slot_role", "deepen"),
                    "optional": is_diversity_slot,
                }
            )
        while len(lessons) < 5:
            slot = len(lessons) + 1
            is_diversity_slot = slot == 5
            lessons.append(
                {
                    "slot": slot,
                    "slug": f"lesson-{slot:02d}",
                    "topic_label": diversity_topic if is_diversity_slot else topic_label,
                    "pressure_question": diversity_pressure if is_diversity_slot else f"Continued pressure for slot {slot}",
                    "narrative_beat": day1.get("beat", ""),
                    "concept": "uncertainty",
                    "formalism_needed": False,
                    "connects_to": [],
                    "slot_role": "bridge" if is_diversity_slot else "deepen",
                    "optional": is_diversity_slot,
                }
            )
        cur, _, _ = enforce_lesson_consolidation(
            {
                "date": today,
                "night_type": "arc",
                "pressure_invariant": "inv-calibration",
                "mastery_rung": 2,
                "activate_edges": ["E-calibration-hub"],
                "arc_id": arc.get("active_arc", {}).get("id", "spam-filter-bayes"),
                "topic_label": topic_label,
                "narrative_day": 1,
                "night_thread": day1.get("beat", "Why point estimates fail the product owner"),
                "lessons": lessons,
                "topic_queue": load_yaml(LEARNER / "topic-queue.yaml"),
                "narrative_arc_patch": {"current_day": 1},
            }
        )
        return cur

    if role == "consolidator":
        phase = "plan"
        if "Phase: draft_review" in user_message or "phase: draft_review" in user_message.lower():
            phase = "draft_review"
        elif "Phase: ship_review" in user_message or "phase: ship_review" in user_message.lower():
            phase = "ship_review"
        curator = dry_run_response("curator", user_message)
        groups = build_lesson_groups(curator)
        return {
            "date": today,
            "phase": phase,
            "published_lesson_count": len(groups),
            "lesson_groups": groups,
            "omit_from_narrative": [],
            "review_summary": {
                "pass": True,
                "escalate_to": [],
                "rationale": "Dry-run: programmatic merge suggestion accepted.",
                "curator_feedback": "",
                "teacher_feedback": "",
                "editor_feedback": "",
            },
            "group_assessments": [
                {"publish_slot": g.get("publish_slot"), "pass": True, "narrative_cohesive": True, "issues": []}
                for g in groups
            ],
        }

    if role == "research":
        curator = dry_run_response("curator", user_message)
        return {
            "date": today,
            "lessons": [
                {
                    "slot": les["slot"],
                    "sources": [
                        {
                            "title": "Calibration: What Is It?",
                            "url": "https://scikit-learn.org/stable/modules/calibration.html",
                            "type": "docs",
                            "problem_first": True,
                            "excerpt_summary": "Frames calibration as matching predicted probabilities to observed frequencies.",
                        },
                        {
                            "title": "Thinking Fast and Slow — reference framing",
                            "url": "https://en.wikipedia.org/wiki/Calibration_(statistics)",
                            "type": "reference",
                            "problem_first": True,
                            "excerpt_summary": "Reliability diagrams show when confidence scores lie.",
                        },
                    ],
                    "confusion_points_to_address": [
                        "Why not just use accuracy?",
                        "Isn't the model score already a probability?",
                    ],
                    "visual_ideas": [
                        "ASCII reliability diagram: predicted vs observed spam rate",
                    ],
                    "avoid_sources": ["Definition-first probability textbooks"],
                }
                for les in curator["lessons"]
            ],
        }

    if role == "teacher":
        curator = dry_run_response("curator", user_message)
        groups = curator.get("lesson_groups") or []
        lessons_out = []
        for g in groups:
            ps = int(g.get("publish_slot") or len(lessons_out) + 1)
            topic = g.get("topic_label", curator.get("topic_label", ""))
            concepts = [c for c in g.get("concepts") or [] if c]
            pressure = g.get("pressure_questions", [""])[0] if g.get("pressure_questions") else f"Merged lesson on {topic}"
            if len(concepts) > 1:
                pressure = f"End-to-end {topic}: " + " → ".join(concepts)
            slug = sanitize_slug(pressure[:40], ps)
            title = topic_prefixed_title(topic, pressure)
            md = lesson_markdown(
                ps,
                slug,
                title,
                pressure,
                g.get("narrative_beats", [""])[0] if g.get("narrative_beats") else "",
                topic,
            )
            lessons_out.append(
                {
                    "slot": ps,
                    "slug": slug,
                    "topic_label": topic,
                    "title": title,
                    "estimated_minutes": 15 + 5 * max(0, len(g.get("source_slots") or []) - 1),
                    "word_count": len(md.split()),
                    "markdown": md,
                    "merged_from_slots": g.get("source_slots") or [],
                    "concepts_covered": concepts,
                }
            )
        index_lines = [
            f"# Daily Learning — {today}",
            "",
            f"**Topic:** {curator.get('topic_label', '')}",
            "",
            f"**Tonight's thread:** {curator['night_thread']}",
            "",
            f"**Arc:** {curator['arc_id']} (day {curator['narrative_day']})",
            "",
            "## Lessons",
            "",
        ]
        for les in lessons_out:
            index_lines.append(
                f"- [ ] [{les['slot']:02d}. {les['title']}](./{les['slot']:02d}-{les['slug']}.md) — ~{les['estimated_minutes']} min"
            )
        index_lines.extend(["", "Mark read/skip in `learner/engagement.yaml` after reading.", ""])
        return {
            "date": today,
            "night_thread": curator["night_thread"],
            "index_md": "\n".join(index_lines),
            "lessons": lessons_out,
        }

    if role == "hypothesis":
        return {
            "date": today,
            "new_hypotheses": [
                {
                    "id": "H-001",
                    "type": "mechanism",
                    "statement": "Binary labels discard the graded trust needed for irreversible actions — decisions consume uncertainty, not just correctness.",
                    "confidence": "low",
                    "evidence": [f"{today}-lesson-01"],
                    "depends_on": [],
                    "narrative_beat": "spam-filter-bayes/day-1",
                    "confusion_addressed": ["why_not_just_accuracy"],
                    "supersedes": None,
                },
                {
                    "id": "H-002",
                    "type": "mechanism",
                    "statement": "A model score is not the same as a calibrated probability — calibration means predicted rates match observed rates.",
                    "confidence": "low",
                    "evidence": [f"{today}-lesson-03"],
                    "depends_on": ["H-001"],
                    "edge_refs": ["E-calibration-hub"],
                    "invariant": "inv-calibration",
                    "narrative_beat": "spam-filter-bayes/day-1",
                    "confusion_addressed": ["score_equals_probability"],
                    "supersedes": None,
                },
            ],
            "confidence_updates": [],
            "gaps": [
                {
                    "pressure": "How do we update belief after each labeled email?",
                    "related_beat": "spam-filter-bayes/day-2",
                    "priority": "high",
                }
            ],
        }

    if role == "editor":
        teacher = dry_run_response("teacher", user_message)
        lessons = []
        for les in teacher["lessons"]:
            lessons.append(
                {
                    "slot": les["slot"],
                    "slug": les["slug"],
                    "markdown": les["markdown"],
                    "word_count": les["word_count"],
                    "style_pass": True,
                    "style_violations": [],
                    "models_strengthened": ["H-001"],
                }
            )
        return {
            "date": today,
            "index_md": teacher["index_md"],
            "lessons": lessons,
            "review_summary": {
                "all_pass": True,
                "notes": "Dry-run: style checks passed.",
                "graph_ready_for_grapher": True,
            },
        }

    if role == "grapher":
        return {
            "date": today,
            "quality_scores": {
                "clarity": 4,
                "mechanism_depth": 4,
                "graph_integration": 3,
                "learning_outcomes": 4,
                "narrative_continuity": 5,
            },
            "new_edges": [],
            "edges_strengthened": ["E-calibration-hub"],
            "hypothesis_audit": [],
            "lesson_feedback": [],
            "curator_guidance": {
                "next_night_focus": "Deepen calibration — scores vs decisions on identical emails",
                "avoid": ["Re-explaining accuracy"],
                "emphasize_edges": ["E-calibration-hub"],
                "mastery_rung_target": 3,
                "recommended_night_type": "bridge",
                "pressure_invariant": "inv-calibration",
            },
            "summary": "Dry-run: calibration invariant linked to spam-filter arc; schedule a bridge night contrasting score types.",
        }

    raise ValueError(f"Unknown role: {role}")


def append_hypotheses(new_entries: list[dict[str, Any]]) -> None:
    path = LEARNER / "hypotheses.jsonl"
    existing = read_jsonl(path)
    existing_ids = {e.get("id") for e in existing}
    with path.open("a", encoding="utf-8") as f:
        for entry in new_entries:
            if entry.get("id") not in existing_ids:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def apply_confidence_updates(updates: list[dict[str, Any]]) -> int:
    """Apply hypothesis agent confidence_updates to learner/hypotheses.jsonl."""
    if not updates:
        return 0
    path = LEARNER / "hypotheses.jsonl"
    entries = read_jsonl(path)
    update_by_id = {u["id"]: u for u in updates if u.get("id")}
    if not update_by_id:
        return 0

    applied = 0
    touched = False
    for entry in entries:
        hid = entry.get("id")
        if hid not in update_by_id:
            continue
        upd = update_by_id[hid]
        new_conf = upd.get("new_confidence")
        if new_conf and new_conf != entry.get("confidence"):
            entry["confidence"] = new_conf
            applied += 1
            touched = True
        if upd.get("reason"):
            entry["confidence_reason"] = upd["reason"]
            touched = True

    if touched:
        lines = [json.dumps(e, ensure_ascii=False) for e in entries]
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return applied


def persist_gaps(new_gaps: list[dict[str, Any]], report_date: str) -> None:
    """Merge nightly gaps into learner/gaps.yaml (persistent, not gitignored)."""
    if not new_gaps:
        return
    path = LEARNER / "gaps.yaml"
    data = load_yaml(path)
    if not isinstance(data, dict):
        data = {}
    existing: list[dict[str, Any]] = list(data.get("gaps") or [])
    seen = {(g.get("pressure") or "").strip() for g in existing if g.get("pressure")}
    for gap in new_gaps:
        pressure = (gap.get("pressure") or "").strip()
        if not pressure or pressure in seen:
            continue
        existing.append({**gap, "added_on": report_date})
        seen.add(pressure)
    data["gaps"] = existing
    data["last_updated"] = report_date
    dump_yaml(path, data)


def append_concept_edges(new_edges: list[dict[str, Any]], report_date: str) -> int:
    """Append grapher-discovered edges to learner/concept-edges.jsonl."""
    if not new_edges:
        return 0
    path = LEARNER / "concept-edges.jsonl"
    existing = read_jsonl(path)
    existing_ids = {e.get("id") for e in existing if e.get("id")}
    added = 0
    with path.open("a", encoding="utf-8") as f:
        for edge in new_edges:
            eid = edge.get("id")
            if not eid or eid in existing_ids:
                continue
            row = {**edge, "added_on": report_date}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            existing_ids.add(eid)
            added += 1
    return added


def persist_pedagogy_feedback(grapher: dict[str, Any], report_date: str) -> None:
    """Store grapher output — delegates to memory consolidator."""
    consolidate_memory(grapher, report_date)


def clamp_arc_patch_for_light_mode(
    curator: dict[str, Any],
    *,
    light_mode: bool,
    advance: bool,
) -> None:
    """In light mode, block narrative_arc_patch from increasing current_day."""
    if not light_mode or advance:
        return
    patch = curator.get("narrative_arc_patch")
    if not patch or "current_day" not in patch:
        return
    arc = load_yaml(CURRICULUM / "narrative-arc.yaml")
    current = arc.get("active_arc", {}).get("current_day", 1)
    proposed = patch["current_day"]
    if proposed > current:
        print(
            f"Light mode: keeping current_day={current} "
            f"(curator proposed {proposed}; pass --advance to allow arc advance)"
        )
        patch["current_day"] = current


def update_narrative_arc(patch: dict[str, Any]) -> None:
    path = CURRICULUM / "narrative-arc.yaml"
    data = load_yaml(path)
    if "current_day" in patch:
        data.setdefault("active_arc", {})["current_day"] = patch["current_day"]
    dump_yaml(path, data)


def update_topic_queue(topic_queue: dict[str, Any]) -> None:
    if topic_queue:
        dump_yaml(LEARNER / "topic-queue.yaml", topic_queue)


def persist_pipeline_state(
    *,
    report_date: str,
    pipe_dir: Path,
    curator: dict[str, Any],
    hypothesis: dict[str, Any],
    grapher: dict[str, Any],
) -> None:
    """Write learner/curriculum state after a successful report."""
    append_hypotheses(hypothesis.get("new_hypotheses", []))
    n_updated = apply_confidence_updates(hypothesis.get("confidence_updates", []))
    if n_updated:
        print(f"Applied {n_updated} hypothesis confidence update(s).")
    n_edges = append_concept_edges(grapher.get("new_edges", []), report_date)
    if n_edges:
        print(f"Added {n_edges} concept graph edge(s).")
    mem = consolidate_memory(grapher, report_date)
    if mem.get("carry_forward_count") or mem.get("proposed_rules_added"):
        print(
            f"Memory consolidator: {mem.get('carry_forward_count', 0)} carry-forward bullet(s), "
            f"{mem.get('proposed_rules_added', 0)} proposed playbook rule(s)"
        )
    if curator.get("narrative_arc_patch"):
        update_narrative_arc(curator["narrative_arc_patch"])
    if curator.get("topic_queue"):
        update_topic_queue(curator["topic_queue"])

    gaps = hypothesis.get("gaps", [])
    (pipe_dir / "gaps.json").write_text(json.dumps(gaps, indent=2), encoding="utf-8")
    persist_gaps(gaps, report_date)


def write_report(
    report_date: str,
    editor: dict[str, Any],
    curator: dict[str, Any],
    research: dict[str, Any],
    hypothesis: dict[str, Any],
    grapher: dict[str, Any],
    *,
    skip_lint: bool = False,
) -> Path:
    out_dir = REPORTS / report_date
    out_dir.mkdir(parents=True, exist_ok=True)

    lint = lint_editor_output(editor, curator)
    if not skip_lint and not lint.passed:
        raise RuntimeError(f"Refusing to write report — editor pass gate failed:\n{lint.summary()}")

    # Remove stale lesson files from prior runs (keep index/meta until rewritten)
    for old in out_dir.glob("[0-9][0-9]-*.md"):
        old.unlink(missing_ok=True)

    (out_dir / "index.md").write_text(editor["index_md"], encoding="utf-8")

    for les in editor["lessons"]:
        slug = les["slug"]
        slot = les["slot"]
        filename = f"{slot:02d}-{slug}.md"
        md = les.get("markdown") or ""
        validate_lesson_markdown(md, source=f"{report_date}/{filename}")
        (out_dir / filename).write_text(md, encoding="utf-8")

    meta = {
        "date": report_date,
        "night_type": curator.get("night_type"),
        "pressure_invariant": curator.get("pressure_invariant"),
        "mastery_rung": curator.get("mastery_rung"),
        "activate_edges": curator.get("activate_edges", []),
        "arc_id": curator.get("arc_id"),
        "topic_label": curator.get("topic_label"),
        "narrative_day": curator.get("narrative_day"),
        "night_thread": curator.get("night_thread"),
        "lessons": [
            {
                "slot": l["slot"],
                "slug": l["slug"],
                "topic_label": l.get("topic_label")
                or next(
                    (
                        g.get("topic_label")
                        for g in curator.get("lesson_groups") or []
                        if int(l["slot"]) == int(g.get("publish_slot") or 0)
                    ),
                    curator.get("topic_label", ""),
                ),
                "concept": ", ".join(l.get("concepts_covered") or [])
                or l.get("concept")
                or next(
                    (
                        ", ".join(c for c in g.get("concepts") or [] if c)
                        for g in curator.get("lesson_groups") or []
                        if int(l["slot"]) == int(g.get("publish_slot") or 0)
                    ),
                    "",
                ),
                "pressure_question": l.get("title") or "",
                "merged_from_slots": l.get("merged_from_slots") or [],
            }
            for l in editor["lessons"]
        ],
        "lesson_groups": curator.get("lesson_groups") or [],
        "published_lesson_count": len(editor.get("lessons") or []),
        "sources_summary": [
            {"slot": r["slot"], "source_count": len(r.get("sources", []))}
            for r in research.get("lessons", [])
        ],
        "hypotheses_added": [h.get("id") for h in hypothesis.get("new_hypotheses", [])],
        "grapher_scores": grapher.get("quality_scores"),
        "pedagogy_summary": grapher.get("summary"),
        "edges_added": [e.get("id") for e in grapher.get("new_edges", [])],
        "generated_at": datetime.now().isoformat(),
    }
    dump_yaml(out_dir / "meta.yaml", meta)
    return out_dir


def git_commit_push(report_date: str, message: str, *, skip_push: bool) -> None:
    subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True)
    if not status.stdout.strip():
        print("Nothing to commit.")
        return
    subprocess.run(["git", "commit", "-m", message], cwd=ROOT, check=True)
    if skip_push:
        print("Skipping push (--no-push).")
        return
    subprocess.run(["git", "push"], cwd=ROOT, check=True)


def rebuild_site() -> None:
    build_script = ROOT / "site" / "build.py"
    if not build_script.exists():
        return
    sync_learner_state(prune=False)
    sync_spine_progress()
    print("Building site...")
    subprocess.run([sys.executable, str(build_script)], cwd=ROOT, check=True)


def pipeline(
    report_date: str,
    *,
    dry_run: bool,
    force: bool,
    use_cloud: bool,
    skip_push: bool,
    skip_site: bool,
    advance: bool = False,
    max_refinement_depth: int = DEFAULT_REFINEMENT_DEPTH,
) -> None:
    report_dir = REPORTS / report_date
    if report_dir.joinpath("index.md").exists() and not force:
        print(f"Report for {report_date} already exists. Use --force to overwrite.")
        sys.exit(0)

    if force:
        removed = cleanup_run_artifacts(root=ROOT)
        if removed:
            print(f"--force: removed {len(removed)} stale run artifact(s):")
            for path in removed:
                print(f"  - {path}")

    api_key = os.environ.get("CURSOR_API_KEY")
    if not dry_run and not api_key:
        print("CURSOR_API_KEY not set. Use --dry-run for offline test.")
        sys.exit(1)

    pipe_dir = PIPELINE / report_date
    pipe_dir.mkdir(parents=True, exist_ok=True)

    sync_spine_progress()
    sync_arc_yaml_to_published(dry_run=dry_run)
    engagement_summary = compute_engagement_summary(report_date)
    (pipe_dir / "engagement-summary.json").write_text(
        json.dumps(engagement_summary, indent=2), encoding="utf-8"
    )
    light_mode = engagement_summary["recommended_mode"] in ("light", "recap")
    if light_mode:
        print(
            f"Adaptive pacing: {engagement_summary['recommended_mode']} mode "
            f"(last night unread={engagement_summary['last_night_unread']})"
        )

    migrate_pedagogy_history()
    suggested_night = suggest_night_type(report_date)
    run_brief = build_run_brief(
        report_date,
        engagement_summary=engagement_summary,
        suggested_night_type=suggested_night,
    )
    save_run_brief(run_brief)

    context = agent_context("curator", report_date=report_date, pipe_dir=pipe_dir)
    meta_context = recent_meta_compact()
    progress = PipelineProgress()

    progress.step("curator")
    curator_msg = (
        f"Today is {report_date}.\n\n"
        f"Suggested night_type from schedule (override only with reason): {suggested_night}\n\n"
        f"Engagement summary (orchestrator-computed — honor recommended_mode):\n"
        f"{json.dumps(engagement_summary, indent=2)}\n\n"
        f"Topic diversity (hard rule): at most 4 of 5 lessons may share the same "
        f"topic_label. At least 1 lesson MUST use a different topic from "
        f"topic-queue, curriculum_interests, bridge_night_templates, or seed_edges "
        f"(slot 5 bridge on the same anchor is the default pattern on arc nights). "
        f"Exploration nights (Sunday) may use one far-field topic for all 5.\n\n"
        f"Master spine: cite spine_phase from spine-progress; defer exploration if rung below depth_budget.\n\n"
        f"Context:\n{context}\n\n"
        f"Recent reports:\n{meta_context}\n\n"
        f"Plan up to 5 planning slots, then set lesson_groups so tonight ships "
        f"{MIN_PUBLISHED_LESSONS}–{MAX_PUBLISHED_LESSONS} published lessons (merge same-topic slots)."
    )
    curator = run_agent(
        "curator", curator_msg, dry_run=dry_run, use_cloud=use_cloud, api_key=api_key, pipe_dir=pipe_dir
    )
    curator = ensure_curator_topic_diversity(
        curator,
        report_date,
        dry_run=dry_run,
        use_cloud=use_cloud,
        api_key=api_key,
        pipe_dir=pipe_dir,
        curator_msg=curator_msg,
        progress=progress,
    )
    curator = apply_prerequisite_gate(
        curator,
        report_date,
        dry_run=dry_run,
        use_cloud=use_cloud,
        api_key=api_key,
        pipe_dir=pipe_dir,
        curator_msg=curator_msg,
        progress=progress,
    )
    curator = ensure_curator_lesson_consolidation(
        curator,
        report_date=report_date,
        dry_run=dry_run,
        use_cloud=use_cloud,
        api_key=api_key,
        pipe_dir=pipe_dir,
        curator_msg=curator_msg,
        progress=progress,
    )
    clamp_arc_patch_for_light_mode(curator, light_mode=light_mode, advance=advance)
    validate_curator_arc(curator, report_date)
    _warn_curator_summary(curator)
    (pipe_dir / "curator.json").write_text(json.dumps(curator, indent=2), encoding="utf-8")

    progress.step("research")
    research_context = agent_context("research", report_date=report_date, pipe_dir=pipe_dir)
    research_msg = f"Curator plan:\n{json.dumps(curator, indent=2)}\n\nContext:\n{research_context}"
    research = run_agent(
        "research", research_msg, dry_run=dry_run, use_cloud=use_cloud, api_key=api_key, pipe_dir=pipe_dir
    )
    (pipe_dir / "research.json").write_text(json.dumps(research, indent=2), encoding="utf-8")

    published_n = int(curator.get("published_lesson_count") or len(curator.get("lesson_groups") or []))
    teacher_context = agent_context("teacher", report_date=report_date, pipe_dir=pipe_dir)

    teacher_msg = (
        f"Pipeline run date (use as top-level \"date\"): {report_date}\n\n"
        f"Curator plan:\n{json.dumps(curator, indent=2)}\n\n"
        f"Research:\n{json.dumps(research, indent=2)}\n\n"
        f"Pedagogy (latest):\n{format_pedagogy_for_agents()}\n\n"
        f"Write {published_n} complete standalone published lessons (Scene card + Terms tonight each).\n"
        f"Merge same-topic planning slots into one narrative — do not write {MAX_PLANNING_SLOTS} separate articles.\n"
        f"{format_consolidation_for_teacher(curator)}\n"
        f"Consolidator rationale: "
        f"{json.dumps((curator.get('consolidation') or {}).get('review_summary') or {}, indent=2)}\n"
        f"Honor lesson_groups narrative_spine and omit_from_narrative — the consolidator agent approved this merge plan.\n"
        f"Include plan_review — reject the curator plan if it violates playbook teaching rules before writing.\n\n"
        f"Context:\n{teacher_context}"
    )

    from lib.lesson_chat import format_for_editor

    learner_questions = format_for_editor()
    teaching_style = (
        format_playbook_for_role("editor")
        + "\n\nHuman reference (detail): learner/teaching-style.md"
    )

    def run_research_for_curator(cur: dict[str, Any]) -> dict[str, Any]:
        msg = (
            f"Curator plan:\n{json.dumps(cur, indent=2)}\n\n"
            f"Context:\n{research_context}"
        )
        return run_agent(
            "research",
            msg,
            dry_run=dry_run,
            use_cloud=use_cloud,
            api_key=api_key,
            pipe_dir=pipe_dir,
        )

    editor_base_msg = (
        f"Curator plan:\n{json.dumps(curator, indent=2)}\n\n"
        f"Research:\n{json.dumps(research, indent=2)}\n\n"
        f"Teacher drafts:\n{{teacher_json}}\n\n"
        f"Consolidator lesson_groups (narrative contract):\n"
        f"{json.dumps(curator.get('lesson_groups') or [], indent=2)}\n\n"
        f"Teaching style:\n{teaching_style}\n\n"
        f"Learner follow-up questions:\n{learner_questions}\n\n"
        f"Merged lessons must read as single end-to-end narratives per consolidator plan."
    )

    def post_teacher_hook(cur: dict[str, Any], teacher_out: dict[str, Any]) -> dict[str, Any]:
        teacher_out, cons_out, retry = run_consolidator_draft_review(
            report_date=report_date,
            curator=cur,
            teacher=teacher_out,
            run_agent=run_agent,
            dry_run=dry_run,
            use_cloud=use_cloud,
            api_key=api_key,
            pipe_dir=pipe_dir,
        )
        if retry:
            cleared = clear_agent_sidecars(report_date=report_date)
            if cleared:
                print(f"Cleared stale sidecars before consolidator teacher retry: {', '.join(cleared)}")
            teacher_out = run_agent(
                "teacher",
                teacher_msg + consolidator_feedback_suffix(cons_out, target="teacher"),
                dry_run=False,
                use_cloud=use_cloud,
                api_key=api_key,
                pipe_dir=pipe_dir / "consolidator-teacher-retry",
                report_date=report_date,
            )
            teacher_out = enrich_lessons_from_groups(teacher_out, cur)
        return teacher_out

    def pre_ship_hook(
        cur: dict[str, Any], teacher_out: dict[str, Any], editor_out: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        editor_out, cons_out, targets = run_consolidator_ship_review(
            report_date=report_date,
            curator=cur,
            teacher=teacher_out,
            editor=editor_out,
            run_agent=run_agent,
            dry_run=dry_run,
            use_cloud=use_cloud,
            api_key=api_key,
            pipe_dir=pipe_dir,
        )
        if review_passes(cons_out) or dry_run:
            return editor_out, True
        if "editor" in targets:
            cleared = clear_agent_sidecars(report_date=report_date)
            if cleared:
                print(f"Cleared stale sidecars before consolidator editor retry: {', '.join(cleared)}")
            editor_out = run_agent(
                "editor",
                editor_base_msg.replace("{teacher_json}", json.dumps(teacher_out, indent=2)[:120000])
                + consolidator_feedback_suffix(cons_out, target="editor"),
                dry_run=False,
                use_cloud=use_cloud,
                api_key=api_key,
                pipe_dir=pipe_dir / "consolidator-editor-retry",
                report_date=report_date,
            )
            editor_out = enrich_lessons_from_groups(editor_out, cur)
            return editor_out, False
        if "teacher" in targets:
            raise RuntimeError(
                "Consolidator ship_review requires teacher revision — "
                + str((cons_out.get("review_summary") or {}).get("teacher_feedback") or "")
            )
        if "curator" in targets:
            raise RuntimeError(
                "Consolidator ship_review requires curator replan — "
                + str((cons_out.get("review_summary") or {}).get("curator_feedback") or "")
            )
        return editor_out, True

    def post_curator_hook(cur: dict[str, Any]) -> dict[str, Any]:
        cur = ensure_curator_topic_diversity(
            cur,
            report_date,
            dry_run=dry_run,
            use_cloud=use_cloud,
            api_key=api_key,
            pipe_dir=pipe_dir,
            curator_msg=curator_msg,
            progress=progress,
        )
        cur = apply_prerequisite_gate(
            cur,
            report_date,
            dry_run=dry_run,
            use_cloud=use_cloud,
            api_key=api_key,
            pipe_dir=pipe_dir,
            curator_msg=curator_msg,
            progress=progress,
        )
        clamp_arc_patch_for_light_mode(cur, light_mode=light_mode, advance=advance)
        validate_curator_arc(cur, report_date)
        _warn_curator_summary(cur)
        return ensure_curator_lesson_consolidation(
            cur,
            report_date=report_date,
            dry_run=dry_run,
            use_cloud=use_cloud,
            api_key=api_key,
            pipe_dir=pipe_dir,
            curator_msg=curator_msg,
            progress=progress,
        )

    curator, research, teacher, editor, _lint = run_content_refinement(
        curator=curator,
        research=research,
        teacher=None,
        curator_base_msg=curator_msg,
        teacher_base_msg=teacher_msg,
        teaching_style=teaching_style,
        learner_questions=learner_questions,
        run_agent=run_agent,
        run_research=run_research_for_curator,
        post_curator=post_curator_hook,
        pipe_dir=pipe_dir,
        dry_run=dry_run,
        use_cloud=use_cloud,
        api_key=api_key,
        max_depth=max_refinement_depth,
        hypothesis=None,
        report_date=report_date,
        progress=progress,
        post_teacher_hook=post_teacher_hook,
        pre_ship_hook=pre_ship_hook,
    )
    (pipe_dir / "curator.json").write_text(json.dumps(curator, indent=2), encoding="utf-8")
    (pipe_dir / "research.json").write_text(json.dumps(research, indent=2), encoding="utf-8")
    (pipe_dir / "teacher.json").write_text(json.dumps(teacher, indent=2), encoding="utf-8")

    progress.step("hypothesis")
    topic_label = curator.get("topic_label")
    lessons_for_hyp = {
        "date": editor.get("date", report_date),
        "lessons": editor.get("lessons", []),
    }
    hypothesis_msg = (
        f"Curator plan:\n{json.dumps(curator, indent=2)}\n\n"
        f"Lessons (editor final — shipped text):\n{json.dumps(lessons_for_hyp, indent=2)}\n\n"
        f"Existing hypotheses (filtered context):\n"
        f"{format_hypotheses_context(topic_label=topic_label)}"
    )
    hypothesis = run_agent(
        "hypothesis", hypothesis_msg, dry_run=dry_run, use_cloud=use_cloud, api_key=api_key, pipe_dir=pipe_dir
    )
    (pipe_dir / "hypothesis.json").write_text(json.dumps(hypothesis, indent=2), encoding="utf-8")

    progress.step("grapher")
    grapher_msg = (
        f"Curator plan:\n{json.dumps(curator, indent=2)}\n\n"
        f"Teacher drafts:\n{json.dumps(teacher, indent=2)}\n\n"
        f"Hypothesis output:\n{json.dumps(hypothesis, indent=2)}\n\n"
        f"Editor final:\n{json.dumps(editor, indent=2)}\n\n"
        f"Concept graph and existing edges in context:\n{context}\n\n"
        f"Evaluate quality, extract edges, produce curator_guidance for tomorrow."
    )
    grapher = run_agent(
        "grapher", grapher_msg, dry_run=dry_run, use_cloud=use_cloud, api_key=api_key, pipe_dir=pipe_dir
    )
    (pipe_dir / "grapher.json").write_text(json.dumps(grapher, indent=2), encoding="utf-8")

    scores = grapher.get("quality_scores") or {}
    if scores:
        print(
            f"Grapher scores: clarity={scores.get('clarity')} depth={scores.get('mechanism_depth')} "
            f"graph={scores.get('graph_integration')} outcomes={scores.get('learning_outcomes')}"
        )

    out_dir = write_report(
        report_date, editor, curator, research, hypothesis, grapher, skip_lint=dry_run
    )
    print(f"Wrote report to {out_dir}")

    persist_pipeline_state(
        report_date=report_date,
        pipe_dir=pipe_dir,
        curator=curator,
        hypothesis=hypothesis,
        grapher=grapher,
    )

    if not skip_site:
        rebuild_site()

    beat = curator.get("night_thread", "learning")
    n_lessons = len(editor.get("lessons") or [])
    msg = f"daily: {report_date} {n_lessons} lessons on {beat}"
    if dry_run:
        msg = f"dry-run: {report_date} {n_lessons} lessons on {beat}"

    git_commit_push(report_date, msg, skip_push=skip_push or dry_run)
    print(f"Pipeline complete ({progress.count} agent steps).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Nightly learning pipeline (local by default)")
    parser.add_argument("--date", default=date.today().isoformat(), help="Report date YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="Offline mode without Cursor API")
    parser.add_argument("--force", action="store_true", help="Overwrite existing report and remove stale sidecar/script artifacts")
    parser.add_argument("--cloud", action="store_true", help="Use cloud agent runtime (default: local)")
    parser.add_argument("--push", action="store_true", help="Git push after commit")
    parser.add_argument("--skip-site", action="store_true", help="Skip HTML site rebuild")
    parser.add_argument(
        "--advance",
        action="store_true",
        help="Allow narrative arc to advance even in light/recap mode",
    )
    parser.add_argument(
        "--max-refinement-depth",
        type=int,
        default=DEFAULT_REFINEMENT_DEPTH,
        help=(
            "Max curator replans and teacher↔editor revision passes per plan "
            f"(default {DEFAULT_REFINEMENT_DEPTH} → {DEFAULT_REFINEMENT_DEPTH + 1} editor passes, "
            f"minimum {1})"
        ),
    )
    args = parser.parse_args()
    args.max_refinement_depth = normalize_refinement_depth(args.max_refinement_depth)

    pipeline(
        args.date,
        dry_run=args.dry_run,
        force=args.force,
        use_cloud=args.cloud,
        skip_push=not args.push,
        skip_site=args.skip_site,
        advance=args.advance,
        max_refinement_depth=args.max_refinement_depth,
    )


if __name__ == "__main__":
    main()
