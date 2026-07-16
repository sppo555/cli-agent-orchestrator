# Grok CLI Token Usage Status Report

日期：2026-07-16  
Repository：`/Users/alex/Developer/cli-agent-orchestrator`

## 結論

Grok CLI (`grok_cli`) 已開始實作 native token usage：**explicit structured
worker 已使用 native usage**；persistent interactive/assign seam 仍是
`estimated-only`。

production data source 是 Grok 0.2.101 headless process 的
`--output-format streaming-json` terminal `end` event。Grok TUI 畫面、普通
response text、terminal transcript、session log 與 rollout log 仍不得使用。

## Branch 與 commit 狀態

目前工作分支是：

```text
cao-tailscale-integration
```

目前 integration HEAD：

```text
81722ea
Merge branch 'custom/4.19-memory-scope-isolation' into cao-tailscale-integration
```

`origin/cao-tailscale-integration` 與本地完全同步。

Grok 相關 branch：

| Branch | HEAD | 狀態 |
|---|---|---|
| `custom/4.18-grok-cli-provider` | `4671c12` | 已合入 integration，與 origin 同步 |
| `feat/grok-cli-provider` | `b3cfb38` | 原始 Grok provider implementation branch |
| `feat/grok-cli-phase0-evidence` | `32db5a1` | 本地 Phase 0 evidence branch，無 remote tracking |

Token branch 目前是：

```text
custom/4.17.5-token-usage-recovery-ux@9289e16
```

它已經不是早期報告中記錄的 `12a8af9` 或 `a7c8f43`。

## Token implementation coverage

目前已核准 native usage 的 provider：

| Provider | Structured native | Interactive/assign native | 目前狀態 |
|---|---:|---:|---|
| Claude Code | Yes | Yes | Native |
| Codex | Yes | Yes | Native |
| Antigravity | No reliable structured usage payload | Yes，在 correlation 條件成立時 | Native fallback |
| Grok CLI | Yes，headless `streaming-json` | No | Structured native；interactive estimated |
| Kiro CLI | No | No | Estimate-only |
| Kimi CLI | No | No | Estimate-only |
| Copilot CLI | No | No | Estimate-only |
| OpenCode CLI | No | No | Estimate-only |
| Hermes | No | No | Estimate-only |
| Cursor CLI | No | No | Estimate-only |

注意：一般 `run_agent_step()` interactive seam 仍保持 estimate-only；目前的
interactive native capture 只在已經有 provider-owned usage correlation 的
assign flow 中使用。

## Token branch 後續更新

早期 token branch 完成後，後續又加入了幾個 commit：

| Commit | 內容 | 是否代表 Grok native |
|---|---|---:|
| `b79cf96` | Capture native interactive worker usage | No；主要是 Claude/Codex/Agy |
| `ec43b3a` | Merge latest upstream main | No |
| `9289e16` | Retain token markers across stale completion edges | No；是 native usage correlation 修正 |

因此，token branch 有更新不等於 Grok 已經取得 native token support。

## Grok 目前實作邊界

`GrokCliProvider` 目前是 persistent interactive TUI provider，功能邊界是：

- 可以啟動 Grok interactive TUI。
- 可以透過 Grok native `--deny` rules 做工具限制。
- 可以做 lifecycle status detection 與 response extraction。
- 支援 explicit Grok structured worker mode，使用單次 process 與唯一 `--session-id`。
- 不支援 CAO MCP orchestration。
- 不複製 profile `mcpServers` 到 Grok config。
- 不修改 `~/.grok/config.toml`、project `.grok/config.toml` 或 shared plugin/MCP config。
- 有嚴格的 Grok `end.usage` adapter；缺失或 malformed 時回 estimate fallback。

目前 token contract 的 structured native provider set 是：

```python
{ProviderType.CLAUDE_CODE.value, ProviderType.CODEX.value, ProviderType.GROK_CLI.value}
```

`extract_native_usage("grok_cli", ...)` 只接受 terminal `end` JSON event，並把
`input_tokens + cache_read_input_tokens` 正規化為 input；`reasoning_tokens` 已包含
在 output，不重複加總。無有效 payload 時由上層保留 shared estimate fallback。

## 為什麼不能直接把 Grok 標成 native

Phase 0 當時只確認 lifecycle/TUI。2026-07-16 對 Grok 0.2.101 的 live probe 已
確認 headless `streaming-json` terminal `end` event 同時帶有 `sessionId`、
`requestId`、`usage` 與 `modelUsage`，可由單一 spawned process stdout 與 fresh
`--session-id` 做 attempt-local correlation。

特別不能使用：

- TUI footer 上的數字或文字。
- response 中偶然出現的 token 數字。
- terminal scrollback/transcript。
- Grok session log 或 rollout log。
- 沒有 per-process identity correlation 的共享資料。

這些資料不是已核准的 production token source，且容易造成重複計算、跨 terminal
污染或把普通文字誤判成 token usage。

## Structured native Gate 結果

本次 structured seam 的 Gate 結果：

1. provider-owned machine-readable payload：完成，terminal `end.usage`。
2. input/output/total/cache/reasoning 語義：完成。
3. 單一 attempt correlation：完成，child stdout + fresh `--session-id`。
4. 並行隔離：structured process pipe 天然分離，不讀共享資料。
5. sanitized fixture 與 parser tests：完成。
6. malformed、缺欄位與 total mismatch：完成 fallback tests；structured 是單次
   terminal counter，沒有跨 turn 累積 counter。
7. 不修改共享 Grok/MCP/plugin config：完成。
8. provider usage inventory：已更新。
9. native source 缺失時 estimate fallback：完成，不阻塞 worker completion。

interactive/assign seam 尚未取得相同的 process-local structured channel，正確產品
行為仍是：

```text
grok_cli interactive/assign token usage = estimated
```

## 目前判定

Grok structured native 第一階段已達 gate 並完成 adapter/worker 接線；只有有效
`end.usage` 才設定 `estimated=false`。interactive TUI/assign 尚無相同安全來源，
仍維持 estimated，且不得解析 footer 或共享 session/rollout 資料。
