# Pre-flight Report

## Environment

- Repository: `/Users/alex/Developer/cli-agent-orchestrator`
- Branch: `feat/grok-cli-phase0-evidence`
- Current commit: `32db5a192d82c7ded5d6e4be270d2a58e9702c3b`
- PLAN baseline comparison: exact match to the PLAN's `32db5a1` baseline.
- Working tree: dirty only because of untracked task/input material (`.cao/`, `AGENTS.md`, `PLAN_CAO_ADD_GROK_CLI_PROVIDER_V2_1.md`, and `PROMPT_PACK_CAO_GROK_CLI_PROVIDER_V1.md`); `git diff --stat` and `git diff --name-only` were empty. This report is also an untracked deliverable under `.cao/`.
- Configured remotes: `origin` fetch/push is `git@github.com:sppo555/cli-agent-orchestrator.git`.
- Operating system: Darwin 25.5.0, arm64 (`uname -a`: `Darwin alexdeMacBook-Pro.local 25.5.0 Darwin Kernel Version 25.5.0: Mon Apr 27 20:41:06 PDT 2026; root:xnu-12377.121.6~2/RELEASE_ARM64_T6030 arm64`).
- Shell: `/bin/zsh`.
- Python: `python` is not on PATH; `python3 --version` is `Python 3.14.6`. The existing `uv` environment used by the test runner reports CPython 3.13.14.
- Package manager/lockfile: `uv` at `/Users/alex/.local/bin/uv`; repository lockfile `uv.lock`; `pyproject.toml` declares the package and dev dependencies. No `poetry` or `Pipfile.lock` was found.
- tmux: `tmux 3.6b` at `/opt/homebrew/bin/tmux`.
- Code-defined CAO backends: `tmux` (default) and `herdr` (experimental), selected by `BackendFactory` through `terminal.backend`; no backend setting was changed or inspected from user configuration.
- CAO version: `cao, version 2.3.0`.

## Repository Baseline

- No `grok` or `grok_cli` references currently exist in `src/`, `test/`, or `web/`; the checkout is a pre-implementation baseline.
- `ProviderType` currently contains: `kiro_cli`, `claude_code`, `codex`, `kimi_cli`, `copilot_cli`, `opencode_cli`, `hermes`, `cursor_cli`, and `antigravity_cli`. `grok_cli` is not registered.
- `BaseProvider.__init__` requires `(terminal_id, session_name, window_name, allowed_tools=None, skill_prompt=None)`. Abstract required methods are `initialize()`, `get_status()`, `extract_last_message_from_script()`, `exit_cli()`, and `cleanup()`. The base contract also provides shell baseline/native-status tracking, `get_status_from_screen()`, paste controls, and `mark_input_received()`.
- `ProviderManager` is a module singleton with a direct `terminal_id -> BaseProvider` map. `create_provider()` uses an explicit provider-type `if/elif` factory and `get_provider()` reconstructs from terminal DB metadata when absent.
- Terminal-service provider sets:
  - `RUNTIME_SKILL_PROMPT_PROVIDERS`: `claude_code`, `codex`, `kimi_cli`, `antigravity_cli`.
  - `SOFT_ENFORCEMENT_PROVIDERS`: `kimi_cli`, `codex`, `antigravity_cli`.
  - `grok_cli` is in neither set because it is not yet registered.
- Launch workspace-access set currently contains `antigravity_cli`, `claude_code`, `codex`, `copilot_cli`, `cursor_cli`, `hermes`, `kimi_cli`, `kiro_cli`, and `opencode_cli`; `grok_cli` is absent.
- Tool mapping currently has native mappings for `claude_code`, `copilot_cli`, and `antigravity_cli` only. There is no Grok mapping.
- API provider binary detection (`GET /agents/providers`) currently maps:
  `kiro_cli -> kiro-cli`, `claude_code -> claude`, `codex -> codex`, `hermes -> hermes`, `kimi_cli -> kimi`, `copilot_cli -> copilot`, `opencode_cli -> opencode`, `cursor_cli -> agent`, and `antigravity_cli -> agy`. `grok_cli -> grok` is absent.
- Web fallback location is `web/src/components/AgentPanel.tsx`, exported as `FALLBACK_PROVIDERS`; its assertions are in `web/src/test/components.test.tsx`.
- Existing provider unit tests are in `test/providers/test_*_unit.py`; shared fixtures are in `test/providers/fixtures/`. Existing provider fixture files are provider-prefixed text/ANSI captures. There is no Grok fixture directory or file.
- E2E tests are in `test/e2e/`, with shared API/tmux prerequisites in `test/e2e/conftest.py`. Existing E2E tests use the API helpers and the registered `e2e` marker; the conftest documents `uv run pytest -m e2e test/e2e/ -v`.

## AgentProfile Schema

