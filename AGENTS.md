# Agent Ticket Tracker

## Mission

Provide a local, read-only delivery view for long-running Agent work. The project observes specs, tickets, blockers, receipts, and explicit manifests. It does not replace Ask Matt, Setup Matt Pocock skills, grill-with-docs, to-spec, to-tickets, implement, or Wayfinder.

## Boundaries

- `init` may create only `.agent-ticket-tracker/<feature-slug>/manifest.json` inside a canonical monitored project.
- `serve` and `wake` are read-only with respect to monitored projects.
- The server is loopback-only and never serves arbitrary project files.
- No command dispatches Agents, edits source files, changes branches, creates PRs, or merges work.
- A node is green only with complete acceptance and current verified evidence.
- Unknown, stale, malformed, or sample state fails closed.

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m agent_ticket_tracker --help
```

Use named-path staging only. Keep secrets out of source, fixtures, logs, and documentation.

The local HTML is served by the package server and is not a native Codex App surface.
