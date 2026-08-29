# Real source adapters

## Decision

`feature=auto` is a read-only source selector, not a requirement that every project use `.scratch`.

Source priority is:

1. `.ask-park/state.json` when present and valid;
2. exactly one complete `.scratch/<feature>/` source;
3. project-level artifact and Git observations when no structured workflow source exists;
4. an explicit visible missing/malformed state when the selected source is unreadable or ambiguous.

The Ask Park adapter projects the persisted v1 state into the existing tracker node model. Activity and evidence remain separate; a file or HTML artifact is never promoted to verified merely because it exists.

The project fallback is a non-authoritative live read model. It displays the project name, artifact counts/recent files, and Git observations. It intentionally has no actionable frontier and does not infer execution status.

All adapters read only. They do not write project state, invoke workflow commands, parse arbitrary HTML semantics, or modify tracker-owned registry data during dashboard polling.
