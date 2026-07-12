# CAO-Tailscale Changes Summary

This file records how the package-level CAO customizations relate to the CAO-Tailscale deployment repo after the latest fork sync.

## Current Package Branch

- Repo: `/Users/alex/Developer/cli-agent-orchestrator`
- Integration branch: `cao-tailscale-integration`
- Base: `origin/main` at `deebf65` (previous: `84d79ff`, `29f175c`, `d971298`, `4dc8bf7`, `25422d7`, `b0d313e`, `5dcf319`, `33c593d`, `f369068`, `0214f23`, `462fa2f`)
- Integration tip: `ea9320c` (4.15 token usage documentation after the 2026-07-12 fork-sync rebuild; merge tip `4cf4976`, previous tip `8c7416c`)
- Local package customizations included here:
  - 4.1 Codex pyte status
  - 4.3 Claude Code `--effort`
  - 4.4 Antigravity workspace trust
  - 4.6 status turn-boundary guard
  - 4.7 Web terminal clipboard shortcuts
  - 4.11 Web terminal viewer isolation
  - 4.12 Web terminal PageUp/PageDown scroll
- 4.13 worker init headless render-viewer
- 4.14 worker init status recovery from `UNKNOWN`
- 4.15 durable worker token usage context, including model, effort, and progress/artifact path

## Latest Sync Notes (2026-07-12)

- Upstream range `84d79ff..deebf65` adds PATH-independent resolution for the bundled `cao-mcp-server`, plus v2.3.0/release and CI updates.
- The MCP resolution change touches Codex, Claude, and Agy provider files alongside customizations 4.1, 4.3, and 4.4. The merge preserved both behaviors: rendered-screen status detection, Claude `--effort`, and proactive Agy workspace trust.
- Upstream deletes the integration-only customization records; this rebuild restores and updates them from the previous integration tip `8c7416c`.
- 4.12's branch-level dependency merge with 4.11 had one `api/main.py` conflict. Commit `eb65a02` keeps both viewer protections: session-scoped `mouse off` and browser-driven `window-size latest`.
- Validation: 339 provider/status tests passed, 79 upstream MCP/install/profile regression tests passed, 10 WebSocket tests passed, black/isort passed, Web build passed, and Web tests passed with 61 tests (existing jsdom/xterm canvas noise remains).
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

### 4.11 Web terminal viewer isolation

Adds per-WebSocket grouped tmux viewer sessions for Web UI terminal views.

Reason: attaching multiple Web UI viewers directly to the shared CAO tmux session makes every viewer share one current-window pointer. Opening terminal B in one browser can switch terminal A in another browser or local macOS tmux attach. The isolated viewer session keeps input pointed at the real pane while each WebSocket keeps its own current window.

### 4.12 Web terminal PageUp/PageDown scroll

Adds Web UI `PageUp` / `PageDown` handling for terminal history:

- Frontend sends a WebSocket `scroll` message instead of forwarding PageUp/PageDown to the agent TUI.
- Backend scrolls the per-connection tmux viewer session from 4.11.
- Normal terminal input cancels viewer copy-mode first, so the viewer does not get stuck at tmux prompts like `[0/37]` or `jump forward`.

### 4.13 Worker init headless render-viewer

Adds a short-lived headless render viewer during tmux worker initialization, plus a periodic SIGWINCH/resize nudge.

Reason: unattended tmux worker panes can fail to flush a final idle frame during CLI startup, leaving dispatch stuck at `UNKNOWN`. The render-viewer gives the pane an attached client while the nudge forces TUI repaint until `StatusMonitor` can observe the settled state.

### 4.14 Worker init status recovery from UNKNOWN

Extends `StatusMonitor.get_status()` so polling callers recover when worker init has already produced a ready frame but cached status remains `UNKNOWN`:

- cached `UNKNOWN` with buffered output now gets fresh detection, matching the existing cached `PROCESSING` recovery path.
- pyte rendered-screen detection still has priority, but if it returns `UNKNOWN`, polling falls back to raw-buffer detection instead of treating lack of screen signal as final.

