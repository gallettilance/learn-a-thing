#!/usr/bin/env python3
"""Build static HTML site from reports, hypotheses, and curriculum."""

from __future__ import annotations

import html
import json
import random
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import markdown
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.active_state import load_active_graph, load_active_hypotheses, load_active_state, sync_learner_state  # noqa: E402
from lib.lesson_content import is_lesson_markdown_stub  # noqa: E402
from lib.spine_state import sync_spine_progress  # noqa: E402
from lib.titles import parse_topic_from_title, topic_prefixed_title, topic_slug  # noqa: E402
from lib.anchor_primer import all_arc_report_links, get_anchor_primer, html_reference_panel, load_anchor_primers, prior_night_links  # noqa: E402
from lib.topic_mastery import is_topic_mastered  # noqa: E402
from lib.concept_mastery import is_concept_mastered_user  # noqa: E402

SITE = Path(__file__).resolve().parent
PUBLIC = SITE / "public"
LEARNER = ROOT / "learner"
CURRICULUM = ROOT / "curriculum"
REPORTS = ROOT / "reports"

MD = markdown.Markdown(
    extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
    output_format="html5",
)


def esc(text: str) -> str:
    return html.escape(str(text))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(json.loads(line))
    return out


def load_yaml(path: Path) -> Any:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def render_md(text: str) -> str:
    MD.reset()
    return MD.convert(text)


def display_title(meta_lesson: dict, fallback: str = "") -> str:
    topic = meta_lesson.get("topic_label") or ""
    question = meta_lesson.get("pressure_question") or fallback
    if topic:
        return topic_prefixed_title(topic, question)
    return question or fallback


def topic_badge(topic_label: str, *, mastered: bool | None = None) -> str:
    if not topic_label:
        return ""
    m = is_topic_mastered(topic_label) if mastered is None else mastered
    cls = " topic-pill-mastered" if m else ""
    mark = ' <span class="mastered-mark" title="Topic mastered">✓</span>' if m else ""
    return f'<span class="topic-pill{cls}">{esc(topic_label)}{mark}</span>'


def topic_mastery_html(topic_label: str) -> str:
    if not topic_label:
        return ""
    mastered = is_topic_mastered(topic_label)
    checked = " checked" if mastered else ""
    return f"""
    <section class="topic-mastery-inline" data-topic="{esc(topic_label)}">
      <label class="topic-mastery-label">
        <input type="checkbox" name="mastered"{checked} />
        <span class="topic-mastery-text">Already know this topic</span>
      </label>
      <p class="hint topic-mastery-hint">Whole-topic claim — skips intro pacing. Does <strong>not</strong> mark every concept in this topic mastered for prerequisite gating.</p>
      <p class="form-msg" hidden></p>
    </section>"""


def concept_mastery_html(concept_id: str, *, topic_label: str = "", lesson_ref: str = "") -> str:
    if not concept_id:
        return ""
    mastered = is_concept_mastered_user(concept_id)
    checked = " checked" if mastered else ""
    return f"""
    <section class="concept-mastery-inline" data-concept="{esc(concept_id)}" data-topic="{esc(topic_label)}" data-lesson-ref="{esc(lesson_ref)}">
      <label class="concept-mastery-label">
        <input type="checkbox" name="concept_mastered"{checked} />
        <span class="concept-mastery-text">I mastered this lesson's concept (<code>{esc(concept_id)}</code>)</span>
      </label>
      <p class="hint concept-mastery-hint">Prerequisite gate uses this — not the whole topic. Example: first-order derivatives yes, Jacobians still blocked.</p>
      <p class="form-msg" hidden></p>
    </section>"""


def lesson_chat_html(report_date: str, lesson_id: str, topic_label: str) -> str:
    return f"""
    <section class="lesson-chat" data-date="{esc(report_date)}" data-lesson="{esc(lesson_id)}" data-topic="{esc(topic_label)}">
      <h3>Ask a follow-up</h3>
      <p class="hint">Questions you ask here inform the editor — they become anticipated traps and checkpoints in future lessons.</p>
      <div class="lesson-chat-log" aria-live="polite"></div>
      <form class="lesson-chat-form">
        <textarea name="message" rows="3" placeholder="What still feels fuzzy? What would you ask in the hallway?"></textarea>
        <button type="submit">Send</button>
        <p class="form-msg" hidden></p>
      </form>
    </section>"""


def confidence_class(level: str) -> str:
    return {"low": "conf-low", "medium": "conf-medium", "high": "conf-high"}.get(level, "")


def load_hypothesis_confidence() -> dict[str, Any]:
    return load_yaml(LEARNER / "hypothesis-confidence.yaml")


def load_gaps() -> list[dict[str, Any]]:
    data = load_yaml(LEARNER / "gaps.yaml")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        gaps = data.get("gaps", [])
        return gaps if isinstance(gaps, list) else []
    return []


def lesson_optional_flags(
    meta: dict[str, Any], lessons_meta: dict[int, dict[str, Any]], num_lessons: int
) -> dict[int, bool]:
    """Slot → optional (stretch). Explicit flags win; else slots 4–5 are stretch."""
    has_explicit = any(lessons_meta.get(i, {}).get("optional") for i in range(1, num_lessons + 1))
    optional_slots = meta.get("optional_slots") or []
    flags: dict[int, bool] = {}
    for i in range(1, num_lessons + 1):
        m = lessons_meta.get(i, {})
        if m.get("optional") is True:
            flags[i] = True
        elif optional_slots:
            flags[i] = i in optional_slots
        elif has_explicit:
            flags[i] = bool(m.get("optional"))
        else:
            flags[i] = i >= 4
    return flags


def night_read_progress(
    report_date: str,
    engagement: dict[str, Any],
    meta: dict[str, Any],
    num_lessons: int,
) -> dict[str, int]:
    lessons_meta = {m["slot"]: m for m in meta.get("lessons", [])}
    optional = lesson_optional_flags(meta, lessons_meta, num_lessons)
    day_eng = engagement.get(report_date, {})
    core_read = stretch_read = core_total = stretch_total = 0
    for i in range(1, num_lessons + 1):
        key = f"lesson-{i:02d}"
        status = day_eng.get(key, {}).get("status", "unread")
        is_read = status == "read"
        if optional.get(i):
            stretch_total += 1
            if is_read:
                stretch_read += 1
        else:
            core_total += 1
            if is_read:
                core_read += 1
    return {
        "core_read": core_read,
        "core_total": core_total,
        "stretch_read": stretch_read,
        "stretch_total": stretch_total,
    }


