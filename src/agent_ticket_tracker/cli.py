"""Command-line entry points for Agent Ticket Tracker."""

from __future__ import annotations

import argparse
import json
import sys

from .core import TrackerError, init_project, load_state, wake_text
from .registry import attach_project
from .server import serve


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="att", description="Agent Ticket Tracker local read-only delivery observer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="create a project-local manifest")
    init.add_argument("--project", required=True, help="existing project directory")
    init.add_argument("--feature", required=True, help="lowercase feature slug")
    init.add_argument("--sample", action="store_true", help="create an explicit non-actionable sample run")

    attach = subparsers.add_parser("attach", help="register and start/reuse the read-only observer")
    attach.add_argument("--project", required=True, help="existing project directory")
    attach.add_argument("--feature", default="auto", help="feature slug or auto, default auto")
    attach.add_argument("--workflow", default="unknown", help="calling workflow label")
    attach.add_argument("--registry", help="tracker-owned registry path for advanced use")
    attach.add_argument("--json", action="store_true", help="print the attach result as JSON")

    server = subparsers.add_parser("serve", help="serve the local read-only observer")
    server.add_argument("--project", required=True, help="existing project directory")
    server.add_argument("--feature", required=True, help="lowercase feature slug or auto")
    server.add_argument("--port", type=int, default=4177, help="loopback port, default 4177")

    wake = subparsers.add_parser("wake", help="refresh observations and print a read-only brief")
    wake.add_argument("--project", required=True, help="existing project directory")
    wake.add_argument("--feature", required=True, help="lowercase feature slug or auto")
    wake.add_argument("--json", action="store_true", help="print normalized state as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            path, created = init_project(args.project, args.feature, sample=args.sample)
            if created:
                mode = "sample" if args.sample else "local_markdown"
                print(f"created={path}")
                print(f"source={mode}")
            else:
                print(f"already_exists={path}")
            return 0
        if args.command == "attach":
            result = attach_project(args.project, feature=args.feature, workflow=args.workflow, registry=args.registry)
            if args.json:
                print(json.dumps(result, ensure_ascii=False))
            else:
                print("attached=" + str(result["attached"]).lower())
                print("mode=" + result["mode"])
                print("project=" + result["project"])
                print("feature=" + result["feature"])
                print("dashboard=" + (result["dashboardUrl"] or "unavailable"))
                print("observer=" + result["observer"]["status"])
            return 0
        if args.command == "serve":
            return serve(args.project, args.feature, args.port)
        state = load_state(args.project, args.feature)
        if args.json:
            print(json.dumps(state, ensure_ascii=False, indent=2))
            return 0 if state["source"]["status"] in {"live", "sample"} else 2
        text, code = wake_text(state, args.project, args.feature)
        sys.stdout.write(text)
        return code
    except TrackerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
