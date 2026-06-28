# 4.8 — Agy handoff terminal retention (DEFERRED / NOT adopted)

> Branch: `custom/4.8-agy-handoff-terminal-retention` · Base: `462fa2f` · Commit: `ace213f`
> Status: **deferred. Reverted from the integration branch. Kept for reference only — do
> not merge as-is.** Superseded by the merged 4.9 + 4.10 profile-only approach (see below).

## What this branch changes

- File: `src/cli_agent_orchestrator/mcp_server/server.py` (`_handoff_impl`)
- File: `test/mcp_server/test_handoff.py` (added coverage)
- Change: the handoff run-step config switched from a hard `"teardown": True` to
  `"teardown": provider != "antigravity_cli"`, so agy worker terminals are **not** torn
  down after a handoff returns.

```python
# before
"teardown": True,
# after
"teardown": provider != "antigravity_cli",
```

## Original intent

agy (`antigravity_cli`) can briefly render a ready/idle footer while work is still in
progress, which can make CAO's run-step report `COMPLETED` early and tear the worker
terminal down on a premature handoff success. Keeping the terminal alive was meant to let
a supervisor inspect or reuse the worker window instead of losing it.

## Why it was deferred (reverted from integration)

Reverted on `feat/customizations-main-462fa2f-r2` (`4dcfd2f` / `537d546` / `a3a56e2`).
Leaving completed agy handoff terminals open works **against** the correct, upstream
behavior ("handoff done → exit → delete terminal"). Lingering terminals confuse later
developer/reviewer dispatch and cleanup, so the fix traded one failure mode for another.

## What replaced it

The root cause is **not** a CAO misread or broken teardown — agy genuinely ends its turn
before the task is done (returns "I am waiting…" / "running in the background", then exits
the CLI), so CAO correctly sees idle and tears down. Disabling teardown does not fix that;
it only hides the symptom and creates cleanup debt.

Instead, **4.9 + 4.10 were merged into a single profile-only version** (implemented in
`/Users/alex/Developer/CAO-Tailscale`, not in this package) that works *with* normal
teardown:

- **developer profile**: must finish the whole task within a single turn and write the
  required artifact before returning — never push work to a background/async task and yield.
- **supervisor profile**: artifact-as-truth guards — the assigned artifact is the only
  proof of completion; missing artifact re-dispatches under a bounded cap then halts or
  re-routes; weak signals (`session status … N/A`, `restore … No snapshot found`) are not
  proof a worker is dead; no duplicate workers per task/artifact; cut tasks small; route
  large DB-backed work to codex/claude.

This secures the *result* without touching CAO package source or disabling teardown. See
the integration branch's `CAO-CUSTOMIZATIONS-PROGRESS.md` (§4.9 + 4.10) and
`CAO-Tailscale/4.9-agy-handoff-reliability-HANDOFF.md`.

## Decision

Keep this branch for reference. **Do not merge 4.8 as-is.** Revisit only if the terminal
retention behavior is redesigned to also handle later dispatch/cleanup cleanly.