def find_continue_target(
    dates: list[str], engagement: dict[str, Any]
) -> tuple[str, int] | None:
    """First unread lesson in latest night, or last partially-read night."""
    if not dates:
        return None
    for d in dates:
        files = lesson_files(d)
        if not files:
            continue
        day_eng = engagement.get(d, {})
        statuses = [
            day_eng.get(f"lesson-{i:02d}", {}).get("status", "unread")
            for i in range(1, len(files) + 1)
        ]
        unread = [i for i, st in enumerate(statuses, 1) if st == "unread"]
        if not unread:
            continue
        read_n = sum(1 for st in statuses if st == "read")
        if d == dates[0] or read_n > 0:
            return d, unread[0]
    return None


def progress_label(progress: dict[str, int]) -> str:
    parts = [f"Core: {progress['core_read']}/{progress['core_total']} read"]
    if progress["stretch_total"] > 0:
        parts.append(f"Stretch: {progress['stretch_read']}/{progress['stretch_total']}")
    return " · ".join(parts)


def slot_kind_badge(is_optional: bool, show_kinds: bool) -> str:
    if not show_kinds:
        return ""
    kind = "stretch" if is_optional else "core"
    return f'<span class="badge slot-{kind}">{kind}</span>'


def extract_self_check_questions(md_text: str) -> list[str]:
    match = re.search(r"\*\*Self-check:\*\*\s*\n((?:\d+\..+(?:\n|$))+)", md_text)
    if not match:
        return []
    return [line.strip() for line in match.group(1).strip().splitlines() if line.strip()]


def retrieval_questions(report_date: str, slot: int, meta: dict[str, Any]) -> list[str]:
    """2–3 pre-read prompts from pressure_question and prior lesson checkpoint."""
    lessons_meta = {m["slot"]: m for m in meta.get("lessons", [])}
    m = lessons_meta.get(slot, {})
    questions: list[str] = []
    pq = m.get("pressure_question")
    if pq:
        questions.append(f"Before reading: can you state the pressure driving this lesson? ({pq})")
    if slot > 1:
        files = lesson_files(report_date)
        if slot - 1 <= len(files):
            prior_md = files[slot - 2].read_text(encoding="utf-8")
            questions.extend(extract_self_check_questions(prior_md)[:2])
    concept = m.get("concept", "")
    if len(questions) < 2 and concept:
        questions.append(f"How might '{concept}' show up in tonight's story?")
    return questions[:3]


def gaps_section_html(gaps: list[dict[str, Any]], *, heading: str = "Story gaps") -> str:
    if not gaps:
        return ""
    items = ""
    for g in gaps:
        priority = g.get("priority", "medium")
        beat = g.get("related_beat", "")
        beat_html = f' <span class="gap-beat">{esc(beat)}</span>' if beat else ""
        items += f"""
        <li class="gap-item gap-priority-{esc(priority)}">
          <strong>{esc(g.get("pressure", ""))}</strong>{beat_html}
          <span class="badge gap-priority-badge">{esc(priority)}</span>
        </li>"""
    return f"""
    <section class="gaps-section">
      <h2>{esc(heading)}</h2>
      <p class="hint">Pressures not yet backed by solid mental models.</p>
      <ul class="gaps-list">{items}</ul>
    </section>"""


def hypothesis_confidence_badge(hid: str, learner_conf: dict[str, Any]) -> str:
    entry = learner_conf.get(hid, {})
    lc = entry.get("learner_confidence") if isinstance(entry, dict) else None
    if not lc:
        return ""
    return f'<span class="badge learner-conf {confidence_class(lc)}">you: {esc(lc)}</span>'


def report_dates() -> list[str]:
    dates = []
    for d in REPORTS.iterdir():
        if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}", d.name):
            if (d / "index.md").exists():
                dates.append(d.name)
    return sorted(dates, reverse=True)


def lesson_files(report_date: str) -> list[Path]:
    d = REPORTS / report_date
    return sorted(d.glob("[0-9][0-9]-*.md"))


def collect_all_lessons() -> list[dict[str, Any]]:
    """Catalog every lesson across all nights for topic grouping and navigation."""
    engagement = load_yaml(LEARNER / "engagement.yaml")
    catalog: list[dict[str, Any]] = []

    for report_date in sorted(report_dates()):
        meta = load_yaml(REPORTS / report_date / "meta.yaml")
        lessons_meta = {m["slot"]: m for m in meta.get("lessons", [])}
        for i, lf in enumerate(lesson_files(report_date), 1):
            m = lessons_meta.get(i, {})
            topic = m.get("topic_label") or meta.get("topic_label") or "General"
            key = f"lesson-{i:02d}"
            status = engagement.get(report_date, {}).get(key, {}).get("status", "unread")
            catalog.append(
                {
                    "date": report_date,
                    "slot": i,
                    "topic_label": topic,
                    "topic_slug": topic_slug(topic),
                    "pressure_question": m.get("pressure_question", lf.stem),
                    "title": display_title(m, lf.stem),
                    "concept": m.get("concept", ""),
                    "night_thread": meta.get("night_thread", ""),
                    "arc_id": meta.get("arc_id", ""),
                    "narrative_day": meta.get("narrative_day"),
                    "status": status,
                    "url": f"/reports/{report_date}/lesson-{i:02d}.html",
                }
            )

    # Assign within-topic sequence numbers
    topic_counts: dict[str, int] = {}
    for les in catalog:
        slug = les["topic_slug"]
        topic_counts[slug] = topic_counts.get(slug, 0) + 1
        les["topic_index"] = topic_counts[slug]
        les["topic_total"] = 0
    totals: dict[str, int] = {}
    for les in catalog:
        totals[les["topic_slug"]] = totals.get(les["topic_slug"], 0) + 1
    for les in catalog:
        les["topic_total"] = totals[les["topic_slug"]]

    return catalog


