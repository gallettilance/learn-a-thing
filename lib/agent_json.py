"""Validate and recover agent JSON payloads (especially large teacher/editor responses)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from lib.lesson_content import is_lesson_markdown_stub
from lib.lesson_consolidation import MAX_PUBLISHED_LESSONS, MIN_PUBLISHED_LESSONS

ROOT = Path(__file__).resolve().parent.parent

RoleValidator = Callable[[Any], list[str]]

COMMON_POINTER_MARKERS = (
    "exceed the response limit",
    "use that file",
    "full output is in",
    "pasting the complete json",
    "split per lesson",
    "too large to embed",
    "embed inline",
    "is valid per",
    "sidecar",
    "reply limit",
    "too large to embed inline",
    "complete payload from",
)

TEACHER_POINTER_MARKERS = COMMON_POINTER_MARKERS + (
    "teacher_output.json",
    "teacher-output",
    "teacher-gen-full",
)

EDITOR_POINTER_MARKERS = COMMON_POINTER_MARKERS + (
    "editor-output",
    "editor_output",
    "editor_output_",
)

CONSOLIDATOR_POINTER_MARKERS = COMMON_POINTER_MARKERS + (
    "consolidator-output",
    "consolidator_output",
)

TEACHER_SIDECAR_RES = (
    re.compile(r"(\.(?:teacher[-_])?output(?:[-\w.]*)?\.json)", re.IGNORECASE),
    re.compile(r"([\w/.-]*\.teacher[-_]output(?:[-\w.]*)?\.json)", re.IGNORECASE),
)

EDITOR_SIDECAR_RES = (
    re.compile(r"(\.editor[-_]output(?:[-\w.]*)?\.json)", re.IGNORECASE),
    re.compile(r"([\w/.-]*\.editor[-_]output(?:[-\w.]*)?\.json)", re.IGNORECASE),
    re.compile(r"(pipeline/\d{4}-\d{2}-\d{2}/editor\.json)", re.IGNORECASE),
)

CONSOLIDATOR_SIDECAR_RES = (
    re.compile(r"(\.consolidator[-_]output(?:[-\w.]*)?\.json)", re.IGNORECASE),
    re.compile(r"([\w/.-]*\.consolidator[-_]output(?:[-\w.]*)?\.json)", re.IGNORECASE),
    re.compile(r"(pipeline/\d{4}-\d{2}-\d{2}/consolidator-\w+\.json)", re.IGNORECASE),
)

TEACHER_GEN_SCRIPT = ".teacher-gen-full.py"
EDITOR_GEN_SCRIPT_RE = re.compile(
    r"(scripts/editor_output[^\s`'\"]+\.py)",
    re.IGNORECASE,
)


def teacher_payload_issues(data: Any) -> list[str]:
    """Human-readable validation failures for teacher JSON."""
    if not isinstance(data, dict):
        return ["payload is not a JSON object"]

    issues: list[str] = []
    if not str(data.get("index_md") or "").strip():
        issues.append("missing or empty index_md")

    lessons = data.get("lessons")
    if not isinstance(lessons, list):
        issues.append("lessons is not a list")
        return issues
    n = len(lessons)
    if n < MIN_PUBLISHED_LESSONS or n > MAX_PUBLISHED_LESSONS:
        issues.append(
            f"expected {MIN_PUBLISHED_LESSONS}–{MAX_PUBLISHED_LESSONS} published lessons, got {n}"
        )

    for les in lessons:
        if isinstance(les, str):
            issues.append("lesson entry is a string placeholder, not an object")
            continue
        if not isinstance(les, dict):
            issues.append("lesson entry is not an object")
            continue
        slot = les.get("slot", "?")
        md = str(les.get("markdown") or "")
        if not md:
            issues.append(f"slot {slot}: missing markdown")
        elif is_lesson_markdown_stub(md):
            issues.append(f"slot {slot}: markdown is a word-count stub")
        elif len(md) < 500:
            issues.append(f"slot {slot}: markdown too short ({len(md)} chars, need 500+)")
        if not les.get("slug"):
            issues.append(f"slot {slot}: missing slug")
        if not les.get("title"):
            issues.append(f"slot {slot}: missing title")

    return issues


def is_valid_teacher_payload(data: Any) -> bool:
    return not teacher_payload_issues(data)


def editor_payload_issues(data: Any) -> list[str]:
    """Human-readable validation failures for editor JSON."""
    if not isinstance(data, dict):
        return ["payload is not a JSON object"]

    issues: list[str] = []
    if not str(data.get("index_md") or "").strip():
        issues.append("missing or empty index_md")
    if not isinstance(data.get("review_summary"), dict):
        issues.append("missing review_summary")

    lessons = data.get("lessons")
    if not isinstance(lessons, list):
        issues.append("lessons is not a list")
        return issues
    n = len(lessons)
    if n < MIN_PUBLISHED_LESSONS or n > MAX_PUBLISHED_LESSONS:
        issues.append(
            f"expected {MIN_PUBLISHED_LESSONS}–{MAX_PUBLISHED_LESSONS} published lessons, got {n}"
        )

    for les in lessons:
        if isinstance(les, str):
            issues.append("lesson entry is a string placeholder, not an object")
            continue
        if not isinstance(les, dict):
            issues.append("lesson entry is not an object")
            continue
        slot = les.get("slot", "?")
        md = str(les.get("markdown") or "")
        if not md:
            issues.append(f"slot {slot}: missing markdown")
        elif is_lesson_markdown_stub(md):
            issues.append(f"slot {slot}: markdown is a word-count stub")
        elif len(md) < 500:
            issues.append(f"slot {slot}: markdown too short ({len(md)} chars, need 500+)")
        if not les.get("slug"):
            issues.append(f"slot {slot}: missing slug")

    return issues


def is_valid_editor_payload(data: Any) -> bool:
    return not editor_payload_issues(data)


CONSOLIDATOR_PHASES = frozenset({"plan", "draft_review", "ship_review"})


def consolidator_payload_issues(data: Any) -> list[str]:
    """Human-readable validation failures for consolidator JSON."""
    if not isinstance(data, dict):
        return ["payload is not a JSON object"]

    issues: list[str] = []
    phase = str(data.get("phase") or "")
    if phase and phase not in CONSOLIDATOR_PHASES:
        issues.append(f"invalid phase {phase!r} (expected plan, draft_review, or ship_review)")

    if not isinstance(data.get("review_summary"), dict):
        issues.append("missing review_summary")

    if phase == "plan":
        groups = data.get("lesson_groups")
        if not isinstance(groups, list):
            issues.append("lesson_groups is not a list")
        elif groups:
            n = len(groups)
            if n < MIN_PUBLISHED_LESSONS or n > MAX_PUBLISHED_LESSONS:
                issues.append(
                    f"expected {MIN_PUBLISHED_LESSONS}–{MAX_PUBLISHED_LESSONS} lesson_groups, got {n}"
                )

    return issues


def is_valid_consolidator_payload(data: Any) -> bool:
    return not consolidator_payload_issues(data)


def normalize_agent_payload(
    data: dict[str, Any], report_date: str | None, *, agent: str
) -> dict[str, Any]:
    """Align agent JSON date with the orchestrator run date when content is otherwise valid."""
    if not report_date:
        return data
    payload_date = str(data.get("date", ""))
    if payload_date and payload_date != report_date:
        print(
            f"Warning: {agent} JSON date {payload_date} != pipeline date {report_date}; "
            f"using {report_date}"
        )
        data = dict(data)
        data["date"] = report_date
    return data


def normalize_teacher_payload(data: dict[str, Any], report_date: str | None) -> dict[str, Any]:
    return normalize_agent_payload(data, report_date, agent="teacher")


def _load_json_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _date_ok(data: dict[str, Any], report_date: str | None) -> bool:
    if not report_date:
        return True
    return str(data.get("date", "")) == report_date


def _standard_sidecar_paths(role: str, root: Path, report_date: str | None) -> list[Path]:
    paths: list[Path] = []
    if role == "teacher":
        if report_date:
            paths.append(root / f".teacher-output-{report_date}.json")
            paths.append(root / "pipeline" / report_date / "teacher.json")
        paths.append(root / ".teacher_output.json")
    elif role == "editor":
        if report_date:
            paths.append(root / f".editor-output-{report_date}.json")
            paths.append(root / "pipeline" / report_date / "editor.json")
        paths.append(root / ".editor_output.json")
    elif role == "consolidator":
        if report_date:
            paths.append(root / f".consolidator-output-{report_date}.json")
            pipe = root / "pipeline" / report_date
            for phase in ("plan", "draft", "ship"):
                paths.append(pipe / f"consolidator-{phase}.json")
        paths.append(root / ".consolidator-output.json")
        paths.append(root / ".consolidator_output.json")
    return paths


def _sidecar_res_for_role(role: str) -> tuple[re.Pattern[str], ...]:
    if role == "editor":
        return EDITOR_SIDECAR_RES
    if role == "consolidator":
        return CONSOLIDATOR_SIDECAR_RES
    return TEACHER_SIDECAR_RES


def _pointer_markers_for_role(role: str) -> tuple[str, ...]:
    if role == "editor":
        return EDITOR_POINTER_MARKERS
    if role == "consolidator":
        return CONSOLIDATOR_POINTER_MARKERS
    return TEACHER_POINTER_MARKERS


def _glob_patterns_for_role(role: str) -> tuple[str, ...]:
    if role == "editor":
        return (
            ".editor-output*.json",
            ".editor-output-*.json",
            ".editor_output*.json",
            "pipeline/*/editor.json",
        )
    if role == "consolidator":
        return (
            ".consolidator-output*.json",
            ".consolidator-output-*.json",
            ".consolidator_output*.json",
            "pipeline/*/consolidator-*.json",
        )
    return (
        ".teacher-output*.json",
        ".teacher-output-*.json",
        ".teacher_output*.json",
        "teacher-output*.json",
        "pipeline/*/teacher.json",
    )


def _validator_for_role(role: str) -> RoleValidator:
    if role == "editor":
        return editor_payload_issues
    if role == "consolidator":
        return consolidator_payload_issues
    return teacher_payload_issues


def _is_valid_payload(role: str, data: Any) -> bool:
    return not _validator_for_role(role)(data)


def _sidecar_paths_from_raw(
    raw: str, *, root: Path, report_date: str | None, role: str
) -> list[Path]:
    """Candidate sidecar paths from agent prose plus canonical repo locations."""
    seen: set[Path] = set()
    ordered: list[Path] = []

    def add(path: Path) -> None:
        candidate = path if path.is_absolute() else root / path
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)

    for pattern in _sidecar_res_for_role(role):
        for match in pattern.finditer(raw or ""):
            add(Path(match.group(1)))

    for candidate in _standard_sidecar_paths(role, root, report_date):
        add(candidate)

    return ordered


def _glob_sidecar_candidates(root: Path, report_date: str | None, role: str) -> list[Path]:
    candidates: list[Path] = []
    for pattern in _glob_patterns_for_role(role):
        candidates.extend(root.glob(pattern))
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    if report_date:
        dated = [p for p in candidates if report_date in p.name or report_date in str(p)]
        if dated:
            return dated
    return candidates


def _load_valid_sidecar(path: Path, role: str) -> dict[str, Any] | None:
    loaded = _load_json_file(path)
    if loaded and _is_valid_payload(role, loaded):
        return loaded
    return None


def find_agent_sidecar_path(
    role: str, raw: str, *, root: Path = ROOT, report_date: str | None = None
) -> Path | None:
    """Locate a JSON sidecar referenced in prose or at canonical repo paths."""
    for candidate in _sidecar_paths_from_raw(raw, root=root, report_date=report_date, role=role):
        if _load_valid_sidecar(candidate, role) is not None:
            return candidate

    raw_l = (raw or "").lower()
    if any(marker in raw_l for marker in _pointer_markers_for_role(role)):
        for path in _glob_sidecar_candidates(root, report_date, role):
            if _load_valid_sidecar(path, role) is not None:
                if report_date and not _date_ok(_load_json_file(path) or {}, report_date):
                    continue
                return path
        for path in _glob_sidecar_candidates(root, report_date=None, role=role):
            if _load_valid_sidecar(path, role) is not None:
                return path

    return None


def find_teacher_sidecar_path(
    raw: str, *, root: Path = ROOT, report_date: str | None = None
) -> Path | None:
    return find_agent_sidecar_path("teacher", raw, root=root, report_date=report_date)


def maybe_regenerate_sidecar(role: str, raw: str, *, root: Path = ROOT) -> bool:
    """Run a generator script when the agent points at one and sidecar is missing."""
    script: Path | None = None
    if role == "teacher" and TEACHER_GEN_SCRIPT in (raw or ""):
        script = root / TEACHER_GEN_SCRIPT
    elif role == "editor":
        match = EDITOR_GEN_SCRIPT_RE.search(raw or "")
        if match:
            script = root / match.group(1)

    if script is None or not script.is_file():
        return False

    print(f"Running {role} sidecar generator: {script}")
    try:
        subprocess.run(
            [sys.executable, str(script)],
            cwd=root,
            check=False,
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Warning: {script.name} failed: {exc}")
        return False
    return True


def maybe_regenerate_teacher_sidecar(raw: str, *, root: Path = ROOT) -> bool:
    return maybe_regenerate_sidecar("teacher", raw, root=root)


def load_agent_response(
    role: str,
    raw: str,
    *,
    report_date: str | None = None,
    root: Path = ROOT,
    extract_json_fn: Any | None = None,
) -> dict[str, Any]:
    """
    Load agent JSON from inline body or sidecar file.

    Sidecar discovery runs before inline parse — large teacher/editor/consolidator payloads often
    return prose pointers instead of embedded JSON.
    """
    if role not in ("teacher", "editor", "consolidator"):
        if extract_json_fn is None:
            raise ValueError(f"No sidecar loader for role {role!r}")
        return extract_json_fn(raw)

    sidecar = find_agent_sidecar_path(role, raw, report_date=report_date, root=root)
    if sidecar is not None:
        loaded = _load_valid_sidecar(sidecar, role)
        if loaded is not None:
            print(f"Recovered {role} JSON from sidecar: {sidecar}")
            return normalize_agent_payload(loaded, report_date, agent=role)

    parsed: dict[str, Any] | None = None
    if extract_json_fn is not None:
        try:
            parsed = extract_json_fn(raw)
        except ValueError:
            parsed = None

    if parsed is not None and _is_valid_payload(role, parsed):
        return normalize_agent_payload(parsed, report_date, agent=role)

    if maybe_regenerate_sidecar(role, raw, root=root):
        sidecar = find_agent_sidecar_path(role, raw, report_date=report_date, root=root)
        if sidecar is not None:
            loaded = _load_valid_sidecar(sidecar, role)
            if loaded is not None:
                print(f"Recovered {role} JSON from sidecar after generator script: {sidecar}")
                return normalize_agent_payload(loaded, report_date, agent=role)

    issues: list[str] = []
    if parsed is not None:
        issues = _validator_for_role(role)(parsed)

    tried = [
        str(p) for p in _sidecar_paths_from_raw(raw, root=root, report_date=report_date, role=role)
    ]
    sidecar_issues: list[str] = []
    for p in _sidecar_paths_from_raw(raw, root=root, report_date=report_date, role=role):
        loaded = _load_json_file(p)
        if loaded is not None:
            sidecar_issues = _validator_for_role(role)(loaded)
            if sidecar_issues:
                msg = [f"No valid {role} JSON in inline response or sidecar file."]
                msg.append(f"Sidecar present but invalid: {p}")
                msg.append("Sidecar validation issues:")
                msg.extend(f"  - {i}" for i in sidecar_issues)
                raise ValueError("\n".join(msg))

    msg = [f"No valid {role} JSON in inline response or sidecar file."]
    if tried:
        msg.append("Checked paths:")
        msg.extend(f"  - {p}" for p in tried)
    if issues:
        msg.append("Inline JSON issues:")
        msg.extend(f"  - {i}" for i in issues)
    raise ValueError("\n".join(msg))


def load_teacher_response(
    raw: str,
    *,
    report_date: str | None = None,
    root: Path = ROOT,
    extract_json_fn: Any | None = None,
) -> dict[str, Any]:
    return load_agent_response(
        "teacher", raw, report_date=report_date, root=root, extract_json_fn=extract_json_fn
    )


def load_editor_response(
    raw: str,
    *,
    report_date: str | None = None,
    root: Path = ROOT,
    extract_json_fn: Any | None = None,
) -> dict[str, Any]:
    return load_agent_response(
        "editor", raw, report_date=report_date, root=root, extract_json_fn=extract_json_fn
    )


def load_consolidator_response(
    raw: str,
    *,
    report_date: str | None = None,
    root: Path = ROOT,
    extract_json_fn: Any | None = None,
) -> dict[str, Any]:
    return load_agent_response(
        "consolidator", raw, report_date=report_date, root=root, extract_json_fn=extract_json_fn
    )


def recover_teacher_json(
    raw: str,
    parsed: dict[str, Any] | None,
    *,
    report_date: str | None = None,
    root: Path = ROOT,
    extract_json_fn: Any | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper around load_teacher_response."""
    if parsed is not None and is_valid_teacher_payload(parsed):
        return normalize_teacher_payload(parsed, report_date)
    try:
        return load_teacher_response(
            raw, report_date=report_date, root=root, extract_json_fn=extract_json_fn
        )
    except ValueError as exc:
        if parsed is not None:
            issues = teacher_payload_issues(parsed)
            if issues:
                raise ValueError(
                    "teacher JSON failed validation:\n"
                    + "\n".join(f"  - {i}" for i in issues)
                ) from exc
        raise
