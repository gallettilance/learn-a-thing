"""Per-lesson learner chat — persisted for editor anticipated-confusion loop."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
LEARNER = ROOT / "learner"
REPORTS = ROOT / "reports"
CHAT_PATH = LEARNER / "lesson-chat.yaml"
TUTOR_MODEL = os.environ.get("LEARNING_MODEL", "composer-2.5")


def _load_yaml(path: Path) -> Any:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _save_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "# Learner follow-up questions per lesson — editor reads for traps/checkpoints\n\n"
    path.write_text(header + yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")


def thread_key(report_date: str, lesson: str) -> str:
    return f"{report_date}::{lesson}"


def load_chat_store() -> dict[str, Any]:
    raw = _load_yaml(CHAT_PATH)
    if not isinstance(raw, dict):
        return {"threads": {}}
    if "threads" not in raw or not isinstance(raw["threads"], dict):
        raw["threads"] = {}
    return raw


def get_thread(report_date: str, lesson: str) -> list[dict[str, Any]]:
    store = load_chat_store()
    key = thread_key(report_date, lesson)
    thread = store["threads"].get(key) or []
    return thread if isinstance(thread, list) else []


def append_message(
    report_date: str,
    lesson: str,
    *,
    role: str,
    content: str,
    topic_label: str = "",
) -> dict[str, Any]:
    content = content.strip()
    if not content:
        raise ValueError("message content required")
    if role not in ("user", "assistant"):
        raise ValueError("role must be user or assistant")

    store = load_chat_store()
    key = thread_key(report_date, lesson)
    thread = list(get_thread(report_date, lesson))
    entry: dict[str, Any] = {
        "role": role,
        "content": content,
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    if topic_label and role == "user":
        entry["topic_label"] = topic_label
    thread.append(entry)
    store["threads"][key] = thread
    _save_yaml(CHAT_PATH, store)
    return entry


def find_lesson_markdown(report_date: str, lesson: str) -> str:
    """Return lesson markdown body for tutor context."""
    slot = lesson.replace("lesson-", "").replace(".html", "")
    try:
        slot_num = int(slot)
    except ValueError:
        return ""
    report_dir = REPORTS / report_date
    if not report_dir.is_dir():
        return ""
    files = sorted(report_dir.glob(f"{slot_num:02d}-*.md"))
    if not files:
        files = sorted(report_dir.glob(f"*-lesson-{slot_num:02d}-*.md"))
    if not files:
        alt = report_dir / f"lesson-{slot_num:02d}.md"
        if alt.exists():
            files = [alt]
    if not files:
        return ""
    text = files[0].read_text(encoding="utf-8")
    return text[:12000]


def tutor_reply(
    report_date: str,
    lesson: str,
    user_message: str,
    *,
    topic_label: str = "",
    history: list[dict[str, Any]] | None = None,
) -> str | None:
    """Generate a short tutor reply when CURSOR_API_KEY is set."""
    api_key = os.environ.get("CURSOR_API_KEY")
    if not api_key:
        return None

    lesson_md = find_lesson_markdown(report_date, lesson)
    hist = history or get_thread(report_date, lesson)
    recent = hist[-8:]
    hist_lines = []
    for m in recent:
        role = m.get("role", "user")
        hist_lines.append(f"{role.upper()}: {m.get('content', '')}")

    prompt = f"""You are a concise tutor for one mini-lesson in a nightly learning system.
Answer the learner's follow-up in 2–4 short paragraphs. Mechanism-first; no definition dumps.
Do not rewrite the whole lesson. If they ask something outside the lesson, say what you'd need to assume.

Topic: {topic_label or "unknown"}
Night: {report_date} · {lesson}

Lesson excerpt:
{lesson_md or "(lesson file not found — answer from general knowledge carefully)"}

Recent thread:
{chr(10).join(hist_lines) if hist_lines else "(none)"}

Learner follow-up:
{user_message}
"""

    try:
        from cursor_sdk import Agent, AgentOptions, LocalAgentOptions

        opts = AgentOptions(
            api_key=api_key,
            model=TUTOR_MODEL,
            local=LocalAgentOptions(cwd=str(ROOT)),
        )
        result = Agent.prompt(prompt, opts)
        if result.status == "error":
            return None
        text = (result.result or "").strip()
        return text or None
    except Exception:
        return None


def format_for_editor(*, max_threads: int = 20, max_chars: int = 6000) -> str:
    """Summarize learner follow-ups for the editor agent."""
    store = load_chat_store()
    threads: dict[str, list] = store.get("threads") or {}
    if not threads:
        return "(no learner follow-up questions yet)"

    # Collect user messages with metadata
    items: list[tuple[str, dict[str, Any]]] = []
    for key, messages in threads.items():
        if not isinstance(messages, list):
            continue
        for msg in messages:
            if not isinstance(msg, dict) or msg.get("role") != "user":
                continue
            items.append((key, msg))

    if not items:
        return "(no learner questions yet — only assistant messages)"

    items.sort(key=lambda x: x[1].get("at", ""), reverse=True)
    items = items[:max_threads]

    lines = [
        "Learner follow-up questions from lesson chat (anticipate these in Traps, checkpoints, and prose):",
        "",
    ]
    for key, msg in items:
        topic = msg.get("topic_label") or "—"
        lines.append(f"- [{key}] ({topic}) {msg.get('content', '').strip()}")
        lines.append(f"  asked: {msg.get('at', '—')}")

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[: max_chars - 40] + "\n… (truncated — see learner/lesson-chat.yaml)"
    return text
