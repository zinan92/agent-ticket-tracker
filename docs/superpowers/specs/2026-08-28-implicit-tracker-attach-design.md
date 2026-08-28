# Implicit tracker attach

## Problem

Park uses one user-facing slash command for a workflow. Asking him to type a second `/track` command creates a second mental entry point and breaks the continuity of workflows such as Ask Matt or Ask Park. The tracker must attach to a project without becoming another workflow router.

## Design

The existing workflow entry invokes one internal observer hook. The hook receives the current project directory and workflow name, then calls the tracker `attach` operation. This is an internal sidecar action; the user still invokes only the original workflow command.

The tracker stores registration and observer lifecycle metadata under a tracker-owned user directory, not in the monitored project. The registry is local-only JSON and contains canonical project paths, the selected feature mode, workflow label, dashboard port, process id, and timestamps. It contains no credentials or project contents.

The default feature mode is `auto`. The observer scans only the direct children of `.scratch/` for feature directories that contain both `spec.md` and `issues/`. Exactly one candidate is followed. Zero candidates produces an explicit waiting state. Multiple candidates produce an explicit ambiguity state; the tracker never picks one arbitrarily.

When attached, the tracker starts or reuses one loopback-only observer server for the project. The server polls the same read-only state as the existing dashboard. A stopped or stale observer may be replaced by a new tracker-owned observer; the hook never starts or changes `/implement` or another executor.

A project may later acquire its `.scratch/<feature>` source after the first workflow command. The auto observer discovers that source on the next read without another user command or a manifest write. Explicit `--feature` remains available for projects with more than one active run.

## User flow

```text
user: /ask-park or /grill-with-docs or /implement
  -> internal tracker hook: attach current project in auto mode
  -> original workflow continues unchanged
  -> dashboard stays read-only and refreshes observations
```

## Public seams

- `att attach --project <path> [--feature <slug>|auto] [--workflow <name>]`: idempotently register and start/reuse the observer, returning a dashboard URL.
- `load_state(project, "auto")`: resolve exactly one local feature at read time, or return explicit waiting/ambiguous source state without writing.
- Existing `serve`, `/api/state`, and `wake`: remain read-only and keep their existing status/frontier semantics.
- Internal `agent-ticket-tracker-hook` skill: callable by workflow instructions, not intended as a user-facing second slash command.

## Failure handling

- No project directory: skip attachment and let the original workflow continue.
- No source yet: show waiting; do not create a fake feature or frontier.
- Multiple sources: show ambiguity; do not guess.
- Registry or observer failure: report observer unavailable; never block or mutate the workflow.
- Untrusted project path: reject before reading or writing tracker registry.

## Out of scope

- The tracker does not execute, retry, pause, resume, terminate, or modify workflow commands.
- The tracker does not scan the entire filesystem, read credentials, call GitHub/Linear, or inject a native Codex sidebar.
- Existing workflow semantics, state contracts, issue ownership, and `/implement` behavior remain unchanged.
