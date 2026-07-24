# Phase 0 Evidence Report

## Files Changed

- `/Users/alex/Developer/cli-agent-orchestrator/docs/adr-grok-cli-phase0.md` — Phase 0 ADR with lifecycle calibration, Gate A/B/C decisions, MCP path outcomes, and V1 capability result.
- `/Users/alex/Developer/cli-agent-orchestrator/test/providers/fixtures/grok_cli/` — committed-ready evidence fixture tree containing CLI help/matrix, target `AgentProfile` snapshot, baseline, raw ANSI captures, tmux-rendered captures, pyte-rendered captures, paste/exit/security spikes, state skip ledger, manifest, and an unregistered MCP identity helper.
- `/Users/alex/Developer/cli-agent-orchestrator/test/providers/fixtures/grok_cli/render_with_pyte.py` — repeatable pyte renderer used to derive rendered fixtures from ANSI streams.
- `/Users/alex/Developer/cli-agent-orchestrator/test/providers/fixtures/grok_cli/mcp/identity_server.py` — minimal allowlisted MCP identity probe; not registered or executed through Grok because doing so would require forbidden config mutation.

No `src/`, `web/`, API, CLI, ProviderType, ProviderManager, or production provider behavior was changed. No `GrokCliProvider` was implemented. No `--plugin-dir` was used. No Grok user/project config or plugin registry was written. A git commit was not created because worker policy forbids `git commit`; the fixture and ADR changes are present as uncommitted branch changes for the supervisor to review and commit.

## Commands Executed

Read-only baseline and capability commands (all completed successfully unless noted):

- `git branch --show-current`; `git rev-parse HEAD`; `python3 --version`; `uv run --no-sync python --version`; `tmux -V`; `uname -a`.
- `grok version`; `grok --help`; `grok inspect --help`; `grok mcp --help`; `grok mcp add --help`; `grok mcp doctor --help`; `grok agent --help`; `grok plugin --help`.
- `cao --help`; `cao session --help`; `cao launch --help`; `cao shutdown --help`.
- Read-only `grok inspect --json`, `grok mcp list --json`, and `grok mcp doctor --json`; JSON output was redacted before fixture storage.
- `git show 32db5a192d82c7ded5d6e4be270d2a58e9702c3b:src/cli_agent_orchestrator/models/agent_profile.py` to preserve the target schema.
- `tmux new-session`, `pipe-pane`, `capture-pane`, `send-keys`, `load-buffer`, `paste-buffer`, and `list-panes` probes in disposable sessions, all cleaned up afterward.
- `uv run --no-sync python test/providers/fixtures/grok_cli/render_with_pyte.py ...` for the captured ANSI streams.
- Config safety checks used hash-only `shasum ~/.grok/config.toml .mcp.json` before/after; hashes were unchanged.

Verification commands:

- `uv run --no-sync black --check test/providers/fixtures/grok_cli/render_with_pyte.py test/providers/fixtures/grok_cli/mcp/identity_server.py` — PASS.
- `uv run --no-sync isort --check-only test/providers/fixtures/grok_cli/render_with_pyte.py test/providers/fixtures/grok_cli/mcp/identity_server.py` — PASS.
- `uv run --no-sync mypy test/providers/fixtures/grok_cli/render_with_pyte.py test/providers/fixtures/grok_cli/mcp/identity_server.py` — PASS, no issues.
- `uv run --no-sync pytest test/providers/test_provider_manager_unit.py -q` — PASS, 16 passed. This is the relevant regression guard confirming the untouched provider registry remains green.

## Captured Fixtures

Raw ANSI captures are under `/Users/alex/Developer/cli-agent-orchestrator/test/providers/fixtures/grok_cli/raw/`; tmux-rendered captures are under `.../rendered/`; pyte renders are under `.../rendered_pyte/`. The manifest at `.../manifest.md` maps every requested state to its raw/rendered evidence or explicit `.SKIP.md` ledger entry.

Captured states include shell-only prompt, Grok startup, idle, processing, completed, long response, Markdown, multiline code, question response, plan output, and policy-denied tool error. Authentication error, native selection wait, and native approval prompt are explicit skips in `spikes/state_skip_ledger.md`; no state was fabricated.

## Capability Matrix

The complete matrix and command outputs are in `test/providers/fixtures/grok_cli/cli/capability_matrix.md` and `cli/*.txt`.

| Capability | Result |
| --- | --- |
| `--always-approve`, `--rules`, `--allow`, `--deny`, `--model` | Present in root TUI help |
| `--effort` | Present as alias of `--reasoning-effort` |
| `--no-subagents`, `--session-id` | Present |
| `--plugin-dir` | Present only in `grok agent`; prohibited and unused for this task |
| `--mcp-config`, rules-file support | Absent from captured root/agent help |
| Exit commands | `/quit` and `/exit` returned to zsh; Ctrl-D/C/Ctrl-Q did not exit in the observation window |
| CAO E2E command surface | `cao launch`; `cao session list/status/send`; no invented session-run command |

