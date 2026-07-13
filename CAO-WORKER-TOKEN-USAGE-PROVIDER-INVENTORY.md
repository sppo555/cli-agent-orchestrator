# CAO Worker Token Usage — Provider Inventory (4.17.5)

- Reviewed: 2026-07-13
- Scope: evidence inventory and structured-worker usage-source contract
- Runtime status: interactive remains estimate-only; Claude Code and Codex have
  strict structured-worker adapters; all other providers remain estimated
- Native/provider-reported coverage: 2/9

## Evidence boundary

This inventory distinguishes the existing interactive `run_agent_step()`
completion seam from the explicit structured worker mode. Interactive captures
a final terminal message and estimates `ceil(text_length / 4)`; it does not
consume a provider usage event, local usage log, or billing API. Structured
mode consumes only the provider's machine-readable stdout.

No provider is marked native from a CLI name, a screen string, a model name, or
an arbitrary number in ordinary response text. A native adapter requires a
sanitized fixture, provenance/version, field semantics, and a reviewed privacy
boundary in 4.17.5.

## Nine-provider inventory

| Provider | Machine-readable usage in structured mode | Usage source | Field semantics | Fixture provenance | Parser failure/fallback | Privacy boundary |
|---|---|---|---|---|---|---|
| `kiro_cli` | No | No native source observed | Input/output/total/cache/reasoning unavailable | No sanitized fixture; adapter not approved | Return `None`; retain shared estimate | No prompt/response/transcript capture |
| `claude_code` | Yes | Structured JSON/JSONL result or assistant usage event | Non-negative input/output; total is input + output | Sanitized contract fixture in `test/services/fixtures/` | Return `None`; retain shared estimate | No prompt/response/transcript capture |
| `codex` | Yes | JSONL `turn/completed` or `turn.completed` usage event | Non-negative input/output; total is input + output; cached field is not double-counted | Sanitized contract fixture in `test/services/fixtures/` | Return `None`; retain shared estimate | No prompt/response/transcript capture |
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

The contract implementation lives in
`src/cli_agent_orchestrator/services/token_usage_contract.py`. The structured
worker currently enables only Claude Code and Codex; interactive execution
continues to use the estimate path for every provider.

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
