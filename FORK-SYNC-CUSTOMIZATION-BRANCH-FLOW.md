# Fork Sync Customization Branch Flow

Use this flow after GitHub fork sync updates `main`.

## Preferred Flow

1. Fork sync on GitHub updates `main`.
2. Fetch latest main locally.
3. Merge latest main into each customization branch.
4. Create a new integration branch from latest main.
5. Merge customization branches into the integration branch.
6. Test the integration branch.

### Permanent Fix Ownership Rule

Any package-code hotfix found after a rebuild must be committed first to the
owning `custom/4.x-*` branch, then merged into integration. Do not leave a
runtime fix only on `cao-tailscale-integration`: its fixed-name force rebuild
drops it on the next fork sync. For example, clipboard fixes belong to 4.7,
viewer scrolling/mouse fixes to 4.12, and init render-viewer fixes to 4.13.

## Required Post-Sync Overlap Check

After every fork sync to `main`, inspect the new upstream commits before merging or rebuilding customization branches. The goal is to catch upstream changes that already fix, partially overlap, or conflict with our local customizations.

1. Identify the new upstream range:

```bash
git fetch origin main
git log --oneline <previous-main-sha>..origin/main
git diff --name-status <previous-main-sha>..origin/main
```

If the previous base is not known, compare from the merge base of the current integration branch:

```bash
git merge-base HEAD origin/main
git log --oneline "$(git merge-base HEAD origin/main)"..origin/main
git diff --name-status "$(git merge-base HEAD origin/main)"..origin/main
```

2. Cross-check the new commits against the customization inventory in `CAO-CUSTOMIZATIONS-PROGRESS.md` and `CAO-Tailscale-CHANGES-SUMMARY.md`. Pay special attention to:

- 4.1 Codex pyte status detection: `src/cli_agent_orchestrator/providers/codex.py`
- 4.3 Claude effort: `src/cli_agent_orchestrator/models/agent_profile.py`, `src/cli_agent_orchestrator/providers/claude_code.py`
- 4.4 Agy workspace trust: `src/cli_agent_orchestrator/providers/antigravity_cli.py`
- 4.6 Status turn-boundary guard: `src/cli_agent_orchestrator/services/status_monitor.py`
- 4.7 Web terminal clipboard shortcuts: `web/src/components/TerminalView.tsx`
- 4.8 Agy handoff terminal retention: deferred branch only; do not merge as-is
- 4.9/4.10 agy handoff reliability (merged, profile-only): implemented in CAO-Tailscale `workers/{developer,code_supervisor}.md`, NOT in this package. No package source file to overlap-check; but watch upstream changes to MCP handoff, terminal cleanup/teardown, and provider status detection (`antigravity_cli.py`, `agent_step.py`, `server.py` `_handoff_impl`), since this version relies on the standard "agy idle → COMPLETED → teardown" behavior staying intact
- 4.11 Web terminal viewer isolation: `src/cli_agent_orchestrator/api/main.py`, `test/api/test_terminals.py`
- 4.12 Web terminal PageUp/PageDown scroll: `web/src/components/TerminalView.tsx`, `src/cli_agent_orchestrator/api/main.py`, `test/api/test_terminals.py`; depends on 4.7 key handling and 4.11 isolated viewer sessions
- 4.14 Worker init status recovery from UNKNOWN: `src/cli_agent_orchestrator/services/status_monitor.py`, `test/services/test_status_monitor.py`; depends on the 4.6 status turn-boundary guard and complements 4.13 worker init rendering
- Shared lifecycle areas: MCP handoff, terminal cleanup, provider init, status monitoring, profile schema, Web UI terminal input/clipboard handling, and tool timeout behavior

3. Classify each relevant upstream change before continuing:

- `No overlap`: safe to merge into customization branches.
- `Upstream fixed same issue`: decide whether to drop or shrink our local patch before merging.
- `Partial overlap`: review manually; do not assume a clean git merge means behavior is safe.
- `Conflict / behavior change`: pause integration until the behavior is tested. This includes handoff timeout/cleanup changes, status lifecycle changes, provider startup changes, and profile schema changes.

