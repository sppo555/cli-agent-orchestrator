# Grok CLI Token Native — Implementation Review

日期：2026-07-16  
Repository：`/Users/alex/Developer/cli-agent-orchestrator`  
工作分支：`cao-tailscale-integration`  
Base HEAD：`81722ea`  
狀態：**Changes addressed；ready for re-review；尚未 commit**

## 1. Review 結論摘要

本次完成的是 **Grok explicit structured worker native token usage**，不是
persistent interactive/assign native usage。

實作使用 Grok 0.2.101 provider-owned、machine-readable 的
`--output-format streaming-json` terminal `end` event。每個 structured attempt
由 CAO 啟動獨立 Grok process，並產生 fresh `--session-id`，usage 只從該 process
stdout 解析，因此不讀取 TUI、terminal scrollback、session log、rollout log 或
共享 config。

建議 review 判定：

- Structured native：可審查是否批准。
- Interactive/assign native：本 patch 未實作，繼續 `estimated-only`。
- Grok lifecycle-only 與 Gate C NO-GO：不受本 patch 改變；仍未開啟 CAO MCP
  orchestration。

## 2. Live evidence

本機 Grok CLI：

```text
grok 0.2.101 (5bc4b5dfadcf) [stable]
```

Live probe command 使用 single-turn headless mode、fresh UUID 與
`streaming-json`。最終 provider event 的 sanitized shape：

```json
{
  "type": "end",
  "stopReason": "EndTurn",
  "sessionId": "<attempt-session-uuid>",
  "requestId": "<request-uuid>",
  "usage": {
    "input_tokens": 1636,
    "cache_read_input_tokens": 11136,
    "output_tokens": 24,
    "reasoning_tokens": 19,
    "total_tokens": 12796
  },
  "num_turns": 1,
  "modelUsage": {
    "grok-4.5": {
      "inputTokens": 1636,
      "outputTokens": 24,
      "cacheReadInputTokens": 11136,
      "modelCalls": 1
    }
  }
}
```

Observed invariant：

```text
(input_tokens + cache_read_input_tokens) + output_tokens
= (1636 + 11136) + 24
= 12796 total_tokens
```

`reasoning_tokens=19` 是 `output_tokens=24` 的組成，不可再次加到 total。

## 3. Token normalization contract

CAO native record 採以下 mapping：

| CAO field | Grok source | 規則 |
|---|---|---|
| `input_tokens` | `usage.input_tokens` + `usage.cache_read_input_tokens` | cache-read 是 provider 已處理的 input |
| `output_tokens` | `usage.output_tokens` | 已包含 reasoning，不重複加總 |
| `total_tokens` | `usage.total_tokens` | 必須嚴格等於 normalized input + output |
| `model` | 唯一的 `modelUsage` key | 只有恰好一個 model 時採用 |
| `estimated` | adapter success | valid native usage 為 `false`；否則 fallback 為 `true` |

Parser 只接受 `type=end` 的完整 JSON object。普通 response、TUI footer
`12K / 500K`、partial event、負數、boolean、string counter 或 total 不一致皆不會
成為 native record。

## 4. Attempt correlation 與 concurrency boundary

Structured worker 的隔離方式：

1. 每個 invocation 建立獨立 Grok child process。
2. command builder 每次產生 fresh UUID，傳給 `--session-id`。
3. CAO 只讀該 child process 的 stdout。
4. usage 必須出現在該 stream 的 terminal `end` event。
5. 不掃描 cwd、shared home、terminal transcript 或其他 Grok process 的資料。

因此兩個並行 structured workers 各自擁有 process pipe 與 session ID，不會從共享
資料來源讀到對方的 usage。

此 correlation 不能直接套用到 persistent interactive TUI；interactive/assign
仍維持 estimated。

## 5. Implementation changes

### Provider command

`src/cli_agent_orchestrator/providers/grok_cli.py`

- 新增 `build_structured_command()`。
- 沿用既有 profile/model/effort/permission deny/rules wiring。
- 移除只適用 TUI startup 的 `STARTUP_GUARD`。
- 加入 `--single --output-format streaming-json --session-id <fresh UUID>`。
- `--single` 固定為最後一個 option，使 runner 追加的 prompt 緊接其後，argv
  形成 `... --single <PROMPT>`。
- 不寫入 Grok user/project config。

### Structured worker dispatch

`src/cli_agent_orchestrator/services/structured_worker.py`

- 將 `grok_cli` 加入 explicit structured provider allowlist。
- 使用 `GrokCliProvider.build_structured_command()`。
- response 只由 Grok `text` JSON events 組合。
- native adapter 回 `None` 時沿用既有 estimate fallback，worker completion 不失敗。

### Native usage adapter

