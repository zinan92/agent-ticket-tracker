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
- Wake semantics: `wake` never writes the manifest, source files, branches, remotes, or logs. It reads the manifest and declared source artifacts, normalizes them in memory, prints the frontier and a continuation brief, and exits. A future `refresh` command may be added only as a separately contracted write capability.
- Source validity: the normalized source status is one of `live`, `sample`, `missing`, `malformed`, or `stale`. `live` requires every declared source to exist and parse, a valid schema, a nonexpired `observedAt`/`maxAgeSeconds` window (default 900 seconds), and no blocker graph cycle. `sample` is visibly non-actionable. `missing`, `malformed`, and `stale` produce no actionable frontier and remain visible as failure states.
- Green-state rule: a node can display `verified` only when its acceptance items are complete and it has at least one current evidence record with verified status. A textual Agent claim, a missing evidence record, or a stale evidence record cannot produce green.
- Frontier rule: only `live` data can produce an actionable frontier. Unknown blockers, malformed blocker references, cycles, or nonterminal prerequisites keep a node out of the frontier. `verified` is the only successful terminal state; `blocked`, `needs-review`, and `waiting` remain explicit non-success states.
- Init idempotence: `init` validates the project path and feature slug, creates the state directory and manifest only when absent, and refuses to overwrite an existing manifest. Re-running it reports the existing path without changing evidence or source files.
- Path safety: the project must resolve to an existing directory, the project root itself may not be a symlink, and feature slugs accept only lowercase letters, digits, dots, underscores, and hyphens. All state writes stay beneath the canonical project root. The local server binds to loopback and serves only packaged UI plus the normalized JSON endpoint; it never exposes arbitrary project files.
- Rendering safety: external artifact text is HTML-escaped before insertion into the UI, status and kind values are enum-validated, and malformed input is rendered as an error state rather than executed or treated as a green result.
- Wake output: the CLI prints stable sections named `Source`, `Frontier`, `Blockers`, `Next brief`, and `Exit`. Exit code `0` means valid live or sample state; exit code `2` means missing, malformed, or stale source; no frontier in a valid live run is reported as a completed or waiting state, not as a fabricated task.
- Node kinds: `run`, `phase`, `ticket`, `decision`, and `acceptance`. Wayfinder decision tickets use `decision`; implementation tickets use `ticket`.
- Statuses: `planned`, `ready`, `running`, `partial`, `verified`, `needs-review`, `blocked`, and `waiting`. The UI uses color as a supplement and always renders a text status.
- Frontier calculation: a node is actionable only when it is not terminal and every named blocker is verified or otherwise explicitly resolved in the manifest. Missing or malformed blockers keep the node out of the frontier.
- Source truth: the tracker reports what it can read and marks missing or stale data. It never promotes a node to verified because a natural-language summary sounds complete.
- UI: map-first as the default. The complete tree remains visible; selecting a node opens a right-side overlay. On narrow screens the overlay becomes a full-width detail section beneath the map.
- Prototype lineage: the earlier static control-tower HTML is retained as a visual reference, but the new repository owns the generated template and the manifest contract.
- Future adapters: GitHub/Linear issue reads, Git and PR state, Codex App Server, other Agent CLIs, and notifications are later adapters. They are not required for the first repo milestone.

## Testing Decisions

- Unit tests cover manifest parsing, status normalization, blocker resolution, frontier selection, wake brief generation, and path safety.
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

- Can do now: read an explicit local run state, visualize the full map, expose evidence and blockers, and produce a safe wake brief.
- Cannot do now: know live GitHub/PR/Agent state without an adapter, dispatch an Agent, or claim that a green dot is real-world acceptance without a receipt.
- Next phase: add read-only adapters first, then bounded executor adapters behind explicit human gates.

The long-term product is a Delivery Control Plane. The HTML is its view, not its identity. Durable truth remains in project artifacts and receipts; the observer aggregates and highlights exceptions.