Do not rely only on textual merge conflicts. A clean merge can still duplicate logic, undo a guard, or make a local patch obsolete.

## Commands

Fetch latest main:

```bash
git fetch origin main
```

Update each package-level customization branch:

```bash
git switch custom/4.1-codex-pyte-status
git merge origin/main

git switch custom/4.3-claude-effort
git merge origin/main

git switch custom/4.4-agy-workspace-trust
git merge origin/main

git switch custom/4.6-status-turn-boundary
git merge origin/main

git switch custom/4.7-web-terminal-clipboard
git merge origin/main

git switch custom/4.11-web-terminal-viewer-isolation
git merge origin/main

git switch custom/4.13-worker-init-headless-viewer
git merge origin/main

# 4.14 depends on the 4.6 StatusMonitor lifecycle guard.
git switch custom/4.14-worker-init-status-recovery
git merge custom/4.6-status-turn-boundary

# 4.12 depends on both 4.7 and 4.11: it extends TerminalView keyboard handling
# and sends scroll commands to the isolated tmux viewer session.
git switch custom/4.12-web-terminal-page-scroll
git merge custom/4.7-web-terminal-clipboard
git merge custom/4.11-web-terminal-viewer-isolation
```

For this repo, there is no `custom/4.5` package branch. 4.5 is the 9-worker deployment customization in `/Users/alex/Developer/CAO-Tailscale`.

Rebuild the fixed-name integration branch from latest main. The deployment target is always
`cao-tailscale-integration` (a stable name so CAO-Tailscale's bootstrap/`CAO_BRANCH` never has
to change); recreate it each sync rather than minting a new SHA-named branch:

```bash
# overwrite the fixed deployment branch onto the freshly-synced main
git branch -f cao-tailscale-integration origin/main
git switch cao-tailscale-integration
# ⚠️ CRITICAL: `git branch -f ... origin/main` + switch sets this branch's UPSTREAM to
# origin/main. If left as-is, a later `git push origin cao-tailscale-integration` can ALSO
# update remote `main` to your customization commits — diverging your fork from upstream and
# breaking GitHub "Sync fork". Immediately repoint the upstream back to the branch itself:
git branch --set-upstream-to=origin/cao-tailscale-integration cao-tailscale-integration
git config push.default current   # extra safety: never push to a differently-named upstream
# (optionally also snapshot a SHA-named copy for history: git branch feat/customizations-<main-sha>)
```

> If remote `main` ever gets clobbered this way, restore it with:
> `git push --force origin <correct-main-sha>:refs/heads/main` (the correct SHA is the
> freshly fork-synced upstream commit, e.g. `0214f23` for this cycle).

Merge package customization branches:

```bash
git merge --no-ff custom/4.1-codex-pyte-status
git merge --no-ff custom/4.3-claude-effort
git merge --no-ff custom/4.4-agy-workspace-trust
git merge --no-ff custom/4.6-status-turn-boundary
git merge --no-ff custom/4.7-web-terminal-clipboard
git merge --no-ff custom/4.11-web-terminal-viewer-isolation
git merge --no-ff custom/4.12-web-terminal-page-scroll
git merge --no-ff custom/4.13-worker-init-headless-viewer
git merge --no-ff custom/4.14-worker-init-status-recovery
```

Do not merge old local 4.2 branches. Antigravity CLI provider is upstream in `086e61a`.

Do not merge `custom/4.8-agy-handoff-terminal-retention` into integration as-is. That branch is retained for investigation only because it disables agy handoff teardown and leaves completed worker terminals open. Revisit it only after designing a conditional cleanup strategy.

There is no `custom/4.9` package branch. Like 4.5, the merged 4.9+4.10 work is profile-only in CAO-Tailscale (`6190f52`) with no package source change, so it is documented (`CAO-Tailscale/CUSTOMIZATIONS.md` §三) rather than branched here. The integration branch's `CAO-CUSTOMIZATIONS-PROGRESS.md` carries the summary.

## Conflict Policy

- If a conflict happens while merging `origin/main` into a customization branch, resolve it inside that customization branch.
- If a conflict happens while merging custom branches into integration, first ask whether the fix belongs in one custom branch. Prefer fixing there, then recreate or redo the integration merge.
- Integration branch should mainly be merge commits plus documentation.

