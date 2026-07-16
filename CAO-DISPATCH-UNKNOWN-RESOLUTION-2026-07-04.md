# CAO 派工卡 UNKNOWN — 調查與修復報告

**日期**：2026-07-04
**環境**：`cao-EngVocabularyLeran` session（9-worker 部署，tmux backend），安裝為 editable install，執行中 server 由 `src/cli_agent_orchestrator` 匯入
**關聯前置報告**：`/Users/alex/Developer/EngVocabularyLeran/docs/tmp/cao-dispatch-failures-2026-07-03.md`

---

## 一、事發問題

Supervisor（code_supervisor）派工給 worker（planner=claude_code、developer=agy）時，**間歇性失敗**：

- 呼叫 `assign` 後，worker 終端被建立，但狀態**從頭到尾卡在 `UNKNOWN`**，一路撞到 `provider_init_timeout=240s` 天花板後被拆掉。
- Web UI 對應顯示該 worker 為 **Unknown**。
- Supervisor 反覆刪除、重派（同一 session 內建立/刪除 15+ 個 worker 終端），連續多個全新終端都失敗後停下回報使用者。

**關鍵二元現象（本次量測,精確秒數）**：

| terminal | provider | 結果 | 從建立到 reached idle |
|----------|----------|------|----------------------|
| dda65f08 | claude | ✅ | 7s |
| 7635c389 | claude | ✅ | 40s |
| e91af7d1 | claude | ✅ | 48s |
| 68a498c6 | claude | ❌ TIMEOUT | 244s |
| 07de8e32 | claude | ❌ TIMEOUT | 245s |
| 6fa9002c | claude | ❌ TIMEOUT | 245s |

成功者一律「幾十秒內」到 idle，失敗者一律撞 240s 天花板 —— **沒有中間地帶**。

**使用者關鍵觀察（決定性線索）**：只要在 Web page 打開該 worker 的 terminal，派工訊息**幾秒內**就會被 worker 收到；若太晚才打開（約 3 分鐘後）則一樣失敗。

---

## 二、造成原因

調查過程中排除了數個假設（見附錄），最終定位到**三個獨立問題**，其中 #2 是本次「一直失敗」的直接主因。

### #1 Timeout 反轉（放大器）
`/Users/alex/.aws/cli-agent-orchestrator/settings.json` 原本：
```json
{ "server": { "mcp_request_timeout": 180, "provider_init_timeout": 240 } }
```
- `assign` → `_create_terminal()` 發 `POST /terminals`，**client 逾時 = `mcp_request_timeout = 180s`**。
- server 端該 POST 內部跑 `provider.initialize()`，等 worker 到 IDLE，最長 **`provider_init_timeout = 240s`**（agy 寫死 180s）。
- `180 < 240` → 只要 worker 慢於 180s，**client 先逾時**（回 `Read timed out. (read timeout=180.0)`），但 server 仍把終端建出來 → 半初始化孤兒；後續 `send_message` 因該終端非 IDLE 而永遠 queue 不投遞。
- 這正是「超過約 3 分鐘（=180s）打開 terminal 也沒用」的原因：assign 早已放棄。

### #2 無人觀看的 tmux 背景 window 不 flush 渲染（**根因**）
CAO 的 worker 跑在 tmux 的**背景 window**（主 client 停在 supervisor window，沒在看 worker）。

- Ink-based 的 **Claude Code** 與 **antigravity/agy** CLI，**只有在有 client attach 觀看該 window 時才會把 TUI 重繪 flush 出來**。
- 無人觀看 → idle prompt 的 frame 不會流進 `pipe-pane` FIFO → StatusMonitor 的 rolling buffer 收不到 idle box → 狀態卡 `UNKNOWN` → `wait_until_status` 空等到 timeout。
- **在 Web page 打開 terminal**（4.11 客製會 attach 一個 grouped `caoview_*` PTY viewer）→ tmux 觸發該 pane 重繪 → idle frame 這時才 flush → StatusMonitor 立刻判定 IDLE → 任務投遞。

**驗證（現場實測,非推論）**：
- 對卡住的 claude worker `df3110a1` 手動 attach 一個 headless PTY viewer → log 顯示 `unknown → idle → reached idle → processing`（任務送達），attach 前它已卡 ~166 秒。
- 把卡住 worker 的畫面 `capture-pane` 下來餵進執行中的 `get_status()` → 回 **IDLE**（證明偵測邏輯本身沒問題，是 frame 沒送達 buffer）。
- 對卡住的 agy worker `6651c388` 用**同尺寸** headless attach → 立即 flush，pending 任務送達，agy 開始 processing（證明同尺寸 attach 即可觸發，不需改變視窗大小）。
- 此問題也會咬在更早的 `wait_for_shell`（10s）階段：agy `ea04d745` 連 shell prompt 都沒 flush → 10s 逾時 → agy 根本沒啟動，畫面只剩裸 shell。

