# 01 - Local Delivery Control Tower

**Outcome:** A local project can generate and serve a map-first delivery view that reads a small, explicit run manifest, lets Park inspect node evidence, and prints a safe wake brief without starting real Agent work.

**Complexity:** M

**Status:** claimed

## Acceptance criteria

- [ ] `python3 -m agent_ticket_tracker init --project <path> --feature <slug>` creates a clearly marked `.agent-ticket-tracker/` run manifest without changing source files, Git branches, or remote services.
- [ ] `python3 -m agent_ticket_tracker serve --project <path> --feature <slug>` serves the map-first control tower on localhost with no third-party runtime dependency.
- [ ] The browser view shows the full delivery tree, semantic status points, completion counts, sample/live state labeling, and a non-destructive node detail panel.
- [ ] The browser view reads the current manifest through a local endpoint and refreshes after the manifest changes; it must not silently invent a green state.
- [ ] `python3 -m agent_ticket_tracker wake --project <path> --feature <slug>` reports the current frontier, blockers, source status, and a copyable continuation brief without dispatching an Agent.
- [ ] README usage covers Ask Matt, Setup Matt Pocock skills, grill-with-docs, to-spec, to-tickets, implement, Wayfinder, and the distinction between observe-only wake and future execution wake.

## In scope

- One Python standard-library CLI package named `agent_ticket_tracker`.
- A local JSON run manifest and a small parser for local Markdown spec/ticket artifacts when present.
- A self-contained map-first HTML/JavaScript UI with overlay detail and progress rings.
- Local HTTP serving, manifest refresh, status reporting, and a safe wake brief.
- Unit tests for manifest normalization, blocker/frontier calculation, wake output, and HTML serving.
- Public-repo documentation describing current capability, limits, and next phase.

## Out of scope

- GitHub API writes, automatic issue creation, PR creation, merging, or deployment.
- Automatic Codex/Claude/other Agent dispatch, pause, retry, or background scheduling.
- Codex App native sidebar injection or modification of Codex App internals.
- Authentication, multi-user collaboration, cloud hosting, billing, or telemetry.
- Inferring completion from an Agent's prose or from a test command that is not recorded in the manifest.
- Rewriting the global Ask Matt skills, Agent hierarchy, or Codex harness.

## Forbidden actions

- Do not modify a monitored project's source files, branches, remotes, or credentials during `init`, `serve`, or `wake`.
- Do not use `git add -A`; stage named paths only.
- Do not place secrets in source, logs, README examples, screenshots, or fixtures.
- Do not report a live project state when the manifest is sample, stale, missing, malformed, or only partially read.
- Do not create a GitHub remote or publish anything under a different visibility than public.

## Verification evidence

- Named-path Git commit for the contract before implementation.
- Unit test output and local HTTP readiness output.
- Browser click-through for map, node overlay, refresh, and mobile layout.
- A wake command output showing frontier and blocker status.