## Validation

Run on the integration branch:

```bash
uv run pytest test/providers/test_antigravity_cli_unit.py test/providers/test_codex_provider_unit.py test/providers/test_claude_code_unit.py test/services/test_status_monitor.py test/services/test_agent_step.py
uv run pytest test/api/test_terminals.py -k 'WebSocket'
uv run black --check src/cli_agent_orchestrator/providers/antigravity_cli.py test/providers/test_antigravity_cli_unit.py src/cli_agent_orchestrator/providers/codex.py src/cli_agent_orchestrator/providers/claude_code.py src/cli_agent_orchestrator/models/agent_profile.py test/providers/test_claude_code_unit.py src/cli_agent_orchestrator/services/status_monitor.py test/services/test_status_monitor.py test/services/test_agent_step.py src/cli_agent_orchestrator/api/main.py test/api/test_terminals.py src/cli_agent_orchestrator/services/render_viewer.py src/cli_agent_orchestrator/services/terminal_service.py
uv run isort --check-only src/cli_agent_orchestrator/providers/antigravity_cli.py test/providers/test_antigravity_cli_unit.py src/cli_agent_orchestrator/providers/codex.py src/cli_agent_orchestrator/providers/claude_code.py src/cli_agent_orchestrator/models/agent_profile.py test/providers/test_claude_code_unit.py src/cli_agent_orchestrator/services/status_monitor.py test/services/test_status_monitor.py test/services/test_agent_step.py src/cli_agent_orchestrator/api/main.py test/api/test_terminals.py src/cli_agent_orchestrator/services/render_viewer.py src/cli_agent_orchestrator/services/terminal_service.py
npm --prefix web run build
npm --prefix web test
```

Re-index code graph after rebuild so codebase-memory-mcp workers (planner/developer/reviewer)
see the updated source, not a stale snapshot from the previous integration tip:

```bash
codebase-memory-mcp cli index_repository '{"repo_path":"/Users/alex/Developer/cli-agent-orchestrator"}'
```

This is a background re-index; it does not affect git state. Run it once after the merge +
doc commit, before triggering any agent session that may call `codebase-memory-mcp`.

Final inspection:

```bash
git log --oneline --decorate origin/main..HEAD
git diff --stat origin/main..HEAD
git status --short --branch
```

## Post-Rebuild Fix (2026-07-07)

After the 2026-07-06 rebuild, Ctrl+C/Ctrl+V stopped working in Web UI terminals when
accessed over Tailscale. Root cause was in `custom/4.7-web-terminal-clipboard`'s
`TerminalView.tsx`, not the rebuild process itself:

- `term.onSelectionChange` called `navigator.clipboard.writeText(...)` without optional
  chaining. `navigator.clipboard` is `undefined` outside a secure context (Tailscale
  access without HTTPS), so this threw on every selection change.
- The Ctrl+C handler copied-and-swallowed (`return false`) whenever `term.getSelection()`
  was non-empty, but never cleared the selection afterward — so once you'd selected any
  text, every subsequent Ctrl+C kept "copying" instead of sending SIGINT, even after you
  meant to interrupt a running process.

Fixed on `custom/4.7-web-terminal-clipboard` (`73bebcd`): guarded the `onSelectionChange`
clipboard call with `?.`, and added `term.clearSelection()` after the Ctrl+C copy branch.
Merged into `cao-tailscale-integration` with `--no-ff`. Validation: `test_terminals.py -k
WebSocket` (10 passed), `npm --prefix web test` (56 passed), `npm --prefix web run build`
(passed).

## Post-Rebuild Fix (2026-07-10)

After the 2026-07-10 rebuild, Ctrl+C/Ctrl+V stopped working specifically in Codex and
Antigravity (agy) terminals in the Web UI (Claude terminal remained unaffected). Root
cause: Codex runs with `--no-alt-screen` to keep output in normal scrollback for status
detection. Running outside alt-screen means tmux's default mouse wheel bindings
(WheelUpPane/WheelDownPane) automatically enter copy-mode. Once in copy-mode, **all**
keys — not just navigation keys — become copy-mode commands, so Ctrl+C and Ctrl+V get
misinterpreted. The 4.12 scroll handlers call `_cancel_tmux_viewer_copy_mode` before
forwarding input, but were silently failing with no log visibility.

