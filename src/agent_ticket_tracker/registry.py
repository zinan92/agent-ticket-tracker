"""Tracker-owned registration and loopback observer lifecycle."""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from .core import TrackerError, canonical_project, validate_slug


REGISTRY_SCHEMA_VERSION = 1
AUTO_FEATURE = "auto"
WORKFLOW_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
OBSERVER_START_TIMEOUT_SECONDS = 3.0
_OWNED_PROCESSES: dict[int, subprocess.Popen[bytes]] = {}


def default_registry_path() -> Path:
    return Path.home() / ".codex" / "agent-ticket-tracker" / "registry.json"


def _registry_path(value: str | Path | None) -> Path:
    path = Path(value).expanduser() if value is not None else default_registry_path()
    if path.is_symlink():
        raise TrackerError("tracker registry symlinks are not allowed")
    return path


def _empty_registry() -> dict[str, Any]:
    return {"schemaVersion": REGISTRY_SCHEMA_VERSION, "entries": []}


def _read_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_registry()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrackerError(f"tracker registry is malformed: {path}") from exc
    if not isinstance(data, dict) or data.get("schemaVersion") != REGISTRY_SCHEMA_VERSION or not isinstance(data.get("entries"), list):
        raise TrackerError("tracker registry schema is unsupported")
    for index, entry in enumerate(data["entries"]):
        if not isinstance(entry, dict):
            raise TrackerError(f"tracker registry entry {index} is malformed")
        for field in ("entryId", "project", "feature", "workflow", "url", "port", "pid", "attachedAt", "lastSeenAt"):
            if field not in entry:
                raise TrackerError(f"tracker registry entry {index} is missing {field}")
        if not isinstance(entry["entryId"], str) or not isinstance(entry["project"], str) or not isinstance(entry["feature"], str) or not isinstance(entry["workflow"], str):
            raise TrackerError(f"tracker registry entry {index} has invalid identity fields")
        if entry["url"] is not None and not isinstance(entry["url"], str):
            raise TrackerError(f"tracker registry entry {index} has an invalid URL")
        for field in ("port", "pid"):
            if entry[field] is not None and (not isinstance(entry[field], int) or isinstance(entry[field], bool)):
                raise TrackerError(f"tracker registry entry {index} has an invalid {field}")
    return data


def _write_registry(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    handle, temporary = tempfile.mkstemp(prefix=".registry-", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(handle, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _feature_value(value: str | None) -> str:
    feature = value or AUTO_FEATURE
    if feature != AUTO_FEATURE:
        validate_slug(feature, "feature")
    return feature


def _workflow_value(value: str | None) -> str:
    workflow = (value or "unknown").strip().lower()
    return workflow if WORKFLOW_RE.fullmatch(workflow) else "unknown"


def _entry_id(project: Path, feature: str) -> str:
    raw = f"{project}\0{feature}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _pick_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _pid_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    return True


def _healthy(port: Any) -> bool:
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        return False
    try:
        with urlopen(f"http://127.0.0.1:{port}/healthz", timeout=0.3) as response:
            payload = json.loads(response.read())
        return isinstance(payload, dict) and payload.get("ok") is True and payload.get("service") == "agent-ticket-tracker"
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def _start_observer(project: Path, feature: str, entry_id: str, registry_dir: Path) -> dict[str, Any] | None:
    port = _pick_port()
    logs = registry_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_path = logs / f"{entry_id}.log"
    package_src = str(Path(__file__).resolve().parents[1])
    observer_cwd = Path(package_src)
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = package_src if not existing_pythonpath else os.pathsep.join((package_src, existing_pythonpath))
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [
        sys.executable,
        "-m",
        "agent_ticket_tracker",
        "serve",
        "--project",
        str(project),
        "--feature",
        feature,
        "--port",
        str(port),
    ]
    try:
        with log_path.open("a", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                cwd=observer_cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except OSError:
        return None

    deadline = time.monotonic() + OBSERVER_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _healthy(port):
            _OWNED_PROCESSES[process.pid] = process
            return {"pid": process.pid, "port": port, "url": f"http://localhost:{port}/"}
        if process.poll() is not None:
            break
        time.sleep(0.1)
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=0.5)
    return None


def attach_project(
    project: str | Path,
    *,
    feature: str = AUTO_FEATURE,
    workflow: str = "unknown",
    registry: str | Path | None = None,
    start_server: bool = True,
) -> dict[str, Any]:
    """Register a project and start/reuse only the tracker observer."""

    root = canonical_project(project)
    feature_value = _feature_value(feature)
    workflow_value = _workflow_value(workflow)
    registry_file = _registry_path(registry)
    data = _read_registry(registry_file)
    entry_id = _entry_id(root, feature_value)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    entries = data["entries"]
    existing = next((entry for entry in entries if entry.get("entryId") == entry_id), None)

    if existing is not None and not start_server:
        return {
            "attached": True,
            "mode": "registered",
            "entryId": entry_id,
            "project": str(root),
            "feature": feature_value,
            "workflow": existing.get("workflow", workflow_value),
            "dashboardUrl": existing.get("url"),
            "pid": existing.get("pid"),
            "port": existing.get("port"),
            "registry": str(registry_file),
            "observer": {"status": "not_started"},
        }

    observer: dict[str, Any] | None = None
    mode = "registered"
    if existing is not None and start_server and _pid_alive(existing.get("pid")) and _healthy(existing.get("port")):
        observer = {"pid": existing["pid"], "port": existing["port"], "url": existing["url"]}
        mode = "reused"
    elif start_server:
        observer = _start_observer(root, feature_value, entry_id, registry_file.parent)
        mode = "started" if observer is not None else "unavailable"

    entry = {
        "entryId": entry_id,
        "project": str(root),
        "feature": feature_value,
        "workflow": workflow_value,
        "url": observer["url"] if observer else (existing.get("url") if existing else None),
        "port": observer["port"] if observer else (existing.get("port") if existing else None),
        "pid": observer["pid"] if observer else (existing.get("pid") if existing else None),
        "attachedAt": existing.get("attachedAt", now) if existing else now,
        "lastSeenAt": now,
    }
    if existing is None:
        entries.append(entry)
    else:
        entries[entries.index(existing)] = entry
    _write_registry(registry_file, data)
    return {
        "attached": True,
        "mode": mode,
        "entryId": entry_id,
        "project": str(root),
        "feature": feature_value,
        "workflow": workflow_value,
        "dashboardUrl": entry["url"],
        "pid": entry["pid"],
        "port": entry["port"],
        "registry": str(registry_file),
        "observer": {"status": "started" if mode == "started" else "reused" if mode == "reused" else "unavailable"},
    }
