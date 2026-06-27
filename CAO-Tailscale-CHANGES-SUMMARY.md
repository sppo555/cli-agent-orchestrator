# CAO-Tailscale Changes Summary

This file records how the package-level CAO customizations relate to the CAO-Tailscale deployment repo after the latest fork sync.

## Current Package Branch

- Repo: `/Users/alex/Developer/cli-agent-orchestrator`
- Integration branch: `feat/customizations-main-462fa2f`
- Base: `origin/main` at `462fa2f`
- Local package customizations included here:
  - 4.1 Codex pyte status
  - 4.3 Claude Code `--effort`
  - 4.4 Antigravity workspace trust
- Local package customizations not included here:
  - 4.2 Antigravity provider, because upstream already merged it in `086e61a`.
  - 4.5 9-worker selection, because it belongs to CAO-Tailscale deployment scripts.

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
uv run pytest test/providers/test_antigravity_cli_unit.py test/providers/test_codex_provider_unit.py test/providers/test_claude_code_unit.py test/services/test_status_monitor.py
uv run black --check src/cli_agent_orchestrator/providers/antigravity_cli.py test/providers/test_antigravity_cli_unit.py src/cli_agent_orchestrator/providers/codex.py src/cli_agent_orchestrator/providers/claude_code.py src/cli_agent_orchestrator/models/agent_profile.py test/providers/test_claude_code_unit.py
uv run isort --check-only src/cli_agent_orchestrator/providers/antigravity_cli.py test/providers/test_antigravity_cli_unit.py src/cli_agent_orchestrator/providers/codex.py src/cli_agent_orchestrator/providers/claude_code.py src/cli_agent_orchestrator/models/agent_profile.py test/providers/test_claude_code_unit.py
```

CAO-Tailscale 9-worker validation should be run in that repo, not here.