Reason: after 4.13 made unattended worker frames visible, a remaining edge case still left Claude planner init at `UNKNOWN`: the ready prompt existed in tmux/API output, but cached status had not been updated. Live validation after reinstall/restart showed planner `89e1b022` transition `unknown → completed`, `wait_until_status` reached `completed`, and the terminal was created successfully.

### 4.15 Durable worker token usage context

The integration now persists one row for every completed `run_agent_step` attempt before the terminal is torn down. Each row contains the estimated input/output/total tokens, provider, agent, model, effort, run/step identity, timestamp, and optional progress/artifact path.

Records remain queryable after terminal deletion through `GET /token-usage`, filtered by `terminal_id`, `run_id`, or `step_id`. A workflow step can set `progress` to an artifact path such as `.cao/worker-results/20260713T010600Z-v0.7.0-slice7-admin-reset-plan-review-r2-reviewer.md`; if omitted, CAO infers a matching `.cao/worker-results/...` path from the worker prompt or final response.

## Deferred / Proposed Package Work

### 4.8 Agy handoff terminal retention (deferred)

Branch retained:

```text
custom/4.8-agy-handoff-terminal-retention
```

The branch contains `ace213f fix(handoff): keep agy terminals after success`, but that change is not part of the current integration branch.

Reason for deferral: disabling teardown for every `antigravity_cli` handoff preserves debug visibility, but completed agy worker terminals then remain open and can confuse later developer/reviewer handoff management. The branch is useful evidence, not a merge-ready production behavior.

### 4.9 + 4.10 Agy handoff reliability (CAO-Tailscale profile-only)

Implemented outside this package repo in `/Users/alex/Developer/CAO-Tailscale` at commit `6190f52`.

The package repo has no 4.9/4.10 source branch. The change lives in regenerated CAO-Tailscale worker/supervisor profiles and should be maintained there:

- Supervisor artifact-as-truth guards: the required artifact path is the proof of completion; weak signals such as `No snapshot found` or `antigravity_cli N/A` are not enough to declare a worker dead.
- Bounded re-dispatch: missing artifact re-dispatches under the existing cap, then halts or reroutes instead of spawning duplicates.
- Agy long-running command hardening: wait for commands to finish, inspect result, write artifact, then return.
- Large DB-backed work should be routed to codex/claude when agy context stability is a risk.

4.8's terminal-retention approach is intentionally not adopted.

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
uv run pytest test/api/test_terminals.py -k 'WebSocket'
uv run black --check src/cli_agent_orchestrator/providers/antigravity_cli.py test/providers/test_antigravity_cli_unit.py src/cli_agent_orchestrator/providers/codex.py src/cli_agent_orchestrator/providers/claude_code.py src/cli_agent_orchestrator/models/agent_profile.py test/providers/test_claude_code_unit.py src/cli_agent_orchestrator/services/status_monitor.py test/services/test_status_monitor.py test/services/test_agent_step.py src/cli_agent_orchestrator/api/main.py test/api/test_terminals.py src/cli_agent_orchestrator/services/render_viewer.py src/cli_agent_orchestrator/services/terminal_service.py
uv run isort --check-only src/cli_agent_orchestrator/providers/antigravity_cli.py test/providers/test_antigravity_cli_unit.py src/cli_agent_orchestrator/providers/codex.py src/cli_agent_orchestrator/providers/claude_code.py src/cli_agent_orchestrator/models/agent_profile.py test/providers/test_claude_code_unit.py src/cli_agent_orchestrator/services/status_monitor.py test/services/test_status_monitor.py test/services/test_agent_step.py src/cli_agent_orchestrator/api/main.py test/api/test_terminals.py src/cli_agent_orchestrator/services/render_viewer.py src/cli_agent_orchestrator/services/terminal_service.py
npm --prefix web run build
npm --prefix web test
```

CAO-Tailscale 9-worker validation should be run in that repo, not here.
