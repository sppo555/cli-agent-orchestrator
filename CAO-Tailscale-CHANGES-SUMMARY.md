# CAO-Tailscale 客製化改動摘要

> 來源：chat history `2026-06-26-184920-readme.txt`（位於 `~/Developer/CAO-Tailscale/`）。
> 本檔把該對話中對 **CAO-Tailscale 部署** 與 **CAO 套件源碼** 的所有改動整理成一份清單，方便追溯。
> 比對結論：`~/Developer/CAO-Tailscale/CUSTOMIZATIONS.md` **與本對話最終實作狀態一致**。

---

## 0. 與 `CUSTOMIZATIONS.md` 的比對

| 項目 | CUSTOMIZATIONS.md | chat 最終狀態 | 一致？ |
|---|---|---|---|
| 套件 4 項 + bundle 攜帶 | 有 | 有 | ✅ |
| Worker 陣容（planner=codex / dev=agy / reviewer=opus） | 有 | 有 | ✅ |
| 兩套配置 default / codex-lead | 有 | 有 | ✅ |
| 預設管線 PLAN→IMPLEMENT→REVIEW→RECORD→REPORT | 有 | 有 | ✅ |
| supervisor HALT / 健康檢查 / 重派上限 / allowedTools / MCP 安裝版 | 有 | 有 | ✅ |
| 腳本改名 launch→start-project | 有 | 有 | ✅ |
| commit 雜湊 2e130e5 / 5aed53e / 23ef04f / b5c45da | 有 | 有 | ✅ |

**唯一未涵蓋（合理）**：對話最後一個請求——改成 9 個 worker（`planner_claude/codex/gemini`、`developer_*`、`reviewer_*`）並在 `start` 腳本用 1/2/3 互動選 model——**未實作**（對話因 weekly limit 中斷）。詳見 §7「未完成」。

---

## 1. supervisor 行為（`agent-store/code_supervisor.md`）

| # | 改動 | 說明 |
|---|---|---|
| 1 | **⛔ ABSOLUTE HALT RULE** | worker 斷線 / 崩潰 / 錯誤 / 5h 額度滿 → supervisor 一律停手、回報、等指示，**絕不自己下海寫 code**（只有使用者明確指示才破例）。最高優先、覆蓋其他規則。 |
| 2 | **Pre-dispatch Health Check** | 每次 handoff 前先查該 worker 狀態並回報一行。 |
| 3 | **Handoff Result Validation（重派上限）** | handoff 回來若是半成品（~90s 內返回 / 畫面停在 `Working…` / 被截斷）→ 視為失敗，**最多重派 2 次（共 3 次）**，觸頂即 HALT 回報；明令禁止自行調高上限。用來封頂 token/額度損失。 |
| 4 | **`allowedTools` + `execute_bash`** | 給 supervisor Bash（跑 `cao session status` 等健康檢查、寫紀錄檔）。⚠️ 欄位名必須是 **`allowedTools`（駝峰）**；蛇形 `allowed_tools` 會被 pydantic 當未知欄位丟掉、落回 role 預設（無 Bash）。 |
| 5 | **MCP 改安裝版** | `mcpServers.cao-mcp-server.command` 從 `uvx --from git+…@main cao-mcp-server` → `cao-mcp-server`，讓 MCP 與 cao-server 永遠同 build，根治 handoff 的 `405 Method Not Allowed`。三個 profile 都改。 |
| 6 | **派工方式固定 handoff** | 同步、循序；不用 assign。 |
| 7 | **預設管線（Routing Policy）** | 每個需求預設自動跑：①PLAN(planner) → ②IMPLEMENT(developer_agy) → ③REVIEW(reviewer，迴圈到通過) → ④RECORD(supervisor 寫 `.cao/records.md`) → ⑤REPORT(回報)。 |
| 8 | **Record Keeping** | 通過審查後 supervisor 用 shell append 一筆紀錄到 `<工作目錄>/.cao/records.md`（需求 / 計畫 / 實作 / 審查結果 + 時間戳）。明示「這是 log 不是 code」，不違反 HALT/不准寫規則。 |

---

## 2. Worker 陣容 / model / effort（`agent-store/*.md`）

對話中角色經歷數次調整，**最終定案**為：

| worker | 角色 | provider | model | effort | 何時用 |
|---|---|---|---|---|---|
| `planner` | 規劃（不寫 code） | codex | gpt-5.5 | high（`codexConfig`） | 講「規劃/plan/設計」或大任務前 |
| `developer_agy` | **實作（唯一）** | antigravity_cli | Gemini 3.1 Pro (High) | （含在 model 名） | 所有實作 |
| `reviewer` | 審查（每次） | claude_code | claude-opus-4-8 | high（`--effort`） | 一律 |