Fixed on `cao-tailscale-integration` (`3c85f19`):
1. Disable tmux mouse wheel bindings (WheelUpPane/WheelDownPane) on viewer sessions when
   they are created (`api/main.py:1960-1969`). PageUp/PageDown scroll is handled via
   WebSocket (4.12 custom), so mouse scroll is not needed and was causing accidental
   copy-mode entry specifically for Codex's non-alt-screen mode.
2. Add return-code checking and error logging to `_cancel_tmux_viewer_copy_mode`
   (`api/main.py:572-587`) so failed cancel attempts are visible (previously silently
   ignored via `check=False`).

Validation: `pytest test/api/test_terminals.py -k WebSocket` (10 passed), provider/status
tests (336 passed), `npm --prefix web test` (61 passed), `npm --prefix web run build`
(passed).

## Current Clean Rebuild (2026-07-12)

The latest clean rebuild was run after fork sync moved `origin/main` from
`84d79ff` to `deebf65`. The previous integration tip was `8c7416c`; the fixed
integration branch was recreated from `deebf65` and finished at `ed7c246`.

It used these customization branch tips:

- `custom/4.1-codex-pyte-status` at `b6a6c92`
- `custom/4.3-claude-effort` at `92d1dcc`
- `custom/4.4-agy-workspace-trust` at `02aa910`
- `custom/4.6-status-turn-boundary` at `c63ba73`
- `custom/4.7-web-terminal-clipboard` at `e805924`
- `custom/4.11-web-terminal-viewer-isolation` at `e75dcfd`
- `custom/4.12-web-terminal-page-scroll` at `eb65a02`
- `custom/4.13-worker-init-headless-viewer` at `c63ba38`
- `custom/4.14-worker-init-status-recovery` at `0bfb7d7`

Upstream range `84d79ff..deebf65`:

- `024638a` added `utils/mcp_resolution.py` and wired PATH-independent bundled
  `cao-mcp-server` resolution into Codex, Claude, Agy, and other providers.
- `391b878` and `72b8ed7` updated v2.3.0 changelog/release metadata.
- `deebf65` aligned the devcontainer feature version with `pyproject.toml`.

Overlap classification: **partial-area overlap, behavior-compatible**. The MCP
resolver touches the same provider files as 4.1/4.3/4.4, but the merges retain
Codex rendered-screen status detection, Claude `--effort`, and Agy workspace
trust. The 4.12 dependency merge with 4.11 had one manual conflict in
`api/main.py`; `eb65a02` retains both session-scoped tmux `mouse off` and
browser-driven `window-size latest`. All integration merges completed cleanly.

Upstream deleted the integration-only customization documents, so the flow,
progress, change-summary, and current investigation report were restored from
`8c7416c` and updated in the post-rebuild documentation commit.

Validation for this rebuild passed on 2026-07-12:

- package/provider/status/FIFO tests: `339 passed`
- upstream MCP/install/profile regression tests: `79 passed`
- terminal WebSocket tests: `10 passed`
- `black --check`: passed
- `isort --check-only`: passed
- `npm --prefix web run build`: passed
- `npm --prefix web test`: `61 passed` (with existing jsdom/xterm canvas noise)

## Previous Current Clean Rebuild

The latest clean rebuild was run on 2026-07-10 after fork sync moved
`origin/main` from `d3fab72` to `29f175c`. It used:

- `custom/4.1-codex-pyte-status` at `0aac572`
- `custom/4.3-claude-effort` at `f9ee8d4`
- `custom/4.4-agy-workspace-trust` at `0a2cb75`
- `custom/4.6-status-turn-boundary` at `af6d01c`
- `custom/4.7-web-terminal-clipboard` at `2ed065c`
- `custom/4.11-web-terminal-viewer-isolation` at `f8ae2db`
- `custom/4.12-web-terminal-page-scroll` at `39f5578`
- `custom/4.13-worker-init-headless-viewer` at `5b4d1dc`
- `custom/4.14-worker-init-status-recovery` at `97fa945`
- integration branch `cao-tailscale-integration` at `6ef7a99`; base `29f175c`; previous
  integration tip before rebuild was `357b8e8`

