# CAO Worker Token Usage — Provider Inventory (4.17.5)

- Reviewed: 2026-07-13
- Scope: structured and assign/interactive usage-source contract
- Runtime status: new Claude Code and Codex assign/interactive turns use
  provider-owned session/rollout usage; their structured adapters remain
  native. Other providers remain estimated where a capture seam exists.
- Native/provider-reported coverage: 2/9

## Evidence boundary

This inventory distinguishes three seams. Explicit structured worker mode
consumes provider-owned machine-readable stdout. The legacy interactive
`run_agent_step()` seam still estimates from its final message. The production
non-blocking `assign` seam keeps its tmux lifecycle and now reads only usage
metadata from the exact Claude session or Codex rollout owned by that worker.

No provider is marked native from a CLI name, a screen string, a model name, or
an arbitrary number in ordinary response text. A native adapter requires a
sanitized fixture, provenance/version, field semantics, and a reviewed privacy
boundary in 4.17.5.

## Nine-provider inventory

| Provider | Native mode | Usage source | Field semantics | Fixture provenance | Parser failure/fallback | Privacy boundary |
|---|---|---|---|---|---|---|
| `kiro_cli` | No | No native source observed | Input/output/total/cache/reasoning unavailable | No sanitized fixture; adapter not approved | Return `None`; retain shared estimate | No prompt/response/transcript capture |
| `claude_code` | Structured + new assign/interactive sessions | Structured JSON/JSONL or the worker's deterministic `--session-id` JSONL | Input is uncached + cache creation + cache read; output is provider output; total is their sum | Sanitized structured fixture plus session-log unit fixtures | Omit a native record when the exact usage payload is unavailable; never invent native data | Read usage/model/message-id fields only; never persist prompt, response, tool payload, transcript, or source path |
| `codex` | Structured + assign/interactive sessions | Structured turn completion or cumulative `token_count` delta from the rollout opened by the tmux pane's Codex process | Provider input already includes cached input; output includes provider output/reasoning; total is input + output | Sanitized structured fixture plus rollout-delta unit fixtures | Omit a native record when process-owned rollout correlation or usage is unavailable | Process/open-file correlation; read usage fields only and never persist rollout content or source path |
| `kimi_cli` | No | No native source observed | Input/output/total/cache/reasoning unavailable | No sanitized fixture; adapter not approved | Return `None`; retain shared estimate | No prompt/response/transcript capture |
| `copilot_cli` | No | No native source observed | Input/output/total/cache/reasoning unavailable | No sanitized fixture; adapter not approved | Return `None`; retain shared estimate | No prompt/response/transcript capture |
| `opencode_cli` | No | No native source observed | Input/output/total/cache/reasoning unavailable | No sanitized fixture; adapter not approved | Return `None`; retain shared estimate | No prompt/response/transcript capture |
| `hermes` | No | No native source observed | Input/output/total/cache/reasoning unavailable | No sanitized fixture; adapter not approved | Return `None`; retain shared estimate | No prompt/response/transcript capture |
| `cursor_cli` | No | No native source observed | Input/output/total/cache/reasoning unavailable | No sanitized fixture; adapter not approved | Return `None`; retain shared estimate | No prompt/response/transcript capture |
| `antigravity_cli` | No | No native source observed | Input/output/total/cache/reasoning unavailable | No sanitized fixture; adapter not approved | Return `None`; retain shared estimate | No prompt/response/transcript capture |

## Contract

```text
extract_usage(provider, execution_context, final_response) -> NativeUsage | None
```

- `None` is the safe result for missing, unknown, or malformed evidence.
- Parser failure must never fail worker completion.
- `native` maps to legacy `estimated=false`.
- `estimated` and `unknown` map to legacy `estimated=true`.
- `estimated` is provenance, not billing accuracy.

The structured contract lives in
`src/cli_agent_orchestrator/services/token_usage_contract.py`; interactive
turn correlation lives in `services/interactive_token_usage.py`. Claude uses a
deterministic session UUID so concurrent workers in one cwd cannot cross. Codex
binds the tmux pane's process tree to the rollout file it actually has open,
then persists the cumulative delta for the completed turn. The older
`run_agent_step()` interactive seam remains estimated, while production
`assign` turns are native for these two providers.

## Durable write recovery

SQLite is the primary sink. If a completed worker record cannot be written,
the same metadata-only record is appended to the owner-only
`token-usage-spool/pending.jsonl` file and fsynced. A background flusher replays
complete records with the original record id and timestamp; SQLite ignores a
duplicate record id after a crash between commit and spool acknowledgement.
Malformed or unknown-version records are quarantined, incomplete tails remain
visible, and the worker completion path is never failed by usage persistence.
The spool contains no prompt, response, transcript, session log, or raw provider
output.

The token-specific page also keeps provenance visible in the UI, supports a
validated custom date range, exports the current filtered rows as UTF-8 CSV
with formula-cell mitigation, and only renders local worker-result paths as
artifact links. Legacy nullable fields remain displayable as `Default` or
`unknown`; no App-level state or interactive terminal flow is involved.
