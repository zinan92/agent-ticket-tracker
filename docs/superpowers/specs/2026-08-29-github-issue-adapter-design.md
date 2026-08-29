# Agent Ticket Tracker

## Problem Statement

Agent Ticket Tracker already observes local Markdown, Ask Park state, project artifacts, and Git activity. Park's ordinary development workflow also produces a durable GitHub issue and pull-request trail, but the tracker currently cannot see it. When a project has no local structured source, the dashboard can only count files; it cannot distinguish an issue that is planned, being implemented, awaiting review, or actually merged with green checks.

The missing capability is a read-only GitHub issue view that keeps the existing one-command workflow intact. It must expose delivery signals without becoming another executor, issue manager, or source of truth.

## Solution

Add a `github_issues` source adapter used by `feature=auto` after Ask Park and before the project-artifact fallback. The adapter reads one GitHub repository through the authenticated `gh` CLI and projects open milestones, open issues, linked pull requests, and pull-request check runs into the existing node schema.

The hierarchy is deliberately small for this single-module repository:

```text
run: GitHub repository
└── phase: each open milestone
    └── ticket: each open issue in that milestone
└── phase: Unscheduled (no milestone)
    └── ticket: each open issue without a milestone
```

The adapter is a source observer only. It never creates, edits, labels, closes, comments on, assigns, or otherwise mutates GitHub data. `/implement`, review commands, and the existing project workflow remain the owners of process state.

## User Stories

1. As Park, I want open GitHub milestones and issues to appear as a delivery map so that the dashboard follows the workflow's real ticket system.
2. As Park, I want linked PR and CI evidence on each issue so that a green point is grounded in current GitHub signals.
3. As Park, I want a draft PR, open PR, and merged PR to produce different statuses so that implementation and review are not conflated.
4. As Park, I want projects without `gh`, authentication, or a GitHub remote to fall through safely to existing observers rather than crash.
5. As Park, I want the dashboard to refresh GitHub at most once every 120 seconds while the UI continues to poll its in-memory state normally.
6. As an Agent, I want the adapter to remain read-only and schema-compatible so that existing `/implement` and workflow commands are never redirected or modified.

## Implementation Decisions

- Source module: `src/agent_ticket_tracker/github_issues.py`, following the shape and normalized node vocabulary used by `ask_park.py`.
- Source discovery: inspect a local GitHub remote, accepting HTTPS and SSH forms. If no GitHub remote exists, return an unavailable adapter result so the auto source cascade continues to project observations.
- Runtime dependency: use the installed `gh` executable only. Run `gh auth status --hostname github.com` before a refresh; an absent executable or failed authentication is unavailable and must never raise out of `load_state`.
- GitHub read: issue one `gh api graphql` request containing the repository's open milestones, open issues, linked pull requests from issue timeline cross-references, and the latest commit's check runs. Do not make one REST request per issue or PR. Request `pageInfo` on bounded connections; if any connection reports another page, mark the response malformed instead of silently dropping data. Fetching additional pages is a later contract.
- Cache: keep the successful GitHub projection in process memory for 120 seconds. A running `serve` process therefore absorbs the UI's two-second polls without repeated GitHub calls. There is no disk cache and no cache written to the monitored project.
- Source metadata: report `source.kind=github_issues`, `status=live`, repository identity, observation time, and a 120-second freshness window. Include non-sensitive read-only observations for the repository, milestone count, and issue count.

### Issue status mapping

Status selection is deterministic and evaluates a `blocked` label first:

| GitHub signal | Tracker status |
| --- | --- |
| Issue has a `blocked` label | `blocked` |
| No linked PR | `planned` |
| Linked PR is draft | `running` |
| Linked PR is open and its checks are not all green | `needs-review` |
| Linked PR is merged and every observed check run is green | `verified` |
| Closed issue without a merged PR | `needs-review` |

If several PRs are linked, a merged PR with all green checks wins; otherwise an open draft wins; otherwise an open non-draft PR wins. Missing or pending checks are not green. A merged PR with no observed check runs is not green. The closed-issue rule is retained as a defensive parser rule even though the live query requests open issues.

Every linked PR URL and every observed check-run result is represented in the node's `evidence` list. Issue acceptance remains pending until the status mapping itself provides the complete merged-and-green signal; this preserves the existing normalizer's rule that evidence, not a status hint alone, is required for green.

The GitHub run and open-milestone phases carry current repository or milestone snapshot acceptance/evidence. This keeps a parent map from becoming an unsupported green claim merely because all child tickets rolled up to verified.

### Synthetic unscheduled phase

Open issues without a milestone are children of the exact phase named `Unscheduled (no milestone)`. Its status is explicitly `needs-review` after the existing `_normalized_state` call. This is an intentional hardcoded exception: it must not be recalculated from child rollup, because an issue outside a milestone is a tracking anomaly that Park should see even when its individual PR evidence is green. The implementation must not change `_normalize_nodes`, manifest schema, or node enums to achieve this. The only post-normalization hardcoded status accepted by this adapter is a downgrade to `needs-review`; it cannot promote a node to `verified`.

### Auto-source fallback

For `feature=auto`, the adapter is attempted after the existing Ask Park source and before the existing project-artifact fallback. Unavailable GitHub input (`gh` missing, auth failure, missing GitHub remote, or unusable repository lookup) returns no adapter state and allows the next observer to run. A malformed live GraphQL payload is visible as a non-actionable source error rather than being silently converted into green state.

## Testing Decisions

- Mock `gh` executable discovery, authentication, Git remote discovery, and the GraphQL subprocess; no test makes a live network call.
- Test each row of the status mapping, including blocked-label precedence, draft/open PR distinctions, merged green checks, pending/failing checks, no linked PR, and closed suspicious issues.
- Test milestone grouping, deterministic ordering, the exact unscheduled phase name, and the hardcoded `needs-review` override after normalizing through `core.load_state`.
- Test unavailable fallback when `gh` is missing or authentication fails, ensuring existing project-artifact observations still produce a live non-actionable state.
- Test an unavailable repository lookup as a fallback and any `pageInfo.hasNextPage=true` connection as visible malformed input.
- Test that GitHub run and milestone phase nodes carry current evidence and that hardcoded status handling cannot manufacture `verified`.
- Test the in-memory 120-second cache so repeated reads do not issue another GraphQL call before expiry.
- Run the complete stdlib unittest suite and the repository's named-path security scan before opening the PR.

## Out of Scope

- Any GitHub mutation, including issue/PR creation, labels, comments, assignment, closure, merge, or workflow dispatch.
- GitHub Projects v2, review comments, full review decision semantics, issue dependencies, auto-triage, or assigning the roughly 38 unscheduled issues to new milestones.
- Multiple modules, cross-repository aggregation, GitHub webhooks, a background scheduler, or a persistent cache.
- Changes to the manifest schema, node schema/enums, `_normalize_nodes`, existing command ownership, or the Codex App native UI.
- Replacing local Markdown, Ask Park, Wayfinder, `/implement`, or any existing workflow command.

## Further Notes

The product remains a tracker, not a controller:

- Can do now: read the authoritative GitHub issue/PR/CI signals, place open work into a stable map, attach source URLs and check results as evidence, and expose a conservative frontier.
- Cannot do now: infer work that GitHub does not publish, resolve an ambiguous workflow, move tickets, or restart/pause/retry an Agent.
- Next phase: only after a separate contract, consider additional read-only sources such as GitHub review decisions, Linear, receipts, or Wayfinder maps.

The HTML dashboard remains a local view of the observer. GitHub remains the source of issue and PR truth; the adapter only translates current read signals into the tracker contract.
