from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from agent_ticket_tracker.core import TrackerError, init_project, load_state, sample_manifest, timestamp, utc_now, wake_text
from agent_ticket_tracker.server import make_server


def manual_manifest(feature: str, *, blocker: list[str] | None = None, leaf_status: str = "ready") -> dict:
    now = utc_now()
    evidence = {
        "id": "receipt", "kind": "test", "label": "Test receipt", "status": "verified",
        "ref": "tests/receipt.txt", "observedAt": timestamp(now), "freshForSeconds": 900,
    }
    return {
        "schemaVersion": 1,
        "run": {"id": feature, "displayName": "Demo", "featureSlug": feature},
        "source": {"kind": "manual", "root": None, "spec": None, "issues": None, "observedAt": timestamp(now), "maxAgeSeconds": 900},
        "nodes": [
            {"id": "run", "parentId": None, "kind": "run", "name": "Demo", "status": "partial", "blockerIds": [], "acceptance": [], "evidence": [], "nextAction": "next", "note": "note"},
            {"id": "ready", "parentId": "run", "kind": "ticket", "name": "Ready", "status": leaf_status, "blockerIds": blocker or [], "acceptance": [{"id": "a1", "label": "Acceptance", "status": "verified"}], "evidence": [evidence], "nextAction": "Do the work", "note": "Evidence is current."},
        ],
        "overrides": {},
    }


