# Review Findings

## [P1] Public LAST-output 路徑仍會把 active partial transcript 當成已完成結果回傳

- File: `/Users/alex/Developer/cli-agent-orchestrator-grok-provider/src/cli_agent_orchestrator/services/terminal_service.py:923`
- Problem: `GrokCliProvider.extract_last_message_from_script()` 現在會正確對 active capture 丟出 `ValueError`，但 Grok 沒有設定 `extraction_tail_lines`，所以 `get_output(..., OutputMode.LAST)` 走 shared escalation path。該路徑在每一層吞掉 `ValueError`，full-history extraction 失敗後仍於 sparse-buffer 分支回傳 HTTP/API 可用的字串：`[NO RESPONSE - agent completed without producing a text response ...]` 加上整份 raw transcript。使用真實 `long_response_completed.ansi` 重現時，回傳值仍包含 active `LONG_RESPONSE_MARKER` partial output，且前綴錯誤宣稱 agent 已完成。
- Why it matters: 第二輪 P1 在 provider method 層已修正，但 public service contract 仍會將「尚在生成」轉換成成功的 LAST-output payload。CLI、API、MCP 或其他直接讀取 LAST 的呼叫者可能把 partial transcript／錯誤的 completed 判斷當作任務結果；這也繞過了 active capture 應安全失敗的修正目的。
- Recommendation: 讓 active／no-completion extraction failure 能穿透 public LAST 路徑，而不是落入 generic no-response/overflow fallback。可為 Grok 使用明確的 typed extraction error 並在 `get_output()` 保留該錯誤，或在 extraction 前檢查 provider status；若採 `extraction_tail_lines` 路徑，也需加入 service-level regression，證明 active Grok capture 會 raise/回傳非成功狀態且不夾帶 partial response。完成 capture 仍須正常 extraction。

## [P2] Sanitized raw fixtures 無法重現提交的 rendered_pyte fixtures

- File: `/Users/alex/Developer/cli-agent-orchestrator-grok-provider/test/providers/fixtures/grok_cli/render_with_pyte.py:12`
- Problem: 依 fixture README 宣告的 120x40 尺寸，用 repository 自帶的 `render_with_pyte.py` 邏輯重新 render 所有具有 `rendered_pyte` 對應檔的 raw ANSI capture，20 組中有 18 組不相等；只有 `idle.ansi` 與 `shell_prompt.ansi` 完全一致。差異不只 trailing whitespace，例如 `completed_capture_pane` 有 13 行水平位移，`plan_after` 有 29 行內容/換行位移。現有 paired status tests 分別讀取兩份檔案，但沒有驗證 rendered fixture 真的是由 sanitized raw fixture 產生。
- Why it matters: Phase 0 evidence 無法由提交內容重現，raw status path 與 pyte status path 實際測的是兩個不同畫面。這削弱了校準證據，也可能在脫敏或 fixture 更新時掩蓋只出現在真實 pyte render 的邊界回歸。
- Recommendation: 從最終 sanitized raw captures 重新產生 `rendered_pyte`，確認 layout/status/extraction 後提交；若脫敏會改變 terminal cell width，應採等寬 placeholder 或重新校準預期畫面。加入 parity test，直接呼叫 render 邏輯並比較每一組 raw → rendered_pyte 輸出。

## [P3] Skills 文件前段仍把 Grok 描述成可使用 `load_skill`

- File: `/Users/alex/Developer/cli-agent-orchestrator-grok-provider/docs/skills.md:115`
- Problem: 文件前段仍宣稱每個 CAO agent 都能依 injected instructions 使用 `load_skill`，並在第 121 行說 skill resolution 對所有 runtime-prompt providers 不變；第 123 行已把 Grok 加入該 provider 群組。只有後面的第 175–179 行才說 Grok lifecycle V1 無法使用 CAO `load_skill`。
- Why it matters: 同一份文件對 Grok 的 skill availability 給出互相衝突的規則。只閱讀 discovery/scoping 章節的使用者可能把 injected catalog 誤認為可實際載入的能力。
- Recommendation: 在第 115 與 121 行的通則直接排除 Grok lifecycle V1，或提前連結 Grok exception；保持「catalog 可注入，但 CAO `load_skill` retrieval 不可用」在所有相關段落一致。

# Open Questions

- 無。上述 public LAST-output 行為與 raw/pyte fixture divergence 均可由目前工作樹直接重現。

# Acceptable Limitations

- Gate C = NO-GO；V1 僅支援 lifecycle，不支援 `assign`、`handoff`、`send_message` 或 CAO `load_skill` retrieval。
- 不使用 `--plugin-dir`，不修改 Grok、MCP、user/project/global plugin configuration，也不自動轉換 profile `mcpServers`。
- Phase 0 保留 Grok 0.2.93 與 0.2.101 的分離證據；未把混合版本宣稱為單一 pinned calibration。
- upstream `AgentProfile` 沒有 `effort`；防禦式 `getattr()` 可接受。
- Bash 被允許時，Edit deny 無法阻止 shell 寫檔。
- 超長 inline rules 採 fail-fast，不截斷。
- native selection、interactive approval 與 authentication-error states 未安全觸發，保留明確 SKIP。
- session resume／continue／fork、ACP/stdio 不在 V1。
- Live Grok E2E 必須明確設定 `CAO_RUN_GROK_INTEGRATION=1` 才執行。

# Validation Notes

第三輪直接驗證：

- 使用 MCP `codebase-memory` 重新索引工作樹（9414 nodes／43788 edges），搜尋 extraction symbol、provider exposure，並檢查 provider/service/test 變更影響。由於 `get_output()` 透過 provider polymorphism 動態呼叫 extraction，graph 沒有建立 inbound caller edge，因此另以原始碼與 runtime probe 驗證 public call path。
- 第二輪的 provider-level findings 已實質改善：active fixture 在直接 extraction 時被拒絕；bare shell `❯` + ANSI Grok prompt regression 通過；個人 username/hostname/path 與本機 MCP inventory 已脫敏；Security/skills provider matrices 與 ADR decision state已更新。
- Public LAST regression probe：以真實 active fixture mock backend history，`get_output(..., LAST)` 回傳 `[NO RESPONSE - agent completed ...]`，內容仍包含 `LONG_RESPONSE_MARKER`，確認 P1 仍存在於 service boundary。
- Fixture reproducibility probe：20 組 raw/rendered_pyte pairs 中 18 組 mismatch；多組有可見的一欄位移及換行差異。
- 針對性 Python suite：`304 passed`。
- 完整非 E2E suite：`4075 passed, 21 skipped, 94 deselected, 1 failed`；唯一失敗仍是與 Grok 無關的既有 workflow cancel timeout（expected `30`、observed `300.0`）。改善報告記載 `14 skipped`，與本次實際結果的 `21 skipped` 不同。
- Grok live E2E：成功收集 `1 test`；未設定 opt-in 環境變數，因此未執行實機流程。
- Web：`61 passed`，production build 成功；僅有既有 jsdom canvas/error noise 與 bundle-size warning。
- `git diff --check`、Black、isort 均通過；五個變更相關 Python source 的 mypy 通過。
- 未修改 Grok/user/project configuration。除本第三輪 review 報告外，未修改實作或 fixture。

目標分支 `HEAD` 仍等於 `origin/main@32db5a1`；Grok provider、fixtures、文件與 reviews 仍是未提交 working-tree 內容。

# Verdict

REQUEST_CHANGES
