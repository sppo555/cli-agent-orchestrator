# Grok CLI Token Native — Implementation Review R2

日期：2026-07-16  
Repository：`/Users/alex/Developer/cli-agent-orchestrator`  
工作分支：`cao-tailscale-integration`  
Base HEAD：`81722ea`  
狀態：**Blocker addressed；ready for re-review；尚未 commit**

## 1. R2 結論

R1 review 提出的 production blocker 成立：Grok 的 `--single` 是帶值參數，prompt
必須緊接在 `--single` 後面。R1 implementation 將其他 options 放在兩者之間，
可能造成 prompt 綁定錯誤。

R2 已修正 command ordering，新增精確 argv regression tests，並使用實際 Grok
0.2.101 與 production command builder 驗證成功。

本次重新申請的 review scope：

```text
Structured Grok token native: READY FOR RE-REVIEW
Interactive/assign Grok token native: OUT OF SCOPE, remains estimated
Grok CAO MCP orchestration: unchanged, Gate C remains NO-GO
```

## 2. R1 blocker

### Review finding

`run_structured_worker_step()` 使用以下通用 launch pattern：

```python
await asyncio.create_subprocess_exec(*command, prompt, ...)
```

因此 prompt 永遠被追加到 command 尾端。

R1 Grok builder 的尾端是：

```text
--single --output-format streaming-json --session-id <UUID>
```

通用 runner 追加 prompt 後形成：

```text
--single --output-format streaming-json --session-id <UUID> <PROMPT>
```

這不符合 Grok help 所示的 `--single <PROMPT>` contract。原測試只檢查 options
存在及 prompt 位於 argv 最尾端，反而沒有驗證 prompt 是否緊接 `--single`，因此
未能攔截問題。

### R1 判定修正

R1 的 GO 判定已撤回。修正前正確判定是：

```text
CHANGES REQUESTED
```

## 3. R2 fix

Grok structured builder 現在將所有其他 options 放在前面，並固定讓 `--single`
成為最後一個 option：

```text
--output-format streaming-json --session-id <UUID> --single
```

通用 runner 追加 prompt 後，production argv 尾端為：

```text
--output-format streaming-json --session-id <UUID> --single <PROMPT>
```

核心 invariant：

```python
argv[-2:] == ["--single", prompt]
```

此修正不需要為 Grok 建立另一套 subprocess lifecycle，也不改變 Claude/Codex
structured command contract。

## 4. Code changes for blocker

### `src/cli_agent_orchestrator/providers/grok_cli.py`

- 將 `--single` 移到 structured command options 的最後。
- 加入 load-bearing comment，說明 runner 會把 prompt 追加到 argv。
- 保留 `--output-format streaming-json`、fresh `--session-id`、profile/rules/model/
  permission wiring。

### `test/providers/test_grok_cli_unit.py`

- 驗證 builder 尾端順序：

```text
--output-format streaming-json --session-id attempt-id --single
```

- 模擬 runner 追加 prompt，精確驗證：

```text
--single do it
```

### `test/services/test_structured_worker.py`

- mock command 改為符合真實 builder contract。
- 不再只驗證部分 prefix 或 `args[-1]`。
- 現在驗證完整 spawn argv：

```python
(
    "grok",
    "--output-format",
    "streaming-json",
    "--single",
    "do it",
)
```

## 5. Production-path live verification

驗證使用實際 `GrokCliProvider.build_structured_command()` 產生 command，接著採用與
production worker 相同的方式追加 prompt：

```python
argv = [*provider.build_structured_command(), prompt]
```

執行環境：

```text
grok 0.2.101 (5bc4b5dfadcf) [stable]
cwd=/tmp
```

驗證項目：

1. `argv[-2:] == ["--single", prompt]`。
2. Grok process exit code 為 0。
3. stdout 可解析出恰好一個 terminal `end` event。
4. `end.usage.total_tokens > 0`。

結果：

```text
production argv smoke: ok; argv ends --single <PROMPT>; end.usage received
```

這次 smoke 使用真實 command builder 與真實 Grok binary，不是 mock-only 驗證。

## 6. Structured native contract（未變更）

Production data source 仍是 Grok process-local `streaming-json` terminal `end`
event，不使用 TUI 或共享資料。

| CAO field | Grok source | Normalization |
|---|---|---|
| `input_tokens` | `input_tokens + cache_read_input_tokens` | cache-read 計入 provider-processed input |
| `output_tokens` | `output_tokens` | 已包含 reasoning，不重複加總 |
| `total_tokens` | `total_tokens` | 必須等於 normalized input + output |
| `model` | 唯一 `modelUsage` key | 多 model 時不臆測 |
| `estimated` | valid adapter result | valid native 為 false，否則 fallback true |

Parser 只接受完整的 terminal `type=end` JSON object。missing、malformed、負數、
錯誤型別或 total mismatch 都回 `None`，由 structured worker 使用既有 estimate
fallback，且不阻塞 worker completion。

## 7. Isolation and privacy boundary（未變更）

- 每個 structured invocation 使用獨立 child process。
- 每個 attempt 產生 fresh `--session-id`。
- usage 只讀該 child process stdout。
- 不讀 Grok TUI footer、scrollback、transcript、session log 或 rollout log。
- 不修改 `~/.grok/config.toml`、project config、MCP 或 plugin config。
- 不開啟 Grok CAO MCP orchestration。

Interactive/assign seam 沒有取得相同的 process-local channel，因此仍為
`estimated-only`。

## 8. Verification summary

Blocker 修正後的聚焦 suite：

```text
101 passed
```

先前完整 token/API related suite：

```text
132 passed, 25 warnings
```

其他檢查：

```text
black --check: pass
isort --check-only: pass
mypy for touched source files: pass
git diff --check: pass
real Grok 0.2.101 production argv smoke: pass
```

Warnings 為既有 FastAPI/Pydantic deprecation 與 SQLite test ResourceWarning，沒有
新增 test failure。

## 9. R2 reviewer checklist

- [ ] 確認 production argv 尾端是 `--single <PROMPT>`。
- [ ] 確認 regression test 驗證完整 spawn argv，而非僅驗證 options 存在。
- [ ] 確認真實 Grok smoke 使用 production command builder。
- [ ] 確認 Grok process 成功回傳 terminal `end.usage`。
- [ ] 確認此修正沒有改變 Claude/Codex structured launch。
- [ ] 確認 native parser、normalization 與 estimate fallback 仍符合 R1 review。
- [ ] 確認批准範圍只涵蓋 structured native。
- [ ] 確認 interactive/assign 仍為 estimated。
- [ ] 確認 MCP / Gate C 無變更。

## 10. Requested decision

```text
Structured Grok token native: GO / CHANGES REQUESTED
Interactive/assign: OUT OF SCOPE, remains estimated
MCP / Gate C: unchanged
```
