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

## Contract clarification from pre-implementation review

The original acceptance criteria remain frozen. The following implementation clarifications are part of the contract and were recorded after independent review:

- `wake` is read-only. It reads and normalizes state in memory, prints stable `Source`, `Frontier`, `Blockers`, `Next brief`, and `Exit` sections, and never writes or dispatches work.
- Manifest schema version 1 is stored at `.agent-ticket-tracker/<feature-slug>/manifest.json`. `init` refuses to overwrite an existing manifest.
- Source states are `live`, `sample`, `missing`, `malformed`, and `stale`. Missing, malformed, and stale inputs produce no actionable frontier. Sample data is visibly non-actionable.
- A green `verified` node requires complete acceptance items plus current verified evidence. Unknown blockers and blocker cycles fail closed.
- Project roots are canonicalized and the root symlink is rejected. Feature slugs are restricted to lowercase letters, digits, dots, underscores, and hyphens. The server is loopback-only and never serves arbitrary project files.
- External artifact text is escaped before UI rendering. No Agent prose or unverified test output can make a node green.

## Contract clarification 2 from architecture review

The original acceptance criteria and the first clarification remain frozen. This second clarification freezes the machine-readable v1 behavior:

- Manifest v1 has `schemaVersion`, `run`, `source`, and `nodes` or `overrides`. Node IDs are lowercase safe slugs; parents, blockers, status enums, acceptance records, evidence records, and RFC3339 UTC timestamps are validated before use.
- Source status precedence is `sample` explicitly, then `malformed`, `missing`, or `stale` on failure, otherwise `live`. Local Markdown is observed on each read; manual state uses `observedAt` and `maxAgeSeconds`.
- Verified requires every acceptance item verified plus at least one current verified evidence record. Evidence is current for 900 seconds by default and future timestamps beyond 60 seconds are invalid.
- `blockerIds` means blockers of the current node. Unknown blockers, self-blockers, and cycles fail closed. Only live nodes in `ready`, `partial`, or `needs-review` with verified blockers enter the frontier.
- `init` creates the manifest exclusively and never overwrites. `serve` and `wake` are read-only. Local Markdown is parsed in memory on each read; sample/manual nodes come from the manifest.
- The project root must be an existing non-symlink directory. Relative sources stay beneath it without `..` or outside symlinks. The server is loopback-only and exposes no arbitrary project files. Browser rendering escapes every external value.

## Final contract rewrite from architecture review

The original acceptance criteria and all earlier clarifications remain frozen. This final contract rewrite removes schema ambiguity before coding:

```json
{
  "schemaVersion": 1,
  "run": {"id": "feature-slug", "displayName": "Feature release", "featureSlug": "feature-slug"},
  "source": {"kind": "manual", "root": null, "spec": null, "issues": null, "observedAt": "RFC3339 UTC", "maxAgeSeconds": 900},
  "nodes": [],
  "overrides": {}
}
```

- `source.kind` is exactly `sample`, `manual`, or `local_markdown`. Sample is non-actionable. Sample/manual manifests require a nonempty `nodes` array. Local Markdown requires an empty `nodes` array and derives nodes from exactly `.scratch/<feature-slug>/spec.md` and `.scratch/<feature-slug>/issues/` on each read.
- `overrides` is optional, keyed by generated node ID, and may contain only `acceptance`, `evidence`, `nextAction`, and `note`. It cannot set status directly.
- Node kinds are `run`, `phase`, `ticket`, `decision`, and `acceptance`. Status hints are `planned`, `ready`, `running`, `partial`, `verified`, `needs-review`, `blocked`, and `waiting`. Evidence kinds are `test`, `review`, `runtime`, `device`, `artifact`, and `manual`.
- A leaf is green only with at least one acceptance item, all acceptance items verified, and at least one current verified evidence record. Parent children are all required. Parent status precedence is source error, blocked, needs-review, running, partial, verified when all children are verified, otherwise waiting.
- `blockerIds` means blockers of the current node. Only verified blockers resolve a dependency. Unknown blockers, self-blockers, and cycles are malformed; there is no implicit `resolved` state.
- Source errors are ordered: malformed, missing, stale, live. Local Markdown is live when its required paths exist and parse; manual source is stale after `maxAgeSeconds`; evidence defaults to 900 seconds and future timestamps beyond 60 seconds are malformed.
- Only live nodes with status `ready`, `partial`, or `needs-review` and all blockers verified enter the frontier. Sample, missing, malformed, and stale states produce no actionable frontier.
- `init` is exclusive and non-overwriting. `serve` and `wake` are read-only. The server binds to loopback and exposes only the packaged UI, `/api/state`, and `/healthz`; the browser escapes all untrusted values.
