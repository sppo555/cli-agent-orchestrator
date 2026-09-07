# Review Findings

## [P1] 生成中的半成品會被當成已完成回覆

- File: `/Users/alex/Developer/cli-agent-orchestrator-grok-provider/src/cli_agent_orchestrator/providers/grok_cli.py:354`
- Problem: `extract_last_message_from_script()` 找到最後一個 prompt 後，遇到 completion marker 才停止，但沒有要求該 marker 必須存在，也沒有拒絕較新的 `Responding…`／`[stop]` processing surface。因此，明確被 status 測試判為 `PROCESSING` 的 `long_response_completed` fixture，仍在 extraction 測試中被成功回傳為一般最終答案。`terminal_service.get_output(..., LAST)` 也會直接呼叫 extraction，沒有先確認 terminal 已完成。
- Why it matters: 呼叫者在 Grok 尚未生成完畢時可能收到看似完整、實際被截斷的內容；這是 silent data corruption，也破壞 lifecycle provider 的完成邊界契約。
- Recommendation: extraction 必須驗證目前 turn 有可信的 completion boundary，且 newest processing marker 不得晚於 completion；active capture 應 `ValueError`。將現有測試改為拒絕 active fixture，另補一份真正完成的 long-response capture 驗證成功路徑。

## [P2] ANSI Grok prompt 前若有 bare `❯` shell prompt，合法 transcript 會被誤判為歧義

- File: `/Users/alex/Developer/cli-agent-orchestrator-grok-provider/src/cli_agent_orchestrator/providers/grok_cli.py:300`
- Problem: ambiguity guard 先把所有符合 `❯ text` 的行視為同等 prompt candidate，並在任何兩個 candidate 間沒有 Grok completion marker 時立即失敗；直到後面才檢查 `_ANSI_PROMPT_BACKGROUND`。以 `❯ grok --always-approve` 的 shell prompt 加上後續真實 ANSI Grok prompt 組成 transcript，可穩定重現 `ValueError: Ambiguous Grok CLI user prompt boundary`。
- Why it matters: 使用 bare `❯` 的 zsh／主題是常見環境；正常啟動歷史仍在 scrollback 時，LAST extraction 可能完全不可用。
- Recommendation: 若較新的 candidate 具有已校準的 Grok ANSI prompt/input-surface 證據，應排除較早的 unstyled shell candidate，再執行歧義檢查；加入「shell prompt + Grok ANSI prompt + completed response」regression test。

## [P2] 標示為 redacted/sanitized 的 Phase 0 fixtures 仍包含個人環境資訊

- File: `/Users/alex/Developer/cli-agent-orchestrator-grok-provider/test/providers/fixtures/grok_cli/cli/grok_inspect_json_redacted.txt:29`
- Problem: fixtures 保留 `/Users/alex/...`、主機名稱 `alex@alexdeMacBook-Pro`、本機 skill/config 路徑、project `.mcp.json`、MCP server 名稱與本機 executable 路徑；相同資訊也散布於 `grok_mcp_doctor_json_redacted.txt`、raw/rendered startup/exit 與 plan captures。
- Why it matters: 這些內容不是 credential，但不適合直接進入公開 awslabs repository，也與檔名及文件宣稱的 redacted/sanitized 不一致；同時提交大量無關的本機 MCP/skill inventory 增加資訊暴露面。
- Recommendation: 將 username、hostname、home/project absolute path 與本機 executable 改為穩定 placeholder，並把與 Gate 判斷無關的 MCP/skill inventory 最小化或泛化；加入 fixture hygiene scan 防止個人絕對路徑與 hostname 回歸。

## [P2] Security 與 skills 文件的 provider matrix 仍漏掉 Grok

- File: `/Users/alex/Developer/cli-agent-orchestrator-grok-provider/SECURITY.md:128`
- Problem: provider enforcement 表未列出 Grok 的 native hard-deny／lifecycle-only 限制；`docs/skills.md:123`、`:159`、`:168` 的 runtime-prompt provider 說明也都漏掉 Grok，與實作、README provider 表及 agent-profile 文件不一致。
- Why it matters: 使用者無法從主要安全與 skills 文件確認 Grok 的限制強度與 skill catalog delivery 行為；provider 公開介面文件彼此矛盾。
- Recommendation: 在 security matrix 加入 Grok 的 native deny 機制與 Gate C/lifecycle-only caveat；在 skills 三處 runtime-provider 列表與表格加入 Grok。

## [P3] Phase 0 ADR 狀態仍停留在「未授權實作」

- File: `/Users/alex/Developer/cli-agent-orchestrator-grok-provider/docs/adr-grok-cli-phase0.md:3`
- Problem: ADR 仍標示 `proposed for Prompt 1R review`、scope 為 evidence-only，並明說「does not authorize PR 2 or add grok_cli to production registration surfaces」，但同一工作樹已完成 provider implementation 與 production registration。
- Why it matters: 這會讓後續審查者無法判斷 lifecycle-only implementation 的正式決策狀態，並與 improvement report 的完成聲明衝突。
- Recommendation: 將 ADR 更新為實際已接受／核准狀態，保留 Gate C = NO-GO，並記錄後續 review 對 lifecycle-only provider 的授權與範圍。

# Open Questions

- `grok inspect`／`grok mcp doctor` 的完整本機 inventory 是否預期提交至公開 upstream？若是，合併前仍需由 repository owner 確認脫敏標準；目前內容不應視為已完成 sanitization。

# Acceptable Limitations

- Gate C = NO-GO；V1 僅支援 lifecycle，不宣稱 CAO MCP orchestration。
- 不使用 `--plugin-dir`，不修改 Grok、MCP、user/global plugin configuration，也不自動轉換 profile `mcpServers`。
- upstream `AgentProfile` 尚無 `effort`；防禦式 `getattr()` 可接受。
- Bash 被允許時，Edit deny 無法阻止 shell 寫檔。
- 超長 inline rules 採 fail-fast，不截斷。
- session resume／continue／fork、ACP/stdio 不在 V1 範圍。
- Live Grok E2E 需明確設定 `CAO_RUN_GROK_INTEGRATION=1` 才執行。

# Validation Notes

第二輪直接驗證：

- 使用 MCP `codebase-memory` 重新索引並檢查 provider registration、status/output call path 與變更影響；未發現 `--plugin-dir`、Grok config write 或虛假的 Gate C orchestration 支援。
- 第一輪的主要 status 問題已修正：真實 raw/pyte ready、waiting、stale-processing fixtures 現在均由 paired tests 覆蓋；startup guard、Markdown ANSI reconstruction、Phase 0 evidence 與 Gate C/restart 文件內容也有實質改善。
- 針對性 Python suite：`286 passed`。
- 完整非 E2E suite：`4071 passed, 21 skipped, 94 deselected, 1 failed`；唯一失敗為既有且與 Grok 無關的 workflow timeout（expected `30`、observed `300.0`）。
- Grok live E2E：確認 `1 test collected`；未設定 opt-in 環境變數，因此未執行實機流程。
- Web：`61 passed`，production build 成功。
- `git diff --check`、Black、isort 均通過；變更相關 Python source 的 mypy 通過。
- 額外 regression probe 已重現兩個問題：active `long_response_completed` 被成功 extraction，以及 bare `❯` shell prompt 加 ANSI Grok prompt 被誤判為 ambiguous。
- 未修改任何 Grok/user configuration。除本 review 報告外，未修改實作檔案。

目標分支 `HEAD` 仍等於 `origin/main@32db5a1`；Grok provider 與相關文件/測試目前仍是未提交 working-tree 內容。

# Verdict

REQUEST_CHANGES
