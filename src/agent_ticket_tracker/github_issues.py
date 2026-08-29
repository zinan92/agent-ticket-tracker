"""Read-only GitHub issue, milestone, pull-request, and CI projection."""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, MutableMapping


FRESH_SECONDS = 120
GH_TIMEOUT_SECONDS = 15.0
GIT_TIMEOUT_SECONDS = 2.0
GREEN_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_REMOTE_RE = re.compile(r"github\.com(?::|/)(?P<owner>[A-Za-z0-9][A-Za-z0-9._-]*)/(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*?)(?:\.git)?/?$")

GRAPHQL_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    milestones(first: 100, states: OPEN) {
      nodes { number title }
    }
    issues(first: 100, states: OPEN) {
      nodes {
        number
        title
        state
        url
        labels(first: 50) { nodes { name } }
        milestone { number title }
        timelineItems(first: 50, itemTypes: [CROSS_REFERENCED_EVENT]) {
          nodes {
            ... on CrossReferencedEvent {
              source {
                __typename
                ... on PullRequest {
                  number
                  url
                  state
                  isDraft
                  mergedAt
                  commits(last: 1) {
                    nodes {
                      commit {
                        checkSuites(first: 100) {
                          nodes {
                            checkRuns(first: 100) {
                              nodes { name status conclusion detailsUrl }
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
""".strip()


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _observation(identifier: str, label: str, status: str, detail: str, observed_at: str) -> dict[str, str]:
    return {
        "id": identifier,
        "kind": "github",
        "label": label,
        "status": status,
        "detail": detail[:240],
        "observedAt": observed_at,
    }


def _source(owner: str, name: str, status: str, errors: list[str], observed_at: str) -> dict[str, Any]:
    return {
        "kind": "github_issues",
        "status": status,
        "root": f"github.com/{owner}/{name}",
        "spec": None,
        "issues": None,
        "observedAt": observed_at,
        "maxAgeSeconds": FRESH_SECONDS,
        "errors": errors,
    }


def _malformed(owner: str, name: str, detail: str, now: datetime) -> dict[str, Any]:
    observed_at = _timestamp(now)
    return {
        "run": {"id": "run", "displayName": f"{owner}/{name}", "featureSlug": "auto"},
        "source": _source(owner, name, "malformed", [detail], observed_at),
        "nodes": [],
        "observations": [_observation("github-source", "GitHub source", "error", detail, observed_at)],
    }


def _run(command: list[str], *, cwd: Path, timeout: float) -> tuple[int | None, str, str]:
    env = dict(os.environ)
    env.update({"GH_PAGER": "cat", "NO_COLOR": "1", "LC_ALL": "C"})
    try:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError:
        return None, "", "executable not found"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, "", str(exc)
    return result.returncode, result.stdout, result.stderr


def _parse_remote(value: str) -> tuple[str, str] | None:
    candidate = value.strip().split()[0] if value.strip() else ""
    candidate = candidate.removeprefix("ssh://git@").removeprefix("git+")
    match = _REMOTE_RE.search(candidate)
    if not match:
        return None
    return match.group("owner"), match.group("name")


def _github_remote(project: Path) -> tuple[str, str] | None:
    code, stdout, _ = _run(["git", "-C", str(project), "remote", "get-url", "origin"], cwd=project, timeout=GIT_TIMEOUT_SECONDS)
    urls: list[str] = []
    if code == 0 and stdout.strip():
        urls.append(stdout.strip())
    for url in urls:
        parsed = _parse_remote(url)
        if parsed is not None:
            return parsed
    code, stdout, _ = _run(["git", "-C", str(project), "remote", "-v"], cwd=project, timeout=GIT_TIMEOUT_SECONDS)
    if code == 0:
        urls.extend(line.split()[1] for line in stdout.splitlines() if len(line.split()) >= 2)
    for url in urls:
        parsed = _parse_remote(url)
        if parsed is not None:
            return parsed
    return None


def _check_runs(pull_request: dict[str, Any]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    commits = pull_request.get("commits")
    if not isinstance(commits, dict):
        return runs
    commit_nodes = commits.get("nodes")
    if not isinstance(commit_nodes, list):
        return runs
    for commit_node in commit_nodes:
        if not isinstance(commit_node, dict):
            continue
        commit = commit_node.get("commit")
        if not isinstance(commit, dict):
            continue
        suites = commit.get("checkSuites")
        if not isinstance(suites, dict) or not isinstance(suites.get("nodes"), list):
            continue
        for suite in suites["nodes"]:
            if not isinstance(suite, dict):
                continue
            checks = suite.get("checkRuns")
            if not isinstance(checks, dict) or not isinstance(checks.get("nodes"), list):
                continue
            for check in checks["nodes"]:
                if isinstance(check, dict):
                    runs.append(check)
    return runs


def _pull_requests(issue: dict[str, Any]) -> list[dict[str, Any]]:
    timeline = issue.get("timelineItems")
    if not isinstance(timeline, dict) or not isinstance(timeline.get("nodes"), list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in timeline["nodes"]:
        if not isinstance(event, dict):
            continue
        source = event.get("source")
        if not isinstance(source, dict):
            continue
        typename = source.get("__typename")
        if typename not in {None, "PullRequest"}:
            continue
        url = source.get("url")
        if not isinstance(url, str) or not url:
            continue
        if typename is None and "/pull/" not in url:
            continue
        if url in seen:
            continue
        seen.add(url)
        checks = _check_runs(source)
        all_green = bool(checks) and all(
            str(check.get("status", "")).upper() == "COMPLETED"
            and str(check.get("conclusion", "")).upper() in GREEN_CONCLUSIONS
            for check in checks
        )
        result.append({
            "number": source.get("number"),
            "url": url,
            "state": str(source.get("state", "")).upper(),
            "draft": bool(source.get("isDraft", False)),
            "merged": bool(source.get("mergedAt")),
            "checks": checks,
            "all_green": all_green,
        })
    return result


def _issue_status(issue: dict[str, Any], pull_requests: list[dict[str, Any]]) -> str:
    labels = issue.get("labels")
    label_nodes = labels.get("nodes", []) if isinstance(labels, dict) else []
    if any(isinstance(label, dict) and str(label.get("name", "")).casefold() == "blocked" for label in label_nodes):
        return "blocked"
    if any(pr["merged"] and pr["all_green"] for pr in pull_requests):
        return "verified"
    issue_state = str(issue.get("state", "OPEN")).upper()
    if issue_state == "CLOSED" and not any(pr["merged"] for pr in pull_requests):
        return "needs-review"
    if any(pr["state"] == "OPEN" and pr["draft"] for pr in pull_requests):
        return "running"
    if any(pr["state"] == "OPEN" for pr in pull_requests):
        return "needs-review"
    if issue_state == "CLOSED":
        return "needs-review"
    if pull_requests:
        return "needs-review"
    return "planned"


def _evidence(identifier: str, kind: str, label: str, status: str, ref: str, observed_at: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": kind,
        "label": label,
        "status": status,
        "ref": ref,
        "observedAt": observed_at,
        "freshForSeconds": FRESH_SECONDS,
    }


def _issue_number(issue: dict[str, Any]) -> int:
    number = issue.get("number")
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise ValueError("GitHub issue number is invalid")
    return number


def _phase_id(number: int) -> str:
    return f"github-milestone-{number}"


def _issue_node(issue: dict[str, Any], parent_id: str, observed_at: str) -> dict[str, Any]:
    number = _issue_number(issue)
    title = issue.get("title")
    url = issue.get("url")
    if not isinstance(title, str) or not title.strip() or not isinstance(url, str) or not url:
        raise ValueError(f"GitHub issue #{number} is missing title or URL")
    pull_requests = _pull_requests(issue)
    status = _issue_status(issue, pull_requests)
    evidence: list[dict[str, Any]] = []
    for index, pull_request in enumerate(pull_requests, start=1):
        pr_number = pull_request.get("number") or pull_request["url"].rstrip("/").rsplit("/", 1)[-1]
        pr_state = "merged" if pull_request["merged"] else "draft" if pull_request["draft"] else str(pull_request["state"]).lower() or "unknown"
        evidence.append(_evidence(f"github-pr-{number}-{index}", "review", f"Linked PR #{pr_number} ({pr_state})", "verified", pull_request["url"], observed_at))
        checks = pull_request["checks"]
        if not checks:
            evidence.append(_evidence(f"github-ci-{number}-{index}-none", "test", "CI checks: no check runs observed", "missing", pull_request["url"], observed_at))
        for check_index, check in enumerate(checks, start=1):
            check_name = str(check.get("name") or "unnamed check")
            check_status = str(check.get("status") or "UNKNOWN").upper()
            conclusion = str(check.get("conclusion") or "PENDING").upper()
            green = check_status == "COMPLETED" and conclusion in GREEN_CONCLUSIONS
            ref = check.get("detailsUrl") if isinstance(check.get("detailsUrl"), str) and check.get("detailsUrl") else pull_request["url"]
            evidence.append(_evidence(
                f"github-ci-{number}-{index}-{check_index}",
                "test",
                f"CI {check_name}: {conclusion}",
                "verified" if green else "failed" if check_status == "COMPLETED" and conclusion not in {"PENDING", ""} else "missing",
                ref,
                observed_at,
            ))
    labels = issue.get("labels")
    label_nodes = labels.get("nodes", []) if isinstance(labels, dict) else []
    if any(isinstance(label, dict) and str(label.get("name", "")).casefold() == "blocked" for label in label_nodes):
        evidence.append(_evidence(f"github-label-{number}-blocked", "manual", "GitHub label: blocked", "verified", url, observed_at))
    acceptance_status = "verified" if status == "verified" else "pending"
    next_action = {
        "planned": "Link or start the implementation PR",
        "running": "Observe the draft implementation PR",
        "needs-review": "Review the linked PR and its CI checks",
        "verified": "Keep the merged PR and green CI evidence",
        "blocked": "Resolve the blocked label in GitHub",
    }[status]
    return {
        "id": f"github-issue-{number}",
        "parentId": parent_id,
        "kind": "ticket",
        "name": f"#{number} {title.strip()}",
        "status": status,
        "blockerIds": [],
        "acceptance": [{"id": f"github-issue-{number}-delivery", "label": "GitHub delivery signal is complete", "status": acceptance_status}],
        "evidence": evidence,
        "nextAction": next_action,
        "note": f"Read-only projection of GitHub issue #{number}.",
    }


def build_github_result(payload: Any, owner: str, name: str, now: datetime) -> dict[str, Any]:
    """Build an adapter result from a GitHub GraphQL response."""

    if not isinstance(payload, dict) or payload.get("errors"):
        raise ValueError("GitHub GraphQL response is malformed")
    data = payload.get("data")
    repository = data.get("repository") if isinstance(data, dict) else None
    if not isinstance(repository, dict):
        raise ValueError("GitHub repository is unavailable")
    milestones = repository.get("milestones")
    issues = repository.get("issues")
    if not isinstance(milestones, dict) or not isinstance(issues, dict) or not isinstance(milestones.get("nodes"), list) or not isinstance(issues.get("nodes"), list):
        raise ValueError("GitHub milestones or issues response is malformed")
    observed_at = _timestamp(now)
    milestone_nodes: list[dict[str, Any]] = []
    milestone_ids: dict[int, str] = {}
    for milestone in milestones["nodes"]:
        if not isinstance(milestone, dict):
            raise ValueError("GitHub milestone is malformed")
        number = milestone.get("number")
        title = milestone.get("title")
        if isinstance(number, bool) or not isinstance(number, int) or number < 1 or not isinstance(title, str) or not title.strip():
            raise ValueError("GitHub milestone is missing number or title")
        if number in milestone_ids:
            raise ValueError(f"duplicate GitHub milestone: {number}")
        phase_id = _phase_id(number)
        milestone_ids[number] = phase_id
        milestone_nodes.append({
            "id": phase_id,
            "parentId": "run",
            "kind": "phase",
            "name": title.strip(),
            "status": "waiting",
            "blockerIds": [],
            "acceptance": [],
            "evidence": [],
            "nextAction": "Observe the issues in this milestone",
            "note": "Open GitHub milestone; issue state is read-only.",
        })
    milestone_nodes.sort(key=lambda node: int(node["id"].rsplit("-", 1)[-1]))
    issue_nodes: list[dict[str, Any]] = []
    unscheduled: list[dict[str, Any]] = []
    seen_issues: set[int] = set()
    for issue in issues["nodes"]:
        if not isinstance(issue, dict):
            raise ValueError("GitHub issue is malformed")
        number = _issue_number(issue)
        if number in seen_issues:
            raise ValueError(f"duplicate GitHub issue: {number}")
        seen_issues.add(number)
        milestone = issue.get("milestone")
        milestone_number = milestone.get("number") if isinstance(milestone, dict) else None
        parent_id = milestone_ids.get(milestone_number) if isinstance(milestone_number, int) else None
        if parent_id is None:
            unscheduled.append(issue)
        else:
            issue_nodes.append(_issue_node(issue, parent_id, observed_at))
    if unscheduled:
        milestone_nodes.append({
            "id": "github-unscheduled",
            "parentId": "run",
            "kind": "phase",
            "name": "Unscheduled (no milestone)",
            "status": "needs-review",
            "blockerIds": [],
            "acceptance": [],
            "evidence": [],
            "nextAction": "Review why these issues have no open milestone",
            "note": "Hardcoded needs-review: an issue is outside an open milestone.",
        })
        issue_nodes.extend(_issue_node(issue, "github-unscheduled", observed_at) for issue in unscheduled)
    issue_nodes.sort(key=lambda node: int(node["id"].rsplit("-", 1)[-1]))
    nodes = [{
        "id": "run",
        "parentId": None,
        "kind": "run",
        "name": f"{owner}/{name}",
        "status": "waiting",
        "blockerIds": [],
        "acceptance": [],
        "evidence": [],
        "nextAction": "Observe GitHub milestone and issue progress",
        "note": "Read-only projection from GitHub.",
    }, *milestone_nodes, *issue_nodes]
    source = _source(owner, name, "live", [], observed_at)
    observations = [
        _observation("github-repository", "GitHub repository", "observed", f"{owner}/{name}", observed_at),
        _observation("github-milestones", "Open milestones", "observed", f"{len(milestone_nodes) - (1 if unscheduled else 0)} open milestone(s)", observed_at),
        _observation("github-issues", "Open issues", "observed", f"{len(issue_nodes)} issue(s) projected", observed_at),
    ]
    return {
        "run": {"id": "run", "displayName": f"{owner}/{name}", "featureSlug": "auto"},
        "source": source,
        "nodes": nodes,
        "observations": observations,
        "statusOverrides": {"github-unscheduled": "needs-review"} if unscheduled else {},
    }


def read_github_issues(project: Path, now: datetime, cache: MutableMapping[str, Any] | None = None) -> dict[str, Any] | None:
    """Read GitHub state, or return ``None`` so the caller can use its fallback."""

    store: MutableMapping[str, Any] = _CACHE if cache is None else cache
    key = str(project)
    cached = store.get(key)
    if isinstance(cached, tuple) and len(cached) == 2 and isinstance(cached[0], (int, float)) and time.monotonic() < cached[0]:
        return copy.deepcopy(cached[1])
    if shutil.which("gh") is None:
        return None
    remote = _github_remote(project)
    if remote is None:
        return None
    owner, name = remote
    auth_code, _, _ = _run(["gh", "auth", "status", "--hostname", "github.com"], cwd=project, timeout=GH_TIMEOUT_SECONDS)
    if auth_code != 0:
        return None
    query_args = [
        "gh", "api", "graphql",
        "-f", f"query={GRAPHQL_QUERY}",
        "-f", f"owner={owner}",
        "-f", f"name={name}",
    ]
    code, stdout, stderr = _run(query_args, cwd=project, timeout=GH_TIMEOUT_SECONDS)
    if code != 0:
        return None
    try:
        payload = json.loads(stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        return _malformed(owner, name, f"cannot parse GitHub GraphQL response: {exc}", now)
    try:
        result = build_github_result(payload, owner, name, now)
    except ValueError as exc:
        return _malformed(owner, name, str(exc), now)
    store[key] = (time.monotonic() + FRESH_SECONDS, copy.deepcopy(result))
    return result


def clear_cache() -> None:
    """Clear the process-local GitHub refresh cache for tests and controlled restarts."""

    _CACHE.clear()
