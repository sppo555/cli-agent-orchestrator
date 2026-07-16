# CAO Worker Token Usage — Provider Inventory (4.17.6)

- Reviewed: 2026-07-15
- Scope: structured and assign/interactive usage-source contract
- Runtime status: new Claude Code, Codex, and Agy assign/interactive turns use
  provider-owned session/rollout/conversation metadata. Claude and Codex
  structured adapters remain native; Agy structured/print output has no usage
  payload and retains estimated fallback.
- Native/provider-reported coverage: 3/9 for assign/interactive; 2/9 for structured

## Evidence boundary

This inventory distinguishes three seams. Explicit structured worker mode
consumes provider-owned machine-readable stdout. The legacy interactive
`run_agent_step()` seam still estimates from its final message. The production
non-blocking `assign` seam keeps its tmux lifecycle and now reads only usage
metadata from the exact Claude session, Codex rollout, or Agy conversation DB
owned by that worker.

No provider is marked native from a CLI name, a screen string, a model name, or
an arbitrary number in ordinary response text. A native adapter requires a
sanitized fixture, provenance/version, field semantics, and a reviewed privacy
boundary in 4.17.5.

## Nine-provider inventory

(The `grok_cli` provider and its native structured token-usage adapter are owned
by customization 4.18; see that branch's inventory row.)

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
| `antigravity_cli` | Assign/interactive sessions on Agy 1.1.x launched in CAO's isolated Agy workspace | `gen_metadata` protobuf counters from conversation DBs whose trajectory metadata contains that terminal-specific workspace URI | Snapshot each matching DB's maximum generation index, then sum GenerationMetadata `input_tokens` and `output_tokens` rows created after the marker; total is their sum; inner Claude/Gemini model comes from the worker profile | Sanitized metadata-only protobuf fixtures for Claude Sonnet/Opus and Gemini Pro/Flash plus live Agy 1.1.2 evidence | Shared cwd, missing correlation, schema mismatch, malformed protobuf, SQLite failure, or zero delta returns `None` and retains estimated fallback | Read-only SQLite; inspect the workspace URI only for correlation and decode only wrapper/schema discriminators and input/output integers; never decode or persist prompt, response, steps, tools, artifacts, or source path |

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
then persists the cumulative delta for the completed turn. Agy accepts native
capture only when the pane runs below CAO's terminal-specific isolated Agy
workspace root. It snapshots matching conversation DB generation indexes and,
at completion, reads later counters from old or newly created DBs carrying that
workspace URI. A shared repository cwd is intentionally left estimated because
it cannot safely distinguish concurrent Agy workers. The older
`run_agent_step()` interactive seam remains estimated, while production
`assign` turns are native for these three providers.

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
