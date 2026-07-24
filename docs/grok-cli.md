# Grok CLI Provider

CAO can run the xAI Grok CLI as a persistent interactive terminal provider.
The provider ID is `grok_cli` and the executable is `grok`.

## Capability

| Capability | V1 status |
| --- | --- |
| Persistent interactive TUI | Supported |
| Multi-turn lifecycle | Supported |
| Profile system prompt and runtime skills | Supported through `--rules` |
| Profile model | Supported through `--model` |
| Profile effort | Used only when the loaded profile schema provides it |
| Native tool restrictions | Supported through `--deny` |
| Subagent escape prevention | `--no-subagents` when Bash is not allowed |
| CAO MCP orchestration | **Not supported** |

The lifecycle-only boundary is intentional. Grok 0.2.x has no verified way to
forward a different `CAO_TERMINAL_ID` from each Grok process to its MCP
subprocesses without changing shared user or project configuration. CAO does
not write `~/.grok/config.toml`, `.grok/config.toml`, `.mcp.json`, or Grok's
plugin registry.

## Installation and authentication

Install Grok CLI using xAI's supported installation method, then authenticate:

```bash
grok login
grok models
```

Confirm CAO can find the executable:

```bash
command -v grok
grok version
```

Phase 0 was initially captured on `grok 0.2.93` and later observed on
`grok 0.2.101` after an automatic update. TUI changes may require fixture and
status-detector updates.

## Launch

Set `provider: grok_cli` in an agent profile or override it on the CLI:

```bash
cao launch --agents developer --provider grok_cli
```

CAO launches the persistent TUI with `--always-approve`. Profile rules and the
runtime skill catalog are appended through `--rules`; the profile model takes
precedence over a runtime model override.

## Tool restrictions

Restricted profiles are translated to Grok's native deny rules. For example,
a read-only profile denies Bash, Edit, and WebFetch. When `execute_bash` is not
allowed, CAO also adds `--no-subagents` so a delegated agent cannot regain a
shell or edit path.

`--always-approve` suppresses interactive approvals; it does not override the
explicit deny rules. If Bash is allowed, Bash can still write files even when
the separate Edit tool is denied.

## MCP limitation

Profile `mcpServers` entries are not copied into Grok configuration. Grok may
use MCP servers that the user has already configured, but V1 does not claim
that `cao-mcp-server` can safely identify concurrent Grok terminals. In
particular, do not store a literal terminal ID in shared Grok configuration.

Phase 0 evaluated three identity-forwarding paths:

- **Path A — direct inheritance:** unverified. The existing project MCP
  registrations did not include the identity probe, and adding one would have
  changed shared configuration.
- **Path B — runtime environment expansion:** unverified. Read-only inspection
  could not establish whether `${CAO_TERMINAL_ID}` is expanded per Grok process
  or once when configuration is registered.
- **Path C — forward an existing variable by name:** not supported by the
  captured CLI. `grok mcp add -e` accepts `KEY=value`, not a key-only forwarding
  form.

Therefore `selected_path = none`, Gate C is NO-GO, and concurrent Grok
terminals must not share a literal terminal ID. Gate C can be reconsidered if
Grok exposes a documented per-process MCP configuration option, key-only
environment forwarding, or another mechanism that passes the launching Grok
process's environment independently to each MCP child. See the
[Phase 0 ADR](adr-grok-cli-phase0.md) and sanitized fixtures under
`test/providers/fixtures/grok_cli/`.

## Known limitations

- CAO does not manage Grok login or credentials.
- CAO never changes Grok user/project configuration.
- CAO orchestration tools are unsupported for Grok V1.
- Grok has no rules-file option in the calibrated versions. Commands whose
  inline rules exceed CAO's conservative limit fail instead of being truncated.
- Waiting-selection, approval-dialog, and authentication-error TUI states were
  not safely reachable during Phase 0 and use conservative detection patterns.
- After a CAO server restart, on-demand provider reconstruction restores the
  persisted profile and shell baseline, but current terminal metadata does not
  restore constructor-only `model` or `skill_prompt` overrides. Relaunch the
  terminal if those overrides are required.
- Session resume, continue, fork, and ACP/stdio transports are outside V1.

## Troubleshooting

- **Binary not found:** ensure `command -v grok` succeeds in the environment
  that starts `cao-server`.
- **Authentication error:** run `grok login`, then verify with `grok models`.
- **Initialization timeout:** attach to the tmux session and check for a new or
  changed Grok startup screen; record sanitized raw and rendered fixtures.
- **Status remains processing:** Grok redraws its footer in place. Enable the
  repository's pyte status path and capture the current rendered viewport.
- **Profile MCP warning:** expected. Configure non-CAO servers manually if
  needed; CAO orchestration remains unsupported.