- `AgentProfile` is a Pydantic model in `src/cli_agent_orchestrator/models/agent_profile.py`.
- Actual fields include identity (`name`, `description`), provider/prompt/role fields, `skills`, `mcpServers`, tool fields (`tools`, `toolAliases`, `allowedTools`, `toolsSettings`), `resources`, `hooks`, `useLegacyMcpJson`, `model`, `permissionMode`, `native_agent`, Codex fields (`codexProfile`, `codexConfig`), and `hermesProfile`.
- `AgentProfile.effort` does not exist. The checked-in JSON schema also has no `effort` property and uses `additionalProperties: false`.
- Therefore the upstream checkout must not use `profile.effort` directly. The PLAN's defensive `getattr(profile, "effort", None)` compatibility hook is consistent with this baseline; formal profile-driven effort remains outside the current upstream schema.

## Test and Quality Conventions

- `pyproject.toml` registers exactly these pytest markers: `asyncio`, `integration`, `e2e`, and `slow`. It sets `testpaths = ["test"]`, `python_files = "test_*.py"`, strict asyncio mode, and default `addopts = "--cov=src --cov-report=term-missing -m 'not e2e'"`.
- Unit/provider command conventions in the repository are `uv run pytest test/providers/<test>.py -v` or `-q`; integration tests use the existing `integration` marker; E2E tests use the existing `e2e` marker and normally override the default `addopts` when needed.
- CI (`.github/workflows/ci.yml`) installs with `uv sync --all-extras --dev`, runs the unit suite with `pytest` while excluding provider integration and E2E tests, and has separate Web UI build/type/test jobs.
- Quality commands in CI are:
  - `uv run black --check src/ test/`
  - `uv run isort --check-only src/ test/`
  - `uv run mypy src/` (configured `continue-on-error: true` in CI)
- `pyproject.toml` declares Black, isort, and mypy in the dev dependency group. A Makefile exists but only provides vendored MCP-app skill refresh/check targets; it has no canonical test or quality target.
- Tool availability was confirmed with `uv run --no-sync`: Black 26.3.1, isort 6.0.1, mypy 1.18.2, and pytest 9.0.3.
- A read-only collection probe (`uv run --no-sync pytest --collect-only -q test/providers/test_provider_manager_unit.py`) listed 16 tests without executing test bodies. Its default coverage reporting emitted warnings about an existing incompatible `.coverage` data file; no source/test file was edited.

## CLI Capability Snapshot

The following read-only commands were actually executed. No `grok mcp add`, plugin mutation, session launch, or configuration-writing command was run.

### CAO

`cao --help` reported these commands: `config`, `env`, `info`, `init`, `install`, `launch`, `mcp-server`, `memory`, `profile`, `schedule`, `session`, `shutdown`, `skills`, `terminal`, and `workflow`.

The real `cao session --help` output was:

```text
Usage: cao session [OPTIONS] COMMAND [ARGS]...

  Manage CAO sessions.

Options:
  --help  Show this message and exit.

Commands:
  list    List all active CAO sessions.
  send    Send a message to a session's conductor (or specific terminal).
  status  Show status of a session's conductor (or specific terminal).
```

The real `cao launch --help` output showed `--provider`, `--agents`, `--headless`, `--async`, `--allowed-tools`, `--working-directory`, and other options. The real `cao shutdown --help` output showed only `--all` and `--session` as shutdown selectors. These are the actual available command surfaces; no `cao session status`/`send` syntax beyond the help output was assumed.

### Grok

- `grok version` returned `grok 0.2.93 (f00f96316d4b)`, exactly matching the PLAN's Grok calibration baseline.
- `grok --help` confirmed persistent interactive TUI operation and the relevant flags: `--allow`, `--always-approve`, `--deny`, `--model`, `--no-subagents`, `--reasoning-effort` (alias `--effort`), `--rules`, `--session-id`, and `--prompt-file`. It also lists `/`-style interactive operation through the root TUI, but `/quit` was not executed and is not claimed as validated.
- `grok inspect --help` exists and supports `--json`; `grok mcp --help` exists with `list`, `add`, `remove`, and `doctor`; `grok mcp doctor --help` supports an optional server name and `--json`.
- `grok mcp add --help` explicitly defines `-e, --env <KEY=value>` as a repeatable environment assignment. It does not advertise key-only or `env_keys` forwarding.
- `grok agent --help` exists and exposes non-interactive `stdio`, `headless`, `serve`, and `leader` modes. Its options include `--agent-profile`, `--always-approve`, `--model`, and `--reasoning-effort`/`--effort`; importantly, it also exposes `--plugin-dir`.
- `grok plugin --help` exists and exposes plugin list/install/uninstall/update/enable/disable/details/validate/tag and marketplace commands.
- No `grok inspect --json` or `grok mcp doctor --json` capability/configuration probe was run in this pre-flight; their presence above is based only on the executed help commands. No MCP registration or config mutation was attempted.