Upstream range `d3fab72..29f175c`:

- `29f175c` `fix(claude_code): background task ("✻ Waiting for N workflows") no longer reads as COMPLETED (fixes #392) (#393)`
- `9b2304b` `feat(workflow): script-tier execution engine — U4 runner (#312) (#396)`
- `e8cd7f6` `feat(settings): enable/disable an agent-profile directory (closes #280, #281) (#368)`
- `4b3e344` `build(deps): bump ws from 8.20.0 to 8.21.0 in /web (#398)`
- `b1a4eb8` `feat(examples): fleet web panel + live console (#366)`

Overlap check classified this as **partial-area overlap, behavior-compatible**:

- `src/cli_agent_orchestrator/providers/claude_code.py`: upstream fixed GH #392 by treating
  `✻ Waiting for N dynamic workflow(s) to finish` as PROCESSING rather than COMPLETED. Our
  4.3 Claude effort customization touches the same file but only profile/config plumbing
  (`effort` field and provider option propagation). The merge was clean and both behaviors are
  present.
- `src/cli_agent_orchestrator/api/main.py`: upstream added agent-directory enable/disable
  settings endpoints plus run-step script-runner hooks (`disabled_dirs`, generation fence,
  `on_terminal_created`). Our 4.11/4.12 customizations modify terminal WebSocket/viewer
  isolation and tmux scroll handling in different sections. Merged cleanly with both sets of
  behavior intact.
- `src/cli_agent_orchestrator/services/agent_step.py`: upstream added the optional
  `on_terminal_created` callback for script-runner orphan reconciliation. This touches the
  shared lifecycle area called out in the overlap checklist, but it does not change our 4.11,
  4.12, 4.13, or 4.14 logic paths. Merge was clean; no behavior conflict observed in
  validation.
- `web/src/components/SettingsPanel.tsx` and `test/api/test_settings_api.py`: upstream added
  UI/API coverage for disabled agent-profile directories. Our local Web UI customizations are
  in `TerminalView.tsx`, not the settings panel. No overlap.
- `test/providers/test_claude_code_unit.py`, `test/services/test_agent_step.py`: upstream
  added coverage for the new Claude background-wait fix and script-runner callback path. These
  are complementary to our local provider/status tests and merged cleanly.

Validation for this rebuild passed on 2026-07-10:

- package/provider/status/FIFO tests: `336 passed`
- terminal WebSocket tests: `10 passed`
- `black --check`: passed
- `isort --check-only`: passed
- `npm --prefix web run build`: passed
- `npm --prefix web test`: `61 passed` (with existing jsdom/xterm canvas noise)

The previous clean rebuild was run on 2026-07-08 after fork sync moved
`origin/main` from `5be4370` to `d3fab72`. It used:

- `custom/4.1-codex-pyte-status` at `12df448`
- `custom/4.3-claude-effort` at `e9e0d34`
- `custom/4.4-agy-workspace-trust` at `fc0e516`
- `custom/4.6-status-turn-boundary` at `4c56de8`
- `custom/4.7-web-terminal-clipboard` at `dad6084`
- `custom/4.11-web-terminal-viewer-isolation` at `f3ee2f2`
- `custom/4.12-web-terminal-page-scroll` at `65afad2`
- `custom/4.13-worker-init-headless-viewer` at `b4eae1c`
- `custom/4.14-worker-init-status-recovery` at `040bfa4`
- integration branch `cao-tailscale-integration` at `a61cd65`; base `d3fab72`; previous
  integration tip before rebuild was `38218e1`

Upstream range `5be4370..d3fab72`:

