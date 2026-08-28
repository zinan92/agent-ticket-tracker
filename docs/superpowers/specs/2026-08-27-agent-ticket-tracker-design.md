# Agent Ticket Tracker

## Problem Statement

Park's most-used engineering route is `Ask Matt → Setup Matt Pocock skills → grill-with-docs → to-spec → to-tickets → implement`, with Wayfinder as an on-ramp for efforts whose route is not yet visible. The route already produces durable artifacts, but those artifacts are spread across spec files, ticket files, blockers, branches, pull requests, tests, and Agent sessions.

The missing capability is a project-level view that keeps the whole delivery map visible, shows which nodes are actually verified, and tells Park what to wake next after a long implementation pause. The first product must be useful while remaining honest about what it has not integrated yet.

## Solution

Create a public repository named `agent-ticket-tracker` under the local `Agent｜Build` workspace. The product name is `Agent Ticket Tracker` and its metadata classifies it as `product_type: visualization`.

The first usable version is a local companion control plane:

1. `init` creates a project-local run manifest and imports available local Markdown spec and ticket metadata.
2. `serve` hosts a map-first HTML interface on localhost.
3. The UI keeps the full delivery tree visible, uses semantic status points with completion counts, and opens node details in a non-destructive overlay.
4. `wake` reconciles the manifest and artifacts, prints the current frontier and blockers, and emits a copyable continuation brief.

The MVP does not dispatch or control Agents. It gives the human and future orchestrator a stable view and a safe wake protocol. Codex App is a convenient browser surface, not the owner of the product state.

## User Stories

1. As Park, I want to initialize a tracker for an existing project so that the delivery view belongs to the project I am actually building.
2. As Park, I want to see the complete spec-to-release map so that I can monitor the whole effort after a long implementation run.
3. As Park, I want a node's status to include a completion count so that a yellow branch cannot look green merely because an Agent reported progress.
4. As Park, I want to click a node and inspect acceptance, evidence, blockers, and next action without losing the map.
5. As Park, I want the tracker to distinguish sample, missing, stale, and live-readable state so that uncertainty remains visible.
6. As Park, I want a safe wake command after an Agent stops so that I can recover the next action without asking the Agent to rediscover the whole project.
7. As Park, I want Wayfinder decision tickets to fit the same node model so that discovery and implementation do not become two unrelated tracking systems.
8. As an Agent, I want a copyable wake brief with paths and blockers so that a fresh implementation context can start from authoritative artifacts.
9. As a future executor adapter, I want a stable manifest and receipt shape so that Codex, Claude, or another Agent can be connected without replacing the visualization.

## Implementation Decisions

- Repository location: `/Users/wendy/Documents/Codex/Workspaces/agent-build/agent-ticket-tracker`.
- GitHub slug: `agent-ticket-tracker`; GitHub visibility: public. No GitHub remote is created until the local contract commit is present.
- Runtime: Python 3.11+ standard library for the first package. No API key, external service, or third-party runtime dependency is required.
- CLI name: `att`, with the module invocation `python3 -m agent_ticket_tracker` as the canonical fallback.
- Commands: `init`, `serve`, and `wake`. `init` writes only under the target project's `.agent-ticket-tracker/` directory. `serve` is read-only with respect to the target project. `wake` is observe-only and never starts an Agent.
- State source: a project-local JSON manifest plus readable local Markdown artifacts. The manifest lives at `.agent-ticket-tracker/<feature-slug>/manifest.json` and records `schemaVersion: 1`, source type, freshness, node state, acceptance summaries, evidence references, blockers, and next actions.
- Wake semantics: `wake` never writes the manifest, source files, branches, remotes, or logs. It reads the manifest and declared source artifacts, normalizes them in memory, prints the frontier and a continuation brief, and exits. A future refresh capability requires a separate contract.
- Init idempotence: `init` validates the project path and feature slug, creates the state directory and manifest only when absent, and refuses to overwrite an existing manifest. Re-running it reports the existing path without changing evidence or source files.
- Path safety: the project must be an existing non-symlink directory, and feature slugs accept only lowercase letters, digits, dots, underscores, and hyphens. All state writes stay beneath the canonical project root. The local server binds to loopback and serves only packaged UI plus normalized JSON endpoints; it never exposes arbitrary project files.
- Rendering safety: all external artifact text is HTML-escaped before insertion into the UI, status and kind values are enum-validated, and malformed input is rendered as an error state rather than executed or treated as a green result.
- Wake output: the CLI prints stable sections named `Source`, `Frontier`, `Blockers`, `Next brief`, and `Exit`. Exit code `0` means valid live or sample state; exit code `2` means missing, malformed, or stale source. No frontier is reported as a waiting or completed state, never as a fabricated task.