- **`developer_chatgpt`（codex 實作者）已刪除**（repo + live store），bootstrap profile 清單同步更新為 `code_supervisor / planner / developer_agy / reviewer`。
- model/effort 各 provider 機制不同：
  - claude_code：`model:` → `--model`；`effort:` → `--effort`（**新增欄位**，見 §4.3）
  - codex：`model:` → `--model`；`codexConfig.model_reasoning_effort` → `-c …`
  - antigravity_cli：`model:` → `--model`（值要跟 `agy models` 完全一致；effort 含在 model 名）

> 中途歷史（已被覆蓋，僅供理解）：曾設 codex 為預設實作者、agy 為「指名才用」、planner 用 Opus 4.8；後改為「agy 唯一實作、codex 只規劃、Opus 只審查」。

---

## 3. 兩套配置（profile sets）

| 組 | 來源目錄 | 啟動檔 | supervisor | planner | developer | reviewer |
|---|---|---|---|---|---|---|
| **default (A)** | `agent-store/` | `start-all.sh` | claude(Opus 4.8) | codex(gpt-5.5) | agy(Gemini 3.1 Pro) | claude(Opus 4.8) |
| **codex-lead (B)** | `agent-store.codex-lead/` | `start-all-codex-lead.sh` | codex(gpt-5.5) | claude(Opus 4.8) | agy(Gemini 3.1 Pro) | codex(gpt-5.5) |

- 啟動檔會先用 `use-profile-set.sh` 把該組 profile 同步進 live store 再啟動。
- 也可 `PROFILE_SET=codex-lead ./scripts/start-all.sh`。
- 防 drift：`diff-profile-sets.sh` 比對兩組 prompt 內文。
- ⚠️ 配置 B 的 codex supervisor 屬實驗性。

---

## 4. CAO 套件源碼客製化

> 目前有效套件分支：`feat/customizations-on-upstream-agy`，base = fork-synced upstream `main`
> `086e61a`（awslabs#323）。因此 4.2 Antigravity CLI provider 已由 upstream 提供，現在只在新分支保留
> 4.1 / 4.3 / 4.4。舊 `cao-customizations` / bundle 紀錄保留作歷史背景，不應再直接 merge 舊 4.2 分支。

> 位於 checkout `~/cao-control/cli-agent-orchestrator`，**不在 CAO-Tailscale repo**，靠精簡 git bundle `cao-source/cao-customizations.bundle`（~10K，base = 上游 `b8b1897`）攜帶。跑在 cao-server 行程，套完須重啟 server。

### 4.1 codex pyte 狀態偵測（commit `2e130e5`）
- **問題**：handoff 給 codex 常 ~60–75s 提早返回半成品並拆終端。根因是 CAO 用 regex 刮原始 pipe-pane 串流判 idle，codex 的 `• Working (Ns • esc to interrupt)` footer 被重繪打碎、footer `›` 被誤判成完成。
- **背景**：上游 #287 / PR #293（2026-06-16）用 pyte 修了，但**只套 claude_code / kimi_cli，漏了 codex**。
- **修法**：`providers/codex.py` 加 `supports_screen_detection = True` + `get_status_from_screen()`，在 pyte 渲染後的乾淨畫面上給 spinner 絕對優先（判 PROCESSING），其餘委派現有 `get_status()`。改 `import`（補 `List`）。
- 另有獨立錨點式 patcher `scripts/patch-codex-pyte.py` / `apply-codex-patch.sh`，可單獨對「最新 main」重套這一項（冪等、錨點不見會報錯）。

### 4.2 agy provider（Antigravity CLI，upstream `086e61a` / awslabs#323）
- 原本本地 commit `5aed53e` 已被 upstream PR #323 取代；fork sync 後 `origin/main` 已內建 `antigravity_cli` provider。
- upstream 版包含 provider、ProviderType enum、manager/tool mapping、docs、unit/e2e fixtures，且已接 MCP config / soft tool restriction。
- 新分支 `feat/customizations-on-upstream-agy` **不再套舊 4.2**，避免把 upstream #323 的新檔案和 tests 反向刪改。

### 4.3 claude_code `--effort` 欄位（新分支 commit `cdb5f68`，歷史來源 `23ef04f`）
- CAO 原本 claude 沒傳 effort（只全域 env `CLAUDE_CODE_EFFORT_LEVEL`）。
- 改 2 處：`models/agent_profile.py` 加 `effort` 欄位、`providers/claude_code.py` 傳 `--effort`。
- 讓 reviewer/planner 跑 high、supervisor 維持預設，逐 worker 控管。
- 新分支版本另限制只有非空字串才輸出 `--effort`，避免 legacy/mock profile 的非字串值進 `shlex.join()`。

