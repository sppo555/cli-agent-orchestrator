# CAO Worker Token Usage — Provider Inventory (4.17.3)

- Reviewed: 2026-07-13
- Scope: evidence inventory and usage-source contract only
- Runtime status: all nine registered providers continue to use the shared estimated path
- Native/provider-reported coverage: 0/9

## Evidence boundary

This inventory is based on the repository's current provider manager and the
common `run_agent_step()` completion seam. The current flow captures a final
terminal message and estimates `ceil(text_length / 4)`; it does not consume a
provider usage event, structured response, local usage log, or billing API.

No provider is marked native from a CLI name, a screen string, a model name, or
an arbitrary number in ordinary response text. A native adapter requires a
sanitized fixture, provenance/version, field semantics, and a reviewed privacy
boundary in 4.17.4.

## Nine-provider inventory

| Provider | Machine-readable usage in current CAO path | Usage source | Field semantics | Fixture provenance | Parser failure/fallback | Privacy boundary |
|---|---|---|---|---|---|---|
| `kiro_cli` | No | No native source observed | Input/output/total/cache/reasoning unavailable | No sanitized fixture; adapter not approved | Return `None`; retain shared estimate | No prompt/response/transcript capture |
| `claude_code` | No | No native source observed | Input/output/total/cache/reasoning unavailable | No sanitized fixture; adapter not approved | Return `None`; retain shared estimate | No prompt/response/transcript capture |
| `codex` | No | No native source observed | Input/output/total/cache/reasoning unavailable | No sanitized fixture; adapter not approved | Return `None`; retain shared estimate | No prompt/response/transcript capture |
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
`src/cli_agent_orchestrator/services/token_usage_contract.py`; it intentionally
returns `None` for every provider until Gate D approves a native adapter.
