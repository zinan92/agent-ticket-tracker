"""Read-only observations of project artifacts and Git activity."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GIT_TIMEOUT_SECONDS = 2.0
OBSERVED_STATUSES = {"observed", "unavailable", "error"}
PROJECT_ARTIFACT_LIMIT = 5000
PROJECT_ARTIFACT_SKIP_DIRS = {".git", ".agent-ticket-tracker", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".tox", ".next", "dist", "build"}


def _within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _safe_declared_path(project: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"declared path is not project-relative: {relative}")
    path = (project / candidate).resolve(strict=False)
    if not _within(project, path):
        raise ValueError(f"declared path escapes project root: {relative}")
    for part_index in range(1, len(candidate.parts) + 1):
        parent = project.joinpath(*candidate.parts[:part_index])
        if parent.is_symlink() and not _within(project, parent.resolve(strict=False)):
            raise ValueError(f"declared symlink escapes project root: {relative}")
    return path


def _observation(identifier: str, kind: str, label: str, status: str, detail: str, observed_at: str) -> dict[str, str]:
    if status not in OBSERVED_STATUSES:
        raise ValueError(f"unsupported observation status: {status}")
    return {
        "id": identifier,
        "kind": kind,
        "label": label,
        "status": status,
        "detail": detail[:240],
        "observedAt": observed_at,
    }


def _mtime_text(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _artifact_observation(identifier: str, label: str, path: Path | None, project: Path, observed_at: str) -> dict[str, str]:
    if path is None:
        return _observation(identifier, "artifact", label, "unavailable", "No local Markdown path declared", observed_at)
    try:
        if not path.exists():
            return _observation(identifier, "artifact", label, "unavailable", f"Missing {path.relative_to(project)}", observed_at)
        if not path.is_file():
            return _observation(identifier, "artifact", label, "error", f"Expected file: {path.relative_to(project)}", observed_at)
        stat = path.stat()
    except (OSError, ValueError) as exc:
        return _observation(identifier, "artifact", label, "error", f"Cannot observe {label}: {exc}", observed_at)
    relative = path.relative_to(project).as_posix()
    return _observation(identifier, "artifact", label, "observed", f"{relative} · {stat.st_size} bytes · modified {_mtime_text(stat.st_mtime)}", observed_at)


def _tickets_observation(path: Path | None, project: Path, observed_at: str) -> dict[str, str]:
    identifier = "artifact-tickets"
    label = "Tickets"
    if path is None:
        return _observation(identifier, "artifact", label, "unavailable", "No local Markdown path declared", observed_at)
    try:
        if not path.exists():
            return _observation(identifier, "artifact", label, "unavailable", f"Missing {path.relative_to(project)}", observed_at)
        if not path.is_dir():
            return _observation(identifier, "artifact", label, "error", f"Expected directory: {path.relative_to(project)}", observed_at)
        files = sorted(item for item in path.iterdir() if not item.is_symlink() and item.is_file())
        latest = max(files, key=lambda item: item.stat().st_mtime, default=None)
        detail = f"{len(files)} readable ticket file(s)"
        if latest is not None:
            detail += f" · latest {latest.name} modified {_mtime_text(latest.stat().st_mtime)}"
        return _observation(identifier, "artifact", label, "observed", detail, observed_at)
    except OSError as exc:
        return _observation(identifier, "artifact", label, "error", f"Cannot observe tickets: {exc}", observed_at)


def _project_artifact_files(project: Path) -> dict[str, list[Path]]:
    found = {"html": [], "markdown": [], "json": []}
    seen = 0
    for directory, directories, filenames in os.walk(project, topdown=True, followlinks=False):
        base = Path(directory)
        directories[:] = sorted(
            name for name in directories
            if name not in PROJECT_ARTIFACT_SKIP_DIRS and not (base / name).is_symlink()
        )
        for filename in sorted(filenames):
            path = base / filename
            if path.is_symlink():
                continue
            suffix = path.suffix.lower()
            key = "html" if suffix == ".html" else "markdown" if suffix == ".md" else "json" if suffix == ".json" else None
            if key is None:
                continue
            found[key].append(path)
            seen += 1
            if seen >= PROJECT_ARTIFACT_LIMIT:
                return found
    return found


def _project_artifact_observation(identifier: str, label: str, paths: list[Path], project: Path, observed_at: str, extension: str) -> dict[str, str]:
    if not paths:
        return _observation(identifier, "artifact", label, "unavailable", f"No {extension} artifacts observed", observed_at)
    try:
        latest = max(paths, key=lambda item: item.stat().st_mtime)
        relative = latest.relative_to(project).as_posix()
        detail = f"{len(paths)} {extension} artifact(s) · latest {relative} modified {_mtime_text(latest.stat().st_mtime)}"
    except (OSError, ValueError) as exc:
        return _observation(identifier, "artifact", label, "error", f"Cannot observe {label}: {exc}", observed_at)
    return _observation(identifier, "artifact", label, "observed", detail, observed_at)


def project_artifact_observations(project: Path, observed_at: str) -> list[dict[str, str]]:
    """Observe bounded project artifacts without reading their contents."""

    files = _project_artifact_files(project)
    return [
        _project_artifact_observation("project-html", "HTML artifacts", files["html"], project, observed_at, "HTML"),
        _project_artifact_observation("project-markdown", "Markdown artifacts", files["markdown"], project, observed_at, "Markdown"),
        _project_artifact_observation("project-json", "JSON artifacts", files["json"], project, observed_at, "JSON"),
    ]


def _run_git(project: Path, args: list[str]) -> tuple[str | None, str | None]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LC_ALL": "C",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
    }
    command = [
        "git",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        *args,
    ]
    try:
        result = subprocess.run(
            command,
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return None, "git executable not found"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"Git observation failed: {exc}"
    if result.returncode != 0:
        detail = result.stderr.strip() or "Git command returned a non-zero status"
        return None, detail[:240]
    return result.stdout.strip(), None


def _git_observations(project: Path, observed_at: str) -> list[dict[str, str]]:
    probe, error = _run_git(project, ["rev-parse", "--is-inside-work-tree"])
    if error or probe != "true":
        detail = "Git repository not detected" if not error or "not a git repository" in error.lower() else error
        return [
            _observation("git-branch", "git", "Branch", "unavailable", detail, observed_at),
            _observation("git-worktree", "git", "Working tree", "unavailable", detail, observed_at),
            _observation("git-last-commit", "git", "Latest commit", "unavailable", detail, observed_at),
        ]

    branch, branch_error = _run_git(project, ["branch", "--show-current"])
    status, status_error = _run_git(project, ["status", "--porcelain=v1", "--branch"])
    commit, commit_error = _run_git(project, ["log", "-1", "--format=%h %s"])
    observations: list[dict[str, str]] = []
    if branch_error:
        observations.append(_observation("git-branch", "git", "Branch", "error", branch_error, observed_at))
    else:
        observations.append(_observation("git-branch", "git", "Branch", "observed", branch or "detached HEAD", observed_at))

    if status_error:
        observations.append(_observation("git-worktree", "git", "Working tree", "error", status_error, observed_at))
    else:
        lines = (status or "").splitlines()
        entries = [line for line in lines if not line.startswith("##")]
        untracked = sum(line.startswith("?? ") for line in entries)
        changed = len(entries) - untracked
        if not entries:
            detail = "clean"
        else:
            pieces = []
            if changed:
                pieces.append(f"{changed} changed")
            if untracked:
                pieces.append(f"{untracked} untracked")
            detail = ", ".join(pieces)
        observations.append(_observation("git-worktree", "git", "Working tree", "observed", detail, observed_at))

    if commit_error:
        observations.append(_observation("git-last-commit", "git", "Latest commit", "unavailable", "No commit observed", observed_at))
    else:
        observations.append(_observation("git-last-commit", "git", "Latest commit", "observed", commit or "No commit subject", observed_at))
    return observations


def collect_observations(project: Path, source: dict[str, Any], observed_at: str) -> list[dict[str, str]]:
    """Collect bounded, read-only observations without changing project state."""

    spec_path: Path | None = None
    issues_path: Path | None = None
    if source.get("kind") == "local_markdown":
        try:
            root = _safe_declared_path(project, source["root"])
            spec_path = _safe_declared_path(project, (root / source["spec"]).relative_to(project).as_posix())
            issues_path = _safe_declared_path(project, (root / source["issues"]).relative_to(project).as_posix())
        except (KeyError, ValueError, TypeError) as exc:
            detail = f"Local source cannot be observed: {exc}"
            return [
                _observation("artifact-spec", "artifact", "Spec", "error", detail, observed_at),
                _observation("artifact-tickets", "artifact", "Tickets", "error", detail, observed_at),
                *_git_observations(project, observed_at),
            ]
    return [
        _artifact_observation("artifact-spec", "Spec", spec_path, project, observed_at),
        _tickets_observation(issues_path, project, observed_at),
        *project_artifact_observations(project, observed_at),
        *_git_observations(project, observed_at),
    ]