- `045f8cc` `feat(workflow): script linter + run-step env guard (#312 B2: U1+U2) (#394)`
- `d2636d6` `feat(workflow): script-tier journal extension (#312 C3/U3) (#391)`
- `474c887` `docs(examples): add AWS cloud-ops agent examples with config (#377)`
- `174784f` `docs: fleet coordinator guide (docs/fleet_instructions.md) (#367)`
- `d3fab72` `fix: unblock multi-agent orchestration on kiro-cli 2.11 — event-loop deadlock, serial/timed-out assign, and provider output/status detection (#390)`

Overlap check classified as **partial-area overlap, behavior-compatible**:

- `src/cli_agent_orchestrator/providers/codex.py`: upstream changed `_extract_response_text`
  to use `strip_terminal_escapes` (replaces narrow ANSI_CODE_PATTERN with full escape strip).
  Our 4.1 adds `supports_screen_detection = True` and `get_status_from_screen()` in a
  different code section. Merged cleanly — no conflict.
- `src/cli_agent_orchestrator/services/status_monitor.py`: upstream added major async
  restructuring (`asyncio.to_thread` in `run()`, `_detect_tasks`, `_arm_quiesce_timer`,
  `_spawn_tracked`, `clear_rolling_buffer`, `call_soon_threadsafe` timer scheduling) to fix
  the kiro-cli 2.11 event-loop deadlock. Our 4.6 adds turn-boundary guard (`_input_sent_at`,
  `_input_sent_buffer_len`, `_ARMED_READY_GRACE_S`, `get_status` logic). Our 4.14 extends
  `get_status` to handle UNKNOWN state. All changes were in different code sections — merged
  cleanly; both upstream threading fix and our turn-boundary guard are present.
- `src/cli_agent_orchestrator/api/main.py`: upstream added `CreateTerminalBody` pydantic
  model with env_vars injection. Our 4.11 adds viewer isolation (different code section).
  Merged cleanly.
- `test/api/test_terminals.py`: upstream added new test for `CreateTerminalBody`; our
  4.11/4.12 add viewer isolation tests. No conflict.
- `src/cli_agent_orchestrator/services/terminal_service.py` (4.13 conflict): upstream moved
  `await provider_instance.initialize()` into the new `if defer_init: ... else:` branch.
  Our 4.13 wraps `initialize()` with `render_during_init`. Conflict resolved by moving
  the `render_during_init` wrapper inside the `else:` branch at the correct location.

Validation for this rebuild passed on 2026-07-08:

- package/provider/status/FIFO tests: `325 passed`
- terminal WebSocket tests: `10 passed`
- `black --check`: passed
- `isort --check-only`: passed
- `npm --prefix web run build`: passed
- `npm --prefix web test`: `56 passed`
The previous clean rebuild was run on 2026-07-06 after fork sync moved
`origin/main` from `d971298` to `5be4370`. It used:

- `custom/4.1-codex-pyte-status` at `08f5e24`
- `custom/4.3-claude-effort` at `850a541`
- `custom/4.4-agy-workspace-trust` at `ebf76c8`
- `custom/4.6-status-turn-boundary` at `9570748`
- `custom/4.7-web-terminal-clipboard` at `304e2f7`
- `custom/4.11-web-terminal-viewer-isolation` at `7496570`
- `custom/4.12-web-terminal-page-scroll` at `ad311b5`
- `custom/4.13-worker-init-headless-viewer` at `dccbbd4`
- `custom/4.14-worker-init-status-recovery` at `3168f94`
- integration branch `cao-tailscale-integration` at HEAD after this sync's docs update
  (pre-doc-commit tip `14474ba`, base `5be4370`; previous integration tip before rebuild
  was `a911023`)

Upstream range `d971298..origin/main`:

- `cf5c0f1` `feat(skills): scope the per-agent skill catalog via a profile allowlist (#351)`
- `1ab0ea9` `feat(memory): Open Knowledge Format (OKF) export/import (#345) (#384)`
- `5be4370` `feat(workflow): durable run journal + resume (#312 N6) (#372)`

Overlap check classified this as **partial-area overlap, behavior-compatible**:

