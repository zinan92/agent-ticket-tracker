---
name: agent-ticket-tracker-hook
description: Attach a read-only Agent Ticket Tracker beside an existing project workflow without adding a second user-facing slash command.
---

# Agent Ticket Tracker Hook

This is an internal sidecar, not a user-facing workflow. The user should continue invoking exactly one existing command such as `/ask-matt`, `/ask-park`, `/grill-with-docs`, `/to-spec`, `/to-tickets`, `/implement`, or `/wayfinder`.

## Attach

When the calling workflow has an existing project worktree, run the tracker attach seam once near the beginning:

```bash
att attach --project <current-project-root> --feature auto --workflow <calling-workflow> --json
```

If `att` is not installed, run the equivalent module invocation with the configured Agent Ticket Tracker source path and `PYTHONPATH`. Never guess a project root from a broad home or workspace directory; use the project directory already established by the calling workflow.

The command is idempotent. It writes only tracker-owned observer registry metadata under the user tracker directory and may start or reuse a loopback-only tracker server. It does not write the monitored project, its manifest, tickets, code, branch, PR, receipts, or workflow state.

## Handoff to the user

If the result contains a `dashboardUrl`, open or reuse that URL in the current Codex browser panel when the browser-opening tool is available. Do not open duplicate tabs on every workflow phase. Report only a short observer line, then let the original workflow continue.

If the hook fails, say `observer unavailable` once and continue the original workflow. The hook is best-effort and must never block, reroute, retry, pause, resume, terminate, or otherwise control the calling workflow.

## Auto mode

`auto` follows exactly one complete local Markdown source under `.scratch/<feature>/` when one exists. With no source it shows waiting. With multiple sources it shows an explicit ambiguity. It never invents a feature or chooses one arbitrarily.

## Hard boundary

The tracker observes and visualizes. `/implement`, Ask Park, Wayfinder, or any other workflow remains the sole owner of execution and state changes. Do not call an executor from this skill.
