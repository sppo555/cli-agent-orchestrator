# CAO 套件客製化 — 實作進度（for new-session handoff）

> 目標：把 `CAO-Tailscale-CHANGES-SUMMARY.md` §4 的 4 項套件客製化，重新實作到這個 fork
> （`git@github.com:sppo555/cli-agent-orchestrator.git`，base = 上游 `main` `17ae1f1`）。
> 每項各自一個 feature 分支 + 一個版本 tag，並 push 到 `origin`。

## 範圍裁定（已與使用者確認）
- 只做 §4 的客製化項目；§1/§2/§3/§5 屬 CAO-Tailscale 部署 repo，不進這裡。
- **Issue 3（allowedTools/execute_bash）**：套件已支援（`AgentProfile.allowedTools` 駝峰欄位 + `resolve_allowed_tools` 已接好）→ **無需改程式碼**。
- **4.5 9-worker 互動選擇**：已改為客製化項目的 4.5，並於 CAO-Tailscale 實作完成。
- **agy handoff 提早完成誤判修復**：經評估後確定不需要此項手動修復（避免複雜的狀態遮罩副作用），不予套用。

## 來源（authoritative）
舊 checkout `~/cao-control/cli-agent-orchestrator`，分支 `cao-customizations`：
- `2e130e5` codex pyte 狀態偵測
- `5aed53e` agy provider（provider-only）
- `23ef04f` claude_code `--effort` 欄位
- `b5c45da` agy workspace 自動信任（在 5aed53e 之上加 trust）

## 分支 / 版本對應
| 功能 | 分支 | tag | base | commit | 狀態 |
|---|---|---|---|---|---|
| 4.1 codex pyte | `feat/codex-pyte-status` | `codex-pyte-v1` | main | `001dad2` | ✅ 已 push |
| 4.2 agy provider | `feat/antigravity-provider` | `agy-provider-v1` | main | `1478b19` | ✅ 已 push (上游官方已合併為 `086e61a`) |
| 4.3 claude --effort | `feat/claude-effort` | `claude-effort-v1` | main | `b733fe2` | ✅ 已 push |
| 4.4 agy 自動信任 | `feat/agy-workspace-trust` | `agy-trust-v1` | feat/antigravity-provider | `e8398cf` | ✅ 已 push |
| 4.5 9-worker 互動選擇 | main (CAO-Tailscale) | — | — | `876940b` | ✅ 已完成 (CAO-Tailscale) |
| **新整合分支（全部）** | `feat/customizations-on-upstream-agy` | — | main | `e51616c` | ✅ 已 push（含 4.1+4.3+4.4） |

> 全部 push 到 `origin`（sppo555 fork）。自用不需開 PR 回上游。

## 各功能改動點
- **4.1**：`providers/codex.py` — import 加 `List`；class 加 `supports_screen_detection = True`；新增 `get_status_from_screen()`。
- **4.2**：上游官方已合併 (`086e61a`)。
- **4.3**：`models/agent_profile.py` 加 `effort` 欄位；`providers/claude_code.py` 在 `--model` 後加 `--effort`。
- **4.4**：在新基底分支中適應上游 official 實作。`providers/antigravity_cli.py` 啟動前取得 pane working directory，將該精確路徑加入 `trustedWorkspaces`，cleanup 只移除本 provider 本次新增的路徑。
- **4.5**：把 worker 拆成 9 個：`planner_claude/planner_codex/planner_gemini`、`developer_claude/developer_codex/developer_gemini`、`reviewer_claude/reviewer_codex/reviewer_gemini`。實作於 CAO-Tailscale 的 `gen-workers.sh`、`select-workers.sh` 與 `start-all.sh` 中。

## 驗證 / 生效
- `python -m py_compile` 檢查語法。
- 狀態偵測跑在 cao-server 行程，實際生效需重啟 server。

## 進度日誌
- 2026-06-26: 4.1→4.2→4.4→4.3 實作、驗證、commit、tag、push 完成。
- 2026-06-26: 9-worker 互動選擇完成（在 CAO-Tailscale repo，commit `f46c1b4`）。
- 2026-06-27: 建立 `feat/customizations-on-upstream-agy` 整合分支，移植 4.1/4.3/4.4 到官方 agy 基礎上，已驗證並 push。
- 2026-06-27: 釐清 4.5 為 9-worker 功能，並排除實驗性質的 agy handoff premature-complete 複雜修復。更新進度檔案。
