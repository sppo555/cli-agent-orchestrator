# CAO 套件客製化 — 實作進度（for new-session handoff）

> 目標：把 `CAO-Tailscale-CHANGES-SUMMARY.md` §4 中仍未上游化的套件客製化，重新整理到
> `git@github.com:sppo555/cli-agent-orchestrator.git`。
> 目前有效分支：`feat/customizations-on-upstream-agy`，base = fork-synced upstream `main`
> `086e61a`（awslabs#323，內建 Antigravity CLI provider）。

## 範圍裁定（已與使用者確認）
- 只做 §4 的 4 項；§1/§2/§3/§5 屬 CAO-Tailscale 部署 repo，不進這裡。
- **Issue 3（allowedTools/execute_bash）**：套件已支援（`AgentProfile.allowedTools` 駝峰欄位 + `resolve_allowed_tools` 已接好）→ **無需改程式碼**。當初「沒生效」是 CAO-Tailscale profile 寫成 snake_case 的作者錯誤。
- **4.2 agy provider**：已由 upstream `086e61a` / awslabs#323 提供，**不再套舊本地 4.2**。
- §2 9-worker 互動選擇：屬 **CAO-Tailscale** 部署 repo，不混進此套件分支。

## 來源（authoritative）
舊 checkout `~/cao-control/cli-agent-orchestrator`，分支 `cao-customizations`：
- `2e130e5` codex pyte 狀態偵測
- `5aed53e` agy provider（provider-only）
- `23ef04f` claude_code `--effort` 欄位
- `b5c45da` agy workspace 自動信任（在 5aed53e 之上加 trust）

## 分支 / 版本對應
| 功能 | 分支 | tag | base | commit | 狀態 |
|---|---|---|---|---|---|
| 4.1 codex pyte | `feat/customizations-on-upstream-agy` | — | `086e61a` | `898bca7` | ✅ 新分支已套 |
| 4.2 agy provider | upstream `main` | — | — | `086e61a` | ✅ upstream 已內建（awslabs#323） |
| 4.3 claude --effort | `feat/customizations-on-upstream-agy` | — | `086e61a` | `cdb5f68` | ✅ 新分支已套 |
| 4.4 agy 自動信任 | `feat/customizations-on-upstream-agy` | — | `086e61a` | `6b2cee4` | ✅ 依 upstream agy provider 重做 |
| 4.x 9-worker 互動選擇 | CAO-Tailscale repo | — | — | `f46c1b4`/後續 | ✅ 部署 repo 已做，不屬此 repo |
| **目前整合分支** | `feat/customizations-on-upstream-agy` | — | `086e61a` | `6b2cee4` | ✅ ahead of `origin/main` 3 commits |

> 舊分支 `feat/antigravity-provider` / `feat/agy-workspace-trust` / `feat/all-customizations`
> 是 `6d7f1b4` 時期的本地重套；在 `086e61a` 之後不要直接 merge，避免把 upstream #323 相關檔案反向刪改。

## 各功能改動點
- **4.1**：`providers/codex.py` — import 加 `List`；class 加 `supports_screen_detection = True`；新增 `get_status_from_screen()`（spinner 優先判 PROCESSING，其餘委派 `get_status`）。
- **4.2**：由 upstream `086e61a` 提供，不再使用舊本地 provider commit。
- **4.3**：`models/agent_profile.py` 加 `effort` 欄位；`providers/claude_code.py` 傳 `--effort`。新分支另收斂為只有非空字串才輸出，避免 legacy/mock profile 的非字串值進 `shlex.join()`。
- **4.4**：`providers/antigravity_cli.py` — 啟動 agy 前取得 pane working directory，把精確路徑加進 `~/.gemini/antigravity-cli/settings.json` 的 `trustedWorkspaces`；`cleanup` 只移除本 provider 本次新增的路徑，保留使用者原本已 trusted 的 workspace。