The pre-flight capture was `grok 0.2.93 (f00f96316d4b)`. During later live launches Grok auto-updated and reported `grok 0.2.101 (5bc4b5dfadcf)`. This version boundary is called out in the ADR and fixtures; it is a recalibration risk, not hidden as a single-version claim.

## Shell and TUI Findings

The ready surface is composite: the input box with `❯` plus the footer containing `Grok 4.5 (high)` and mode text such as `always-approve`. A shell prompt containing only `❯`, including an extreme prompt containing Grok-like footer text, was captured separately and must remain `UNKNOWN`; a single broad `❯` regex is not safe.

Processing showed `Starting session…`. Completion showed an assistant response followed by `Turn completed in ...` and the same Grok footer/input chrome. The first 0.2.93 captures establish the requested baseline for idle/processing/completed; later startup/security captures are labeled with the observed 0.2.101 drift.

## Paste and Exit Findings

Bracketed paste was exercised for single-line, multiline, fenced-code, and Chinese/Unicode prompts. Each probe used one Enter after an observed 0.8-second submit delay. The completed transcript showed one user prompt for each payload and no editor-only residue, so the evidence selects `paste_enter_count = 1` with a provider-tunable submit delay.

Both `/quit` and `/exit` returned the pane to zsh. Ctrl-D, Ctrl-C, Ctrl-C twice, and Ctrl-Q remained in Grok after three seconds. `/quit` is the selected normal exit command; Ctrl-C remains a later cancellation fallback rather than the normal path.

## Subagent Security Findings

With `--no-subagents --deny Bash --deny Edit`, direct shell write returned `Denied by permission policy` and did not create `/tmp/cao_grok_phase0_security_probe.txt`. The combined direct Edit, subagent shell, and subagent Edit probe created neither requested file and showed write/shell denial while subagents were disabled. The read-only MCP inventory contained no configured non-CAO file-write server. This supports Gate B for the tested restricted/read-only scenario; the later provider must preserve the `--no-subagents` rule whenever Bash is disallowed and must document the boundary for profiles that explicitly allow Bash.

## MCP Path A

**SKIP / unverified.** The unregistered helper `mcp/identity_server.py` reports only PID, invocation ID, `CAO_TERMINAL_ID` presence/value, and allowlisted metadata. Existing `grok mcp doctor --json` showed two healthy project servers, but neither is the identity helper. Registering a static helper would require changing shared Grok configuration, which was forbidden. Therefore no two-terminal identity result is claimed.

## MCP Path B

**SKIP / unverified.** Read-only inspect/doctor output confirmed the user config and project `.mcp.json` discovery surfaces, but no dynamic `${CAO_TERMINAL_ID}` config was installed. Registration-time versus MCP-process-start expansion is unknown. No shared literal terminal ID was written.

## MCP Path C

**NO-GO.** Captured `grok mcp add --help` documents `-e, --env <KEY=value>` as an environment assignment. It does not advertise key-only `CAO_TERMINAL_ID` forwarding. The key-only mutation command was not run because it could alter shared config. Path C therefore cannot be treated as Codex/Kimi-style forward-by-name.

## Concurrency Result

No 20-check concurrency run was performed. It is only required for a path that first appears safe; Paths A/B were unverified under the no-config-write constraint and Path C failed its documented interface check. Running concurrent sessions against an unverified static/shared identity would risk false evidence and cross-terminal contamination, so this part is explicitly SKIP rather than fabricated.

## Gate Decisions

- Gate A: **GO** — readiness, submission, completion, and `/quit` exit are observable from real captures, with version-pinning/recalibration required before implementation.
- Gate B: **GO** — native deny rules plus `--no-subagents` blocked the tested direct and delegated write attempts.
- Gate C: **NO-GO** — no safe per-terminal identity forwarding path was verified without shared config mutation.

## Supported V1 Outcome

LIFECYCLE_ONLY

## Tests

- PASS: Black check on both evidence helper files.
- PASS: isort check on both evidence helper files.
- PASS: mypy on both evidence helper files.
- PASS: 16 existing provider-manager unit tests.
- PASS: pyte rendering helper over 19 captured ANSI streams.
- SKIP: native auth-error, native selection-wait, native permission-approval, non-CAO MCP write, and MCP 20-check concurrency probes for the reasons recorded above.
- No live CAO `grok_cli` integration/E2E test was run because the provider is intentionally not implemented or registered in this phase.

## Blockers

- Grok auto-updated from the requested 0.2.93 baseline to 0.2.101 during capture. The evidence is retained, but implementation must pin/recalibrate the supported version.
- Gate C is not supported by this evidence. Later work must follow the lifecycle-only route and must not implement orchestration unless a new, approved Phase 0 experiment proves safe per-terminal identity forwarding.
- Native question/selection, approval, and authentication-error surfaces were unavailable without unsafe or destructive setup; they are explicit skips, not inferred behavior.

## Next Recommended Prompt

Prompt 1R should review this evidence, the mixed-version boundary, the explicit skips, and the Gate C NO-GO/lifecycle-only routing before any provider registration or implementation prompt.

Completed at: Wed Jul 15 20:01:47 CST 2026