class CoreTests(unittest.TestCase):
    def test_sample_is_valid_but_not_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            init_project(project, "demo", sample=True)
            state = load_state(project, "demo")
            self.assertEqual(state["source"]["status"], "sample")
            self.assertEqual(state["frontier"], [])

    def test_green_requires_evidence_and_frontier_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            path, _ = init_project(project, "demo")
            manifest = manual_manifest("demo", leaf_status="verified")
            manifest["nodes"][1]["evidence"] = []
            path.write_text(json.dumps(manifest), encoding="utf-8")
            state = load_state(project, "demo")
            self.assertEqual(state["nodes"][1]["status"], "needs-review")
            self.assertEqual([item["id"] for item in state["frontier"]], ["ready"])

    def test_frontier_requires_verified_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            path, _ = init_project(project, "demo")
            manifest = manual_manifest("demo")
            manifest["nodes"][1]["acceptance"][0]["status"] = "pending"
            blocker = dict(manifest["nodes"][1])
            blocker.update({"id": "blocker", "name": "Blocker", "status": "waiting", "blockerIds": [], "acceptance": [{"id": "a1", "label": "Acceptance", "status": "pending"}]})
            manifest["nodes"].append(blocker)
            manifest["nodes"][1]["blockerIds"] = ["blocker"]
            path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(load_state(project, "demo")["frontier"], [])
            blocker["status"] = "verified"
            blocker["acceptance"][0]["status"] = "verified"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual([item["id"] for item in load_state(project, "demo")["frontier"]], ["ready"])

    def test_cycles_and_stale_state_fail_closed_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            path, _ = init_project(project, "demo")
            manifest = manual_manifest("demo")
            first = dict(manifest["nodes"][1]); first["id"] = "first"; first["blockerIds"] = ["second"]
            second = dict(manifest["nodes"][1]); second["id"] = "second"; second["blockerIds"] = ["first"]
            manifest["nodes"] = [manifest["nodes"][0], first, second]
            path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(load_state(project, "demo")["source"]["status"], "malformed")
            manifest = manual_manifest("demo")
            manifest["source"]["observedAt"] = "2020-01-01T00:00:00Z"
            manifest["source"]["maxAgeSeconds"] = 1
            path.write_text(json.dumps(manifest), encoding="utf-8")
            before = path.read_text(encoding="utf-8")
            self.assertEqual(load_state(project, "demo")["source"]["status"], "stale")
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_local_markdown_import_and_safe_slug(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            source = project / ".scratch" / "demo"; issues = source / "issues"; issues.mkdir(parents=True)
            (source / "spec.md").write_text("# Demo spec\n", encoding="utf-8")
            (issues / "01-first.md").write_text("# 01 - First ticket\n\n**Status:** claimed\n\n## Acceptance criteria\n\n- [x] First check\n", encoding="utf-8")
            (issues / "02-second.md").write_text("# 02 - Second ticket\n\n**Status:** ready-for-agent\n**Blocked by:** 01\n", encoding="utf-8")
            init_project(project, "demo")
            state = load_state(project, "demo")
            self.assertEqual(state["source"]["status"], "live")
            self.assertEqual(next(node for node in state["nodes"] if node["id"] == "ticket-01-first")["status"], "running")
            self.assertEqual(state["frontier"], [])
            with self.assertRaises(TrackerError):
                init_project(project, "..")

    def test_read_only_observations_include_git_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            source = project / ".scratch" / "demo"; issues = source / "issues"; issues.mkdir(parents=True)
            (source / "spec.md").write_text("# Demo spec\n", encoding="utf-8")
            (issues / "01-first.md").write_text("# 01 - First ticket\n", encoding="utf-8")
            init_project(project, "demo")
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=project, check=True)
            subprocess.run(["git", "config", "user.email", "tracker@example.test"], cwd=project, check=True)
            subprocess.run(["git", "config", "user.name", "Tracker Test"], cwd=project, check=True)
            (project / "README.md").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=project, check=True)
            subprocess.run(["git", "commit", "-qm", "Initial fixture"], cwd=project, check=True)
            manifest = project / ".agent-ticket-tracker" / "demo" / "manifest.json"
            before_manifest = manifest.read_bytes()
            before_status = subprocess.run(["git", "status", "--porcelain"], cwd=project, check=True, capture_output=True, text=True).stdout

            state = load_state(project, "demo")
            observations = {item["id"]: item for item in state["observations"]}

            self.assertEqual(state["source"]["status"], "live")
            self.assertEqual(observations["artifact-spec"]["status"], "observed")
            self.assertIn("spec.md", observations["artifact-spec"]["detail"])
            self.assertEqual(observations["artifact-tickets"]["status"], "observed")
            self.assertEqual(observations["git-branch"]["status"], "observed")
            self.assertIn("main", observations["git-branch"]["detail"])
            self.assertEqual(observations["git-worktree"]["status"], "observed")
            self.assertIn(f"{len(before_status.splitlines())} untracked", observations["git-worktree"]["detail"])
            self.assertEqual(observations["git-last-commit"]["status"], "observed")
            self.assertIn("Initial fixture", observations["git-last-commit"]["detail"])
            wake, wake_code = wake_text(state, project, "demo")
            self.assertEqual(wake_code, 0)
            self.assertIn("Observations:", wake)
            self.assertIn("Initial fixture", wake)
            self.assertEqual(manifest.read_bytes(), before_manifest)
            after_status = subprocess.run(["git", "status", "--porcelain"], cwd=project, check=True, capture_output=True, text=True).stdout
            self.assertEqual(after_status, before_status)

    def test_observations_mark_missing_git_without_affecting_frontier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            source = project / ".scratch" / "demo"; issues = source / "issues"; issues.mkdir(parents=True)
            (source / "spec.md").write_text("# Demo spec\n", encoding="utf-8")
            (issues / "01-first.md").write_text("# 01 - First ticket\n**Status:** ready-for-agent\n", encoding="utf-8")
            init_project(project, "demo")
            manifest = project / ".agent-ticket-tracker" / "demo" / "manifest.json"
            before_manifest = manifest.read_bytes()

            state = load_state(project, "demo")
            observations = {item["id"]: item for item in state["observations"]}

            self.assertEqual(state["source"]["status"], "live")
            self.assertEqual(observations["git-branch"]["status"], "unavailable")
            self.assertIn("not detected", observations["git-branch"]["detail"])
            self.assertEqual(observations["git-worktree"]["status"], "unavailable")
            self.assertEqual(observations["git-last-commit"]["status"], "unavailable")
            self.assertEqual([item["id"] for item in state["frontier"]], ["ticket-01-first"])
            self.assertEqual(manifest.read_bytes(), before_manifest)

    def test_missing_local_source_is_visible_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            init_project(project, "demo")
            manifest = project / ".agent-ticket-tracker" / "demo" / "manifest.json"
            before_manifest = manifest.read_bytes()

            state = load_state(project, "demo")

            self.assertEqual(state["source"]["status"], "missing")
            self.assertEqual(state["nodes"], [])
            self.assertEqual(state["frontier"], [])
            self.assertTrue(any(item["id"] == "artifact-spec" and item["status"] == "unavailable" for item in state["observations"]))
            self.assertEqual(manifest.read_bytes(), before_manifest)

    def test_escaping_artifact_symlink_is_visible_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside_directory:
            project = Path(directory)
            source = project / ".scratch" / "demo"; issues = source / "issues"; issues.mkdir(parents=True)
            (source / "spec.md").write_text("# Demo spec\n", encoding="utf-8")
            external = Path(outside_directory) / "outside.md"
            external.write_text("# Outside\n", encoding="utf-8")
            (issues / "01-leak.md").symlink_to(external)
            init_project(project, "demo")
            manifest = project / ".agent-ticket-tracker" / "demo" / "manifest.json"
            before_manifest = manifest.read_bytes()

            state = load_state(project, "demo")

            self.assertEqual(state["source"]["status"], "malformed")
            self.assertEqual(state["nodes"], [])
            self.assertEqual(state["frontier"], [])
            self.assertTrue(any("symlink" in error.lower() for error in state["source"]["errors"]))
            self.assertEqual(manifest.read_bytes(), before_manifest)

    def test_init_is_non_overwriting_and_wake_has_stable_sections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            path, created = init_project(project, "demo", sample=True)
            self.assertTrue(created)
            _, created_again = init_project(project, "demo")
            self.assertFalse(created_again)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["source"]["kind"], "sample")
            text, code = wake_text(load_state(project, "demo"), project, "demo")
            self.assertEqual(code, 0)
            for section in ("Source:", "Frontier:", "Blockers:", "Observations:", "Next brief:", "Exit:"):
                self.assertIn(section, text)


class ServerTests(unittest.TestCase):
    def test_loopback_routes_and_no_arbitrary_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            init_project(project, "demo", sample=True)
            (project / "secret.txt").write_text("do not serve", encoding="utf-8")
            server = make_server(project, "demo", port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                with urlopen(f"{base}/healthz") as response:
                    self.assertTrue(json.loads(response.read())["ok"])
                with urlopen(f"{base}/api/state") as response:
                    payload = json.loads(response.read())
                    self.assertEqual(payload["source"]["status"], "sample")
                    self.assertIn("observations", payload)
                with urlopen(f"{base}/") as response:
                    page = response.read()
                    self.assertIn(b"Agent Ticket Tracker", page)
                    self.assertIn("最近观察".encode("utf-8"), page)
                with self.assertRaises(HTTPError) as error:
                    urlopen(f"{base}/secret.txt")
                self.assertEqual(error.exception.code, 404)
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