### #3 agy 全域 MCP 過多（加重因素）
`~/.gemini/antigravity-cli/mcp/` 註冊了 **~11 個全域 MCP server**（argocd/docker/filesystem/gcloud/github/grafana/jenkins/kubernetes/prometheus + codebase-memory-mcp + context7）。每個 agy worker 啟動時要對它們逐一 handshake；其中連真實基礎設施的 server 若當下不健康會卡住 handshake，拖長/卡死 agy init。context7 走 `npx -y`（未全域安裝）也是變動延遲來源。此問題獨立於 #1/#2，本次未修，僅記錄。

---

## 三、如何修復

### 已修 #1（設定，待重啟生效）
把 client 逾時拉到大於所有 provider 的 init 等待：
```json
{ "server": { "mcp_request_timeout": 300, "provider_init_timeout": 240 } }
```
守則：`mcp_request_timeout` > 每個 provider 的 init 等待（agy 寫死 180、claude 用 240，故設 300）。
> ⚠️ 需**重啟 CAO server** 才生效；執行中的 server 仍是舊值 180。

### 已修 #2 —— 新客製 **4.13**（程式碼,已 merge 進 integration,待重啟生效）
在 worker init 期間，自動對該 pane attach 一個**短命的 headless PTY viewer**（沿用 4.11 的 grouped viewer 機制，尺寸對齊 pane 以免 reflow），並**週期性送 SIGWINCH re-render**，讓 shell prompt、CLI 啟動、idle box 全部 flush 進 StatusMonitor；init 一結束立即 detach 並還原視窗設定。**不用再靠人工打開 web terminal**。

> **重要（兩次迭代的教訓）**：第一版只「被動 attach viewer」**不夠** —— 實測 worker 掛著 viewer、畫面明明在 idle box，狀態仍卡 UNKNOWN 80 秒以上。原因是 CLI 只在啟動亂流中畫過一次 idle frame 就靜默，StatusMonitor 分段讀取會漏掉，之後沒有新輸出就不再重算。第二版加上**主動 SIGWINCH nudge**：把 worker window 釘成 `window-size manual`，nudge 執行緒每 2.5s 把列數 ±1 切換一次觸發 resize → CLI 重繪當前 frame → 一旦已 settle 到 idle,那次重繪就是乾淨的 idle box → 一個 tick 內翻成 IDLE。現場實測強制一次 resize 即讓卡住的 `0f3db917` `unknown → idle → 任務送達`。

- 分支：`custom/4.13-worker-init-headless-viewer`（已更新到 `origin/main` `4dc8bf7`，tip `f9c0634`），已 `--no-ff` merge 進 `cao-tailscale-integration`。
- 只作用於 pipe-pane（tmux）backend；herdr 走 socket 事件，不經此路徑。
- best-effort：attach 失敗會被吞掉，只退回原本行為，不會擋住終端建立。

**已通過的驗證**：
- `black` / `isort` 乾淨；模組 import 正常。
- 對 bogus session 呼叫 context manager **不拋例外**（graceful fail）。
- 對真實 live window 測試真模組：`start → True`、nudge 期間視窗高度在 49↔50 交替（證明 resize/SIGWINCH 生效）、`window-size` 期間為 manual、`stop` 後還原、**0 個** `caoinit_` 殘留（無洩漏）。
- 觸發機制（`window-size manual` + resize toggle）已在**真實卡住的 CAO worker `0f3db917`** 上實測有效：`unknown → idle → reached idle → processing`。
- 手動等效 attach 也在 claude `df3110a1`、agy `6651c388` 上實測有效。

### 已修 #2 follow-up —— 新客製 **4.14**（程式碼,已 merge 進 integration,重啟後已實測）

4.13 解掉「無人觀看時 ready frame 不進 buffer」後，現場又出現第二層邊界：

- worker 的 ready prompt 已經能在 tmux / API output 看到。
- `ClaudeCodeProvider.get_status(raw_tail)` 對實際 terminal log tail 會回 `idle`。
- 但 `StatusMonitor` cache 仍停在初始 `UNKNOWN`，`wait_until_status()` 只讀 cache，沒有在 `UNKNOWN` 狀態重新偵測，因此仍可能 timeout。
- 對支援 pyte screen detection 的 provider，polling path 原本只信 screen detector；若 pyte 回 `UNKNOWN`，沒有退回 raw-buffer detector。

4.14 修法：

- `StatusMonitor.get_status()` 在 cached status 為 `UNKNOWN` 且 buffer 有內容時，和 `PROCESSING` 一樣執行 fresh detection。
- `_detect_current_status()` 對 pyte screen detector 回 `UNKNOWN` 的情況，fallback 到 raw-buffer detection；`UNKNOWN` 被視為「沒有訊號」，不是最終狀態。
- 新增 regression tests：
  - cached `UNKNOWN` + buffer ready signal → 回 `IDLE` 並回寫 cache。
  - screen detector `UNKNOWN` + raw detector `IDLE` → 回 `IDLE`。

Live validation：

