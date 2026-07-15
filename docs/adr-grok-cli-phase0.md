# ADR: Grok CLI Phase 0 calibration and V1 capability

- Status: accepted for lifecycle-only V1 implementation
- Date: 2026-07-15; accepted 2026-07-16 after implementation review
- Scope: calibration decision governing the production `grok_cli` lifecycle provider
- Target CAO commit: `32db5a192d82c7ded5d6e4be270d2a58e9702c3b`

## Decision

Use a persistent interactive Grok TUI for the later lifecycle provider. Gate A
is GO for the observed TUI surfaces, Gate B is GO for the tested restricted
profile, and Gate C is NO-GO: no safe, reproducible per-terminal MCP identity
forwarding path was verified without changing shared Grok configuration.

The supported outcome is **LIFECYCLE_ONLY**. Implementation review accepted
production registration of `grok_cli` within that boundary. This decision does
not authorize CAO MCP orchestration, automatic Grok configuration writes, or
claims of per-terminal MCP identity forwarding.

## Calibration and version boundary

The pre-flight and first captures used `grok 0.2.93 (f00f96316d4b)`. Grok
auto-updated while later sessions were launched; subsequent live captures show
`grok 0.2.101 (5bc4b5dfadcf)`. The 0.2.93 and 0.2.101 captures are kept
separate by their command output and timestamps. The accepted V1 implementation
does not treat the mixed set as one pinned release. Its
regression suite preserves both observed surfaces and logs the runtime version;
future pinned-version updates require fresh calibration evidence.

The target `AgentProfile` at the CAO commit has no `effort` field. The evidence
does not assume one.

## Lifecycle calibration

- Grok-specific ready surface: the input box containing `❯` together with the
  footer `Grok 4.5 (high)` and mode text (for example `always-approve`). A bare
  shell `❯` is insufficient; see `grok_cli/rendered/shell_prompt.txt` and
  `shell_groklike_prompt.txt`.
- Startup, idle, processing, completed, long response, Markdown, and
  multiline-code captures are present in paired raw and rendered directories.
- Processing showed `Starting session…`; completion showed a response followed
  by `Turn completed in ...` and the ready footer.
- Bracketed paste submitted single-line, multiline, fenced-code, and Unicode
  prompts with one Enter after an observed 0.8 second delay. Captures show one
  user prompt per probe and no editor-only residue. The accepted provider
  exposes `paste_enter_count = 1` and retains the calibrated submit delay.
- `/quit` and `/exit` returned to zsh. Ctrl-D, Ctrl-C, Ctrl-C twice, and Ctrl-Q
  did not return to zsh within the three-second observation window. `/quit` is
  the selected normal exit command; Ctrl-C remains a cancellation fallback to
  be re-tested during implementation.

## Restriction calibration

With `--no-subagents --deny Bash --deny Edit`, a direct shell-write attempt
returned `Denied by permission policy` and created no file. A combined direct
Edit, subagent shell, and subagent Edit probe produced no files and showed
write/shell denial while subagent spawning was disabled. The configured
read-only MCP inventory had no file-writing non-CAO server. These observations
support Gate B GO for the tested restricted profile, subject to implementation
regression tests and the known boundary that a profile allowing Bash can write
through shell commands.

## MCP paths and Gate C

The fixture `grok_cli/mcp/identity_server.py` reports only PID, invocation ID,
`CAO_TERMINAL_ID` presence/value, and a small allowlist of terminal metadata. It
was not registered because the task forbids user/project Grok configuration
writes.

| Path | Decision | Evidence |
| --- | --- | --- |
| A: direct inheritance | SKIP / unverified | Existing read-only `grok mcp doctor --json` found two project servers, but neither is the identity probe. Adding a static registration would mutate shared config, so no two-terminal identity claim is made. |
| B: `${CAO_TERMINAL_ID}` config expansion | SKIP / unverified | `grok inspect --json` and doctor output were read-only snapshots only. No config containing a dynamic expansion was installed, so registration-time versus process-start expansion is unknown. |
| C: `grok mcp add -e` forward-by-name | NO-GO | Captured help documents `-e, --env <KEY=value>`; key-only forwarding is not an advertised interface. The key-only mutation command was not run because it could alter shared config. |

`selected_path = none` and `orchestration_supported = false`. A shared literal
`CAO_TERMINAL_ID` is prohibited because two concurrent terminals would race or
cross-talk, and the task forbids embedding terminal-specific values in shared
configuration. No 20-check concurrency run was authorized or claimed because
no path passed the safety precondition.

## Gate decisions and follow-up

- Gate A: GO for lifecycle V1; future pinned-version changes require recalibration.
- Gate B: GO for the observed native deny rules and `--no-subagents` scenario.
- Gate C: NO-GO; lifecycle-only path is the approved V1 capability route.

Implementation and subsequent reviews retained the mixed-version fixture
boundary, explicit state skips, and no-config-write MCP conclusion. Any future
orchestration work requires a new Gate C decision backed by safe concurrent
identity evidence.