### Manifest v1 schema

The top-level manifest object has exactly `schemaVersion`, `run`, `source`, `nodes`, and `overrides` responsibilities:

```json
{
  "schemaVersion": 1,
  "run": {
    "id": "feature-slug",
    "displayName": "Feature release",
    "featureSlug": "feature-slug"
  },
  "source": {
    "kind": "manual",
    "root": null,
    "spec": null,
    "issues": null,
    "observedAt": "2026-08-27T09:00:00Z",
    "maxAgeSeconds": 900
  },
  "nodes": [],
  "overrides": {}
}
```

- `source.kind` is exactly one of `sample`, `manual`, or `local_markdown`. `sample` is never actionable. `nodes` is required and nonempty for `sample` and `manual`; for `local_markdown`, `nodes` must be empty and generated nodes are built in memory. `overrides` is keyed by generated node ID and may contain only `acceptance`, `evidence`, `nextAction`, and `note`; it cannot set `status`.
- All run, node, acceptance, and evidence IDs match `^[a-z0-9][a-z0-9._-]{0,63}$`. There is exactly one run root with `parentId: null`; every other parent must exist. Node kinds are `run`, `phase`, `ticket`, `decision`, and `acceptance`.
- Node status hints are `planned`, `ready`, `running`, `partial`, `verified`, `needs-review`, `blocked`, or `waiting`. Acceptance records are `{id, label, status}` with status `pending`, `verified`, or `failed`.
- Evidence records are `{id, kind, label, status, ref, observedAt, freshForSeconds}`. Evidence kind is `test`, `review`, `runtime`, `device`, `artifact`, or `manual`; evidence status is `verified`, `missing`, `stale`, or `failed`. Timestamps are RFC3339 UTC, future-dated by at most 60 seconds, and `freshForSeconds` is an integer from 1 through 604800 with a default of 900.

### Deterministic source and state rules

- JSON parse failure, schema failure, duplicate IDs, unknown parents, invalid enums, invalid timestamps, future timestamps beyond the tolerance, unknown source kinds, mixed source declarations, unknown blockers, self-blockers, or blocker cycles produce `malformed`.
- For `local_markdown`, the exact source root is `.scratch/<feature-slug>`, with `spec.md` and `issues/`; a missing root, spec, or issues directory produces `missing`, while an existing empty issues directory is valid live input. Markdown parse failure produces `malformed`. Local Markdown is observed on each read, so unchanged files are not stale merely because the manifest is old.
- For `manual`, absent or future-dated `observedAt` is `malformed`, and age beyond `maxAgeSeconds` is `stale`. Error precedence is total: `malformed` overrides `missing`, `missing` overrides `stale`, and `stale` overrides `live`. `sample` is an explicit separate state.
- Verified evidence is current only when its status is `verified`, its timestamp is within the future tolerance, and its age is within `freshForSeconds`. Missing, stale, failed, absent, or invalid evidence cannot support green.
- A leaf is normalized to `verified` only when it has at least one acceptance record, every acceptance item is `verified`, and at least one current verified evidence record. A claimed verified hint that fails these checks becomes `needs-review`.
- All children are required. Parent status precedence is source error, then `blocked`, then `needs-review`, then `running`, then `partial`, then `verified` when every child is verified, otherwise `waiting`.
- `blockerIds` means “this node is blocked by these node IDs”. A blocker is resolved only when its normalized status is `verified`; there is no implicit `resolved` status. Only live nodes with status `ready`, `partial`, or `needs-review` and all blockers verified enter the actionable frontier.