- `src/cli_agent_orchestrator/models/agent_profile.py` added `skills: Optional[List[str]] = None` field under the new scope-per-agent skill catalog feature. Our local 4.3 Claude effort customization touches the same file (adds `effort` field) but does not overlap or conflict.
- `src/cli_agent_orchestrator/api/main.py` added resume workflow run endpoint (`/workflows/runs/{run_id}/resume`) and memory export endpoint (`/memory/export`). Our local 4.11/4.12 Web terminal customizations touch the terminal WebSocket and delete terminal session endpoints in the same file but do not overlap or conflict.
- `CHANGELOG.md` and memory/skills/workflow modules have no overlap with package customizations.

All package customization branches merged cleanly with no conflicts. Validation is run after
rebuilding integration and before push.

Validation for this rebuild passed on 2026-07-06:

- package/provider/status/FIFO tests: `323 passed`
- terminal WebSocket tests: `10 passed`
- `black --check`: passed
- `isort --check-only`: passed
- `npm --prefix web run build`: passed
- `npm --prefix web test`: `56 passed` (with existing jsdom/xterm canvas noise)

> ⚠️ **These customization docs live ONLY on the integration branch** —
> `FORK-SYNC-CUSTOMIZATION-BRANCH-FLOW.md`, `CAO-CUSTOMIZATIONS-PROGRESS.md`, and
> `CAO-Tailscale-CHANGES-SUMMARY.md` are not on `main` or any `custom/*` branch, so the
> force-rebuild (`git branch -f cao-tailscale-integration origin/main`) DROPS them every
> sync. After rebuilding, restore from the previous integration tip
> (`git checkout <old-integration-sha> -- <doc>`), update, and re-commit. Also restore
> per-fix investigation reports when they are still current (for this cycle:
> `CAO-DISPATCH-UNKNOWN-RESOLUTION-2026-07-04.md`). The pre-rebuild tip for the `5be4370`
> fork-sync rebuild was `a911023`.

The previous clean rebuilds were:
- fork sync to `d971298` on 2026-07-05: pre-rebuild tip `6865bac` (pre-doc merge tip `3381a1a`); base `d971298`; customs 4.1 `3b02f23` / 4.3 `558eb1c` / 4.4 `8cd89b1` / 4.6 `77f4e1d` / 4.7 `4d297f2` / 4.11 `fe82d3d` / 4.12 `d2edf03` / 4.13 `088ee01` / 4.14 `e0ceb51`. Upstream range `4dc8bf7..d971298` (partial-area overlap, behavior-compatible).
- no-upstream-delta rebuild on 2026-07-05: pre-rebuild tip `6e340e9`;
  pre-doc merge tip `3ec6105`; base `4dc8bf7`; customs 4.1 `48c6439` /
  4.3 `dcf8cf5` / 4.4 `1d3993c` / 4.6 `2c56460` / 4.7 `91d49c5` /
  4.11 `c44581b` / 4.12 `a7136f7` / 4.13 `f9c0634` / 4.14 `71c793a`.
- no-upstream-delta rebuild on 2026-07-04 after adding 4.14: pre-rebuild tip `fd5a635`;
  pre-doc merge tip `85b024c`; base `4dc8bf7`; customs 4.1 `48c6439` /
  4.3 `dcf8cf5` / 4.4 `1d3993c` / 4.6 `2c56460` / 4.7 `91d49c5` /
  4.11 `c44581b` / 4.12 `a7136f7` / 4.13 `f9c0634` / 4.14 `71c793a`.