`src/cli_agent_orchestrator/services/token_usage_adapters.py`

- 新增 `extract_grok_cli_usage()`。
- 新增 `extract_grok_cli_last_message()`。
- provider dispatch 加入 `ProviderType.GROK_CLI`。
- 嚴格驗證型別、非負值與 total invariant。

### Evidence contract and inventory

`src/cli_agent_orchestrator/services/token_usage_contract.py`  
`CAO-WORKER-TOKEN-USAGE-PROVIDER-INVENTORY.md`

- structured native provider set 加入 `grok_cli`。
- 記錄 source、field semantics、fixture provenance、fallback 與 privacy boundary。
- structured native coverage 從 2/10 更新為 3/10。

### Tests and fixture

- `test/services/fixtures/grok_cli_usage_stream.jsonl`
- `test/services/test_token_usage_adapters.py`
- `test/services/test_structured_worker.py`
- `test/services/test_token_usage_contract.py`
- `test/providers/test_grok_cli_unit.py`

涵蓋 sanitized native payload、cache normalization、model extraction、message
extraction、structured dispatch、fresh session ID command、malformed payload 與 TUI
false-positive resistance。

另有精確 argv regression assertion，驗證 production spawn argv 尾端必須是
`--single`, `<PROMPT>`；避免 options 插入兩者之間造成 prompt 綁定錯誤。

## 6. Failure behavior

| 情境 | 行為 |
|---|---|
| valid terminal `end.usage` | 儲存 native record，`estimated=false` |
| missing `end` | adapter 回 `None`，使用 estimate |
| missing usage field | adapter 回 `None`，使用 estimate |
| wrong type / negative count | adapter 回 `None`，使用 estimate |
| total invariant 不成立 | adapter 回 `None`，使用 estimate |
| ordinary text 出現 token 數字 | 不解析，使用 estimate |
| structured process non-zero exit | 維持既有 `StructuredWorkerError` 行為 |
| timeout | 維持既有 kill + timeout 行為 |

## 7. Verification result

執行的相關 test suite：

```text
132 passed, 25 warnings in 1.70s
```

額外檢查：

```text
black --check: pass
isort --check-only: pass
mypy (4 touched source files): pass
git diff --check: pass
Grok 0.2.101 production argv smoke: pass (`... --single <PROMPT>` + `end.usage` received)
```

Warnings 是既有 FastAPI/Pydantic deprecation 與測試 SQLite `ResourceWarning`；本次
測試沒有 failure。

## 8. Deliberate non-goals

本 patch 沒有：

- 從 Grok TUI footer 解析 `12K / 500K`。
- 讀取 terminal transcript/scrollback。
- 讀取 Grok session/rollout/debug log。
- 修改 `~/.grok/config.toml` 或 project `.grok/config.toml`。
- 複製或修改 Grok MCP/plugin config。
- 開啟 Grok CAO MCP orchestration。
- 宣稱 persistent interactive/assign 已 native。
- 將 token usage 宣稱為 billing data。

## 9. Known limitations and follow-up

1. Evidence 目前校準於 Grok 0.2.101；未來 CLI schema 變更會安全 fallback，但需新
   fixture 才能恢復 native。
2. 首版只接受 snake_case `usage` contract；不猜測其他格式。
3. Multi-model `modelUsage` 不臆測單一 model，token counts 仍可 native，model 回到
   configured/default value。
4. Interactive/assign native 尚缺安全、per-attempt 的 provider-owned usage channel。
5. 若要把 interactive/assign 升級 native，需另立 evidence gate 與 concurrency
   tests，不應擴張本 parser 去讀共享資料。

## 10. Reviewer checklist

- [ ] 同意 structured stdout `end` event 是 provider-owned native source。
- [ ] 同意 fresh `--session-id` + child stdout pipe 滿足 attempt correlation。
- [ ] 同意 input 應包含 `cache_read_input_tokens`。
- [ ] 確認 `reasoning_tokens` 不應重複加到 output/total。
- [ ] 確認 total mismatch 必須 fallback，不可修補或臆測。
- [ ] 確認 malformed/missing native payload 不影響 worker completion。
- [ ] 確認普通 response/TUI token 字樣無 false positive。
- [ ] 確認沒有 shared Grok/MCP/plugin config mutation。
- [ ] 確認 review 僅批准 structured native，不包含 interactive/assign native。
- [ ] 決定是否要求 Grok CLI minimum-version gate；目前策略是 schema validation +
  safe fallback。

## 11. Suggested review decision

```text
Structured Grok token native: GO / CHANGES REQUESTED
Interactive/assign Grok token native: OUT OF SCOPE, remains estimated
Grok CAO MCP orchestration: unchanged, Gate C remains NO-GO
```