def lessons_by_topic(catalog: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for les in catalog:
        grouped.setdefault(les["topic_slug"], []).append(les)
    return grouped


def topic_nav_html(les: dict[str, Any], catalog: list[dict[str, Any]]) -> str:
    """Prev/next links within the same topic."""
    slug = les["topic_slug"]
    topic_lessons = [x for x in catalog if x["topic_slug"] == slug]
    idx = next(i for i, x in enumerate(topic_lessons) if x["date"] == les["date"] and x["slot"] == les["slot"])

    prev_link = ""
    if idx > 0:
        p = topic_lessons[idx - 1]
        prev_link = f'<a href="{p["url"]}">← Previous in topic</a>'

    next_link = ""
    if idx < len(topic_lessons) - 1:
        n = topic_lessons[idx + 1]
        next_link = f'<a href="{n["url"]}">Next in topic →</a>'

    topic_url = f"/topics/{slug}.html"
    label = les["topic_label"]
    return f"""
    <nav class="topic-nav">
      <div class="topic-nav-top">
        <a class="topic-nav-home" href="{topic_url}">↑ {esc(label)}</a>
        <span class="topic-nav-pos">Lesson {les["topic_index"]} of {les["topic_total"]} in this topic</span>
      </div>
      <div class="topic-nav-links">{prev_link}<span></span>{next_link}</div>
    </nav>"""


def page(title: str, body: str, *, nav_active: str = "", extra_head: str = "", extra_scripts: str = "", wide: bool = False, graph_page: bool = False) -> str:
    nav = [
        ("home", "Home", "/index.html"),
        ("topics", "Topics", "/topics/index.html"),
        ("hypotheses", "Mental Models", "/hypotheses.html"),
        ("graph", "Concept Graph", "/graph.html"),
        ("review", "Review", "/review.html"),
        ("arc", "Narrative Arc", "/arc.html"),
        ("engagement", "Engagement", "/engagement.html"),
    ]
    links = "\n".join(
        f'<a href="{href}" class="nav-link{" active" if key == nav_active else ""}">{label}</a>'
        for key, label, href in nav
    )
    wide_cls = " wide" if wide else ""
    graph_cls = " graph-page" if graph_page else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} · Nightly Learning</title>
  <link rel="stylesheet" href="/static/style.css">
  {extra_head}
</head>
<body>
  <header class="site-header">
    <div class="wrap">
      <a href="/index.html" class="brand">Nightly Learning</a>
      <nav class="nav">{links}</nav>
    </div>
  </header>
  <main class="wrap content{wide_cls}{graph_cls}">
    {body}
  </main>
  <footer class="site-footer">
    <div class="wrap">Built {esc(datetime.now().strftime("%Y-%m-%d %H:%M"))} · problem-first, mechanism-driven</div>
  </footer>
  <script src="/static/app.js"></script>
  {extra_scripts}
