# CAO Customizations Progress

> Current clean integration branch: `feat/customizations-main-462fa2f`.
> Base: `origin/main` at `462fa2f` (`fix(claude_code): stop echoed system prompt from short-circuiting trust dialog (#319)`).

## Current Decision

- 4.2 is no longer local customization work. Antigravity CLI provider was merged upstream in `086e61a` / awslabs#323.
- 4.5 is not in this repo. The 9-worker model selection work belongs to `/Users/alex/Developer/CAO-Tailscale` and has already been implemented there.
- This repo now carries only package-level customizations 4.1, 4.3, and 4.4.

## Branch Model

| Item | Branch | Base | Commit | Status |
|---|---|---|---|---|
| 4.1 Codex pyte status | `custom/4.1-codex-pyte-status` | `462fa2f` | `77b14d2` | Done |
| 4.2 Antigravity provider | upstream `main` | `086e61a` | `086e61a` | Upstream, no local branch |
| 4.3 Claude effort | `custom/4.3-claude-effort` | `462fa2f` | `7569b22` | Done |
| 4.4 Agy workspace trust | `custom/4.4-agy-workspace-trust` | `462fa2f` | `e2c2b58` | Done |
| 4.5 9-worker selection | CAO-Tailscale repo | n/a | n/a | Done outside this repo |
| Integration | `feat/customizations-main-462fa2f` | `462fa2f` | HEAD | Done |

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

## Validation Required

Run on integration branch:

```bash
uv run pytest test/providers/test_antigravity_cli_unit.py test/providers/test_codex_provider_unit.py test/providers/test_claude_code_unit.py test/services/test_status_monitor.py
uv run black --check src/cli_agent_orchestrator/providers/antigravity_cli.py test/providers/test_antigravity_cli_unit.py src/cli_agent_orchestrator/providers/codex.py src/cli_agent_orchestrator/providers/claude_code.py src/cli_agent_orchestrator/models/agent_profile.py test/providers/test_claude_code_unit.py
uv run isort --check-only src/cli_agent_orchestrator/providers/antigravity_cli.py test/providers/test_antigravity_cli_unit.py src/cli_agent_orchestrator/providers/codex.py src/cli_agent_orchestrator/providers/claude_code.py src/cli_agent_orchestrator/models/agent_profile.py test/providers/test_claude_code_unit.py
```

## Open Notes

- 4.5 should be maintained and tested in CAO-Tailscale, not here.
- `.cao/` review artifacts belong to investigation/fix branches and should not be carried into this integration branch.
- `ISSUES.md` in the original working tree is untracked and intentionally not included.
