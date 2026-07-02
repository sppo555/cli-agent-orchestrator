# CAO-Tailscale Changes Summary

This file records how the package-level CAO customizations relate to the CAO-Tailscale deployment repo after the latest fork sync.

## Current Package Branch

- Repo: `/Users/alex/Developer/cli-agent-orchestrator`
- Integration branch: `cao-tailscale-integration`
- Base: `origin/main` at `25422d7` (previous: `b0d313e`, `5dcf319`, `33c593d`, `f369068`, `0214f23`, `462fa2f`)
- Integration tip: `HEAD` (this sync's rebuild)
- Local package customizations included here:
  - 4.1 Codex pyte status
  - 4.3 Claude Code `--effort`
  - 4.4 Antigravity workspace trust
  - 4.6 status turn-boundary guard
  - 4.7 Web terminal clipboard shortcuts
  - 4.11 Web terminal viewer isolation
  - 4.12 Web terminal PageUp/PageDown scroll
- Local package customizations not included here:
  - 4.2 Antigravity provider, because upstream already merged it in `086e61a`.
  - 4.5 9-worker selection, because it belongs to CAO-Tailscale deployment scripts.
  - 4.8 agy handoff terminal retention, because it was reverted from integration and is deferred pending a safer cleanup design.
  - 4.9 + 4.10 agy handoff reliability, because it was implemented profile-only in CAO-Tailscale (`6190f52`), with no package source change.

## Package Customizations

### 4.1 Codex pyte status

Adds Codex provider opt-in to pyte rendered-screen status detection:

- `supports_screen_detection = True`
- `get_status_from_screen(screen_lines)`

Reason: Codex TUI progress and idle footers are unreliable when read from raw append-only terminal output. Rendered-screen detection sees the final composited TUI state.

### 4.2 Antigravity CLI provider

No local patch is needed.

Upstream commit `086e61a` / awslabs#323 already provides the official `antigravity_cli` implementation and wiring. Old local provider branches should not be merged into modern main.

### 4.3 Claude Code effort

Adds profile-level `effort` support:

- `AgentProfile.effort`
- Claude command emits `--effort <value>` when `effort` is a non-empty string.

This allows profiles such as reviewers to run at high effort without changing global Claude Code environment settings.

### 4.4 Antigravity workspace trust

Adapts to upstream official `antigravity_cli.py`.

Before launching `agy`, the provider reads the pane working directory and adds that exact path to:

```text
~/.gemini/antigravity-cli/settings.json
```

under:

```json
{
  "trustedWorkspaces": []
}
```

Cleanup removes only the path this provider instance added, preserving any pre-existing user trust entries.

### 4.6 Status turn-boundary guard

Adds a global guard in `StatusMonitor` for the handoff window immediately after CAO sends input to a worker.

When a terminal was previously `IDLE` or `COMPLETED`, a newly sent prompt now arms a stale-ready mask. `get_status()` reports `PROCESSING` until the terminal produces new output and the short stale-frame grace period has elapsed. This prevents a new wait from being satisfied by the previous turn's cached ready state.

This is separate from 4.1:

- 4.1 improves Codex screen classification.
- 4.6 fixes the orchestration/status lifecycle around a new input turn.

### 4.7 Web terminal clipboard shortcuts

Adds explicit clipboard handling to the Web UI terminal:

- `web/src/components/TerminalView.tsx` intercepts browser paste paths and sends plain text to the terminal websocket.
- `Ctrl+V` / `Ctrl+Shift+V` paste text instead of being forwarded to the agent TUI.
- `Ctrl+C` copies selected terminal text, while still allowing interrupt behavior when there is no selection.

Reason: Windows Chrome clients connected to the macOS-hosted Web UI over LAN/Tailscale can otherwise send `Ctrl+V` into Codex/Claude/agy TUIs, where it is interpreted as an image-paste shortcut and fails with `Failed to paste image: no image on clipboard`.

## Deferred / Proposed Package Work

### 4.8 Agy handoff terminal retention (deferred)

Branch retained:

```text
custom/4.8-agy-handoff-terminal-retention
```

The branch contains `ace213f fix(handoff): keep agy terminals after success`, but that change is not part of the current integration branch.

Reason for deferral: disabling teardown for every `antigravity_cli` handoff preserves debug visibility, but completed agy worker terminals then remain open and can confuse later developer/reviewer handoff management. The branch is useful evidence, not a merge-ready production behavior.

### 4.9 Supervisor premature-return guard (proposed)

The custom CAO-Tailscale supervisor profile needs a stricter handoff validation rule:

- Check the required artifact path before judging a handoff as failed.
- Do not treat `cao terminal restore <id>` returning `No snapshot found` as proof that the worker is gone.
- Do not treat `developer antigravity_cli N/A` as proof that the worker is dead.
- Check CAO terminal registry and the tmux window before re-dispatching.
- Avoid duplicate dispatch when a live worker already owns the same task/artifact.

### 4.10 Agy prompt/context hardening (proposed)

The `/tmp/4.8-another.txt` investigation found two agy-specific failure modes:

- Context truncation: agy emitted `CHECKPOINT 0`, then the model produced an empty response and returned to idle.
- Long-running command handling: agy could start DB-backed validation, then say it was waiting instead of waiting for the command to complete and writing the final artifact.

Planned direction:

- Reduce `developer_agy` profile and handoff prompt size.
- Remove duplicated instruction/security blocks.
- Make long-running command instructions explicit: wait for completion, inspect exit code/output, write artifact, then return.
- Prefer `developer_codex` or `developer_claude` for large DB-backed tasks until agy is stable.

## CAO-Tailscale Deployment Customization

### 4.5 9-worker selection

This is not implemented in `cli-agent-orchestrator`.

It belongs to:

```text
/Users/alex/Developer/CAO-Tailscale
```

Relevant deployment files:

- `scripts/gen-workers.sh`
- `scripts/select-workers.sh`
- `start-all.sh`

Expected worker set:

- `planner_claude`, `planner_codex`, `planner_gemini`
- `developer_claude`, `developer_codex`, `developer_gemini`
- `reviewer_claude`, `reviewer_codex`, `reviewer_gemini`

## Verification

Package integration branch should pass:

```bash
uv run pytest test/providers/test_antigravity_cli_unit.py test/providers/test_codex_provider_unit.py test/providers/test_claude_code_unit.py test/services/test_status_monitor.py test/services/test_agent_step.py
uv run black --check src/cli_agent_orchestrator/providers/antigravity_cli.py test/providers/test_antigravity_cli_unit.py src/cli_agent_orchestrator/providers/codex.py src/cli_agent_orchestrator/providers/claude_code.py src/cli_agent_orchestrator/models/agent_profile.py test/providers/test_claude_code_unit.py src/cli_agent_orchestrator/services/status_monitor.py test/services/test_status_monitor.py test/services/test_agent_step.py
uv run isort --check-only src/cli_agent_orchestrator/providers/antigravity_cli.py test/providers/test_antigravity_cli_unit.py src/cli_agent_orchestrator/providers/codex.py src/cli_agent_orchestrator/providers/claude_code.py src/cli_agent_orchestrator/models/agent_profile.py test/providers/test_claude_code_unit.py src/cli_agent_orchestrator/services/status_monitor.py test/services/test_status_monitor.py test/services/test_agent_step.py
npm --prefix web run build
```

CAO-Tailscale 9-worker validation should be run in that repo, not here.