</body>
</html>"""


def build_home() -> None:
    dates = report_dates()
    hypotheses = load_active_hypotheses()
    arc = load_yaml(CURRICULUM / "narrative-arc.yaml").get("active_arc", {})
    engagement = load_yaml(LEARNER / "engagement.yaml")
    gaps = load_gaps()
    catalog = collect_all_lessons()
    by_topic = lessons_by_topic(catalog)

    continue_block = ""
    target = find_continue_target(dates, engagement)
    if target:
        cont_date, cont_slot = target
        cont_meta = load_yaml(REPORTS / cont_date / "meta.yaml")
        lessons_meta = {m["slot"]: m for m in cont_meta.get("lessons", [])}
        cont_files = lesson_files(cont_date)
        progress = night_read_progress(cont_date, engagement, cont_meta, len(cont_files))
        optional = lesson_optional_flags(cont_meta, lessons_meta, len(cont_files))
        show_kinds = progress["stretch_total"] > 0
        cont_title = display_title(lessons_meta.get(cont_slot, {}), cont_files[cont_slot - 1].stem)
        cont_topic = lessons_meta.get(cont_slot, {}).get("topic_label", cont_meta.get("topic_label", ""))
        continue_block = f"""
        <section class="continue-here">
          <h2>Continue here</h2>
          <p class="continue-progress">{esc(progress_label(progress))}</p>
          <a class="lesson-card continue-target status-unread" href="/reports/{cont_date}/lesson-{cont_slot:02d}.html">
            <span class="lesson-num">{cont_slot:02d}</span>
            <span class="lesson-title">
              {topic_badge(cont_topic)}
              {slot_kind_badge(optional.get(cont_slot, False), show_kinds)}
              {esc(cont_title)}
            </span>
            <span class="badge">next up</span>
          </a>
          <p class="hint">Night · {esc(cont_date)} · <a href="/reports/{cont_date}/index.html">full night →</a></p>
        </section>"""

    gaps_block = gaps_section_html(gaps)

    pedagogy_block = ""
    pedagogy = load_yaml(LEARNER / "pedagogy-feedback.yaml")
    latest = pedagogy.get("latest") or {}
    if latest.get("summary"):
        guidance = latest.get("curator_guidance") or {}
        scores = latest.get("quality_scores") or {}
        score_bits = ", ".join(f"{k}: {v}" for k, v in scores.items()) if scores else ""
        pedagogy_block = f"""
        <section class="pedagogy-feedback">
          <h2>Last night · graph review</h2>
          <p>{esc(latest.get("summary", ""))}</p>
          {"<p class='meta'>" + esc(score_bits) + "</p>" if score_bits else ""}
          {"<p class='hint'><strong>Next focus:</strong> " + esc(guidance.get("next_night_focus", "")) + "</p>" if guidance.get("next_night_focus") else ""}
          <p><a href="/graph.html">Concept graph →</a></p>
        </section>"""

    topics_block = ""
    if by_topic:
        cards = ""
        for slug in sorted(by_topic.keys(), key=lambda s: by_topic[s][0]["topic_label"]):
            lessons = by_topic[slug]
            label = lessons[0]["topic_label"]
            read_n = sum(1 for x in lessons if x["status"] == "read")
            cards += f"""
            <a class="topic-card" href="/topics/{slug}.html">
              {topic_badge(label)}
              <span class="topic-count">{len(lessons)} lessons</span>
              <span class="topic-progress">{read_n} read</span>
            </a>"""
        topics_block = f"""
        <section class="topics-section">
          <h2>Topics</h2>
          <p class="hint">Review all lessons on a subject in one place — across multiple nights.</p>
          <div class="topic-grid">{cards}</div>
          <p><a href="/topics/index.html">All topics →</a></p>
        </section>"""

    latest_block = ""
    if dates:
        latest = dates[0]
        meta = load_yaml(REPORTS / latest / "meta.yaml")
        lessons_meta = {m["slot"]: m for m in meta.get("lessons", [])}
        lessons = lesson_files(latest)
        topic = meta.get("topic_label", "")
        slug = topic_slug(topic) if topic else ""
        optional = lesson_optional_flags(meta, lessons_meta, len(lessons))
        progress = night_read_progress(latest, engagement, meta, len(lessons))
        show_kinds = progress["stretch_total"] > 0
        cont_target = find_continue_target(dates, engagement)
        highlight_slot = cont_target[1] if cont_target and cont_target[0] == latest else None
        cards = ""
        for i, lf in enumerate(lessons, 1):
            key = f"lesson-{i:02d}"
            status = engagement.get(latest, {}).get(key, {}).get("status", "unread")
            title = display_title(lessons_meta.get(i, {}), lf.stem)
            highlight = " continue-highlight" if i == highlight_slot else ""
            cards += f"""
            <a class="lesson-card status-{status}{highlight}" href="/reports/{latest}/lesson-{i:02d}.html">
              <span class="lesson-num">{i:02d}</span>
              <span class="lesson-title">{topic_badge(lessons_meta.get(i, {}).get("topic_label", topic))}{slot_kind_badge(optional.get(i, False), show_kinds)}{esc(title)}</span>
              <span class="badge">{esc(status)}</span>
            </a>"""
        topic_link = f'<p><a href="/topics/{slug}.html">Review full topic: {esc(topic)} →</a></p>' if topic else ""
        latest_block = f"""
        <section class="hero">
          <p class="eyebrow">Latest · {esc(latest)}</p>
          {topic_badge(topic)}
          <h1>{esc(meta.get("night_thread", "Tonight's lessons"))}</h1>
          <p class="meta">Arc: <strong>{esc(meta.get("arc_id", ""))}</strong> · Day {esc(str(meta.get("narrative_day", "")))} · {esc(progress_label(progress))}</p>
          <div class="lesson-grid">{cards}</div>
          <p><a href="/reports/{latest}/index.html">View full night →</a></p>
          {topic_link}
        </section>"""

    archive = ""
    if len(dates) > 1:
        items = "".join(
            f'<li><a href="/reports/{d}/index.html">{esc(d)}</a></li>' for d in dates[1:8]
        )
        archive = f'<section><h2>Archive</h2><ul class="archive-list">{items}</ul></section>'

    stats = f"""
    <section class="stats-row">
      <div class="stat"><span class="stat-n">{len(dates)}</span><span class="stat-l">Nights</span></div>
      <div class="stat"><span class="stat-n">{len(by_topic)}</span><span class="stat-l">Topics</span></div>
      <div class="stat"><span class="stat-n">{len(hypotheses)}</span><span class="stat-l">Mental models</span></div>
    </section>"""

    body = stats + continue_block + pedagogy_block + latest_block + gaps_block + topics_block + archive
    (PUBLIC / "index.html").write_text(page("Home", body, nav_active="home"), encoding="utf-8")


def build_report_index(report_date: str, catalog: list[dict[str, Any]]) -> None:
    out = PUBLIC / "reports" / report_date
    out.mkdir(parents=True, exist_ok=True)
    meta = load_yaml(REPORTS / report_date / "meta.yaml")
    engagement = load_yaml(LEARNER / "engagement.yaml").get(report_date, {})
    lessons = lesson_files(report_date)
    topic = meta.get("topic_label", "")
    slug = topic_slug(topic) if topic else ""

    cards = ""
    for i, lf in enumerate(lessons, 1):
        key = f"lesson-{i:02d}"
        st = engagement.get(key, {}).get("status", "unread")
        meta_lesson = next((m for m in meta.get("lessons", []) if m.get("slot") == i), {})
        title = display_title(meta_lesson, lf.stem)
        les = next((x for x in catalog if x["date"] == report_date and x["slot"] == i), None)
        pos = f'<span class="topic-pos">#{les["topic_index"]} in {esc(topic)}</span>' if les and topic else ""
        cards += f"""
        <article class="night-lesson status-{st}">
          <a href="lesson-{i:02d}.html">
            {topic_badge(meta_lesson.get("topic_label", topic))}
            <span class="lesson-num">{i:02d}</span>
            {pos}
            <h2>{esc(title)}</h2>
            <p class="concept">{esc(meta_lesson.get("concept", ""))}</p>
            <span class="badge">{esc(st)}</span>
          </a>
        </article>"""

    topic_link = (
        f'<p class="topic-review-link"><a href="/topics/{slug}.html">Review all {esc(topic)} lessons ({len([x for x in catalog if x["topic_slug"] == slug])} total) →</a></p>'
        if slug
        else ""
    )

    body = f"""
    <p class="breadcrumb"><a href="/index.html">Home</a> / {esc(report_date)}</p>
    <header class="night-header">
      <p class="eyebrow">Night · {esc(report_date)}</p>
      {topic_badge(topic)}
      <h1>{esc(meta.get("night_thread", "Lessons"))}</h1>
      <p class="meta">Arc <strong>{esc(meta.get("arc_id", ""))}</strong> · Day {esc(str(meta.get("narrative_day", "")))}</p>
    </header>
    <p class="hint">Read in order — tonight's lessons are one continuous story ({esc(str(len(lessons)))} published article{"s" if len(lessons) != 1 else ""}).</p>
    {topic_link}
    <div class="night-lessons">{cards}</div>
    """
    (out / "index.html").write_text(page(f"Night {report_date}", body), encoding="utf-8")


def build_lesson_pages(report_date: str, catalog: list[dict[str, Any]]) -> None:
    out = PUBLIC / "reports" / report_date
    meta = load_yaml(REPORTS / report_date / "meta.yaml")
    lessons_meta = {m["slot"]: m for m in meta.get("lessons", [])}
    files = lesson_files(report_date)

    for i, lf in enumerate(files, 1):
        md = lf.read_text(encoding="utf-8")
        if is_lesson_markdown_stub(md):
            raise ValueError(
                f"{lf.relative_to(ROOT)} is a word-count stub, not full lesson content. "
                "Restore from pipeline editor.json or re-run the editor stage."
            )
        content = render_md(md)
        m = lessons_meta.get(i, {})
        les = next((x for x in catalog if x["date"] == report_date and x["slot"] == i), {})
        topic_nav = topic_nav_html(les, catalog) if les else ""

        prev_night = f'<a href="lesson-{i-1:02d}.html">← Previous tonight</a>' if i > 1 else ""
        next_night = (
            f'<a href="lesson-{i+1:02d}.html">Next tonight →</a>'
            if i < len(files)
            else f'<a href="index.html">Back to night</a>'
        )

        retrieval = retrieval_questions(report_date, i, meta)
        retrieval_q = ""
        if retrieval:
            q_items = "".join(f"<li>{esc(q)}</li>" for q in retrieval)
            retrieval_q = f"""
    <details class="retrieval-hook">
      <summary>Before you read</summary>
      <p class="hint">Try answering from memory — no peeking at the lesson yet.</p>
      <ol class="retrieval-questions">{q_items}</ol>
    </details>"""
        ref_panel = html_reference_panel(
            meta.get("arc_id", "spam-filter-bayes"),
            report_date=report_date,
            narrative_day=meta.get("narrative_day"),
        )
        retrieval_block = ref_panel + retrieval_q

        body = f"""
    <p class="breadcrumb">
      <a href="/index.html">Home</a> /
      <a href="/topics/{les.get("topic_slug", "")}.html">{esc(les.get("topic_label", "Topic"))}</a> /
      <a href="index.html">{esc(report_date)}</a> /
      Lesson {i:02d}
    </p>
    {topic_nav}
    {topic_badge(m.get("topic_label", meta.get("topic_label", "")))}
    {concept_mastery_html(m.get("concept", ""), topic_label=m.get("topic_label") or meta.get("topic_label", ""), lesson_ref=f"{report_date}/lesson-{i:02d}")}
    {topic_mastery_html(m.get("topic_label") or meta.get("topic_label", ""))}
    {retrieval_block}
    <article class="lesson prose">
      {content}
    </article>
    <nav class="lesson-nav lesson-nav-night">
      <span class="nav-label">Tonight</span>
      {prev_night}<span>{i} / {len(files)}</span>{next_night}
    </nav>
    {lesson_chat_html(report_date, f"lesson-{i:02d}", m.get("topic_label") or meta.get("topic_label", ""))}
    <section class="engagement-inline" data-date="{esc(report_date)}" data-lesson="lesson-{i:02d}">
      <h3>Mark this lesson</h3>
      <form class="engagement-form">
        <label><input type="radio" name="status" value="read"> Read</label>
        <label><input type="radio" name="status" value="skipped"> Skipped</label>
        <label><input type="radio" name="status" value="unread" checked> Unread</label>
        <label>Depth
          <select name="depth">
            <option value="">—</option>
            <option value="too_shallow">Too shallow</option>
            <option value="just_right">Just right</option>
            <option value="too_deep">Too deep</option>
          </select>
        </label>
        <label>Interest
          <select name="interest">
            <option value="">—</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </label>
        <label>Note <input type="text" name="note" placeholder="Optional"></label>
        <button type="submit">Save engagement</button>
        <p class="form-msg" hidden></p>
      </form>
    </section>
        """
        title = les.get("title") or m.get("pressure_question", f"Lesson {i}")
        chat_script = '<script src="/static/lesson-chat.js"></script>'
        (out / f"lesson-{i:02d}.html").write_text(
            page(title, body, extra_scripts=chat_script),
            encoding="utf-8",
        )


def build_topics(catalog: list[dict[str, Any]]) -> None:
    topics_dir = PUBLIC / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    by_topic = lessons_by_topic(catalog)

    index_cards = ""
    for slug in sorted(by_topic.keys(), key=lambda s: by_topic[s][0]["topic_label"]):
        lessons = by_topic[slug]
        label = lessons[0]["topic_label"]
        read_n = sum(1 for x in lessons if x["status"] == "read")
        skipped_n = sum(1 for x in lessons if x["status"] == "skipped")
        nights = len({x["date"] for x in lessons})
        mastered = is_topic_mastered(label)
        mastered_row = '<span class="badge mastered-badge">mastered</span>' if mastered else ""
        index_cards += f"""
        <a class="topic-card topic-card-lg{" topic-card-mastered" if mastered else ""}" href="{slug}.html">
          {topic_badge(label, mastered=mastered)}
          {mastered_row}
          <p class="topic-stats">{len(lessons)} lessons · {nights} night{"s" if nights != 1 else ""}</p>
          <p class="topic-stats">{read_n} read · {skipped_n} skipped</p>
        </a>"""

    index_body = f"""
    <h1>Topics</h1>
    <p class="lead">All lessons grouped by subject — read or review a full topic across multiple nights.</p>
    <div class="topic-grid">{index_cards or "<p>No topics yet.</p>"}</div>
    """
    (topics_dir / "index.html").write_text(page("Topics", index_body, nav_active="topics"), encoding="utf-8")

    for slug, lessons in by_topic.items():
        label = lessons[0]["topic_label"]
        read_n = sum(1 for x in lessons if x["status"] == "read")

        # Group by night for display
        nights: dict[str, list[dict[str, Any]]] = {}
        for les in lessons:
            nights.setdefault(les["date"], []).append(les)

        lesson_rows = ""
        for les in lessons:
            lesson_rows += f"""
            <a class="topic-lesson-row status-{les["status"]}" href="{les["url"]}">
              <span class="topic-lesson-idx">{les["topic_index"]}</span>
              <span class="topic-lesson-main">
                <span class="topic-lesson-title">{esc(les["title"])}</span>
                <span class="topic-lesson-meta">{esc(les["date"])} · night slot {les["slot"]:02d} · {esc(les.get("concept", ""))}</span>
              </span>
              <span class="badge">{esc(les["status"])}</span>
            </a>"""

        night_sections = ""
        for date in sorted(nights.keys()):
            night_lessons = nights[date]
            thread = night_lessons[0].get("night_thread", "")
            items = ""
            for les in night_lessons:
                items += f"""
                <li class="status-{les["status"]}">
                  <a href="{les["url"]}"><strong>{les["topic_index"]}.</strong> {esc(les["title"])}</a>
                  <span class="badge">{esc(les["status"])}</span>
                </li>"""
            night_sections += f"""
            <section class="topic-night-group">
              <h3><a href="/reports/{date}/index.html">{esc(date)}</a> — {esc(thread)}</h3>
              <ol class="topic-night-list">{items}</ol>
            </section>"""

        body = f"""
        <p class="breadcrumb"><a href="/index.html">Home</a> / <a href="index.html">Topics</a> / {esc(label)}</p>
        <header class="topic-header">
          {topic_badge(label)}
          <h1>{esc(label)}</h1>
          <p class="meta">{len(lessons)} lessons across {len(nights)} night{"s" if len(nights) != 1 else ""} · {read_n} read</p>
        </header>
        {topic_mastery_html(label)}
        <p class="hint">Lessons are in learning order — continue where you left off or jump to any lesson.</p>

        <section class="topic-all-lessons">
          <h2>All lessons in order</h2>
          <div class="topic-lesson-list">{lesson_rows}</div>
        </section>

        <section class="topic-by-night">
          <h2>By night</h2>
          {night_sections}
        </section>
        """
        (topics_dir / f"{slug}.html").write_text(page(label, body, nav_active="topics"), encoding="utf-8")


def build_hypotheses() -> None:
    entries = load_active_hypotheses()
    state = load_active_state()
    stats = state.get("stats") or {}
    learner_conf = load_hypothesis_confidence()

    cards = ""
    for e in reversed(entries):
        deps = ", ".join(e.get("depends_on") or []) or "—"
        edges = ", ".join(e.get("edge_refs") or []) or "—"
        inv = e.get("invariant") or "—"
        conf = e.get("confidence", "low")
        hid = e.get("id", "")
        lc_entry = learner_conf.get(hid, {}) if isinstance(learner_conf.get(hid), dict) else {}
        lc = lc_entry.get("learner_confidence", "")
        topic_val = e.get("topic_label") or ""
        topic_dd = (
            f'<a href="/topics/{topic_slug(topic_val)}.html">{esc(topic_val)}</a>'
            if topic_val
            else "—"
        )
        lc_badge = hypothesis_confidence_badge(hid, learner_conf)
        lc_checked = {v: "checked" for v in ("low", "medium", "high") if v == lc}
        cards += f"""
        <article class="hypothesis-card {confidence_class(conf)}" id="{esc(hid)}" data-hypothesis-id="{esc(hid)}">
          <header>
            <span class="hid">{esc(hid)}</span>
            {topic_badge(topic_val)}
            <span class="badge type-{esc(e.get("type", ""))}">{esc(e.get("type", ""))}</span>
            <span class="badge {confidence_class(conf)}">agent: {esc(conf)}</span>
            {lc_badge}
          </header>
          <p class="statement">{esc(e.get("statement", ""))}</p>
          <dl class="hyp-meta">
            <dt>Topic</dt><dd>{topic_dd}</dd>
            <dt>Depends on</dt><dd>{esc(deps)}</dd>
            <dt>Graph edges</dt><dd><a href="/graph.html">{esc(edges)}</a></dd>
            <dt>Invariant</dt><dd>{esc(inv)}</dd>
            <dt>Narrative beat</dt><dd>{esc(e.get("narrative_beat", "—"))}</dd>
            <dt>Evidence</dt><dd>{esc(", ".join(e.get("evidence") or []))}</dd>
            <dt>Confusion addressed</dt><dd>{esc(", ".join(e.get("confusion_addressed") or []))}</dd>
          </dl>
          <section class="hypothesis-confidence-inline" data-id="{esc(hid)}">
            <p class="hint">Your confidence in this model:</p>
            <form class="hyp-confidence-form">
              <label><input type="radio" name="learner_confidence" value="low" {lc_checked.get("low", "")}> Still fuzzy</label>
              <label><input type="radio" name="learner_confidence" value="medium" {lc_checked.get("medium", "")}> Getting it</label>
              <label><input type="radio" name="learner_confidence" value="high" {lc_checked.get("high", "")}> I own this</label>
              <button type="submit">Save</button>
              <p class="form-msg" hidden></p>
            </form>
          </section>
        </article>"""

    body = f"""
    <h1>Mental Models</h1>
    <p class="lead">Mechanism-level beliefs from <strong>seed models</strong> plus lessons you&apos;ve marked read ({stats.get("hypotheses_active", len(entries))} active).</p>
    <div class="hypothesis-grid">{cards or "<p>No active models yet — mark lessons read or run the pipeline.</p>"}</div>
    """
    (PUBLIC / "hypotheses.html").write_text(page("Mental Models", body, nav_active="hypotheses"), encoding="utf-8")


def build_arc() -> None:
    data = load_yaml(CURRICULUM / "narrative-arc.yaml")
    arc = data.get("active_arc", {})
    beats = arc.get("planned_beats", [])
    current = arc.get("current_day", 0)
    gaps = load_gaps()

    beat_html = ""
    for b in beats:
        day = b.get("day", 0)
        done = day <= current
        concepts = ", ".join(b.get("concepts", []))
        beat_html += f"""
        <article class="beat-card{" done" if done else ""}">
          <span class="beat-day">Day {day}</span>
          <h2>{esc(b.get("beat", ""))}</h2>
          <p class="concepts">{esc(concepts)}</p>
          <p class="terms">Terms earned: {esc(", ".join(b.get("terminology_earned", [])))}</p>
        </article>"""

    flex_items = ""
    fp_raw = arc.get("flex_points", {})
    if isinstance(fp_raw, dict):
        flex_items = "".join(f"<li><strong>{esc(k)}</strong> — {esc(v)}</li>" for k, v in fp_raw.items())
    elif isinstance(fp_raw, list):
        for item in fp_raw:
            if isinstance(item, dict):
                flex_items += "".join(f"<li><strong>{esc(k)}</strong> — {esc(v)}</li>" for k, v in item.items())

    current_beat = next((b for b in beats if b.get("day") == current), {})
    arc_summary = ""
    if current_beat:
        arc_summary = f"""
    <section class="arc-current">
      <h2>Current day ({current})</h2>
      <p><strong>{esc(current_beat.get("beat", ""))}</strong></p>
      <p class="meta">Concepts: {esc(", ".join(current_beat.get("concepts", [])))}</p>
    </section>"""

    gaps_block = gaps_section_html(gaps, heading="What the story needs next")

    body = f"""
    <h1>Narrative Arc</h1>
    <p class="lead">{esc(arc.get("title", ""))}</p>
    <div class="arc-setting">{esc(arc.get("setting", ""))}</div>
    <p><strong>Anchor:</strong> {esc(arc.get("anchor", ""))} · <a href="/anchor/{esc(arc.get('id', 'spam-filter-bayes'))}.html">Standalone primer (characters, glossary, numbers)</a></p>
    {arc_summary}
    {gaps_block}
    <h2>Flex points</h2>
    <ul class="flex-list">{flex_items}</ul>
    <h2>Planned beats</h2>
    <div class="beats">{beat_html}</div>
    """
    (PUBLIC / "arc.html").write_text(page("Narrative Arc", body, nav_active="arc"), encoding="utf-8")


def build_anchor_primers() -> None:
    anchors_dir = PUBLIC / "anchor"
    anchors_dir.mkdir(parents=True, exist_ok=True)
    for arc_id, primer in load_anchor_primers().items():
        if not isinstance(primer, dict):
            continue
        fd = primer.get("fixed_anchor_data") or {}
        chars = "".join(
            f"<li><strong>{esc(c.get('name', ''))}</strong> — {esc(c.get('role', ''))}</li>"
            for c in (primer.get("characters") or [])
            if isinstance(c, dict)
        )
        beats = ""
        for b in primer.get("story_beats") or []:
            if not isinstance(b, dict):
                continue
            beats += f"""
        <article class="beat-card">
          <span class="beat-day">Day {esc(str(b.get('day', '')))}</span>
          <p>{esc(str(b.get('summary', '')).strip())}</p>
          <p class="meta">Key idea: {esc(b.get('key_idea', ''))}</p>
        </article>"""
        terms = "".join(
            f"<dt>{esc(t.get('term', ''))}</dt><dd>{esc(str(t.get('plain', '')).strip())}</dd>"
            for t in (primer.get("terms") or [])
            if isinstance(t, dict)
        )
        prior = all_arc_report_links(arc_id)
        prior_html = ""
        if prior:
            prior_html = "<h2>Published nights</h2><ul>" + "".join(
                f'<li><a href="{p["url"]}">{esc(p["label"])}</a></li>' for p in prior
            ) + "</ul>"
        precision = "".join(f"<li>{esc(r)}</li>" for r in (primer.get("precision_rules") or []))
        body = f"""
    <h1>{esc(primer.get('title', arc_id))}</h1>
    <p class="lead">{esc(primer.get('one_line', ''))}</p>
    <p>{esc(str(primer.get('setting', '')).strip())}</p>
    <h2>Fixed numbers (this anchor)</h2>
    <ul>
      <li><strong>Queue:</strong> {esc(str(fd.get('labeled_batch_size', '')))} labeled emails in the {esc(str(fd.get('queue_name', '')))}</li>
      <li><strong>Labels:</strong> {esc(str(fd.get('spam_labels', '')))} spam, {esc(str(fd.get('ham_labels', '')))} ham (rate {esc(str(fd.get('label_rate', '')))})</li>
      <li><strong>Routing threshold:</strong> {esc(str(fd.get('auto_quarantine_threshold', '')))}</li>
      <li><strong>Classifier:</strong> {esc(str(fd.get('classifier', '')))}</li>
      <li><strong>Features:</strong> {esc(str(fd.get('feature_spec', '')).strip())}</li>
    </ul>
    <h2>Characters</h2>
    <ul>{chars}</ul>
    <h2>Story beats (recap for standalone lessons)</h2>
    <div class="beats">{beats}</div>
    {prior_html}
    <h2>Glossary</h2>
    <dl class="hyp-meta anchor-glossary">{terms}</dl>
    <h2>Precision rules</h2>
    <ul>{precision}</ul>
    <p class="hint"><a href="/arc.html">Narrative arc (planned beats)</a> · <a href="/graph.html">Concept graph</a></p>
    """
        (anchors_dir / f"{arc_id}.html").write_text(
            page(primer.get("title", "Anchor"), body, nav_active="arc"),
            encoding="utf-8",
        )


def build_engagement() -> None:
    engagement = load_yaml(LEARNER / "engagement.yaml")
    dates = report_dates()

    rows = ""
    for d in dates[:14]:
        day = engagement.get(d, {})
        if not day:
            for i in range(1, 6):
                rows += f"""
                <tr data-date="{esc(d)}" data-lesson="lesson-{i:02d}">
                  <td>{esc(d)}</td><td>{i:02d}</td>
                  <td colspan="4"><em>not set</em></td>
                </tr>"""
            continue
        for key, val in sorted(day.items()):
            if not key.startswith("lesson"):
                continue
            rows += f"""
            <tr>
              <td>{esc(d)}</td>
              <td>{esc(key.replace("lesson-", ""))}</td>
              <td>{esc(val.get("status", "unread"))}</td>
              <td>{esc(val.get("depth", "—"))}</td>
              <td>{esc(val.get("interest", "—"))}</td>
              <td>{esc(val.get("note", ""))}</td>
            </tr>"""

    body = f"""
    <h1>Engagement</h1>
    <p class="lead">Mark lessons from each lesson page, or use the table below. Saves to <code>learner/engagement.yaml</code> when using the local server.</p>
    <table class="engagement-table">
      <thead><tr><th>Date</th><th>Lesson</th><th>Status</th><th>Depth</th><th>Interest</th><th>Note</th></tr></thead>
      <tbody>{rows or "<tr><td colspan='6'>No reports yet</td></tr>"}</tbody>
    </table>
    """
    (PUBLIC / "engagement.html").write_text(page("Engagement", body, nav_active="engagement"), encoding="utf-8")


def effective_hypothesis_confidence(entry: dict[str, Any], learner_conf: dict[str, Any]) -> str:
    hid = entry.get("id", "")
    lc_entry = learner_conf.get(hid, {})
    if isinstance(lc_entry, dict) and lc_entry.get("learner_confidence"):
        return lc_entry["learner_confidence"]
    return entry.get("confidence", "low")


def build_review(catalog: list[dict[str, Any]]) -> None:
    entries = load_active_hypotheses()
    learner_conf = load_hypothesis_confidence()
    gaps = load_gaps()
    arc_data = load_yaml(CURRICULUM / "narrative-arc.yaml")
    arc = arc_data.get("active_arc", {})
    current = arc.get("current_day", 0)
    beats = arc.get("planned_beats", [])
    current_beat = next((b for b in beats if b.get("day") == current), {})

    low_entries = [e for e in entries if effective_hypothesis_confidence(e, learner_conf) == "low"]
    today = date.today()
    week_seed = today.isocalendar()[1] + today.year * 100
    rng = random.Random(week_seed)
    sample = rng.sample(low_entries, min(5, len(low_entries))) if low_entries else []

    recall_cards = ""
    for e in sample:
        hid = e.get("id", "")
        recall_cards += f"""
        <article class="review-recall-card">
          <span class="hid">{esc(hid)}</span>
          <p class="recall-prompt">Can you reconstruct this mechanism in your own words?</p>
          <details>
            <summary>Reveal statement</summary>
            <p class="statement">{esc(e.get("statement", ""))}</p>
          </details>
          <p><a href="/hypotheses.html#{esc(hid)}">Rate your confidence →</a></p>
        </article>"""

    unread = [les for les in catalog if les["status"] == "unread"]
    backlog_items = ""
    for les in unread[:20]:
        backlog_items += f"""
        <li>
          <a href="{les["url"]}">{esc(les["date"])} · slot {les["slot"]:02d} — {esc(les["title"])}</a>
        </li>"""
    backlog_more = ""
    if len(unread) > 20:
        backlog_more = f'<p class="hint">…and {len(unread) - 20} more across older nights.</p>'

    arc_block = f"""
    <section class="review-arc">
      <h2>Arc · Day {current}</h2>
      <p><strong>{esc(arc.get("title", ""))}</strong></p>
      <p>{esc(current_beat.get("beat", "—"))}</p>
      <p><a href="/arc.html">Full narrative arc →</a></p>
    </section>"""

    gaps_block = gaps_section_html(gaps, heading="Story gaps to close")

    body = f"""
    <h1>Weekly review</h1>
    <p class="lead">Recall weak models, clear your backlog, and see where the arc is headed. Refreshes weekly (seed {week_seed}).</p>

    {arc_block}
    {gaps_block}

    <section class="review-recall">
      <h2>Recall prompts</h2>
      <p class="hint">Five low-confidence mental models — try explaining each before revealing.</p>
      <div class="review-recall-grid">{recall_cards or "<p>All models at medium/high confidence — nice work.</p>"}</div>
    </section>

    <section class="review-backlog">
      <h2>Unread backlog</h2>
      <p class="meta">{len(unread)} lesson{"s" if len(unread) != 1 else ""} waiting</p>
      <ul class="review-backlog-list">{backlog_items or "<li><em>Caught up — nothing unread.</em></li>"}</ul>
      {backlog_more}
      <p><a href="/index.html">Continue from home →</a></p>
    </section>
    """
    (PUBLIC / "review.html").write_text(page("Weekly Review", body, nav_active="review"), encoding="utf-8")


def build_graph() -> None:
    state = load_active_state()
    graph_data = load_active_graph()
    active_topics_set = set(graph_data.get("topics") or [])
    invariants = graph_data.get("invariants") or []
    all_edges = graph_data.get("edges") or []
    stats = state.get("stats") or {}

    catalog = collect_all_lessons()
    read_catalog = [x for x in catalog if x.get("status") == "read"]
    by_topic = lessons_by_topic(read_catalog)

    nodes = []
    for label in sorted(active_topics_set):
        slug = topic_slug(label)
        nodes.append(
            {
                "id": label,
                "label": label,
                "slug": slug if slug in by_topic else "",
                "lesson_count": len(by_topic.get(slug, [])),
                "mastered": is_topic_mastered(label),
            }
        )

    edges = [
        {
            "id": e.get("id", ""),
            "source": e.get("from_topic", ""),
            "target": e.get("to_topic", ""),
            "type": e.get("edge_type", ""),
            "statement": (e.get("statement") or "").strip(),
            "runtime": bool(e.get("runtime")),
        }
        for e in all_edges
        if e.get("from_topic") and e.get("to_topic")
    ]

    graph_payload = json.dumps(
        {
            "nodes": nodes,
            "edges": edges,
            "invariants": [
                {
                    "id": inv.get("id", ""),
                    "name": inv.get("name", ""),
                    "statement": (inv.get("statement") or "").strip(),
                    "topics": inv.get("topics") or [],
                }
                for inv in invariants
            ],
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")

    inv_html = ""
    for inv in invariants:
        topics_list = ", ".join(inv.get("topics") or [])
        inv_html += f"""
        <article class="invariant-card">
          <h3>{esc(inv.get("id", ""))}</h3>
          <p><strong>{esc(inv.get("name", ""))}</strong></p>
          <p>{esc(inv.get("statement", ""))}</p>
          <p class="meta">Topics: {esc(topics_list)}</p>
        </article>"""

    edge_rows = ""
    for e in all_edges:
        edge_rows += f"""
        <tr data-edge-type="{esc(e.get("edge_type", ""))}">
          <td><code>{esc(e.get("id", ""))}</code></td>
          <td>{esc(e.get("from_topic", ""))}</td>
          <td><span class="badge edge-type">{esc(e.get("edge_type", ""))}</span></td>
          <td>{esc(e.get("to_topic", ""))}</td>
          <td>{esc(e.get("statement", ""))}</td>
        </tr>"""

    pedagogy = load_yaml(LEARNER / "pedagogy-feedback.yaml")
    latest = pedagogy.get("latest") or {}
    guidance = latest.get("curator_guidance") or {}
    next_focus = guidance.get("next_night_focus", "")
    guidance_html = ""
    if next_focus:
        guidance_html = f"""
        <section class="graph-guidance">
          <h2>Curator guidance (from grapher)</h2>
          <p>{esc(next_focus)}</p>
          <p class="meta">Emphasize: {esc(", ".join(guidance.get("emphasize_edges") or []))}</p>
        </section>"""

    body = f"""
    <header class="graph-page-header">
      <h1>Concept Graph</h1>
      <p class="lead">Your map so far — <strong>{stats.get("graph_nodes", len(nodes))} topics</strong> from read lessons and seed mental models, <strong>{stats.get("graph_edges", len(edges))} edges</strong> connecting them. Mark more lessons read to grow the graph.</p>
    </header>

    {guidance_html}

    <section class="graph-viz-section">
      <div class="graph-layout">
        <div class="graph-canvas-wrap">
          <div id="concept-graph-mount" class="concept-graph-mount" aria-label="Interactive concept graph"></div>
        </div>
        <aside id="graph-detail" class="graph-detail-panel"></aside>
      </div>
      <script type="application/json" id="concept-graph-data">{graph_payload}</script>
    </section>

    <details class="graph-meta-details">
      <summary>Reference — invariants, edge table, legend</summary>

    <section>
      <h2>Pressure invariants</h2>
      <div class="invariant-grid">{inv_html or "<p>No invariants defined.</p>"}</div>
    </section>

    <details class="graph-table-details">
      <summary>Edge table ({len(all_edges)} edges)</summary>
      <p class="hint">Seed edges from curriculum; dashed lines in the viz are runtime edges from the grapher.</p>
      <table class="graph-table">
        <thead><tr><th>ID</th><th>From</th><th>Type</th><th>To</th><th>Mechanism</th></tr></thead>
        <tbody>{edge_rows or "<tr><td colspan='5'>No edges yet.</td></tr>"}</tbody>
      </table>
    </details>

    <section>
      <h2>Edge types</h2>
      <ul class="edge-legend">
        <li><code>same_pressure</code> — different tool, same problem</li>
        <li><code>calibration_link</code> — scores vs probabilities</li>
        <li><code>same_geometry</code> — different loss, same boundary</li>
        <li><code>same_algebra</code> — shared substrate (SVD, Fourier, …)</li>
        <li><code>isomorphism</code> — different domain, same structure</li>
      </ul>
    </section>
    </details>
    """
    graph_scripts = (
        '<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>\n'
        '  <script src="/static/graph.js"></script>'
    )
    (PUBLIC / "graph.html").write_text(
        page("Concept Graph", body, nav_active="graph", extra_scripts=graph_scripts, wide=True, graph_page=True),
        encoding="utf-8",
    )


def build_all() -> None:
    sync_learner_state(prune=False)
    sync_spine_progress()
    if PUBLIC.exists():
        shutil.rmtree(PUBLIC)
    PUBLIC.mkdir(parents=True)
    (PUBLIC / "static").mkdir()
    shutil.copy(SITE / "static" / "style.css", PUBLIC / "static" / "style.css")
    shutil.copy(SITE / "static" / "app.js", PUBLIC / "static" / "app.js")
    shutil.copy(SITE / "static" / "graph.js", PUBLIC / "static" / "graph.js")
    shutil.copy(SITE / "static" / "lesson-chat.js", PUBLIC / "static" / "lesson-chat.js")

    build_home()
    catalog = collect_all_lessons()
    build_topics(catalog)
    build_hypotheses()
    build_graph()
    build_arc()
    build_anchor_primers()
    build_engagement()
    build_review(catalog)
    for d in report_dates():
        build_report_index(d, catalog)
        build_lesson_pages(d, catalog)

    print(f"Site built → {PUBLIC} ({len(report_dates())} nights, {len(lessons_by_topic(catalog))} topics)")


if __name__ == "__main__":
    build_all()