- 重啟並 reinstall 後，planner `89e1b022`（`planner-7c8b`, Claude Opus 4.8 high）成功走完：
  - `Terminal 89e1b022 status changed: unknown`
  - `wait_until_status [89e1b022]: waiting for {completed, idle}`
  - `Terminal 89e1b022 status changed: completed`
  - `wait_until_status [89e1b022]: reached completed`
  - `Created terminal: 89e1b022`

### 待辦 #3（未修,建議）
agy 全域 MCP 精簡 / 隔離（讓 CAO worker 不繼承全域 11 個 server）或把 context7 改全域安裝（`npm i -g @upstash/context7-mcp` + command 指向 bin）。屬另一項工作。

---

## 四、更新哪些檔案

### CAO 套件（`cli-agent-orchestrator` repo）
| 檔案 | 變更 | 分支/commit |
|------|------|------------|
| `src/cli_agent_orchestrator/services/render_viewer.py` | **新增**：headless render-viewer 模組（`render_during_init` context manager + `_RenderViewer` + SIGWINCH/resize nudge） | `custom/4.13` `f9c0634` |
| `src/cli_agent_orchestrator/services/terminal_service.py` | 在 `create_terminal()` 的 `provider.initialize()` 外包一層 `render_during_init(...)`（僅 tmux backend）+ import | `custom/4.13` `f9c0634` |
| `src/cli_agent_orchestrator/services/status_monitor.py` | cached `UNKNOWN` polling fresh-detection + pyte `UNKNOWN` raw fallback | `custom/4.14` `71c793a` |
| `test/services/test_status_monitor.py` | 4.14 regression tests for cached `UNKNOWN` recovery and screen-UNKNOWN raw fallback | `custom/4.14` `71c793a` |
| （merge）`cao-tailscale-integration` | `--no-ff` merge `custom/4.13` + `custom/4.14` | `6fc8075`（4.13 merge） / `85b024c`（4.14 merge） |

### 部署設定（非 repo）
| 檔案 | 變更 |
|------|------|
| `/Users/alex/.aws/cli-agent-orchestrator/settings.json` | `mcp_request_timeout` 180 → **300** |

### 本報告
| 檔案 | 說明 |
|------|------|
| `CAO-DISPATCH-UNKNOWN-RESOLUTION-2026-07-04.md`（本檔，integration 分支） | 調查與修復記錄 |

---

## 五、結論

- 「派工卡 UNKNOWN」的**直接根因**是 **#2**：無人觀看的 tmux 背景 window 不 flush Ink TUI 渲染，導致 StatusMonitor 收不到 idle frame。偵測邏輯本身沒壞 —— 是「frame 沒送達 buffer」。使用者「打開 terminal 才收到」的觀察正是決定性證據。
- **#1 timeout 反轉**是放大器，決定「卡住時算不算失敗、有多久窗口可補救」；已改設定（180→300），待重啟。
- **#3 agy 全域 MCP** 是 agy 專有的加重因素，本次未動，已記錄待辦。
- **修法 4.13** 讓 CAO 在 init 期間自動撐渲染，治本地移除「必須人工打開 web terminal」這個隱性依賴，對 claude / agy / 所有 pipe-pane provider 一體適用，且對現有行為 best-effort、不破壞。
- **修法 4.14** 補上 4.13 後暴露的 status-cache 邊界：ready frame 已在 buffer 內但 cache 還是 `UNKNOWN` 時，polling 會重新偵測並可從 raw buffer recover。`89e1b022` live validation 已確認 worker init 可從 `unknown` 走到 `completed` 並建立成功。

### 要生效 + 收尾的步驟
1. **重啟 CAO server**（同時吃到 #1 的 300s 與 #2 的 4.13）。重啟會中斷目前 session；交接已在 `.cao/tasks/…-session-handoff.md`。
2. 重啟後**故意派一個 worker 但不開 terminal**，確認它能在幾十秒內自行 `reached idle` 並收到任務（驗證 4.13 端到端）。
3. （可選）處理 #3：精簡 agy 全域 MCP。
4. 依 fork-sync 流程，`custom/4.13` 與 `custom/4.14` 已可被後續每次重建 re-merge；目前已加入 `FORK-SYNC-CUSTOMIZATION-BRANCH-FLOW.md` 的合併清單與 `CAO-CUSTOMIZATIONS-PROGRESS.md` 表格。

---

## 附錄：已排除的假設（避免重蹈）
- ❌ **claude 佔位提示 `❯ Try "..."` 打敗 idle 偵測**：`get_status` 與 `get_status_from_screen` 都已明確處理佔位提示，實測都回 IDLE。
- ❌ **記憶體耗盡**：`memory_pressure` 顯示 37% free，非主因。
- ❌ **orphan 進程堆積**：teardown 正常,FIFO/tmp 乾淨。
- ❌ **pyte `IndexError` 崩潰**：只發生在 supervisor 自己的大畫面,會 fallback 到 raw buffer,與 worker 失敗無關。
- ❌ **#359 native-status**：只在 herdr backend 有差,本部署是 tmux backend。
- ❌ **context7 npx 慢**：熱快取僅 ~1.15s,非「卡死到 190s」的量級。
