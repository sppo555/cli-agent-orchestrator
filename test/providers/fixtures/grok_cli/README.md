# Grok CLI Phase 0 fixtures

These are evidence captures for Grok CLI `grok_cli` calibration only. They do
not implement or register a provider.

The `raw/` files are tmux `capture-pane -e` or `pipe-pane` ANSI captures. The
`rendered/` files are tmux screen captures, and `rendered_pyte/` contains the
same ANSI streams rendered through the repository's `pyte` dependency using
`render_with_pyte.py` at 120x40. CLI help and read-only JSON probes are under
`cli/`; the shell, paste, exit, and security observations are under `spikes/`.

The requested 0.2.93 build was captured first. Grok then auto-updated during
the live session to 0.2.101; the ADR and evidence report distinguish those
captures instead of treating them as one calibration version.

Public fixtures replace usernames, hostnames, home directories, project paths,
local executable paths, MCP server names, and unrelated skill inventory with
stable placeholders. The provider unit suite scans this directory to prevent
personal paths and hostnames from being reintroduced.

`mcp/identity_server.py` is an unregistered, allowlisted probe. No Grok user
config, project `.mcp.json`, or plugin registry was changed while collecting
this evidence.