## Available Prerequisites

- Grok binary: **available** at `/Users/alex/.grok/bin/grok`; version command succeeded.
- Grok authentication/model readiness: **available**. The read-only `grok models` probe reported that the user is logged in with grok.com and that `grok-4.5` is the default/available model. No credentials or tokens were exposed.
- tmux: **available** at `/opt/homebrew/bin/tmux`, version 3.6b. A temporary detached tmux session was created, detected, and cleaned up successfully.
- CAO executable: **available** at `/Users/alex/.local/bin/cao`; `cao --help`, `cao session --help`, `cao launch --help`, `cao shutdown --help`, and `cao --version` succeeded.
- `cao-mcp-server` executable: **available** at `/Users/alex/.local/bin/cao-mcp-server` by `command -v`; it was not launched.
- Ability to run integration tests: **partially verified**. The uv environment has pytest and the existing provider test module collected successfully, but no live integration test was executed in this PRE-FLIGHT stage and no live-test pass is claimed.
- Ability to create temporary tmux sessions: **verified** by the create/has-session/cleanup probe above.
- Ability to run two Grok sessions concurrently: **not validated** in this pre-flight. Grok binary, authentication, and tmux prerequisites are present, but the required two-terminal identity/concurrency experiment belongs to Phase 0 evidence and was not claimed here.

## PLAN Discrepancies

### Required correction

1. **MCP Path C syntax is not supported as written.** The PLAN proposes `grok mcp add ... -e CAO_TERMINAL_ID` as a forward-by-name candidate. Actual `grok mcp add --help` documents only `-e, --env <KEY=value>`, so the key-only example is not a validated Grok CLI interface. Phase 0 must treat Path C as a failed/unavailable candidate unless a separately verified mechanism is found; it must never write a terminal-specific literal ID into shared configuration.
2. **The PLAN's “confirm `--plugin-dir` does not exist” check conflicts with the actual CLI.** `grok agent --help` exposes `--plugin-dir <DIR>`. This task explicitly forbids using it, so the provider must continue not to use it; the PLAN's capability-matrix wording should be corrected to “available in `grok agent`, prohibited for this provider,” rather than claiming it is absent.
3. **The current checkout has no Grok implementation surfaces.** `ProviderType`, `ProviderManager`, launch workspace access, terminal skill/enforcement sets, tool mapping, API binary list, Web fallback, provider tests/fixtures, E2E tests, and Grok docs all lack `grok_cli`. This is the expected implementation delta for later prompts, but it is a required correction before the PLAN's final provider can exist and is not a Phase 0 pre-flight blocker.
4. **The Web fallback list is already stale relative to the checkout's current enum.** `FALLBACK_PROVIDERS` currently contains `q_cli` and `gemini_cli`, which are not current `ProviderType` values, and omits current `antigravity_cli`; it also lacks `grok_cli`. The PLAN's instruction to clean stale entries and add Grok is therefore applicable.

### Non-blocking drift

1. The system Python is 3.14.6 while the existing uv test environment is Python 3.13.14; the project declares Python `>=3.10` and CI tests 3.10–3.12. This is environment drift, not a baseline commit mismatch.
2. The repository registers `asyncio` and `slow` in addition to the PLAN-emphasized `integration` and `e2e` markers. This does not prevent using the existing markers for Grok-specific live tests.
3. The existing `mypy.ini`/`pyproject.toml` configuration reports `python_version = "2.3.0"` while CI invokes mypy with `continue-on-error`; this is pre-existing quality configuration drift worth correcting before treating mypy as a hard gate, but it does not affect the read-only pre-flight facts above.

### Cosmetic

1. The current README/module comments still describe older provider examples and do not mention Grok. This is expected documentation work and does not affect Phase 0 evidence collection.

### Blocker assessment

No blocker was found for entering Phase 0 evidence collection. Gate C orchestration remains unverified; the actual `-e KEY=value` interface means Path C cannot be assumed, and Paths A/B require controlled evidence before any orchestration capability is declared.

## Recommended Next Action

READY_WITH_CORRECTIONS

Proceed to Phase 0 evidence collection after recording the Path C `KEY=value` incompatibility and the actual `--plugin-dir` availability in the evidence/ADR. Preserve the checked-out upstream `AgentProfile` schema with no `effort` field, use only the real CAO command surfaces captured above, and keep Grok/provider/config registration and all source/test/doc/config edits for later prompts. Do not use `--plugin-dir`, do not modify Grok config, and do not declare orchestration support until the two-terminal Path A/B experiments pass without identity cross-talk.

Completed at: Wed Jul 15 19:32:25 CST 2026