### 4.4 agy workspace 自動信任（新分支 commit `6b2cee4`，歷史來源 `b5c45da`）
- agy 對未知目錄會跳「信任這個工作區?」提示，且只認**精確路徑**（不支援萬用字元/前綴）。CAO 每次給 agy 一個隨機 per-terminal workspace → 每次都重問。
- 舊修法：`antigravity_cli.py` 啟動前把 per-terminal workspace 精確路徑寫進 `~/.gemini/antigravity-cli/settings.json` 的 `trustedWorkspaces`，cleanup 時移除。best-effort（try/except）。
- 新分支修法：upstream agy provider 已改成直接用 `-i` 注入 prompt，不再建立舊版 per-terminal `GEMINI.md` workspace；因此改為啟動 agy 前取得 pane working directory，將該精確路徑加入 `trustedWorkspaces`，cleanup 只移除本 provider 本次新增的路徑，不刪使用者原本已 trusted 的 workspace。
- 另外清掉 `settings.json` 既有殘留（危險的 `*`、`/*`、過期 session hash），備份後清空 `trustedWorkspaces`。

### 4.6 fork-sync 後的新整合分支（2026-06-27）
- 分支：`feat/customizations-on-upstream-agy`，base `086e61a`。
- commits：
  - `898bca7` 4.1 codex pyte rendered-screen status detection。
  - `cdb5f68` 4.3 claude_code per-agent `--effort`。
  - `6b2cee4` 4.4 antigravity pane workspace auto-trust。
- 驗證：`uv run pytest test/providers/test_antigravity_cli_unit.py test/providers/test_codex_provider_unit.py test/providers/test_claude_code_unit.py test/services/test_status_monitor.py` → 297 passed；`uv run black --check`、`uv run isort --check-only` 通過。

### 4.5 agy handoff 提早完成誤判修復（2026-06-27）
- **問題**：handoff 正式任務送出後，agy 畫面仍在 `Working...` / `Prioritizing Tool Usage` / `Tip:` / artifact prompt，
  但 CAO 把 idle footer 或 TUI chrome 誤判為 `COMPLETED`，`run_agent_step(teardown=True)` 隨即 `/quit` 並刪 terminal。
- **provider 修法**：`antigravity_cli.py` 把 `Working...`、`Running...`、`Loading...`、`Prioritizing Tool Usage`、tool-progress、
  thought rows、artifact chrome 都歸類為進行中 chrome；latest query 後若只有這些 chrome，即使尾端出現 idle footer 也回
  `PROCESSING`。其中 `Working...` / `Running...` / `Loading...` 只在整行 spinner/status 型態下才算進度，避免誤吃正常回答。
  其他 footer/artifact phrase 也只匹配實際 TUI row 形狀；output extraction 會排除 chrome，避免把 TUI 狀態列當 answer。
  若 idle footer 已出現且最後 query 後已有真實答案，舊 progress row 不再壓過 completed 判斷。
  最新 query 定位改為 TUI segment-based，答案中的 Markdown blockquote `> text` 不再被誤當成 query 而從 extraction 丟掉。
- **誤判收窄**：`Press` 不再用寬鬆 `Press\b` 判 chrome，`Tip:` 也只匹配 agy TUI footer/status 前綴樣式；
  避免正常回答 `Press Enter to continue.` 或 `Tip: run npm test before committing.` 被吃掉並卡成 PROCESSING。
- **handoff 根治防線**：在經歷 7 輪 regex arms race 後，確認根本問題是 `StatusMonitor` 缺乏 turn boundary。
  - **修復**：修改 `status_monitor.py` 中的 `get_status()`。當 input 剛送出（`_allow_processing_revert` arm 設為 True）時，若 latched status 還是上一輪的 ready status（如 `COMPLETED`），會將其 mask 轉為 `PROCESSING`，直到 provider 偵測到新的 PROCESSING 為止。
  - 這保證了 `wait_until_status(COMPLETED)` 不可能在 11-41ms 內拿到舊的 `COMPLETED`。
  - **移除**：移除了 `agent_step.run_agent_step()` 裡用 regex 猜測 `FULL` 原始輸出來判定 premature 的邏輯，讓設計回歸正軌。
- **驗證**：targeted regression `uv run pytest test/providers/test_antigravity_cli_unit.py test/services/test_agent_step.py test/services/test_status_monitor.py`
  通過（68 passed）；`black --check`、`isort --check-only`、`git diff --check` 通過。
