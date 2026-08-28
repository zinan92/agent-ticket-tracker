"""Manifest, source, status, blocker, and frontier logic for v1."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .observations import collect_observations


class TrackerError(ValueError):
    """A user-visible, fail-closed tracker error."""


SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
ISSUE_FILE_RE = re.compile(r"^(?P<number>[0-9]{2})-(?P<slug>[a-z0-9][a-z0-9._-]*)\.md$")
H1_RE = re.compile(r"^#\s+(?P<title>.+?)\s*$")
STATUS_RE = re.compile(r"^(?:\*\*Status:\*\*|Status:)\s*(?P<status>[^\s]+)", re.IGNORECASE)
BLOCKED_BY_RE = re.compile(r"^(?:\*\*Blocked by:\*\*|Blocked by:)\s*(?P<value>.+?)\s*$", re.IGNORECASE)
CHECKBOX_RE = re.compile(r"^-\s+\[(?P<mark>[ xX])\]\s+(?P<label>.+?)\s*$")

SOURCE_KINDS = {"sample", "manual", "local_markdown"}
NODE_KINDS = {"run", "phase", "ticket", "decision", "acceptance"}
STATUS_HINTS = {"planned", "ready", "running", "partial", "verified", "needs-review", "blocked", "waiting"}
ACCEPTANCE_STATUSES = {"pending", "verified", "failed"}
EVIDENCE_KINDS = {"test", "review", "runtime", "device", "artifact", "manual"}
EVIDENCE_STATUSES = {"verified", "missing", "stale", "failed"}
SOURCE_STATUSES = {"live", "sample", "missing", "malformed", "stale"}
FRONTIER_STATUSES = {"ready", "partial", "needs-review"}
PARENT_STATUS_ORDER = ("blocked", "needs-review", "running", "partial")
DEFAULT_FRESH_SECONDS = 900
MIN_FRESH_SECONDS = 1
MAX_FRESH_SECONDS = 604800
FUTURE_CLOCK_TOLERANCE = timedelta(seconds=60)
AUTO_FEATURE = "auto"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def timestamp(value: datetime | None = None) -> str:
    current = value or utc_now()
    return current.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: Any, field: str, now: datetime | None = None) -> datetime:
    if not isinstance(value, str) or not value:
        raise TrackerError(f"{field} must be an RFC3339 UTC string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TrackerError(f"{field} is not a valid RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise TrackerError(f"{field} must use UTC")
    current = now or utc_now()
    if parsed > current + FUTURE_CLOCK_TOLERANCE:
        raise TrackerError(f"{field} is too far in the future")
    return parsed.astimezone(timezone.utc)


def validate_slug(value: Any, field: str = "feature slug") -> str:
    if not isinstance(value, str) or not SLUG_RE.fullmatch(value) or value in {".", ".."}:
        raise TrackerError(f"{field} must match lowercase safe slug syntax")
    return value


def canonical_project(path: str | Path) -> Path:
    raw = Path(path).expanduser()
    if not raw.exists():
        raise TrackerError(f"project does not exist: {raw}")
    if not raw.is_dir():
        raise TrackerError(f"project is not a directory: {raw}")
    if raw.is_symlink():
        raise TrackerError("project root symlinks are not allowed")
    return raw.resolve(strict=True)


def _within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def safe_state_dir(project: Path, feature: str, create: bool = False) -> Path:
    validate_slug(feature)
    state_root = project / ".agent-ticket-tracker"
    if state_root.exists() and state_root.is_symlink():
        raise TrackerError(".agent-ticket-tracker symlinks are not allowed")
    if state_root.exists() and not state_root.is_dir():
        raise TrackerError(".agent-ticket-tracker is not a directory")
    if create:
        state_root.mkdir(exist_ok=True)
    if not state_root.exists():
        return state_root / feature
    resolved_root = state_root.resolve(strict=True)
    if not _within(project, resolved_root):
        raise TrackerError("tracker state directory escapes the project root")
    feature_dir = state_root / feature
    if feature_dir.exists() and feature_dir.is_symlink():
        raise TrackerError("feature state symlinks are not allowed")
    if feature_dir.exists() and not feature_dir.is_dir():
        raise TrackerError("feature state path is not a directory")
    resolved_feature = feature_dir.resolve(strict=False)
    if not _within(project, resolved_feature):
        raise TrackerError("feature state directory escapes the project root")
    if create:
        feature_dir.mkdir(exist_ok=True)
    return feature_dir


def manifest_path(project: Path, feature: str, create: bool = False) -> Path:
    return safe_state_dir(project, feature, create=create) / "manifest.json"


def _require_keys(value: dict[str, Any], required: set[str], allowed: set[str], label: str) -> None:
    missing = sorted(required - value.keys())
    extra = sorted(set(value) - allowed)
    if missing:
        raise TrackerError(f"{label} missing fields: {', '.join(missing)}")
    if extra:
        raise TrackerError(f"{label} has unsupported fields: {', '.join(extra)}")


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise TrackerError(f"{field} must be a string")
    return value


def _validate_source(source: Any, feature: str, now: datetime) -> None:
    if not isinstance(source, dict):
        raise TrackerError("source must be an object")
    fields = {"kind", "root", "spec", "issues", "observedAt", "maxAgeSeconds"}
    _require_keys(source, fields, fields, "source")
    kind = _require_string(source["kind"], "source.kind")
    if kind not in SOURCE_KINDS:
        raise TrackerError(f"unsupported source.kind: {kind}")
    for field in ("root", "spec", "issues"):
        if source[field] is not None and not isinstance(source[field], str):
            raise TrackerError(f"source.{field} must be a string or null")
    if kind in {"sample", "manual"} and any(source[field] is not None for field in ("root", "spec", "issues")):
        raise TrackerError(f"source.{kind} cannot declare local Markdown paths")
    if kind == "local_markdown":
        expected = {"root": f".scratch/{feature}", "spec": "spec.md", "issues": "issues"}
        for field, expected_value in expected.items():
            if source[field] != expected_value:
                raise TrackerError(f"source.{field} must be {expected_value!r} for local_markdown")
    parse_utc(source["observedAt"], "source.observedAt", now)
    max_age = source["maxAgeSeconds"]
    if not isinstance(max_age, int) or isinstance(max_age, bool) or not 1 <= max_age <= MAX_FRESH_SECONDS:
        raise TrackerError("source.maxAgeSeconds must be an integer from 1 through 604800")


def _validate_evidence(record: Any, prefix: str, now: datetime) -> None:
    if not isinstance(record, dict):
        raise TrackerError(f"{prefix} must be an object")
    fields = {"id", "kind", "label", "status", "ref", "observedAt", "freshForSeconds"}
    _require_keys(record, fields, fields, prefix)
    validate_slug(record["id"], f"{prefix}.id")
    kind = _require_string(record["kind"], f"{prefix}.kind")
    if kind not in EVIDENCE_KINDS:
        raise TrackerError(f"unsupported {prefix}.kind: {kind}")
    status = _require_string(record["status"], f"{prefix}.status")
    if status not in EVIDENCE_STATUSES:
        raise TrackerError(f"unsupported {prefix}.status: {status}")
    _require_string(record["label"], f"{prefix}.label")
    _require_string(record["ref"], f"{prefix}.ref")
    parse_utc(record["observedAt"], f"{prefix}.observedAt", now)
    fresh_for = record["freshForSeconds"]
    if not isinstance(fresh_for, int) or isinstance(fresh_for, bool) or not MIN_FRESH_SECONDS <= fresh_for <= MAX_FRESH_SECONDS:
        raise TrackerError(f"{prefix}.freshForSeconds must be an integer from 1 through 604800")


def _validate_acceptance(record: Any, prefix: str) -> None:
    if not isinstance(record, dict):
        raise TrackerError(f"{prefix} must be an object")
    fields = {"id", "label", "status"}
    _require_keys(record, fields, fields, prefix)
    validate_slug(record["id"], f"{prefix}.id")
    _require_string(record["label"], f"{prefix}.label")
    status = _require_string(record["status"], f"{prefix}.status")
    if status not in ACCEPTANCE_STATUSES:
        raise TrackerError(f"unsupported {prefix}.status: {status}")


def _validate_node(node: Any, prefix: str, now: datetime) -> None:
    if not isinstance(node, dict):
        raise TrackerError(f"{prefix} must be an object")
    fields = {"id", "parentId", "kind", "name", "status", "blockerIds", "acceptance", "evidence", "nextAction", "note"}
    _require_keys(node, fields, fields, prefix)
    validate_slug(node["id"], f"{prefix}.id")
    if node["parentId"] is not None:
        validate_slug(node["parentId"], f"{prefix}.parentId")
    kind = _require_string(node["kind"], f"{prefix}.kind")
    if kind not in NODE_KINDS:
        raise TrackerError(f"unsupported {prefix}.kind: {kind}")
    status = _require_string(node["status"], f"{prefix}.status")
    if status not in STATUS_HINTS:
        raise TrackerError(f"unsupported {prefix}.status: {status}")
    _require_string(node["name"], f"{prefix}.name")
    _require_string(node["nextAction"], f"{prefix}.nextAction")
    _require_string(node["note"], f"{prefix}.note")
    blockers = node["blockerIds"]
    if not isinstance(blockers, list) or any(not isinstance(item, str) for item in blockers):
        raise TrackerError(f"{prefix}.blockerIds must be a string array")
    if not isinstance(node["acceptance"], list):
        raise TrackerError(f"{prefix}.acceptance must be an array")
    for index, record in enumerate(node["acceptance"]):
        _validate_acceptance(record, f"{prefix}.acceptance[{index}]")
    if not isinstance(node["evidence"], list):
        raise TrackerError(f"{prefix}.evidence must be an array")
    for index, record in enumerate(node["evidence"]):
        _validate_evidence(record, f"{prefix}.evidence[{index}]", now)


def validate_manifest(manifest: Any, feature: str, now: datetime | None = None) -> dict[str, Any]:
    current = now or utc_now()
    if not isinstance(manifest, dict):
        raise TrackerError("manifest must be a JSON object")
    fields = {"schemaVersion", "run", "source", "nodes", "overrides"}
    _require_keys(manifest, fields, fields, "manifest")
    if manifest["schemaVersion"] != 1:
        raise TrackerError("manifest.schemaVersion must be 1")
    run = manifest["run"]
    if not isinstance(run, dict):
        raise TrackerError("run must be an object")
    run_fields = {"id", "displayName", "featureSlug"}
    _require_keys(run, run_fields, run_fields, "run")
    run_id = validate_slug(run["id"], "run.id")
    feature_slug = validate_slug(run["featureSlug"], "run.featureSlug")
    if run_id != feature_slug or feature_slug != feature:
        raise TrackerError("run.id, run.featureSlug, and requested feature must match")
    _require_string(run["displayName"], "run.displayName")
    _validate_source(manifest["source"], feature, current)
    nodes = manifest["nodes"]
    if not isinstance(nodes, list):
        raise TrackerError("nodes must be an array")
    kind = manifest["source"]["kind"]
    if kind in {"sample", "manual"} and not nodes:
        raise TrackerError(f"source.{kind} requires a nonempty nodes array")
    if kind == "local_markdown" and nodes:
        raise TrackerError("source.local_markdown requires an empty nodes array")
    seen: set[str] = set()
    for index, node in enumerate(nodes):
        _validate_node(node, f"nodes[{index}]", current)
        if node["id"] in seen:
            raise TrackerError(f"duplicate node id: {node['id']}")
        seen.add(node["id"])
    overrides = manifest["overrides"]
    if not isinstance(overrides, dict):
        raise TrackerError("overrides must be an object")
    if kind in {"sample", "manual"} and overrides:
        raise TrackerError(f"source.{kind} cannot declare generated-node overrides")
    allowed_override = {"acceptance", "evidence", "nextAction", "note"}
    for node_id, override in overrides.items():
        validate_slug(node_id, "override node id")
        if not isinstance(override, dict):
            raise TrackerError(f"override for {node_id} must be an object")
        extra = set(override) - allowed_override
        if extra:
            raise TrackerError(f"override for {node_id} has unsupported fields: {', '.join(sorted(extra))}")
        if "acceptance" in override:
            if not isinstance(override["acceptance"], list):
                raise TrackerError(f"override {node_id}.acceptance must be an array")
            for index, record in enumerate(override["acceptance"]):
                _validate_acceptance(record, f"overrides.{node_id}.acceptance[{index}]")
        if "evidence" in override:
            if not isinstance(override["evidence"], list):
                raise TrackerError(f"override {node_id}.evidence must be an array")
            for index, record in enumerate(override["evidence"]):
                _validate_evidence(record, f"overrides.{node_id}.evidence[{index}]", current)
        for field in ("nextAction", "note"):
            if field in override:
                _require_string(override[field], f"overrides.{node_id}.{field}")
    return manifest


def read_manifest(path: Path, feature: str, now: datetime | None = None) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TrackerError(f"manifest missing: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise TrackerError(f"manifest is malformed: {path}") from exc
    return validate_manifest(manifest, feature, now=now)


def _write_exclusive(path: Path, payload: dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        return True
    except FileExistsError:
        return False


def _acceptance(identifier: str, label: str, status: str = "verified") -> dict[str, str]:
    return {"id": identifier, "label": label, "status": status}


def _evidence(identifier: str, kind: str, label: str, ref: str, now: datetime) -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": kind,
        "label": label,
        "status": "verified",
        "ref": ref,
        "observedAt": timestamp(now),
        "freshForSeconds": DEFAULT_FRESH_SECONDS,
    }


def sample_manifest(feature: str, now: datetime | None = None) -> dict[str, Any]:
    current = now or utc_now()
    def node(node_id: str, parent: str | None, kind: str, name: str, status: str, acceptance: list[dict[str, str]], evidence: list[dict[str, Any]], next_action: str, note: str, blockers: list[str] | None = None) -> dict[str, Any]:
        return {
            "id": node_id,
            "parentId": parent,
            "kind": kind,
            "name": name,
            "status": status,
            "blockerIds": blockers or [],
            "acceptance": acceptance,
            "evidence": evidence,
            "nextAction": next_action,
            "note": note,
        }

    nodes = [
        node("run", None, "run", "Feature release", "partial", [_acceptance("run-map", "Delivery map loaded", "verified")], [_evidence("run-fixture", "artifact", "Sample run fixture", "sample", current)], "Finish the active implementation frontier", "Sample state is non-actionable."),
        node("spec", "run", "phase", "Spec", "verified", [_acceptance("spec-contract", "Product contract", "verified")], [_evidence("spec-review", "review", "Spec review", "sample/spec-review", current)], "Keep the contract stable", "The contract is an upstream anchor."),
        node("tickets", "run", "phase", "Tickets", "verified", [_acceptance("ticket-map", "Ticket graph", "verified")], [_evidence("ticket-map", "artifact", "Ticket map", "sample/tickets", current)], "Work the unblocked frontier", "Each ticket is a vertical slice."),
        node("implementation", "run", "phase", "Implementation", "partial", [_acceptance("impl-frontier", "Implementation frontier", "pending")], [], "Resolve the first incomplete leaf", "Two branches are still active."),
        node("release", "run", "phase", "Release", "waiting", [_acceptance("release-ready", "Release readiness", "pending")], [], "Wait for implementation evidence", "Release is intentionally not connected."),
        node("ticket-session", "tickets", "ticket", "Session recovery", "verified", [_acceptance("session-launch", "Launch", "verified"), _acceptance("session-reopen", "Reopen", "verified")], [_evidence("session-test", "test", "Test receipt", "sample/session-test", current), _evidence("session-review", "review", "Review receipt", "sample/session-review", current)], "Preserve the verified receipt", "Green requires current evidence."),
        node("ticket-composer", "tickets", "ticket", "Composer queue", "running", [_acceptance("composer-cache", "Draft cache", "verified"), _acceptance("composer-retry", "Retry path", "verified"), _acceptance("composer-failure", "Failure receipt", "pending"), _acceptance("composer-review", "Review confirmation", "pending")], [_evidence("composer-test", "test", "Test receipt", "sample/composer-test", current)], "Complete the failure receipt, then request review", "Running is not green."),
        node("ticket-workbench", "tickets", "ticket", "Workbench evidence", "needs-review", [_acceptance("workbench-preview", "Preview", "verified"), _acceptance("workbench-device", "Device check", "pending")], [_evidence("workbench-preview", "artifact", "Preview receipt", "sample/workbench-preview", current)], "Re-run the missing device check", "Review is required before release."),
        node("ticket-review", "implementation", "ticket", "Cross-review", "verified", [_acceptance("review-standards", "Standards axis", "verified"), _acceptance("review-spec", "Spec axis", "verified")], [_evidence("review-receipt", "review", "Cross-review receipt", "sample/review", current)], "Preserve the review receipt", "Review is separate from self-report.", ["ticket-session"]),
        node("ticket-smoke", "implementation", "ticket", "Integration smoke", "running", [_acceptance("smoke-launch", "Local launch", "verified"), _acceptance("smoke-flow", "Primary flow", "pending")], [_evidence("smoke-log", "runtime", "Run log", "sample/smoke", current)], "Finish the primary flow", "The sample runner is active.", ["ticket-composer"]),
    ]
    return {
        "schemaVersion": 1,
        "run": {"id": feature, "displayName": "Feature release", "featureSlug": feature},
        "source": {"kind": "sample", "root": None, "spec": None, "issues": None, "observedAt": timestamp(current), "maxAgeSeconds": DEFAULT_FRESH_SECONDS},
        "nodes": nodes,
        "overrides": {},
    }


def init_project(project: str | Path, feature: str, sample: bool = False) -> tuple[Path, bool]:
    root = canonical_project(project)
    validate_slug(feature)
    state_dir = safe_state_dir(root, feature, create=True)
    state_dir.mkdir(exist_ok=True)
    now = utc_now()
    manifest = sample_manifest(feature, now) if sample else {
        "schemaVersion": 1,
        "run": {"id": feature, "displayName": feature.replace("-", " ").title(), "featureSlug": feature},
        "source": {"kind": "local_markdown", "root": f".scratch/{feature}", "spec": "spec.md", "issues": "issues", "observedAt": timestamp(now), "maxAgeSeconds": DEFAULT_FRESH_SECONDS},
        "nodes": [],
        "overrides": {},
    }
    path = state_dir / "manifest.json"
    created = _write_exclusive(path, manifest)
    return path, created


def _safe_source_path(project: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise TrackerError(f"source path is not project-relative: {relative}")
    path = (project / candidate).resolve(strict=False)
    if not _within(project, path):
        raise TrackerError(f"source path escapes project root: {relative}")
    for parent in [project / part for part in candidate.parts]:
        if parent.is_symlink():
            resolved = parent.resolve(strict=False)
            if not _within(project, resolved):
                raise TrackerError(f"source symlink escapes project root: {relative}")
    return path


def _section_lines(lines: list[str], heading: str) -> list[str]:
    start = None
    for index, line in enumerate(lines):
        if line.strip().lower() == heading.lower():
            start = index + 1
            break
    if start is None:
        return []
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return lines[start:end]


def _issue_status(value: str) -> str:
    normalized = value.strip().lower()
    return {"ready-for-agent": "ready", "ready": "ready", "claimed": "running", "running": "running", "resolved": "verified", "verified": "verified", "merged": "verified", "blocked": "blocked", "needs-review": "needs-review", "partial": "partial", "waiting": "waiting", "planned": "planned"}.get(normalized, "planned")


def _issue_title(lines: list[str], fallback: str) -> str:
    for line in lines:
        match = H1_RE.match(line)
        if match:
            title = match.group("title")
            title = re.sub(r"^[0-9]{2}\s*[-–—]\s*", "", title).strip()
            return title or fallback
    return fallback


def _parse_issue(path: Path, number_to_id: dict[str, str], parent: str) -> dict[str, Any]:
    match = ISSUE_FILE_RE.fullmatch(path.name)
    if not match:
        raise TrackerError(f"issue filename must match NN-slug.md: {path.name}")
    number = match.group("number")
    slug = match.group("slug")
    node_id = f"ticket-{number}-{slug}"
    validate_slug(node_id, "generated ticket id")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise TrackerError(f"cannot read issue: {path}") from exc
    status = "planned"
    blockers_raw: str | None = None
    for line in lines:
        status_match = STATUS_RE.match(line.strip())
        if status_match:
            status = _issue_status(status_match.group("status"))
        blocked_match = BLOCKED_BY_RE.match(line.strip())
        if blocked_match:
            blockers_raw = blocked_match.group("value")
    blocker_ids: list[str] = []
    if blockers_raw and not blockers_raw.strip().lower().startswith("none"):
        for token in blockers_raw.split(","):
            value = token.strip()
            if not value:
                continue
            if value in number_to_id:
                blocker_ids.append(number_to_id[value])
            elif SLUG_RE.fullmatch(value):
                blocker_ids.append(value)
            else:
                blocker_ids.append(f"unknown-{value.lower().replace(' ', '-')}")
    acceptance: list[dict[str, str]] = []
    for index, line in enumerate(_section_lines(lines, "## Acceptance criteria"), start=1):
        check = CHECKBOX_RE.match(line.strip())
        if check:
            acceptance.append(_acceptance(f"a{index}", check.group("label"), "verified" if check.group("mark").lower() == "x" else "pending"))
    return {
        "id": node_id,
        "parentId": parent,
        "kind": "ticket",
        "name": _issue_title(lines, slug.replace("-", " ").title()),
        "status": status,
        "blockerIds": blocker_ids,
        "acceptance": acceptance,
        "evidence": [],
        "nextAction": "Read the issue contract and begin the next safe step",
        "note": f"Generated from {path.name}; green requires explicit evidence.",
    }


def _local_markdown_nodes(project: Path, feature: str, source: dict[str, Any], now: datetime) -> tuple[list[dict[str, Any]], str, list[str]]:
    root_path = _safe_source_path(project, source["root"])
    spec_path = _safe_source_path(root_path, source["spec"]) if root_path.exists() else root_path / source["spec"]
    issues_path = _safe_source_path(root_path, source["issues"]) if root_path.exists() else root_path / source["issues"]
    errors: list[str] = []
    if not root_path.exists() or not spec_path.exists() or not issues_path.exists():
        return [], "missing", [f"missing local source under {root_path}"]
    if not spec_path.is_file() or not issues_path.is_dir():
        return [], "malformed", ["local Markdown source types are invalid"]
    try:
        spec_lines = spec_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return [], "malformed", [f"cannot parse spec: {exc}"]
    try:
        issue_files = sorted((path for path in issues_path.iterdir() if path.is_file()), key=lambda path: path.name)
    except OSError as exc:
        return [], "malformed", [f"cannot list issues: {exc}"]
    number_to_id: dict[str, str] = {}
    for path in issue_files:
        match = ISSUE_FILE_RE.fullmatch(path.name)
        if not match:
            return [], "malformed", [f"invalid issue filename: {path.name}"]
        generated = f"ticket-{match.group('number')}-{match.group('slug')}"
        if match.group("number") in number_to_id or generated in number_to_id.values():
            return [], "malformed", [f"duplicate issue id: {generated}"]
        number_to_id[match.group("number")] = generated
    nodes: list[dict[str, Any]] = [
        {"id": "run", "parentId": None, "kind": "run", "name": feature.replace("-", " ").title(), "status": "partial", "blockerIds": [], "acceptance": [], "evidence": [], "nextAction": "Work the current ticket frontier", "note": "Generated from local Markdown artifacts."},
        {"id": "spec", "parentId": "run", "kind": "phase", "name": "Spec", "status": "verified", "blockerIds": [], "acceptance": [_acceptance("spec-file", "Spec file is readable", "verified")], "evidence": [_evidence("spec-source", "artifact", "Spec file", str(spec_path.relative_to(project)), now)], "nextAction": "Keep the approved contract stable", "note": "Existence of a spec is not product acceptance."},
        {"id": "tickets", "parentId": "run", "kind": "phase", "name": "Tickets", "status": "partial", "blockerIds": [], "acceptance": [], "evidence": [], "nextAction": "Resolve blockers and work the frontier", "note": "Issue files are read on every request."},
        {"id": "implementation", "parentId": "run", "kind": "phase", "name": "Implementation", "status": "waiting", "blockerIds": [], "acceptance": [], "evidence": [], "nextAction": "Use implement on the selected ticket", "note": "Git and Agent state are not read in v1."},
        {"id": "release", "parentId": "run", "kind": "phase", "name": "Release", "status": "waiting", "blockerIds": [], "acceptance": [], "evidence": [], "nextAction": "Wait for implementation receipts", "note": "Release actions are not connected in v1."},
    ]
    for path in issue_files:
        if path.is_symlink():
            resolved = path.resolve(strict=False)
            if not _within(project, resolved):
                return [], "malformed", [f"issue symlink escapes project: {path.name}"]
        nodes.append(_parse_issue(path, number_to_id, "tickets"))
    if not issue_files:
        nodes[2]["status"] = "waiting"
    return nodes, "live", errors


def _merge_override(node: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    if not override:
        return dict(node)
    merged = dict(node)
    for field in ("acceptance", "evidence", "nextAction", "note"):
        if field in override:
            merged[field] = override[field]
    return merged


def _evidence_current(record: dict[str, Any], now: datetime) -> bool:
    if record["status"] != "verified":
        return False
    observed = parse_utc(record["observedAt"], "evidence.observedAt", now)
    return now - observed <= timedelta(seconds=record.get("freshForSeconds", DEFAULT_FRESH_SECONDS))


def _leaf_status(node: dict[str, Any], now: datetime) -> str:
    hint = node["status"]
    acceptance = node["acceptance"]
    evidence = node["evidence"]
    green = bool(acceptance) and all(item["status"] == "verified" for item in acceptance) and any(_evidence_current(item, now) for item in evidence)
    if green:
        return "verified"
    if hint == "verified":
        return "needs-review"
    return hint


def _has_cycle(nodes_by_id: dict[str, dict[str, Any]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        for blocker_id in nodes_by_id[node_id].get("blockerIds", []):
            if blocker_id in nodes_by_id and visit(blocker_id):
                return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    return any(visit(node_id) for node_id in nodes_by_id)


def _normalize_nodes(nodes: list[dict[str, Any]], source_status: str, now: datetime) -> list[dict[str, Any]]:
    by_id = {node["id"]: dict(node) for node in nodes}
    if len(by_id) != len(nodes):
        raise TrackerError("duplicate node id")
    roots = [node for node in nodes if node["parentId"] is None]
    if len(roots) != 1 or roots[0]["kind"] != "run":
        raise TrackerError("manifest must contain exactly one run root")
    for node in nodes:
        parent = node["parentId"]
        if parent is not None and parent not in by_id:
            raise TrackerError(f"unknown parent: {parent}")
        for blocker in node["blockerIds"]:
            if blocker not in by_id:
                raise TrackerError(f"unknown blocker: {blocker}")
            if blocker == node["id"]:
                raise TrackerError(f"self-blocker: {node['id']}")
    if _has_cycle(by_id):
        raise TrackerError("blocker cycle detected")
    children: dict[str, list[str]] = {node_id: [] for node_id in by_id}
    for node in nodes:
        if node["parentId"] is not None:
            children[node["parentId"]].append(node["id"])
    normalized: dict[str, dict[str, Any]] = {}
    for node_id, node in by_id.items():
        item = dict(node)
        item["children"] = sorted(children[node_id])
        item["status"] = "needs-review" if source_status in {"malformed", "missing", "stale"} else _leaf_status(item, now)
        normalized[node_id] = item
    pending = set(normalized)
    while pending:
        progressed = False
        for node_id in sorted(pending, reverse=True):
            item = normalized[node_id]
            if not item["children"]:
                pending.remove(node_id)
                progressed = True
                continue
            if any(child_id not in normalized for child_id in item["children"]):
                raise TrackerError(f"unknown child for {node_id}")
            statuses = [normalized[child_id]["status"] for child_id in item["children"]]
            if source_status in {"malformed", "missing", "stale"}:
                status = "needs-review"
            elif "blocked" in statuses:
                status = "blocked"
            elif "needs-review" in statuses:
                status = "needs-review"
            elif "running" in statuses:
                status = "running"
            elif "partial" in statuses:
                status = "partial"
            elif all(status == "verified" for status in statuses):
                status = "verified"
            else:
                status = "waiting"
            item["status"] = status
            pending.remove(node_id)
            progressed = True
        if not progressed:
            raise TrackerError("node parent cycle detected")
    result: list[dict[str, Any]] = []
    for node in nodes:
        item = normalized[node["id"]]
        if item["children"]:
            total = len(item["children"])
            done = sum(normalized[child_id]["status"] == "verified" for child_id in item["children"])
        else:
            total = len(item["acceptance"]) or 1
            done = sum(record["status"] == "verified" for record in item["acceptance"])
            if item["status"] == "verified" and not item["acceptance"]:
                done = 1
        item["progress"] = {"done": int(done), "total": total}
        result.append(item)
    return result


def _source_info(source: dict[str, Any], status: str, errors: list[str]) -> dict[str, Any]:
    return {"kind": source["kind"], "status": status, "root": source["root"], "spec": source["spec"], "issues": source["issues"], "observedAt": source["observedAt"], "maxAgeSeconds": source["maxAgeSeconds"], "errors": errors}

def _implicit_local_manifest(project: Path, feature: str, now: datetime) -> dict[str, Any] | None:
    source_root = project / ".scratch" / feature
    if not source_root.exists():
        return None
    return {
        "schemaVersion": 1,
        "run": {"id": feature, "displayName": feature.replace("-", " ").title(), "featureSlug": feature},
        "source": {"kind": "local_markdown", "root": f".scratch/{feature}", "spec": "spec.md", "issues": "issues", "observedAt": timestamp(now), "maxAgeSeconds": DEFAULT_FRESH_SECONDS},
        "nodes": [],
        "overrides": {},
    }


def _auto_feature_candidates(project: Path) -> tuple[list[str], str | None]:
    scratch = project / ".scratch"
    if not scratch.exists():
        return [], None
    if scratch.is_symlink():
        resolved = scratch.resolve(strict=False)
        if not _within(project, resolved):
            return [], "auto source escapes project root"
    if not scratch.is_dir():
        return [], "auto source root is not a directory"
    candidates: list[str] = []
    try:
        children = sorted(scratch.iterdir(), key=lambda item: item.name)
    except OSError as exc:
        return [], f"cannot inspect auto source root: {exc}"
    for child in children:
        if not child.is_dir():
            continue
        try:
            validate_slug(child.name, "auto feature")
        except TrackerError as exc:
            return [], str(exc)
        if (child / "spec.md").is_file() and (child / "issues").is_dir():
            candidates.append(child.name)
    return candidates, None


def _auto_state(project: Path, status: str, error: str, current: datetime) -> dict[str, Any]:
    observed_at = timestamp(current)
    source = {"kind": AUTO_FEATURE, "status": status, "root": ".scratch", "spec": None, "issues": None, "observedAt": observed_at, "maxAgeSeconds": DEFAULT_FRESH_SECONDS, "errors": [error]}
    observations = collect_observations(project, {"kind": "manual", "root": None, "spec": None, "issues": None}, observed_at)
    observations.insert(0, {"id": "auto-source", "kind": "discovery", "label": "Auto feature", "status": "error" if status == "malformed" else "unavailable", "detail": error, "observedAt": observed_at})
    return {
        "schemaVersion": 1,
        "run": {"id": AUTO_FEATURE, "displayName": project.name.replace("-", " ").title(), "featureSlug": AUTO_FEATURE},
        "source": source,
        "nodes": [],
        "frontier": [],
        "blockers": [],
        "summary": {"verified": 0, "total": 0, "active": 0, "needsReview": 0},
        "observations": observations,
        "generatedAt": observed_at,
    }

def _state_error(feature: str, status: str, message: str) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "run": {"id": feature, "displayName": feature.replace("-", " ").title(), "featureSlug": feature},
        "source": {"kind": "unknown", "status": status, "root": None, "spec": None, "issues": None, "observedAt": None, "maxAgeSeconds": DEFAULT_FRESH_SECONDS, "errors": [message]},
        "nodes": [],
        "frontier": [],
        "blockers": [],
        "summary": {"verified": 0, "total": 0, "active": 0, "needsReview": 0},
        "observations": [],
        "generatedAt": timestamp(),
    }


def _failed_source_state(manifest: dict[str, Any], source_status: str, errors: list[str], root: Path, current: datetime) -> dict[str, Any]:
    source = manifest["source"]
    try:
        observations = collect_observations(root, source, timestamp(current))
    except (KeyError, OSError, TypeError, ValueError) as exc:
        observations = [{
            "id": "observer",
            "kind": "observer",
            "label": "Observer",
            "status": "error",
            "detail": f"Cannot collect observations: {exc}",
            "observedAt": timestamp(current),
        }]
    return {
        "schemaVersion": 1,
        "run": manifest["run"],
        "source": _source_info(source, source_status, errors),
        "nodes": [],
        "frontier": [],
        "blockers": [],
        "summary": {"verified": 0, "total": 0, "active": 0, "needsReview": 0},
        "observations": observations,
        "generatedAt": timestamp(current),
    }


def load_state(project: str | Path, feature: str, now: datetime | None = None) -> dict[str, Any]:
    try:
        root = canonical_project(project)
        validate_slug(feature)
        current = now or utc_now()
        path = manifest_path(root, feature)
    except TrackerError as exc:
        return _state_error(feature, "malformed", str(exc))
    if feature == AUTO_FEATURE:
        candidates, error = _auto_feature_candidates(root)
        if error:
            return _auto_state(root, "malformed", error, current)
        if not candidates:
            return _auto_state(root, "missing", "Waiting for exactly one .scratch/<feature> source", current)
        if len(candidates) > 1:
            return _auto_state(root, "malformed", f"Multiple local feature sources: {', '.join(candidates)}", current)
        return load_state(root, candidates[0], now=current)
    try:
        manifest = read_manifest(path, feature, now=current) if path.exists() else _implicit_local_manifest(root, feature, current)
        if manifest is None:
            return _state_error(feature, "missing", f"manifest and local source missing: {path}")
        source = manifest["source"]
        errors: list[str] = []
        if source["kind"] == "local_markdown":
            nodes, source_status, source_errors = _local_markdown_nodes(root, feature, source, current)
            errors.extend(source_errors)
            if not nodes and source_status in {"missing", "malformed"}:
                return _failed_source_state(manifest, source_status, errors, root, current)
            generated_ids = {node["id"] for node in nodes}
            unknown_overrides = sorted(set(manifest["overrides"]) - generated_ids)
            if unknown_overrides:
                raise TrackerError(f"override targets unknown generated node: {unknown_overrides[0]}")
            nodes = [_merge_override(node, manifest["overrides"].get(node["id"])) for node in nodes]
        else:
            nodes = [_merge_override(node, manifest["overrides"].get(node["id"])) for node in manifest["nodes"]]
            source_status = "live" if source["kind"] == "manual" else "sample"
            if source["kind"] == "manual":
                observed = parse_utc(source["observedAt"], "source.observedAt", current)
                if current - observed > timedelta(seconds=source["maxAgeSeconds"]):
                    source_status = "stale"
        normalized = _normalize_nodes(nodes, source_status, current)
        try:
            observations = collect_observations(root, source, timestamp(current))
        except (KeyError, OSError, TypeError, ValueError) as exc:
            observations = [{
                "id": "observer",
                "kind": "observer",
                "label": "Observer",
                "status": "error",
                "detail": f"Cannot collect observations: {exc}",
                "observedAt": timestamp(current),
            }]
        by_id = {node["id"]: node for node in normalized}
        frontier: list[dict[str, Any]] = []
        blockers: list[dict[str, Any]] = []
        if source_status == "live":
            for node in normalized:
                if node["status"] in FRONTIER_STATUSES and not node["children"] and all(by_id[blocker]["status"] == "verified" for blocker in node["blockerIds"]):
                    frontier.append({"id": node["id"], "name": node["name"], "kind": node["kind"], "status": node["status"], "nextAction": node["nextAction"], "blockerIds": node["blockerIds"]})
        for node in normalized:
            if node["status"] in {"blocked", "needs-review"}:
                blockers.append({"id": node["id"], "name": node["name"], "status": node["status"], "blockerIds": node["blockerIds"], "nextAction": node["nextAction"]})
        verified = sum(node["status"] == "verified" for node in normalized if not node["children"])
        total = sum(not node["children"] for node in normalized)
        active = sum(node["status"] in {"running", "partial"} for node in normalized if not node["children"])
        needs_review = sum(node["status"] == "needs-review" for node in normalized if not node["children"])
        return {
            "schemaVersion": 1,
            "run": manifest["run"],
            "source": _source_info(source, source_status, errors),
            "nodes": normalized,
            "frontier": frontier,
            "blockers": blockers,
            "summary": {"verified": verified, "total": total, "active": active, "needsReview": needs_review},
            "observations": observations,
            "generatedAt": timestamp(current),
        }
    except TrackerError as exc:
        return _state_error(feature, "malformed", str(exc))
    except OSError as exc:
        return _state_error(feature, "malformed", str(exc))


def wake_text(state: dict[str, Any], project: str | Path, feature: str) -> tuple[str, int]:
    source = state["source"]
    status = source["status"]
    lines = [f"Source: {status}"]
    if source.get("errors"):
        lines.append("Source errors:")
        lines.extend(f"- {error}" for error in source["errors"])
    lines.append("Frontier:")
    if state["frontier"]:
        lines.extend(f"- {item['id']}: {item['name']} [{item['status']}] -> {item['nextAction']}" for item in state["frontier"])
    else:
        lines.append("- none")
    lines.append("Blockers:")
    if state["blockers"]:
        lines.extend(f"- {item['id']}: {item['name']} [{item['status']}] -> {item['nextAction']}" for item in state["blockers"])
    else:
        lines.append("- none")
    lines.append("Observations:")
    if state.get("observations"):
        lines.extend(f"- {item['label']} [{item['status']}] -> {item['detail']}" for item in state["observations"])
    else:
        lines.append("- none")
    lines.append("Next brief:")
    if state["frontier"]:
        first = state["frontier"][0]
        lines.extend([
            f"Read the current artifacts for {feature}.",
            f"Work only on {first['id']} ({first['name']}).",
            "Preserve the issue contract, record verification evidence, and stop at any human gate.",
        ])
    elif status == "sample":
        lines.append("Sample state is for UI review only. Do not dispatch work from it.")
    elif status == "live":
        lines.append("No actionable frontier. Recheck authoritative artifacts before continuing.")
    else:
        lines.append("Repair the source state before attempting to continue.")
    lines.append("Exit:")
    if status in {"live", "sample"}:
        lines.append("valid-live" if status == "live" else "valid-sample")
        code = 0
    else:
        lines.append(f"invalid-{status}")
        code = 2
    return "\n".join(lines) + "\n", code
