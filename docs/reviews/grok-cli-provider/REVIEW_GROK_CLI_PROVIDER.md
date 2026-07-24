# Review Findings

## [P1] pyte 實際 viewport 無法辨識 ready 與 waiting 狀態

- File: `/Users/alex/Developer/cli-agent-orchestrator-grok-provider/src/cli_agent_orchestrator/providers/grok_cli.py:236`
- Problem: `READY_INPUT_PATTERN` 要求輸入框左右邊界位於同一行，但 Phase 0 的真實 pyte capture 會因寬度換行，使 `│ ❯`、右邊界與 Grok footer 分散在多行。直接套用真實 capture 時，idle 與 completed viewport 會回傳 `UNKNOWN`。此外，真實 `waiting_question_after` 也會被判成 `COMPLETED`，不是 PLAN 要求的 `WAITING_USER_ANSWER`。
- Why it matters: 啟用 `CAO_PYTE_STATUS` 時，初始化可能逾時，完成狀態也可能無法被辨識；等待使用者回答時，`blocks_orchestrated_input_while_waiting_user_answer` 的保護不會生效。
- Recommendation: 以已校準的真實 pyte viewport 建立換行容忍的複合 ready marker，並補入真實 waiting-question／plan fixture；不要只用同一行的簡化輸入框。

## [P1] 舊 processing marker 會永久壓過較新的完成畫面

- File: `/Users/alex/Developer/cli-agent-orchestrator-grok-provider/src/cli_agent_orchestrator/providers/grok_cli.py:229`
- Problem: `_detect_status()` 在整個 4096 字元 tail 內先搜尋 processing marker，再判斷 ready surface。只要歷史輸出仍含 `Starting session…`、`Thinking…` 或 `Responding…`，即使較新的 ready footer 已出現，仍會回傳 `PROCESSING`。目前測試反而固定了這個行為。
- Why it matters: 違反 PLAN 明定的 stale-processing regression 要求，會讓已完成的 Grok turn 卡在 `PROCESSING`，導致等待、輸出擷取與後續訊息無法正常推進。
- Recommendation: 根據 marker 的順序、viewport 位置或完成邊界判斷目前狀態，並加入「舊 spinner + 新 ready footer」的 raw/rendered regression fixture。

## [P1] 回覆擷取會靜默遺失內容，且真實 Markdown 格式未被保留

- File: `/Users/alex/Developer/cli-agent-orchestrator-grok-provider/src/cli_agent_orchestrator/providers/grok_cli.py:269`
- Problem: `body_start` 會在 prompt 後八行內尋找任何空行；若 transcript 沒有 prompt separator、但 assistant 第一段後有正常段落空行，整個第一段會被丟棄而不報錯。另外，`QUERY_PATTERN` 會把 assistant code/output 中任何以 `❯ ` 開頭的行誤認為新的 user boundary。實際 Phase 0 Markdown capture 經目前路徑擷取後只剩 `GROK_MARKDOWN` 與 `print("GROK_CODE")`，heading 與 code fence 已消失；現有通過測試使用的是人工含反引號字串，沒有驗證真實 TUI 輸出。
- Why it matters: 這會回傳看似成功但不完整或錯誤的結果，直接違反 PLAN 的「保留 Markdown/code fence/list/blank lines」及「歧義時安全失敗」契約。
- Recommendation: 以真實 raw capture 驗證 boundary；不能可靠區分 prompt continuation 時應 `ValueError`，不要跳過不確定的前段。Markdown 必須使用可保留語意的來源或經 fixture 驗證的 ANSI/style reconstruction。

## [P2] 測試 fixtures 不是 Phase 0 的 raw/rendered 證據集

- File: `/Users/alex/Developer/cli-agent-orchestrator-grok-provider/test/providers/test_grok_cli_unit.py:23`
- Problem: 目標 worktree 只有四個簡化的 `*_screen.txt`，沒有 PLAN 要求的 raw fixtures、startup、waiting question、plan approval、permission、auth/tool error、stale marker、long response、Unicode、nested list 等案例，也沒有逐一對 `get_status(raw)` 與 `get_status_from_screen(screen)` 驗證。完整 Phase 0 ADR/captures 目前未提交到目標分支，甚至沒有存在於任何 Grok branch commit。
- Why it matters: 測試無法代表真實 raw 與 pyte 路徑，已實際掩蓋上述狀態與 extraction 缺陷。
- Recommendation: 將經審核的 Phase 0 脫敏證據提交到分支，直接參數化 raw/rendered 測試；不要以手工縮短的畫面取代校準 fixture。

