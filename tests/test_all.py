from __future__ import annotations

import json
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
            for section in ("Source:", "Frontier:", "Blockers:", "Next brief:", "Exit:"):
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
                    self.assertEqual(json.loads(response.read())["source"]["status"], "sample")
                with urlopen(f"{base}/") as response:
                    self.assertIn(b"Agent Ticket Tracker", response.read())
                with self.assertRaises(HTTPError) as error:
                    urlopen(f"{base}/secret.txt")
                self.assertEqual(error.exception.code, 404)
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