## 驗證 / 生效
- `python -c "import ast; ast.parse(open(f).read())"` 或 `python -m py_compile` 檢查語法。
- 狀態偵測跑在 cao-server 行程，實際生效需重啟 server。
- agy handoff 修復已補單元 regression；實際生效仍需重啟 cao-server 後真實派工驗收。
- 新分支 `feat/customizations-on-upstream-agy` 目前只含 4.1 + 4.3 + 4.4；4.2 走 upstream。

## 驗證紀錄
- 4.1 / 4.2（provider + enum + manager + tool_mapping）：committed 內容與舊 checkout 對應 commit **新增行逐字一致**（diff 比對通過）。
- 4.2：`PYTHONPATH=src python3` import smoke 通過（enum / TOOL_MAPPING / ALL_NATIVE_TOOLS 都含 agy）。
- 4.3：新增行與 `23ef04f` **逐字一致**。
- 4.4：py_compile 通過、trust 邏輯存在；formatting 配合 repo 行長微調（功能等價於 `b5c45da`，非逐字）。import smoke 因 bare python3 缺 `frontmatter` dep 略過（非程式問題）。
- `feat/customizations-on-upstream-agy`：`uv run pytest test/providers/test_antigravity_cli_unit.py test/providers/test_codex_provider_unit.py test/providers/test_claude_code_unit.py test/services/test_status_monitor.py` → 297 passed；
  `uv run black --check`、`uv run isort --check-only` 通過。

## 進度日誌
- 2026-06-26: 盤點完成、來源取出、anchors 確認。
- 2026-06-26: 4.1→4.2→4.4→4.3 依序實作、驗證、commit、tag、push 完成。回到 main。
- 2026-06-26: 9-worker 互動選擇完成（在 **CAO-Tailscale** repo，commit `f46c1b4`，本機 main，無遠端）。
  - 設計：選項 1（鬆綁 supervisor 固定角色 + MCP 僅 claude）。
  - 新增 `workers/{planner,developer,reviewer}.md` + `_mcp-addendum.md`、`scripts/gen-workers.sh`、
    `scripts/select-workers.sh`；改 `start-all.sh`(第0步)、`code_supervisor.md`(路由鬆綁)、`install.sh`、
    `CUSTOMIZATIONS.md` §2、`scripts/README.md`。產生 9 個 `agent-store/{role}_{model}.md`。
  - 驗證：bash -n 全過；gen + select(非互動 defaults) 寫入 /tmp/live_test 正確（3 預設名 + 9 具名 + supervisor）。
  - 舊 profile-sets（default/codex-lead）降為 legacy 仍可用；舊 `agent-store/{planner,developer_agy,reviewer}.md`
    保留為 legacy 樣板（未刪）。
- 2026-06-26: 升級**選項 2**——codex 變體也加 `cao-mcp-server`（memory/assign），只剩 gemini handoff-only。
  CAO-Tailscale commit `3b80933`（+ `8baf8b0` regen claude addendum）。caveat：codex+MCP 多一段
  「Starting MCP servers」（提早返回觸發點），靠 supervisor 重派上限兜底，首次小任務試。
- 待辦：9-worker 真實 `start-all.sh` 互動 + handoff/assign 端對端驗收
  （需重啟 cao-server / session；codex+MCP 這組合首次驗）。
- 2026-06-26: 建立 `feat/all-customizations` 整合分支（merge 4.1+4.2+4.3+4.4），已 push。自用不需開 PR。
- 2026-06-26: CAO-Tailscale 9-worker 加入 supervisor model 選擇（`SUPERVISOR=` 環境變數）。
  改動：`workers/code_supervisor.md`（新）、`gen-workers.sh`、`select-workers.sh`、`start-all.sh`。
  產生 `code_supervisor_{codex,claude,gemini}.md` 三份 supervisor profile。已 commit（`17bae80`）。
