# CAO Customizations Progress

> Current clean integration branch: `cao-tailscale-integration` (fixed name — the deployment target that CAO-Tailscale's bootstrap installs; rebuilt onto the latest fork-synced main each cycle, so the name never changes even though the base SHA does).
> Base: `origin/main` at `deebf65` (`fix(ci): sync devcontainer feature version with pyproject.toml on release (#419)`). Previous bases: `84d79ff`, `29f175c`, `d971298`, `4dc8bf7`, `25422d7`, `b0d313e`, `5dcf319`, `33c593d`, `f369068`, `0214f23`, `462fa2f`.
> Latest rebuild: 2026-07-12 after fork sync `84d79ff..deebf65`; upstream added bundled `cao-mcp-server` command resolution, release metadata, and CI/dependency updates. Provider overlap was reviewed and merged with customization behavior preserved. Previous integration tip was `8c7416c`.

## Current Decision

- 4.2 is no longer local customization work. Antigravity CLI provider was merged upstream in `086e61a` / awslabs#323.
- 4.5 is not in this repo. The 9-worker model selection work belongs to `/Users/alex/Developer/CAO-Tailscale` and has already been implemented there.
- This repo now carries package-level customizations 4.1, 4.3, 4.4, 4.6, 4.7, 4.11, 4.12, 4.13, 4.14, and 4.15.
- Token usage 4.17.1–4.17.5 is the current successor series: standalone page, query completeness, provider evidence contract, Codex/Claude structured native adapters, durable recovery, and token-specific UX. Interactive execution remains estimate-only.
- 4.8 was investigated and implemented on its own branch, but was reverted from the integration branch. Keep the branch for reference; do not merge it until the cleanup behavior is redesigned.
- 4.9 and 4.10 were merged into a single **profile-only** version and implemented in `/Users/alex/Developer/CAO-Tailscale` (workers/supervisor profiles), not in this package repo. 4.8 is explicitly not adopted by that version.

## Branch Model

| Item | Branch | Base | Commit | Status |
|---|---|---|---|---|
| 4.1 Codex pyte status | `custom/4.1-codex-pyte-status` | `deebf65` | `b6a6c92` | Done; synced with upstream MCP resolution |
| 4.2 Antigravity provider | upstream `main` | `086e61a` | `086e61a` | Upstream, no local branch |
| 4.3 Claude effort | `custom/4.3-claude-effort` | `deebf65` | `92d1dcc` | Done; synced with upstream MCP resolution |
| 4.4 Agy workspace trust | `custom/4.4-agy-workspace-trust` | `deebf65` | `02aa910` | Done; synced with upstream MCP resolution |
| 4.5 9-worker selection | CAO-Tailscale repo | n/a | n/a | Done outside this repo |
| 4.6 Status turn-boundary guard | `custom/4.6-status-turn-boundary` | `deebf65` | `c63ba73` | Done |
| 4.7 Web terminal clipboard shortcuts | `custom/4.7-web-terminal-clipboard` | `deebf65` | `e805924` | Done; includes HTTP fallback/focus fixes |
| 4.8 Agy handoff terminal retention | `custom/4.8-agy-handoff-terminal-retention` | `462fa2f` | `56500e4` (doc) / `ace213f` (code) | Deferred, not in integration; superseded by 4.9 (see `CAO-4.8-AGY-HANDOFF-TERMINAL-RETENTION.md` on that branch) |
| 4.9 + 4.10 Agy handoff reliability (merged, profile-only) | CAO-Tailscale repo | n/a | CAO-Tailscale `6190f52` | Done outside this repo (profile-only); see `CAO-Tailscale/CUSTOMIZATIONS.md` §三 |
| 4.11 Web terminal viewer isolation | `custom/4.11-web-terminal-viewer-isolation` | `deebf65` | `e75dcfd` | Done |
| 4.12 Web terminal PageUp/PageDown scroll | `custom/4.7 + 4.11` | 4.7 + 4.11 | `eb65a02` | Done; resolved dependency conflict, keeps mouse-off and viewer sizing |
| 4.13 Worker init headless render-viewer | `custom/4.13-worker-init-headless-viewer` | `deebf65` | `c63ba38` | Done; viewer sizing is session-scoped |
| 4.14 Worker init status recovery from UNKNOWN | `custom/4.14-worker-init-status-recovery` | `custom/4.6-status-turn-boundary` | `0bfb7d7` | Done |
| 4.15 Durable worker token usage context | `custom/4.15-worker-token-usage` | `c428319` | `ec5b396` | Done; merged into integration with `--no-ff` |
| 4.17.1–4.17.5 Worker token usage successor series | `custom/4.17.5-token-usage-recovery-ux` | `custom/4.17.4-token-usage-native-adapters` | current owner HEAD | Done in owner branch; 4.16 tab superseded, Codex/Claude structured usage enabled, F1/F2 recovery and UX validated; ready for integration review |
| Integration | `cao-tailscale-integration` | `deebf65` | `ea9320c` | 4.15 merged and documented after 2026-07-12 rebuild |

## 2026-07-12 Sync Record

- Upstream range: `84d79ff..deebf65`.
- `024638a` adds `utils/mcp_resolution.py` and applies PATH-independent bundled `cao-mcp-server` resolution to Codex, Claude, Agy, and other providers. This partially overlaps the 4.1/4.3/4.4 provider files, but is behavior-compatible: screen detection, Claude `--effort`, and workspace trust remain present.
- `391b878` / `72b8ed7` update the v2.3.0 changelog and release metadata; `deebf65` aligns the devcontainer feature version with `pyproject.toml`. These areas do not overlap package customizations.
- Upstream also removes the integration-only customization documents. They were restored from the previous integration tip `8c7416c` and updated in this rebuild commit.
- Custom branch merges were clean except for 4.12's dependency merge with 4.11 in `api/main.py`; the conflict was resolved in `eb65a02` by retaining both session-scoped tmux `mouse off` and `window-size latest` behavior. Integration merges were clean.

## Change Summary

### 4.1 Codex pyte status

- File: `src/cli_agent_orchestrator/providers/codex.py`
- Adds `List` import.
- Adds `CodexProvider.supports_screen_detection = True`.
- Adds `get_status_from_screen()` so Codex status can be detected from pyte-rendered screen rows.
- Purpose: prevent Codex TUI progress / idle footer redraws from being misread from raw pipe-pane output.

### 4.2 Antigravity CLI provider

- No local work.
- Upstream `086e61a` already adds the official `antigravity_cli` provider, enum, manager wiring, docs, fixtures, and tests.
- Do not merge old local branches `feat/antigravity-provider`, `feat/agy-workspace-trust`, or `feat/all-customizations` into modern main; they were based on older upstream state and can reverse upstream #323 work.

### 4.3 Claude Code effort

- Files:
  - `src/cli_agent_orchestrator/models/agent_profile.py`
  - `src/cli_agent_orchestrator/providers/claude_code.py`
  - `test/providers/test_claude_code_unit.py`
- Adds `AgentProfile.effort: Optional[str] = None`.
- Passes `--effort <value>` to Claude Code after `--model`.
- Only emits `--effort` when the value is a non-empty string, so legacy/mocked profiles do not pass non-string values into `shlex.join()`.

### 4.4 Antigravity workspace trust

- Files:
  - `src/cli_agent_orchestrator/providers/antigravity_cli.py`
  - `test/providers/test_antigravity_cli_unit.py`
- Before launching `agy`, resolves the pane working directory.
- Adds that exact path to `~/.gemini/antigravity-cli/settings.json` under `trustedWorkspaces`.
- During cleanup, removes only the path this provider instance added.
- Existing user-trusted workspaces are preserved.
- Upstream `d34fd26` (#364, fork sync to `b0d313e`) added its own reactive fix for the
  same hang: `_handle_startup_dialog()` polls for the trust picker after `send_keys` and
  sends `Enter` to accept it. It merges cleanly alongside this proactive fix (different,
  non-overlapping call sites in `initialize()`) and now acts as a harmless fallback if the
  proactive settings-file write ever fails.

### 4.5 9-worker selection

- Not part of `cli-agent-orchestrator`.
- Implemented in `/Users/alex/Developer/CAO-Tailscale`.
- Relevant files there:
  - `scripts/gen-workers.sh`
  - `scripts/select-workers.sh`
  - `start-all.sh`
- Worker set:
  - `planner_claude`, `planner_codex`, `planner_gemini`
  - `developer_claude`, `developer_codex`, `developer_gemini`
  - `reviewer_claude`, `reviewer_codex`, `reviewer_gemini`

### 4.6 Status turn-boundary guard

- Files:
  - `src/cli_agent_orchestrator/services/status_monitor.py`
  - `test/services/test_status_monitor.py`
- When CAO sends new input to a terminal whose cached status is `IDLE` or `COMPLETED`, `StatusMonitor.get_status()` now masks that stale ready status as `PROCESSING`.
- The ready status is accepted again only after new terminal output arrives and a short stale-frame grace window has elapsed.
- This fixes premature handoff/completion checks that can happen immediately after a new prompt is sent, before the target CLI has rendered its next working frame.
- This is a global status lifecycle fix, not a Codex-provider screen-detection fix. It complements 4.1.

### 4.7 Web terminal clipboard shortcuts

- File: `web/src/components/TerminalView.tsx`
- Adds explicit browser clipboard handling for the xterm terminal view:
  - `Ctrl+V` / `Ctrl+Shift+V` paste text from the browser clipboard into the terminal websocket instead of leaking the key chord into the agent TUI.
  - DOM `paste` events read `text/plain` from `clipboardData`, which is important for Windows Chrome over a LAN/Tailscale HTTP Web UI where `navigator.clipboard.readText()` can be restricted.
  - `Ctrl+C` copies the current terminal selection when text is selected; without a selection it still passes through so terminal interrupt behavior is preserved.
- Purpose: when the Web UI runs on macOS but is opened from Windows Chrome, the agent TUI can otherwise receive `Ctrl+V` and interpret it as an image-paste command, producing `Failed to paste image: no image on clipboard` instead of pasting text.
- Follow-up: capture-phase `keydown` handling blocks `Ctrl+V` from reaching xterm/pty while still allowing the browser `paste` event to provide `text/plain`; this covers non-localhost LAN/Tailscale clients where async clipboard reads may be unavailable.

### 4.8 Agy handoff terminal retention (deferred)

- Branch retained: `custom/4.8-agy-handoff-terminal-retention`
- Commit retained on that branch: `ace213f`
- Not included in integration branch `cao-tailscale-integration`.
- Original purpose: avoid losing the agy worker terminal after a handoff return by disabling automatic teardown for `antigravity_cli`.
- Decision: reverted from integration because it makes completed agy handoff terminals remain open, which can confuse later developer/reviewer dispatch and cleanup behavior.
- Keep the branch for reference only. Do not merge 4.8 as-is.
- Per-branch doc: `CAO-4.8-AGY-HANDOFF-TERMINAL-RETENTION.md` on `custom/4.8-agy-handoff-terminal-retention` (`56500e4`) explains the change, the revert, and the supersession by 4.9.

### 4.9 + 4.10 Agy handoff reliability (merged, implemented as profile-only)

- Record lives in CAO-Tailscale (no branch in this package repo, same convention as 4.5): `CAO-Tailscale/CUSTOMIZATIONS.md` §三 + `CAO-Tailscale/4.9-agy-handoff-reliability-HANDOFF.md`; implementation commit CAO-Tailscale `6190f52`.
- **Status: implemented in `/Users/alex/Developer/CAO-Tailscale` as a single profile-only change. Not part of this package repo.** 4.9 (supervisor premature-return guard) and 4.10 (agy prompt/long-running hardening) were merged into one version per `CAO-Tailscale/4.9-agy-handoff-reliability-HANDOFF.md`.
- **4.8 is NOT adopted.** This version deliberately does not use 4.8's `teardown=False`; it works with the normal "handoff done → terminal deleted" behavior instead of fighting it.
- **Scope: profile layer only** — `CAO-Tailscale/workers/{developer,code_supervisor}.md` regenerated via `scripts/gen-workers.sh` into the 9 worker + 3 supervisor profiles. No changes to this CAO package source, `server.py`, or `agent_step.py`; no server restart required (profiles are read fresh on each worker spawn).
- **Root issue (evidence-backed, not a CAO false positive):** agy ends its turn before the task is actually done — it returns "I am waiting…" / "running in the background" and exits the CLI. CAO then correctly sees idle → COMPLETED → standard teardown. So the guarantee shifts from controlling the *process* (can't stop agy yielding) to securing the *result* (artifact-as-truth + bounded re-dispatch).
- **4.10 developer change** (`workers/developer.md`, "Long-Running Commands — Wait, Never Yield Mid-Run"): run verification/build/DB commands synchronously and block until exit; never end the turn while a command runs; write the required artifact before returning; **finish the entire task within a single turn — never split work into a later turn, background job, async task, or task queue and then yield.**
- **4.9 supervisor change** (`workers/code_supervisor.md`, "Agy Handoff Reliability — Artifact-as-Truth Guards (4.9)"), six guards:
  1. The assigned artifact path is the only proof of completion; a returned message alone is never success.
  2. Missing artifact → re-dispatch the same task under the existing hard cap (max 2 re-dispatches / 3 attempts total); on cap, halt and report or re-route to `developer_codex` / `developer_claude`.
  3. Weak signals are not proof a worker is dead: `cao session status … N/A` and `cao terminal restore … No snapshot found` do not mean dead — check the artifact path and the live tmux window / terminal registry first.
  4. No duplicate workers for the same task/artifact when a live worker already owns it.
  5. Cut handoff tasks small and single-artifact-scoped (most effective prevention of agy mid-run yield).
  6. Route large / long-running DB-backed work to codex or claude (the only fix for agy context truncation: `CHECKPOINT 0` → empty response → idle).
- **Acknowledged limits:** agy may still yield early or hit context truncation; this version bounds the damage and guarantees the result via the supervisor, rather than eliminating the behavior.

### 4.11 Web terminal viewer isolation

- Branch: `custom/4.11-web-terminal-viewer-isolation`
- Files:
  - `src/cli_agent_orchestrator/api/main.py`
  - `test/api/test_terminals.py`
- Root-cause note: `WEB-UI-TERMINAL-SYNC-ROOT-CAUSE.md`
- Fixes the Web UI live terminal viewer using `tmux attach-session -t <session>:<window>` directly against the shared CAO session.
- Root cause: a tmux session has one shared current window. Opening terminal B in one Web UI viewer selected window B for every client attached to the same session, including another browser window and a local macOS Terminal `tmux attach`.
- New behavior: each WebSocket connection creates a short-lived grouped viewer session (`tmux new-session -d -t <cao-session> -s caoview_<id>`) and attaches to `<viewer-session>:<window>`.
- Grouped sessions share the same panes/windows, so input still reaches the real agent pane, but each viewer has its own current-window pointer. Closing the WebSocket tears down only the per-connection viewer session.
- Validation adds a regression test that asserts WebSocket attach targets the isolated viewer session, not the shared CAO session.

### 4.12 Web terminal PageUp/PageDown scroll

- Branch: `custom/4.12-web-terminal-page-scroll`
- Base: `custom/4.7-web-terminal-clipboard` plus `custom/4.11-web-terminal-viewer-isolation`.
- Files:
  - `web/src/components/TerminalView.tsx`
  - `src/cli_agent_orchestrator/api/main.py`
  - `test/api/test_terminals.py`
- Intercepts unmodified `PageUp` / `PageDown` in the Web UI terminal viewer and sends a WebSocket `scroll` message instead of sending those keys to the agent pane.
- The backend applies the scroll to the per-connection tmux viewer session from 4.11:
  - `PageUp` → `tmux copy-mode -u -t <viewer-session>:<window>`
  - `PageDown` → `tmux send-keys -t <viewer-session>:<window> -X page-down`
- Before forwarding normal terminal input, the backend sends `tmux send-keys -X cancel` to the isolated viewer session so a PageUp/PageDown scroll does not leave the viewer stuck in tmux copy-mode (`[0/37]`, `jump forward`) and block typing.
- Purpose: Codex and Antigravity CLI TUIs run in terminal modes where xterm local scrollback is not enough; they can consume PageUp/PageDown before browser scrolling happens. Scrolling the isolated tmux viewer session shows terminal history for all providers without sending PageUp/PageDown to the agent TUI or switching other viewers.

### 4.13 Worker init headless render-viewer

- Branch: `custom/4.13-worker-init-headless-viewer`
- Files:
  - `src/cli_agent_orchestrator/services/render_viewer.py`
  - `src/cli_agent_orchestrator/services/terminal_service.py`
- During tmux provider initialization, wraps `provider.initialize()` with a short-lived grouped headless viewer session.
- The viewer keeps the worker pane rendered while a resize/SIGWINCH nudge forces Ink-style TUIs to repaint their settled startup frame.
- Purpose: unattended worker panes can otherwise fail to flush shell/CLI idle frames into `pipe-pane`, leaving dispatch stuck at `UNKNOWN` until `provider_init_timeout`.
- Scope: tmux/pipe-pane backend only. Herdr/event-inbox backends bypass this path.

### 4.14 Worker init status recovery from UNKNOWN

- Branch: `custom/4.14-worker-init-status-recovery`
- Files:
  - `src/cli_agent_orchestrator/services/status_monitor.py`
  - `test/services/test_status_monitor.py`
- Extends the 4.6 status lifecycle guard for worker initialization:
  - If cached status is `UNKNOWN` and the rolling buffer has output, `StatusMonitor.get_status()` now performs fresh detection for polling callers such as `wait_until_status()`.
  - For providers using pyte rendered-screen detection, if screen detection returns `UNKNOWN`, polling falls back to raw-buffer detection instead of treating `UNKNOWN` as final.
- Purpose: after 4.13, the ready frame can be present in the buffer while the cached status remains `UNKNOWN` or pyte screen detection has no signal. Polling now recovers to `IDLE` / `COMPLETED` instead of timing out.
- Live validation: after reinstall/restart, planner `89e1b022` (`planner-7c8b`, Claude Opus 4.8 high) transitioned `unknown → completed`, `wait_until_status` reached `completed`, and the terminal was created successfully.

### 4.15 Durable worker token usage context

- Branch: `custom/4.15-worker-token-usage`
- Commit: `ec5b396`; merged into `cao-tailscale-integration` with `--no-ff`.
- Persists one usage record per completed worker attempt before terminal teardown.
- Records token estimates, provider, agent, model, effort, run/step identity, and optional progress/artifact path.
- `GET /token-usage` lists records after the terminal has been deleted; progress can be supplied explicitly or inferred from `.cao/worker-results/...` in the worker prompt/reply.

### 4.17.1–4.17.5 Worker token usage successor series

- 4.17.1 moved Token Usage to the isolated `token.html` entry and added the dashboard anchor/icon.
- 4.17.2 added authenticated page/summary endpoints with snapshot keyset pagination, repeated filters, null sentinels, and Load more.
- 4.17.3/4.17.4 added the nine-provider evidence inventory and strict Claude Code/Codex structured adapters. Native usage is sourced only from provider-owned structured stdout; interactive remains estimate-only.
- 4.17.5 F1 added an owner-only fsynced metadata spool with idempotent replay, quarantine, metrics, concurrent writer/flusher protection, and no prompt/response/session-log data.
- 4.17.5 F2 added validated custom dates, safe local artifact links, UTF-8 CSV export with formula mitigation, provenance split, attempt drill-down, and migration/API/no-data guidance. Changes remain token-specific and do not re-enter `App.tsx` state.

## Validation

Run on integration branch:

```bash
uv run pytest test/providers/test_antigravity_cli_unit.py test/providers/test_codex_provider_unit.py test/providers/test_claude_code_unit.py test/services/test_status_monitor.py test/services/test_agent_step.py
uv run pytest test/api/test_terminals.py -k 'WebSocket'
uv run black --check src/cli_agent_orchestrator/providers/antigravity_cli.py test/providers/test_antigravity_cli_unit.py src/cli_agent_orchestrator/providers/codex.py src/cli_agent_orchestrator/providers/claude_code.py src/cli_agent_orchestrator/models/agent_profile.py test/providers/test_claude_code_unit.py src/cli_agent_orchestrator/services/status_monitor.py test/services/test_status_monitor.py test/services/test_agent_step.py src/cli_agent_orchestrator/api/main.py test/api/test_terminals.py src/cli_agent_orchestrator/services/render_viewer.py src/cli_agent_orchestrator/services/terminal_service.py
uv run isort --check-only src/cli_agent_orchestrator/providers/antigravity_cli.py test/providers/test_antigravity_cli_unit.py src/cli_agent_orchestrator/providers/codex.py src/cli_agent_orchestrator/providers/claude_code.py src/cli_agent_orchestrator/models/agent_profile.py test/providers/test_claude_code_unit.py src/cli_agent_orchestrator/services/status_monitor.py test/services/test_status_monitor.py test/services/test_agent_step.py src/cli_agent_orchestrator/api/main.py test/api/test_terminals.py src/cli_agent_orchestrator/services/render_viewer.py src/cli_agent_orchestrator/services/terminal_service.py
npm --prefix web run build
npm --prefix web test
```

Latest validation for the 2026-07-12 `deebf65` rebuild:

- package/provider/status/FIFO tests: `339 passed`
- upstream MCP/install/profile regression tests: `79 passed`
- terminal WebSocket tests: `10 passed`
- `black --check`: passed
- `isort --check-only`: passed
- `npm --prefix web run build`: passed
- `npm --prefix web test`: `61 passed` (with existing jsdom/xterm canvas noise)

## Open Notes

- 4.5 should be maintained and tested in CAO-Tailscale, not here.
- 4.8 is intentionally deferred after revert. The branch is retained, but integration should not merge it as-is.
- `.cao/` review artifacts belong to investigation/fix branches and should not be carried into this integration branch.
- `ISSUES.md` in the original working tree is untracked and intentionally not included.
- `cao-tailscale-integration` is an integration branch. It is not customization item 4.7; numbered customization work should still live on a `custom/4.x-*` branch and then be merged into a fresh integration branch.
