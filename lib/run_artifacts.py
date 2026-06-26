"""Remove stale agent sidecar files and one-off scripts from prior runs."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Repo root — hidden sidecars and agent scratch scripts
ROOT_GLOBS = (
    ".teacher-output*.json",
    ".teacher-output-*.json",
    ".teacher_output.json",
    ".editor-output*.json",
    ".editor-output-*.json",
    ".editor_output.json",
    ".consolidator-output*.json",
    ".consolidator-output-*.json",
    ".consolidator_output.json",
    "teacher-*.json",
    ".teacher-gen*.py",
    "teacher-response-body.txt",
)

# scripts/ — keep nightly-local.sh and install-schedule.sh only
SCRIPTS_GLOBS = (
    "editor_output_*.py",
    "teacher_lessons_*.py",
    "generate_teacher_output_*.py",
    "_*.json",
)

SCRIPTS_KEEP = frozenset({"nightly-local.sh", "install-schedule.sh"})


def cleanup_run_artifacts(*, root: Path = ROOT) -> list[str]:
    """
    Delete hidden sidecar JSON, agent gen scripts, and dated scripts/ helpers.

    Returns paths removed (as strings relative to root when possible).
    """
    removed: list[str] = []

    for pattern in ROOT_GLOBS:
        for path in root.glob(pattern):
            if path.is_file():
                path.unlink()
                removed.append(str(path.relative_to(root)))

    scripts_dir = root / "scripts"
    if scripts_dir.is_dir():
        for pattern in SCRIPTS_GLOBS:
            for path in scripts_dir.glob(pattern):
                if path.is_file() and path.name not in SCRIPTS_KEEP:
                    path.unlink()
                    removed.append(str(path.relative_to(root)))

    return sorted(removed)


def clear_agent_sidecars(*, report_date: str | None = None, root: Path = ROOT) -> list[str]:
    """Remove teacher/editor/consolidator sidecars so retries cannot reuse stale JSON."""
    removed: list[str] = []
    for pattern in ROOT_GLOBS:
        for path in root.glob(pattern):
            if path.is_file():
                path.unlink()
                removed.append(str(path.relative_to(root)))

    if report_date:
        pipe = root / "pipeline" / report_date
        for name in ("teacher.json", "editor.json"):
            path = pipe / name
            if path.is_file():
                path.unlink()
                removed.append(str(path.relative_to(root)))
        if pipe.is_dir():
            for path in pipe.glob("consolidator-*.json"):
                if path.is_file():
                    path.unlink()
                    removed.append(str(path.relative_to(root)))

    return sorted(set(removed))