- fork sync to `25422d7`: pre-rebuild tip `8ba548f`; customs 4.1 `1ed1fcc` /
  4.3 `986bb06` / 4.4 `5d37519` / 4.6 `2d41485` / 4.7 `ce97898` /
  4.11 `658b774` / 4.12 `9dd65b7` / 4.13 `bb98aea`.
  Upstream range `b0d313e..25422d7`; one partial overlap across provider
  native-status handling (#359/#361), benign after merge and validation.
- fork sync to `b0d313e`: pre-rebuild tip `b70eeb6`; customs 4.1 `5f3022d` / 4.3 `a258134`
  / 4.4 `8c0fe27` / 4.6 `752df34` / 4.7 `8ec162e` / 4.11 `b4297ad` / 4.12 `6d0d365`.
  Upstream range `5dcf319..b0d313e`; one partial overlap in `antigravity_cli.py` (#364
  reactive workspace-trust dialog handler vs our proactive 4.4 trust-write — benign).
- fork sync to `5dcf319`: pre-rebuild tip `e9eb886`; customs 4.1 `266fd79` / 4.3 `3210e72`
  / 4.4 `2f27d6e` / 4.6 `e3a9149` / 4.7 `d122431` / 4.11 `ffac088` / 4.12 `337fcd9`.
- fork sync to `33c593d`: pre-rebuild tip `25a61ba`; customs 4.1 `b66e93e` / 4.3 `792cca1`
  / 4.4 `adfa830` / 4.6 `4016fbb` / 4.7 `e195859`.
- fork sync to `f369068`: pre-rebuild tip `c6d2fad`; customs 4.1 `a8a43a6` / 4.3 `3f046d5`
  / 4.4 `15f73e7` / 4.6 `2de5d0e` / 4.7 `4e84892`.
- fork sync to `0214f23`: pre-rebuild tip `b4de381`; customs 4.1 `c20aef4` / 4.3 `6037c70`
  / 4.4 `f0e05bc` / 4.6 `f07d58c` / 4.7 `782d240`.
- fork sync to `462fa2f`: customs 4.1 `77b14d2` / 4.3 `7569b22` / 4.4 `e2c2b58`
  / 4.6 `dccf768` / 4.7 `0ba72a5`.

### 4.17 token usage successor integration note

The active owner branch is `custom/4.17.5-token-usage-recovery-ux`, successor of
the 4.17.4 native-adapter branch. It contains the complete 4.17.1–4.17.5
ancestry and must be integrated as the highest approved successor only. Before
the next fixed-name integration rebuild, merge the latest `origin/main`, record
the upstream range and Web overlap review, then merge this successor with
`--no-ff`. Do not separately merge the superseded 4.16 tab or earlier 4.17
branches. Token-specific frontend changes remain isolated from `App.tsx` and
shared dashboard state.

4.5 remains in CAO-Tailscale and is intentionally not merged here.

4.8 remains on `custom/4.8-agy-handoff-terminal-retention` at `56500e4` (doc) / `ace213f` (code), but was reverted from integration and is superseded by 4.9.

4.9 and 4.10 were merged into a single **profile-only** version (no package source change), implemented in `/Users/alex/Developer/CAO-Tailscale` at `6190f52` and documented there in `CUSTOMIZATIONS.md` §三 (no package branch, same convention as 4.5):

- 4.9 (supervisor): artifact-as-truth guards in `workers/code_supervisor.md` — the assigned artifact is the only proof of completion; missing artifact re-dispatches under a bounded cap then halts/reroutes; weak signals (`No snapshot found`, `antigravity_cli N/A`) are not dead-worker proof, so artifact/registry/tmux checks happen before re-dispatch; no duplicate workers per task/artifact; cut tasks small; route large DB-backed work to codex/claude.
- 4.10 (developer): `workers/developer.md` long-running-command rule — block until commands exit, finish the whole task within a single turn, and write the artifact before returning; never push work to a background/async task and yield.

`custom/4.8` is not merged into integration (it disables teardown — rejected). 4.9 has no package branch at all; its implementation and record live in CAO-Tailscale.

4.11 is a package customization in this repo. It isolates each Web UI live terminal WebSocket in
a per-connection grouped tmux viewer session so opening terminal B no longer switches browser
viewer A or a local macOS Terminal attached to the original CAO session.

4.12 is a package customization in this repo. It maps Web UI PageUp/PageDown to a WebSocket
`scroll` message and applies that scroll to the per-connection tmux viewer session introduced by
4.11 (`copy-mode -u` / `send-keys -X page-down`). This avoids relying on xterm local scrollback,
which is insufficient for Codex and Antigravity CLI TUI screens, and it prevents the keys from
being consumed by the agent pane. Before forwarding normal terminal input, it also sends
`send-keys -X cancel` to leave tmux copy-mode, so the yellow `[0/37]` / `jump forward` state
does not trap subsequent typing. It depends on 4.7's `TerminalView` key handler and 4.11's
isolated viewer session.
