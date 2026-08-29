# Decision Log

## 2026-08-29 — GitHub issue adapter

- Decision: read open GitHub milestones, issues, linked pull requests, and observed check runs through one authenticated `gh api graphql` request, then project them into the existing read-only tracker node model.
- Decision: keep GitHub as a fallback source for `feature=auto`; local Ask Park and `.scratch` sources retain priority, and unavailable GitHub input falls through to project observations.
- Decision: a `blocked` label wins over PR state. A merged PR is green only when at least one current check run exists and every observed check is completed with a green conclusion.
- Gotcha: issues without an open milestone must live under the exact synthetic phase `Unscheduled (no milestone)`. That phase is hardcoded to `needs-review` after normal child rollup, so a green child cannot hide the tracking anomaly.
- Boundary: the adapter never mutates GitHub, the monitored project, workflow state, branches, tickets, pull requests, or the existing manifest/node schema.
