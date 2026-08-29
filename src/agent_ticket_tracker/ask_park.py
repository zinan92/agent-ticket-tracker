"""Read-only projection of the Ask Park state contract."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .observations import collect_observations

ASK_PARK_CONTRACT = "ask-park.state/v1"
ASK_PARK_SOURCE = ".ask-park/state.json"
FRESH_SECONDS = 900
MODULES = ("plan", "build", "cloudbase", "experience", "device", "release")
MODULE_LABELS = {"plan": "Plan", "build": "Build", "cloudbase": "CloudBase", "experience": "Experience", "device": "Device", "release": "Release"}
ACTIVITY_STATES = {"waiting", "current", "completed", "failed", "blocked-external", "locked", "not-applicable"}
EVIDENCE_STATES = {"absent", "valid", "stale", "invalid", "not-applicable"}
APPLICABILITY_STATES = {"required", "not-applicable"}


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _record(identifier: str, kind: str, label: str, status: str, detail: str, observed_at: str) -> dict[str, str]:
    return {"id": identifier, "kind": kind, "label": label, "status": status, "detail": detail[:240], "observedAt": observed_at}


def _source(status: str, errors: list[str], observed_at: str) -> dict[str, Any]:
    return {"kind": "ask_park", "status": status, "root": ASK_PARK_SOURCE, "spec": None, "issues": None, "observedAt": observed_at, "maxAgeSeconds": FRESH_SECONDS, "errors": errors}


def _malformed(project: Path, detail: str, observed_at: str) -> dict[str, Any]:
    observations = [_record("ask-park-state", "workflow", "Ask Park state", "error", detail, observed_at)]
    observations.extend(collect_observations(project, {"kind": "manual", "root": None, "spec": None, "issues": None}, observed_at))
    return {"run": {"id": "run", "displayName": project.name, "featureSlug": "auto"}, "source": _source("malformed", [detail], observed_at), "nodes": [], "observations": observations}


def _validate(data: Any) -> str | None:
    if not isinstance(data, dict):
        return "Ask Park state must be an object"
    if data.get("contract_version") != ASK_PARK_CONTRACT:
        return "unsupported Ask Park state contract"
    if not isinstance(data.get("project_id"), str) or not data["project_id"]:
        return "Ask Park project_id is missing"
    modules = data.get("modules")
    if not isinstance(modules, dict) or set(modules) != set(MODULES):
        return "Ask Park state must contain the six canonical modules"
    for name in MODULES:
        module = modules[name]
        if not isinstance(module, dict):
            return f"Ask Park module {name} is malformed"
        if module.get("applicability") not in APPLICABILITY_STATES:
            return f"Ask Park module {name} has invalid applicability"
        if module.get("activity_state") not in ACTIVITY_STATES:
            return f"Ask Park module {name} has invalid activity_state"
        if module.get("evidence_state") not in EVIDENCE_STATES:
            return f"Ask Park module {name} has invalid evidence_state"
        if module.get("receipt_id") is not None and not isinstance(module["receipt_id"], str):
            return f"Ask Park module {name} has invalid receipt_id"
    current = data.get("current_module")
    if current is not None and current not in MODULES:
        return "Ask Park current_module is invalid"
    return None


def _module_status(module: dict[str, Any]) -> str:
    activity = module["activity_state"]
    evidence = module["evidence_state"]
    if activity == "not-applicable":
        return "verified"
    if activity == "completed":
        return "verified" if evidence in {"valid", "not-applicable"} else "partial"
    if activity == "current":
        return "running"
    if activity in {"failed"}:
        return "needs-review"
    if activity == "blocked-external":
        return "blocked"
    return "waiting"


def _acceptance(module_name: str, module: dict[str, Any]) -> list[dict[str, str]]:
    activity = module["activity_state"]
    status = "verified" if activity in {"completed", "not-applicable"} else "pending"
    return [{"id": f"{module_name}-activity", "label": f"Ask Park activity: {activity}", "status": status}]


def _evidence(module_name: str, module: dict[str, Any], observed_at: str) -> list[dict[str, Any]]:
    evidence_state = module["evidence_state"]
    ref = f"{ASK_PARK_SOURCE}#modules.{module_name}"
    if evidence_state == "valid" and module.get("receipt_id"):
        return [{"id": f"{module_name}-receipt", "kind": "artifact", "label": "Ask Park receipt", "status": "verified", "ref": ref, "observedAt": observed_at, "freshForSeconds": FRESH_SECONDS}]
    if evidence_state == "not-applicable":
        return [{"id": f"{module_name}-not-applicable", "kind": "manual", "label": "Ask Park not applicable", "status": "verified", "ref": ref, "observedAt": observed_at, "freshForSeconds": FRESH_SECONDS}]
    if evidence_state == "stale":
        return [{"id": f"{module_name}-stale", "kind": "artifact", "label": "Ask Park evidence is stale", "status": "stale", "ref": ref, "observedAt": observed_at, "freshForSeconds": FRESH_SECONDS}]
    if evidence_state == "invalid":
        return [{"id": f"{module_name}-invalid", "kind": "artifact", "label": "Ask Park evidence is invalid", "status": "failed", "ref": ref, "observedAt": observed_at, "freshForSeconds": FRESH_SECONDS}]
    return []


def _nodes(data: dict[str, Any], observed_at: str) -> list[dict[str, Any]]:
    project_id = data["project_id"]
    current = data.get("current_module")
    current_label = current or "none"
    nodes: list[dict[str, Any]] = [
        {"id": "run", "parentId": None, "kind": "run", "name": project_id, "status": "partial", "blockerIds": [], "acceptance": [], "evidence": [], "nextAction": "Observe the current Ask Park module", "note": "Projected read-only from Ask Park state."},
        {"id": "ask-park", "parentId": "run", "kind": "phase", "name": "Ask Park", "status": "partial", "blockerIds": [], "acceptance": [], "evidence": [], "nextAction": "Continue the module named by Ask Park", "note": f"Current module: {current_label}."},
    ]
    for name in MODULES:
        module = data["modules"][name]
        activity = module["activity_state"]
        module_label = MODULE_LABELS[name]
        evidence_state = module["evidence_state"]
        if name == current:
            next_action = f"Continue Ask Park at {module_label}"
        elif activity == "locked":
            next_action = f"Wait for the predecessor before {module_label}"
        elif activity in {"completed", "not-applicable"}:
            next_action = f"Keep the recorded Ask Park evidence for {module_label}"
        else:
            next_action = f"Observe the next Ask Park update for {module_label}"
        nodes.append({"id": f"ask-park-{name}", "parentId": "ask-park", "kind": "ticket", "name": module_label, "status": _module_status(module), "blockerIds": [], "acceptance": _acceptance(name, module), "evidence": _evidence(name, module, observed_at), "nextAction": next_action, "note": f"activity_state={activity}; evidence_state={evidence_state}."})
    return nodes


def read_ask_park(project: Path, now: datetime) -> dict[str, Any] | None:
    path = project / ".ask-park" / "state.json"
    if not path.exists():
        return None
    observed_at = _timestamp(now)
    for candidate in (project / ".ask-park", path):
        if candidate.is_symlink() or not _within(project, candidate.resolve(strict=False)):
            return _malformed(project, "Ask Park state symlink is not allowed", observed_at)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _malformed(project, f"cannot read Ask Park state: {exc}", observed_at)
    error = _validate(data)
    if error:
        return _malformed(project, error, observed_at)
    assert isinstance(data, dict)
    project_id = data["project_id"]
    current_label = data.get("current_module") or "none"
    detail = f"{ASK_PARK_SOURCE} · project={project_id} · current={current_label}"
    observations = [_record("ask-park-state", "workflow", "Ask Park state", "observed", detail, observed_at)]
    if data.get("current_module"):
        observations.append(_record("ask-park-current", "workflow", "Current module", "observed", str(data["current_module"]), observed_at))
    if data.get("control_outcome") not in {None, "none"}:
        observations.append(_record("ask-park-control", "workflow", "Control outcome", "error", str(data["control_outcome"]), observed_at))
    observations.extend(collect_observations(project, {"kind": "manual", "root": None, "spec": None, "issues": None}, observed_at))
    return {"run": {"id": "run", "displayName": project_id, "featureSlug": "auto"}, "source": _source("live", [], observed_at), "nodes": _nodes(data, observed_at), "observations": observations}
