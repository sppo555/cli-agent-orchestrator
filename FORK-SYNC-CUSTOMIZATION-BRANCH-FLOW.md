# Fork Sync Customization Branch Flow

Use this flow after GitHub fork sync updates `main`.

## Preferred Flow

1. Fork sync on GitHub updates `main`.
2. Fetch latest main locally.
3. Merge latest main into each customization branch.
4. Create a new integration branch from latest main.
5. Merge customization branches into the integration branch.
6. Test the integration branch.

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
uv run black --check src/cli_agent_orchestrator/providers/antigravity_cli.py test/providers/test_antigravity_cli_unit.py src/cli_agent_orchestrator/providers/codex.py src/cli_agent_orchestrator/providers/claude_code.py src/cli_agent_orchestrator/models/agent_profile.py test/providers/test_claude_code_unit.py src/cli_agent_orchestrator/services/status_monitor.py test/services/test_status_monitor.py test/services/test_agent_step.py src/cli_agent_orchestrator/api/main.py test/api/test_terminals.py
uv run isort --check-only src/cli_agent_orchestrator/providers/antigravity_cli.py test/providers/test_antigravity_cli_unit.py src/cli_agent_orchestrator/providers/codex.py src/cli_agent_orchestrator/providers/claude_code.py src/cli_agent_orchestrator/models/agent_profile.py test/providers/test_claude_code_unit.py src/cli_agent_orchestrator/services/status_monitor.py test/services/test_status_monitor.py test/services/test_agent_step.py src/cli_agent_orchestrator/api/main.py test/api/test_terminals.py
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

## Current Clean Rebuild

The clean rebuild after fork sync to `25422d7` used:

- `custom/4.1-codex-pyte-status` at `1ed1fcc`
- `custom/4.3-claude-effort` at `986bb06`
- `custom/4.4-agy-workspace-trust` at `5d37519`
- `custom/4.6-status-turn-boundary` at `2d41485`
- `custom/4.7-web-terminal-clipboard` at `ce97898`
- `custom/4.11-web-terminal-viewer-isolation` at `658b774`
- `custom/4.12-web-terminal-page-scroll` at `9dd65b7`
- integration branch `cao-tailscale-integration` at HEAD after this sync's docs update
  (pre-doc-commit tip `da18c76`, base `25422d7`)

> ℹ️ This sync arrived as a GitHub "Sync fork" run **targeting the integration branch**,
> which produced a merge commit `45e5ed1` ("Merge branch 'awslabs:main' into
> cao-tailscale-integration", merging main into the old integration tip `8ba548f`) on
> `origin/cao-tailscale-integration` instead of advancing `main` alone. That is not the
> prescribed topology (integration should be rebuilt from `origin/main`, not have main
> merged into it). It was **not** clobbered — customizations were preserved — but we still
> reran the full clean-rebuild flow below and force-pushed to replace `45e5ed1`. For future
> syncs, run "Sync fork" against `main`, not the integration branch.

Upstream range `b0d313e..25422d7` — a single commit, `25422d7` (#359/#361)
"fix(providers): read herdr native status in all providers". Overlap check classified this
as a **partial overlap (benign)** on three customization files. It refactors native-status
detection out of `claude_code.py` into a shared `BaseProvider._resolve_native_status()`
(+ shared dispatch-tracking fields and a `super().mark_input_received()` contract in
`base.py`), and inserts a `_resolve_native_status()` early-return at the top of **every**
provider's `get_status()`. Our patches sit in different regions of the same files and all
merged with no textual conflict:

- 4.1 (`codex.py`): our `supports_screen_detection` attr + new `get_status_from_screen()`
  method are additive; upstream's early-return is at the top of `get_status()`. Our screen
  path internally calls `self.get_status()`, which now first hits `_resolve_native_status()`
  — on the tmux backend that returns None and falls through unchanged (herdr never uses the
  pyte screen path), so behavior is unchanged.
- 4.3 (`claude_code.py` / `agent_profile.py`): our `--effort` flag lives in
  `_build_claude_command`; upstream deleted the old inline native-status block and
  `mark_input_received` override from `claude_code.py` (now inherited from `base.py`).
  Different methods; `--effort` intact.
- 4.4 (`antigravity_cli.py`): our workspace-trust write is in `__init__`/`initialize()`;
  upstream's early-return is in `get_status()` and a `super().mark_input_received()` line is
  in `mark_input_received()`. Different methods; trust-write intact. (The prior-cycle #364
  reactive dialog handler is untouched by #359, so that documented partial overlap stands.)

Watch-list files not touched by this range: `status_monitor.py`, `agent_step.py`,
`mcp_server/server.py`, `api/main.py`, `test/api/test_terminals.py`, and all Web UI files —
no overlap with 4.6/4.7/4.11/4.12. Verified on the integration branch post-merge: full
Validation suite green (411 provider/service tests incl. the new
`test_native_status_shared.py`, 10 WebSocket tests, black/isort clean, web build + 56 web
tests). All seven package customs merged cleanly with no conflicts.

> ⚠️ **These three customization docs live ONLY on the integration branch** —
> `FORK-SYNC-CUSTOMIZATION-BRANCH-FLOW.md`, `CAO-CUSTOMIZATIONS-PROGRESS.md`, and
> `CAO-Tailscale-CHANGES-SUMMARY.md` are not on `main` or any `custom/*` branch, so the
> force-rebuild (`git branch -f cao-tailscale-integration origin/main`) DROPS them every
> sync. After rebuilding, restore from the previous integration tip
> (`git checkout <old-integration-sha> -- <doc>`), update, and re-commit. The pre-rebuild
> tip for the `25422d7` sync was `8ba548f` (its origin counterpart was GitHub's sync merge
> `45e5ed1`).

The previous clean rebuilds were:
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
