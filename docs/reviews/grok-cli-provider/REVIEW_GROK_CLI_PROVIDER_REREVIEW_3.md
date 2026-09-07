# Review Findings

## [P2] Active output 在 HTTP API 被錯誤映射為 404 Not Found

- File: `/Users/alex/Developer/cli-agent-orchestrator-grok-provider/src/cli_agent_orchestrator/api/main.py:1393`
- Problem: 新增的 `IncompleteOutputError` 繼承 `ValueError`。`terminal_service.get_output()` 現在會正確傳遞此錯誤，但 `GET /terminals/{terminal_id}/output` 將所有 `ValueError` 都映射成 404。以 TestClient 讓 service 丟出 `IncompleteOutputError("still processing")`，實際回應為 `404 {"detail":"still processing"}`，不是代表 terminal 仍存在且輸出尚未完成的狀態。現有 regression 只測 service function，沒有覆蓋 API boundary。
- Why it matters: public API client、CLI 與 ops MCP 可能把仍在工作的 terminal 誤判為不存在，採取錯誤的重建、清理或失敗處理。第三輪的 partial-output 洩漏已修正，但新增的 typed contract 尚未在真正 public boundary 得到正確語意。
- Recommendation: 在 generic `ValueError` 之前明確捕捉 `IncompleteOutputError`，回傳可重試且不暗示資源不存在的狀態，例如 `409 Conflict`（或專案明確選定的 425/503 contract），並加入 API regression；404 應只保留給 terminal/provider not found。

## [P2] PR-range `git diff --check` 失敗，改善報告的通過結果不可重現

- File: `/Users/alex/Developer/cli-agent-orchestrator-grok-provider/test/providers/fixtures/grok_cli/rendered_pyte/completed_capture_pane.txt:1`
- Problem: `git diff --check origin/main...HEAD` 以 exit code 2 失敗，對 raw ANSI、rendered 與 rendered_pyte fixtures 報出大量 trailing whitespace／blank-at-EOF。這些空白多半是 120x40 terminal snapshot 的必要 cell content，但 repository 沒有 `.gitattributes` 對該 fixture tree 宣告 whitespace policy。改善報告宣稱 `git diff --check` 通過，與實際 committed PR range 不符；在 clean working tree 執行無 ref 的 `git diff --check` 只會檢查空 diff。
- Why it matters: 任何以 base...HEAD 執行 whitespace gate 的 CI／review workflow 都會失敗，且目前無法區分刻意保留的 terminal cells 與真正意外的 whitespace。這使已提交 commit 尚未符合可重現的 validation claim。
- Recommendation: 為需要 byte-exact 固定寬度內容的 fixture 路徑加入明確 `.gitattributes` whitespace 例外，或改用不觸發 repository whitespace gate、但仍可 byte-for-byte重建的表示方式；再以 `git diff --check origin/main...HEAD` 驗證。不要移除會破壞 20/20 parity 的必要空白。

# Open Questions

- 無。API 404 mapping 與 PR-range whitespace failure 均可在目前 commit `b05a6be` 直接重現。

# Acceptable Limitations

- Gate C = NO-GO；V1 僅支援 lifecycle，不支援 `assign`、`handoff`、`send_message` 或 CAO `load_skill` retrieval。
- 不使用 `--plugin-dir`，不修改 Grok、MCP、user/project/global plugin configuration，也不自動轉換 profile `mcpServers`。
- Phase 0 保留 Grok 0.2.93 與 0.2.101 的分離證據；未把混合版本宣稱為單一 pinned calibration。
- Bash 被允許時，Edit deny 無法阻止 shell 寫檔。
- native selection、interactive approval 與 authentication-error states 未安全觸發，保留明確 SKIP。
- session resume／continue／fork、ACP/stdio 不在 V1。
- Live Grok E2E 必須明確設定 `CAO_RUN_GROK_INTEGRATION=1` 才執行。

# Validation Notes

第四輪直接驗證：

- 使用 MCP `codebase-memory` 重新索引 commit（9440 nodes／43753 edges），搜尋 `IncompleteOutputError`、`get_output()`、API route 與下游 CLI/ops MCP consumers，並檢查相對 `origin/main` 的 142 個變更檔案。
- 第三輪三項 findings 的核心修正均成立：service LAST path 不再吞掉 `IncompleteOutputError` 或回傳 partial；raw→rendered_pyte parity 為 `20/20`；skills discovery/scoping 段落已在首次介紹處說明 Grok 無 CAO `load_skill` retrieval。
- Service regression：active Grok fixture 丟出 `IncompleteOutputError`，completed fixture 正常回傳 `CAPTURE_COMPLETED`。
- API regression probe：相同 typed error 經 `GET /terminals/.../output?mode=last` 被映射成 `404 {"detail":"still processing"}`。
- 針對性 Python suite：`356 passed`。
- 完整非 E2E suite（`--ignore=test/e2e -m 'not e2e'`）：`4097 passed, 21 skipped, 1 failed`；唯一失敗仍是與 Grok 無關的既有 workflow cancel timeout（expected `30`、observed `300.0`）。改善報告記載 `14 skipped`，本次使用其宣稱的 explicit E2E exclusion 仍得到 `21 skipped`。
- Grok live E2E：成功收集 `1 test`；未執行 opt-in 實機流程。
- Web：`61 passed`，production build 成功；只有既有 jsdom noise 與 bundle-size warning。
- Black、isort 與六個變更相關 source 的 mypy 通過。
- `git diff --check origin/main...HEAD` 失敗；這是本輪第二項 finding。無 ref 的 `git diff --check` 因 working tree 對 tracked files 為 clean，不能驗證已提交 PR range。
- Branch 現為 `feat/grok-cli-provider@b05a6be`；implementation 已提交。working tree 只剩 improvement/review 報告為 untracked，不含實作變更。
- 未修改 Grok/user/project configuration。除本第四輪 review 報告外，未修改實作、fixtures 或 committed content。

# Verdict

REQUEST_CHANGES
