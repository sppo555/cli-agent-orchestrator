# Fork Sync Customization Branch Flow

Use this flow after GitHub fork sync updates `main`.

## Preferred Flow

1. Fork sync on GitHub updates `main`.
2. Fetch latest main locally.
3. Merge latest main into each customization branch.
4. Create a new integration branch from latest main.
5. Merge customization branches into the integration branch.
6. Test the integration branch.

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
```

For this repo, there is no `custom/4.5` package branch. 4.5 is the 9-worker deployment customization in `/Users/alex/Developer/CAO-Tailscale`.

Create a fresh integration branch from latest main:

```bash
git switch -c feat/customizations-<main-sha> origin/main
```

Merge package customization branches:

```bash
git merge --no-ff custom/4.1-codex-pyte-status
git merge --no-ff custom/4.3-claude-effort
git merge --no-ff custom/4.4-agy-workspace-trust
```

Do not merge old local 4.2 branches. Antigravity CLI provider is upstream in `086e61a`.

## Conflict Policy

- If a conflict happens while merging `origin/main` into a customization branch, resolve it inside that customization branch.
- If a conflict happens while merging custom branches into integration, first ask whether the fix belongs in one custom branch. Prefer fixing there, then recreate or redo the integration merge.
- Integration branch should mainly be merge commits plus documentation.

## Validation

Run on the integration branch:

```bash
uv run pytest test/providers/test_antigravity_cli_unit.py test/providers/test_codex_provider_unit.py test/providers/test_claude_code_unit.py test/services/test_status_monitor.py
uv run black --check src/cli_agent_orchestrator/providers/antigravity_cli.py test/providers/test_antigravity_cli_unit.py src/cli_agent_orchestrator/providers/codex.py src/cli_agent_orchestrator/providers/claude_code.py src/cli_agent_orchestrator/models/agent_profile.py test/providers/test_claude_code_unit.py
uv run isort --check-only src/cli_agent_orchestrator/providers/antigravity_cli.py test/providers/test_antigravity_cli_unit.py src/cli_agent_orchestrator/providers/codex.py src/cli_agent_orchestrator/providers/claude_code.py src/cli_agent_orchestrator/models/agent_profile.py test/providers/test_claude_code_unit.py
```

Final inspection:

```bash
git log --oneline --decorate origin/main..HEAD
git diff --stat origin/main..HEAD
git status --short --branch
```

## Current Clean Rebuild

The clean rebuild after fork sync to `462fa2f` used:

- `custom/4.1-codex-pyte-status` at `77b14d2`
- `custom/4.3-claude-effort` at `7569b22`
- `custom/4.4-agy-workspace-trust` at `e2c2b58`
- integration branch `feat/customizations-main-462fa2f`

4.5 remains in CAO-Tailscale and is intentionally not merged here.
