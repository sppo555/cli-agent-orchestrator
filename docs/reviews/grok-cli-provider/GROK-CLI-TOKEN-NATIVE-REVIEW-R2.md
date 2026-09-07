# Grok CLI Token Native — Review Report R2

日期：2026-07-16  
Repository：`/Users/alex/Developer/cli-agent-orchestrator`  
工作分支：`cao-tailscale-integration`  
Base HEAD：`81722ea`  
對應實作報告：`GROK-CLI-TOKEN-NATIVE-IMPLEMENTATION-REVIEW-R2.md`  
狀態：**尚未 commit**

## 1. 審查結論

| 範圍 | 判定 |
|---|---|
| Structured Grok token native | **APPROVED (GO)** |
| Interactive / assign Grok token native | **OUT OF SCOPE**（維持 estimated） |
| Grok CAO MCP orchestration / Gate C | **不變**（仍為 NO-GO / 未開啟） |

```text
Structured Grok token native: APPROVED
Interactive/assign Grok token native: OUT OF SCOPE, remains estimated
Grok CAO MCP orchestration: unchanged, Gate C remains NO-GO
```

R1 的 production blocker（`--single <PROMPT>` argv 順序錯誤）已在 R2 修復並經獨立 re-review 確認。  
殘餘項目皆為非阻擋（suggestion / nit），不阻擋本次 structured native 批准。

## 2. 審查範圍

本次 re-review 僅針對 **explicit structured worker** 的 Grok native token usage：

- Provider：`grok_cli`
- 資料來源：process-local `--output-format streaming-json` terminal `end.usage`
- 不批准：TUI footer、response 散文 token 數字、scrollback / transcript、session / rollout log、共享 config 變更
- 不批准：interactive / assign native

審查依據：

- 未提交 diff（相對 `81722ea`）
- 實作報告 R2
- R1 review 判定與 blocker 追蹤
- 關鍵原始碼與測試：`grok_cli.py`、`structured_worker.py`、`token_usage_adapters.py`、`token_usage_contract.py` 及相關 tests / fixture

## 3. R1 → R2 追蹤

| R1 議題 | 嚴重度 | R2 處置 |
|---|---|---|
| `--single` 非 value-last；prompt 綁定錯誤 | bug | **已修復** |
| 缺 Grok worker 層 estimate fallback 測試 | suggestion | 仍開（非阻擋） |
| `extract_usage` docstring 過時 | suggestion | 仍開（非阻擋） |
| size-check 含 `STARTUP_GUARD` 後再 strip | nit | 仍開（非阻擋） |
| 缺 multi-model / missing `total_tokens` adapter 案例 | nit | 仍開（非阻擋） |

### R1 blocker 修復確認

通用 runner 固定為：

```python
create_subprocess_exec(*command, prompt, ...)
```

R2 builder 尾端為：

```text
--output-format streaming-json --session-id <UUID> --single
```

runner 追加 prompt 後生產 argv 尾端：

```text
--output-format streaming-json --session-id <UUID> --single <PROMPT>
```

Invariant：

```python
argv[-2:] == ["--single", prompt]
```

Provider unit test 與 structured-worker spawn argv 斷言已鎖住完整路徑。  
Claude / Codex structured launch 未被改壞。

## 4. 合約審查結果

### 4.1 資料來源與隔離

- 每個 structured invocation 使用獨立 child process
- 每次 attempt 使用 fresh `--session-id`
- 只解析該 process stdout 的 terminal `type=end` + `usage`
- 不讀 TUI、共享 home log、transcript、共享 Grok/MCP/plugin config
- 不開啟 CAO MCP orchestration

### 4.2 Token 正規化

| CAO 欄位 | 規則 | 判定 |
|---|---|---|
| `input_tokens` | `input_tokens + cache_read_input_tokens` | 通過 |
| `output_tokens` | 使用 `output_tokens`；不重加 `reasoning_tokens` | 通過 |
| `total_tokens` | 必須嚴格等於 normalized input + output | 通過 |
| `model` | 僅在唯一 `modelUsage` key 時採用 | 通過 |
| `estimated` | 合法 native 為 `false`；否則 estimate fallback | 通過 |

### 4.3 失敗行為

- missing / malformed / 負數 / 型別錯誤 / total mismatch → adapter `None` → estimate
- worker completion 不因 native 缺失而失敗
- 普通 text / TUI 樣式字串不產生 native record

## 5. 殘餘非阻擋項目

可於後續小修處理，**不阻擋 APPROVED**：

1. 補 Grok structured-worker 層「無 `end.usage` → COMPLETED + estimated=true」測試  
2. 更新 `extract_usage` docstring，列出 Claude / Codex / Grok  
3. structured size-check 改為 strip `STARTUP_GUARD` 後再量  
4. adapter 補 multi-key `modelUsage` 與 missing `total_tokens` 案例  

## 6. Reviewer checklist

- [x] production argv 尾端為 `--single <PROMPT>`
- [x] regression test 驗證完整 spawn argv
- [x] 真實 Grok smoke 使用 production command builder（依 R2 報告；re-review 接受其實作證據）
- [x] native parser / normalization / estimate fallback 仍符合合約
- [x] Claude / Codex structured launch 未受影響
- [x] 批准範圍僅 structured native
- [x] interactive / assign 仍為 estimated
- [x] MCP / Gate C 無變更

## 7. 最終判定

```text
APPROVED
```

**批准範圍（僅限）：**

- Grok CLI **explicit structured worker** native token usage  
- provider-owned process-local `streaming-json` terminal `end.usage`  
- 合法 payload 時 `estimated=false`；否則 estimate fallback  

**明確不在本次批准內：**

- interactive TUI / assign native token usage  
- 解析 footer / scrollback / session / rollout log  
- 共享 Grok config / MCP / plugin 變更  
- 開啟 Grok CAO MCP orchestration  
- 將 token usage 宣稱為 billing data  

---

**Decision stamp**

```text
Review: R2
Structured Grok token native: APPROVED
Interactive/assign: OUT OF SCOPE (estimated)
MCP / Gate C: NO CHANGE
Date: 2026-07-16
Base HEAD: 81722ea
Working tree: uncommitted at review time
```