- 2026-06-27: 修復 `antigravity_cli`/agy handoff 提早完成誤判（分支 `fix/agy-handoff-premature-complete`）。
  - 基底：從 `65adf6b7986fa044103a24e74f63617a64ee21ef` 開分支，merge `1863729c1f2176ebbe2e9c7291386a145894a47e` 與
    `2e7e7e3776611c9cdd25715a8e311414b2a43b62` 後修復。
  - 修補：agy classifier 將 `Working...`、`Running...`、`Loading...`、`Prioritizing Tool Usage`、tool/thought/artifact chrome
    視為 PROCESSING；`Working...`/`Running...`/`Loading...` 只在整行 spinner/status 型態下才算進度，避免誤吃正常回答。
    TUI footer/status 型 `Tip:`/artifact/`esc to cancel`/`for shortcuts`/`ctrl+...` 狀態列不再當成 answer；
    所有 chrome phrase 都收窄為實際 TUI row 形狀，避免誤吃正常回答。
    若 idle footer 已出現且最後 query 後已有真實答案，舊 progress row 不再壓過 completed 判斷。
    最新 query 定位改為 TUI segment-based，答案中的 Markdown blockquote `> text` 不再被誤當成 query 而從 extraction 丟掉。
  - 根治防線：經過 7 輪 regex arms race 後確認根本問題在於 `StatusMonitor` 的 sticky latch 沒有 turn boundary。
    - 修復：在 `status_monitor.py` 的 `get_status()` 新增 turn-boundary guard。當送出 input（arm 被設為 True）時，若 latched status 還是上一輪的 ready status（如 COMPLETED），會被 mask 轉為 `PROCESSING`。
    - 這確保了 `wait_until_status(COMPLETED)` 絕對不會在 11-41ms 的 race 期間拿到舊的 `COMPLETED`。
    - 移除：完全移除了 `agent_step.run_agent_step()` 中依賴 output 內容判斷的 regex premature guard（因為無法可靠分辨內容中的 `Working...` 與進度條），讓設計回歸正軌。
  - 驗證：`uv run pytest test/providers/test_antigravity_cli_unit.py test/services/test_agent_step.py test/services/test_status_monitor.py` → 68 passed；
    `black --check`、`isort --check-only`、`git diff --check` 皆通過。
- 2026-06-27 11:08 CST: handoff root-fix R8 review 完成，結果 **CHANGES REQUESTED**。
  - Review artifact: `.cao/reviews/handoff-rootfix-review-r8.md`。
  - 正向驗證：用正式 `handoff` 派 `reviewer` 驗證本次修復，未再發生 11-41ms 提早完成，也未 hit 600s timeout；handoff 約 256s 正常回傳 review。
  - Blocker 1（High）：`StatusMonitor.get_status()` 在 arm=True 時會把 sticky ready status mask 成 `PROCESSING`，但若新 turn 沒觀察到 `PROCESSING` frame 而直接進入真正 `COMPLETED`，arm 可能不會被清掉，導致合法快速完成被永久 mask 成 `PROCESSING`，最後 false timeout。
  - Blocker 2（Low）：`black --check` 失敗，`src/cli_agent_orchestrator/services/status_monitor.py` 需要格式化。
  - Validation：targeted suite `uv run pytest test/providers/test_antigravity_cli_unit.py test/services/test_agent_step.py test/services/test_status_monitor.py` → 68 passed；`isort --check-only`、`git diff --check` 通過；full `uv run pytest` 仍有 15 failures（看起來是 branch 既有 unrelated：launch allowed-tools defaults、`answer_user_prompt` sender id、Claude Code MagicMock effort）。
  - 下次修復方向：補 armed ready-to-ready/direct-completion regression，讓 stale ready rerender 不會早退，同時合法新 turn direct `COMPLETED` 能清 arm；跑 Black。
- 2026-06-27: fork sync 後 `origin/main` 已包含 upstream `086e61a` / awslabs#323（Antigravity CLI provider），因此新開
  `feat/customizations-on-upstream-agy`，只保留 4.1、4.3，並把 4.4 依 upstream agy provider 重新實作。
  - commits：`898bca7` codex pyte、`cdb5f68` claude effort、`6b2cee4` agy pane workspace auto-trust。
  - 驗證：agy/codex/claude/status-monitor targeted suite 297 passed；Black/isort 通過。
