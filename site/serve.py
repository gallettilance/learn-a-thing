#!/usr/bin/env python3
"""Serve the learning site locally with engagement API."""

from __future__ import annotations

import json
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib.lesson_chat import append_message, get_thread, tutor_reply  # noqa: E402
from lib.topic_mastery import set_topic_mastered  # noqa: E402
from lib.concept_mastery import set_concept_mastered  # noqa: E402

PUBLIC = Path(__file__).resolve().parent / "public"
ENGAGEMENT = ROOT / "learner" / "engagement.yaml"
HYPOTHESIS_CONFIDENCE = ROOT / "learner" / "hypothesis-confidence.yaml"
MASTERED_TOPICS = ROOT / "learner" / "mastered-topics.yaml"
PORT = 8765


def load_engagement() -> dict:
    if not ENGAGEMENT.exists():
        return {}
    data = yaml.safe_load(ENGAGEMENT.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def save_engagement(data: dict) -> None:
    ENGAGEMENT.parent.mkdir(parents=True, exist_ok=True)
    header = "# Updated via local site — also used by nightly curator\n\n"
    ENGAGEMENT.write_text(header + yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")


def load_hypothesis_confidence() -> dict:
    if not HYPOTHESIS_CONFIDENCE.exists():
        return {}
    data = yaml.safe_load(HYPOTHESIS_CONFIDENCE.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def save_hypothesis_confidence(data: dict) -> None:
    HYPOTHESIS_CONFIDENCE.parent.mkdir(parents=True, exist_ok=True)
    header = "# Learner self-ratings for mental models — used by curator\n\n"
    HYPOTHESIS_CONFIDENCE.write_text(
        header + yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8"
    )


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/lesson-chat":
            self._handle_lesson_chat_get()
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/engagement":
            self._handle_engagement()
        elif parsed.path == "/api/hypothesis-confidence":
            self._handle_hypothesis_confidence()
        elif parsed.path == "/api/topic-mastery":
            self._handle_topic_mastery()
        elif parsed.path == "/api/concept-mastery":
            self._handle_concept_mastery()
        elif parsed.path == "/api/lesson-chat":
            self._handle_lesson_chat_post()
        else:
            self.send_error(404)

    def _rebuild_site(self) -> None:
        subprocess.run([sys.executable, str(ROOT / "site" / "build.py")], cwd=ROOT, check=True)

    def _json_response(self, status: int, payload: dict) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def _handle_engagement(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
            date = payload["date"]
            lesson = payload["lesson"]
            entry = {"status": payload.get("status", "unread")}
            if payload.get("depth"):
                entry["depth"] = payload["depth"]
            if payload.get("interest"):
                entry["interest"] = payload["interest"]
            if payload.get("note"):
                entry["note"] = payload["note"]

            data = load_engagement()
            data.setdefault(date, {})[lesson] = entry
            save_engagement(data)
            self._rebuild_site()
            self._json_response(200, {"ok": True})
        except Exception as exc:
            self._json_response(400, {"error": str(exc)})

    def _handle_hypothesis_confidence(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
            hid = payload["id"]
            level = payload.get("learner_confidence")
            if level not in ("low", "medium", "high"):
                raise ValueError("learner_confidence must be low, medium, or high")

            data = load_hypothesis_confidence()
            data[hid] = {"learner_confidence": level}
            save_hypothesis_confidence(data)
            self._rebuild_site()
            self._json_response(200, {"ok": True})
        except Exception as exc:
            self._json_response(400, {"error": str(exc)})

    def _handle_topic_mastery(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
            topic_label = payload.get("topic_label") or payload.get("topic")
            if not topic_label:
                raise ValueError("topic_label required")
            mastered = bool(payload.get("mastered"))
            note = str(payload.get("note") or "")

            result = set_topic_mastered(topic_label, mastered, note=note)
            self._rebuild_site()
            self._json_response(200, {"ok": True, **result})
        except Exception as exc:
            self._json_response(400, {"error": str(exc)})

    def _handle_concept_mastery(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
            concept_id = payload.get("concept_id") or payload.get("concept")
            if not concept_id:
                raise ValueError("concept_id required")
            mastered = bool(payload.get("mastered"))
            note = str(payload.get("note") or "")
            lesson_ref = str(payload.get("lesson_ref") or "")
            topic_label = str(payload.get("topic_label") or "")

            result = set_concept_mastered(
                concept_id,
                mastered,
                note=note,
                lesson_ref=lesson_ref,
                topic_label=topic_label,
            )
            self._rebuild_site()
            self._json_response(200, {"ok": True, **result})
        except Exception as exc:
            self._json_response(400, {"error": str(exc)})

    def _handle_lesson_chat_get(self) -> None:
        from urllib.parse import parse_qs

        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        try:
            report_date = qs.get("date", [""])[0]
            lesson = qs.get("lesson", [""])[0]
            if not report_date or not lesson:
                raise ValueError("date and lesson query params required")
            messages = get_thread(report_date, lesson)
            self._json_response(200, {"ok": True, "messages": messages})
        except Exception as exc:
            self._json_response(400, {"error": str(exc)})

    def _handle_lesson_chat_post(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
            report_date = payload["date"]
            lesson = payload["lesson"]
            message = payload.get("message") or payload.get("content")
            topic_label = str(payload.get("topic_label") or "")

            append_message(
                report_date,
                lesson,
                role="user",
                content=str(message),
                topic_label=topic_label,
            )

            assistant = tutor_reply(
                report_date,
                lesson,
                str(message),
                topic_label=topic_label,
            )
            saved_only = assistant is None
            if assistant:
                append_message(
                    report_date,
                    lesson,
                    role="assistant",
                    content=assistant,
                )

            self._json_response(
                200,
                {
                    "ok": True,
                    "assistant": assistant,
                    "saved_only": saved_only,
                },
            )
        except Exception as exc:
            self._json_response(400, {"error": str(exc)})

    def log_message(self, format: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {args[0]}")


def main() -> None:
    if not PUBLIC.exists():
        subprocess.run([sys.executable, str(ROOT / "site" / "build.py")], cwd=ROOT, check=True)

    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Learning site → http://127.0.0.1:{PORT}/")
    print("Engagement forms save to learner/engagement.yaml")
    print("Hypothesis confidence saves to learner/hypothesis-confidence.yaml")
    print("Topic mastery saves to learner/mastered-topics.yaml")
    print("Lesson chat saves to learner/lesson-chat.yaml (CURSOR_API_KEY → live tutor replies)")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