## [P2] 無 profile 的正常啟動不會注入 startup guard

- File: `/Users/alex/Developer/cli-agent-orchestrator-grok-provider/src/cli_agent_orchestrator/providers/grok_cli.py:174`
- Problem: `STARTUP_GUARD` 只在 profile rules、skill prompt 或 security prompt 非空時加入；基本 command 直接成為 `grok --always-approve`。現有 `test_basic_command_uses_resolved_binary` 還把缺少 guard 固定成預期行為。
- Why it matters: 不符合 PLAN 的 combined-rules 與 Definition of Done；不同 profile 是否具有啟動期防護取決於是否恰好有其他 rules。
- Recommendation: 將 startup guard 視為獨立且一致的 rules 部分，並更新基本 command 與初始化測試。

## [P3] 文件未完整記錄 Gate C 證據與 restart 限制

- File: `/Users/alex/Developer/cli-agent-orchestrator-grok-provider/docs/grok-cli.md:68`
- Problem: 文件只概述「沒有 verified way」，未逐項說明 Path A direct inheritance、Path B runtime env expansion、Path C key-only forwarding 的結果；也漏掉 PLAN 要求的 on-demand restore 不恢復 constructor-only model／skill prompt 限制。
- Why it matters: 使用者無法判斷 Gate C 為何是 NO-GO、何種 Grok 上游能力可重新評估，也可能誤解 server restart 後的設定還原程度。
- Recommendation: 簡要加入三條路徑的實證結果、重新評估條件及 restore 限制。

# Open Questions

- Phase 0 ADR 與完整 captures 是否原本預期先合併至此分支？目前它們只存在另一個 worktree 的未追蹤檔案中，沒有可供 PR 審查或 CI 使用的 commit。

# Acceptable Limitations

- Gate C = NO-GO，V1 僅提供 lifecycle，不支援 CAO MCP orchestration。
- 不使用 `--plugin-dir`。
- 不修改 Grok、MCP、user 或 global plugin configuration。
- 不自動轉換 profile `mcpServers`。
- upstream `AgentProfile` 沒有 `effort`；使用防禦式 `getattr()` 即可。
- Bash 被允許時，Edit deny 無法阻止 shell 寫檔。
- 超長 inline rules 採 fail-fast，不截斷。
- session resume／continue／fork、ACP/stdio 不在 V1。
- Live Grok E2E 必須明確設定 `CAO_RUN_GROK_INTEGRATION=1` 才執行。

# Validation Notes

直接驗證：

- 使用 `mcp codebase-memory` 確認索引、架構、變更影響及 status call path。
- 檢查全部目標 worktree diff；未發現 `--plugin-dir`、Grok config write 或 orchestration 支援的虛假實作。
- 針對性 Python suite：`270 passed`。
- 完整非 E2E suite：`4055 passed, 21 skipped, 1 failed`；唯一失敗正是已知且與 Grok 無關的 workflow timeout `300.0 != 30`。
- Web：`61 passed`，production build 成功。
- Black 與 isort 通過。
- Grok 相關四個 source 檔 mypy 通過；全專案 mypy 有 14 個既存錯誤，均不在 Grok 修改檔。
- 以 Phase 0 真實 captures 額外交叉測試，重現 pyte `UNKNOWN`、waiting question 誤判及 Markdown 格式流失。
- 未執行 Live Grok E2E，也未修改任何使用者或 Grok 設定。

僅由 implementer 報告、未直接驗證：

- 實機 Grok lifecycle、paste、exit 與 restriction 行為。
- Gate B 實機 deny／`--no-subagents` 結果。
- Grok 0.2.93／0.2.101 的 live calibration 執行過程。

另外，目標分支 `HEAD` 仍等於 `origin/main@32db5a1`；所有 Grok 變更目前都是未提交 working-tree 內容。

# Verdict

REQUEST_CHANGES