### Commands, discovery, and future boundaries

- `init` uses exactly `.scratch/<feature-slug>/spec.md` and `.scratch/<feature-slug>/issues/`. It maps `NN-slug.md` to `ticket-NN-slug`, reads files in lexical order, maps `ready-for-agent` to `ready`, `claimed` to `running`, and `resolved` or `merged` to a non-green hint until evidence proves `verified`. `Blocked by:` accepts comma-separated two-digit ticket numbers or exact generated IDs. Checkboxes under `## Acceptance criteria` become ordered acceptance records. Files are read as text and never executed.
- The project root must be an existing non-symlink directory. Relative source paths cannot be absolute, contain `..`, or resolve through a symlink outside the project root. The HTTP server binds to `127.0.0.1` and exposes only the packaged UI, `/api/state`, and `/healthz`. All values inserted into HTML are escaped in the browser.
- The default UI is map-first. The complete tree stays visible while a selected node opens a right-side overlay; on narrow screens it becomes a full-width detail section below the map.
- Wayfinder decision tickets use `decision`; implementation tickets use `ticket`. Ask Matt, Setup Matt Pocock skills, grill-with-docs, to-spec, to-tickets, and implement remain workflow owners; this repo observes their artifacts and does not replace them.

### Read-only process observations

- Every normalized state response may include a derived `observations` array. Observations are read on demand from declared local artifacts and the target project's Git metadata; they are never written back to the manifest or project.
- An observation has stable fields `id`, `kind`, `label`, `status`, `detail`, and `observedAt`. `status` describes observability only (`observed`, `unavailable`, or `error`); it is not a ticket status and cannot change green/frontier calculation.
- The first observer reports spec/ticket file presence and recency, plus Git branch, working-tree summary, and latest commit when the project is a Git worktree. Git is invoked with fixed read-only commands and a bounded timeout. A missing Git repository is an explicit unavailable observation.
- The dashboard renders the latest observations as a monitor feed. `wake` prints the same feed for a human or another command to read. Neither surface dispatches, resumes, retries, pauses, edits, or otherwise changes the development process.
## Testing Decisions

- Unit tests cover manifest parsing, status normalization, blocker resolution, frontier selection, wake brief generation, path safety, and read-only observations.
- HTTP tests cover localhost serving, the state endpoint, malformed manifest handling, and HTML response content.
- Manual browser checks cover map visibility, node selection, overlay close and reopen, manifest refresh, keyboard focus, desktop layout, and narrow mobile layout.
- Tests must distinguish `verified-software` from `verified-experience`; a passing test does not prove that Park used the UI successfully.
- The first implementation does not require a full end-to-end Agent run. A real project pilot will be a later acceptance gate.

## Out of Scope

- Native UI changes to the Codex App.
- GitHub issue or PR mutations, branch management, merge automation, or deployment.
- Automatic Agent dispatch or a hidden Ralph loop.
- Cloud hosting, accounts, shared teams, paid plans, and telemetry.
- Replacing Ask Matt, Setup Matt Pocock skills, grill-with-docs, to-spec, to-tickets, implement, or Wayfinder.
- A second registry that competes with a project's existing `REGISTRY.md` or issue tracker.

## Further Notes

The product should be explained in three layers:

- Can do now: read an explicit local run state, observe local artifact/Git activity, visualize the full map, expose evidence and blockers, and produce a read-only wake brief.
- Cannot do now: know live GitHub/Linear/PR/Agent state without a dedicated adapter, dispatch an Agent, or claim that a green dot is real-world acceptance without a receipt.
- Next phase: add narrowly-scoped read-only adapters for additional sources. Executor adapters are not part of this product contract.

The product is an Agent delivery observer/dashboard. The HTML is one view of it, not its identity. Durable truth remains in project artifacts and receipts; the observer extracts signals and highlights exceptions without becoming the owner of process state.