- **R8 review 結果（2026-06-27 11:08 CST）**：**CHANGES REQUESTED**，artifact：
  `/Users/alex/Developer/cli-agent-orchestrator/.cao/reviews/handoff-rootfix-review-r8.md`。
  - 正向：用正式 `handoff` 派 reviewer 驗證，未再重現 11-41ms premature complete；handoff 約 256 秒正常回傳。
  - High blocker：`StatusMonitor` arm 後若新 turn 沒看到 PROCESSING frame、直接變成合法 COMPLETED，現有 mask 可能持續把 public status 回成 PROCESSING，造成 false timeout。
  - Low blocker：`status_monitor.py` 未通過 Black formatting。
  - 已通過：targeted suite 68 passed、isort、git diff check。Full pytest 仍有 15 個疑似既有 unrelated failures。
  - 下次修：補 direct-completion/ready-to-ready regression，調整 arm 清除語意，並跑 Black。

> 維護規則：在 `cao-customizations` 分支新增 commit 後 → 跑 `scripts/rebuild-cao-bundle.sh` → commit 本 repo 的 bundle，否則 bundle 仍是舊的。

---

## 5. 部署腳本（`scripts/`）

| 改動 | 說明 |
|---|---|
| `launch-project.sh` → **`start-project.sh`** | 命名與 `start-server/webui/all` 對稱；同步更新 `start-all.sh`、`stop-project.sh`/`stop-all.sh`（含 `pgrep` 比對字串）、`bootstrap.sh`、`scripts/README.md`。 |
| `start-project.sh` 拿掉寫死 `--provider claude_code` | 改讀 profile 宣告的 provider（A=claude_code、B=codex）；可用 `CONDUCTOR_PROVIDER` 覆蓋。修掉「codex 的 gpt-5.5 被丟給 Claude 而報 model 不存在」。 |
| 新增 `use-profile-set.sh <default\|codex-lead>` | 只切換 profile 組到 live store。 |
| 新增 `start-all-codex-lead.sh` | 等同 `PROFILE_SET=codex-lead ./start-all.sh`。 |
| `start-all.sh` 加第 0 步 | 啟動前先 `use-profile-set.sh "$PROFILE_SET"`（預設 default）。 |
| 新增 `diff-profile-sets.sh` | 比對兩組 prompt 內文找 drift。 |
| 新增 `patch-codex-pyte.py` / `apply-codex-patch.sh` | 錨點式 codex patcher（次要，單套 codex pyte）。 |
| 新增 `apply-cao-customizations.sh` | 一鍵帶齊 4 項：確保 checkout（沒有就 clone 上游）→ 從 bundle 套 `cao-customizations` 分支 → 重裝。 |
| 新增 `rebuild-cao-bundle.sh` | 重建 `cao-source/cao-customizations.bundle`。 |
| `bootstrap.sh` 第 9 步 | 從「只套 codex patch」改成「用 bundle 一次帶齊 4 項」（以安裝版是否含 `antigravity_cli.py` 為冪等指標）。profile 清單也更新。 |

---

## 6. 版控

- `~/Developer/CAO-Tailscale` → 獨立 git repo（main），`.gitignore` 排除 `logs/`、`*.log`、`.DS_Store`、`.claude/settings.local.json`。
- `~/Developer/Claude_Remote-CAO` → 另一獨立 git repo。
- CAO 套件 checkout 分支由 `codex-pyte-status-detection` **改名為 `cao-customizations`**（共 4 commit）。
- 皆未推遠端（GitHub repo 非使用者所有）。

---

## 7. 未完成（對話因 weekly limit 中斷）

最後一個請求**尚未實作**：

- 把 worker 拆成 **9 個**：`planner_claude/planner_codex/planner_gemini`、`developer_claude/developer_codex/developer_gemini`、`reviewer_claude/reviewer_codex/reviewer_gemini`。
- 三組各自遵循同一份 `planner.md` / `developer.md` / `reviewer.md`。
- `start` 腳本用 `echo` 顯示「1. codex / 2. claude / 3. gemini」，讓使用者對 planner / developer / reviewer 各填數字 1/2/3 選 model。
- 對應 model：codex gpt-5.5 high(codexConfig)、claude_code claude-opus-4-8 high(--effort)、antigravity_cli Gemini 3.1 Pro (High)。
- 需求：9 個 worker 都能用；可下指令如「這次 V8 fix 請 `developer_codex` 跟 `reviewer_claude`」，沒講就用預設。

---

## 8. 生效速查

| 改了什麼 | 怎麼生效 |
|---|---|
| 任何 `agent-store/*.md`（profile / 派工 / model / effort） | 同步 live store（`install.sh` 或 `cp`）→ **重啟 session** |
| CAO 套件（codex patch / agy provider / effort 欄位 / agy 信任） | 從 checkout 重裝 → **重啟 cao-server**（`stop-all` → `start-all`） |

> 一律啟動時載入一次，跑著的 session/server 不會熱重載。
