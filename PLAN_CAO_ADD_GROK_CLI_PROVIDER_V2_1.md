# PLAN V2.1：CAO 新增 Grok CLI Provider

> 文件狀態：Approved for Phase 0 — Review V2.1 修正版  
> 文件版本：V2.1  
> 文件日期：2026-07-15  
> V2.1 修正：upstream `AgentProfile` 不存在 `effort` 欄位  
> 目標專案：`awslabs/cli-agent-orchestrator`  
> Provider ID：`grok_cli`  
> Provider binary：`grok`  
> CAO 驗證基準：upstream `main` 同步至 commit `32db5a1`  
> Grok CLI 驗證基準：`grok 0.2.93 (f00f96316d4b)`  
> Review 來源：`Review_CAO_ADD_Grok_CLI_Provider.md`、`Review_CAO_ADD_Grok_CLI_Provider-v1.md`

---

## 0. V2.1 修訂摘要

本版已消化第二輪 review 與 approved follow-up 的全部修正，重點如下：

| Review V1 發現 | V2 決策 |
|---|---|
| Grok MCP subprocess 很可能不繼承 parent env | 將「不繼承」設為 Phase 0 base case；依序驗證 direct inheritance、config env expansion、`grok mcp add -e` forward-by-name |
| 兩種 MCP fallback 也可能失敗 | 明確把「V1 僅支援 lifecycle，不宣告 orchestration」列為預期且可接受的交付結果 |
| 測試目錄不符合 repo 慣例 | 改回 `test/providers/test_grok_cli_unit.py` 與 `test/providers/fixtures/` |
| quality 指令錯用 Ruff | 改為 repo 現行的 Black、isort、mypy |
| `grok_cli` pytest marker 未註冊 | 第一版只使用既有 `integration`／`e2e` marker，並以 `require_grok` fixture 做 skip |
| pseudo-code 使用不存在的 `ProviderError` | 改為 `RuntimeError`／`ValueError`／`TimeoutError`，並補 profile `None` guard |
| Grok 無 rules file | 明確列為 V1 known limitation；rules 過長時 fail fast，不假設不存在的替代方案 |
| E2E CLI 子命令未核實 | Phase 0 必須保存 `cao --help`／`cao session --help`，E2E runbook 只使用實際存在的命令 |
| 每次 launch 執行 `grok version` | 改為 server process 生命週期內 cache |
| upstream `AgentProfile.effort` 不存在 | V1 不把 profile-driven effort 當核心 scope；使用 `getattr(profile, "effort", None)` 保持 fork 相容，正式 schema 支援拆成 Optional PR 2B |

V2 的 base case：

> 基本 Grok lifecycle provider 應可交付；CAO MCP orchestration 是否包含在 V1，取決於 Phase 0 能否找到不改寫共享 config、且可安全傳遞 `CAO_TERMINAL_ID` 的方式。

---

## 1. 目標

在 CLI Agent Orchestrator（CAO）中加入正式的 `grok_cli` provider，使 CAO 可以：

1. 在獨立 terminal backend 中啟動 Grok interactive TUI。
2. 注入 CAO agent profile、runtime skills 與 model；reasoning effort 僅在目標分支已提供 profile schema 支援時啟用。
3. 使用 Grok 原生 permission flags 執行 hard enforcement。
4. 正確判斷 `UNKNOWN`、`IDLE`、`PROCESSING`、`COMPLETED`、`WAITING_USER_ANSWER`、`ERROR`。
5. 從 Grok TUI transcript 擷取最後一則 assistant response。
6. 在 Gate C 通過時支援 CAO 的 `assign`、`handoff`、`send_message` orchestration；若無安全的 MCP identity forwarding，V1 明確標示為不支援。
7. 同時支援 tmux raw-buffer path、pyte rendered-screen path，以及 herdr native-status path。
8. 不修改或覆寫使用者既有 Grok 全域設定。
9. 提供可重現的 unit、integration、security 與 E2E 驗證。

---

## 2. Review 後的主要修正

| Review 問題 | 原方案 | V2 決策 |
|---|---|---|
| `--plugin-dir` 不存在 | 每 terminal 建立 plugin directory | 完全移除，不使用不存在的旗標 |
| MCP identity forwarding | 假設 Grok MCP subprocess 會繼承 pane env | **預期不繼承**；Claude Code 已有相同 precedent，Phase 0 依序實測三條候選路徑 |
| MCP config race | 將 literal terminal ID 寫入共享 config | 絕不使用共享 literal ID；找不到安全 forwarding 就不宣告 V1 orchestration |
| Subagent 逃逸 | 只限制 Bash／Edit 等工具 | restricted 且不允許 `execute_bash` 時強制 `--no-subagents` |
| Shell false-IDLE | 只匹配 `❯` | composite Grok-ready marker + `shell_baseline` |
| `_detect_status` 死碼 | active marker branch 與 fallback 相同 | 刪除重複 branch，保留單一優先序 |
| on-demand restore metadata | 未記錄 | 文件化既有限制，另開 follow-up |
| Web UI 修改點 | 只給搜尋方向 | 指名 `AgentPanel.tsx` 與 `components.test.tsx` |
| effort schema | 假設 upstream `AgentProfile.effort` 存在 | upstream V1 不把 effort 當必要功能；provider 使用 `getattr(profile, "effort", None)` 保持 fork 相容，完整 upstream 支援拆成 Optional PR 2B |
| herdr | 只規劃 tmux fixtures | native-status contract test + smoke test |
| 測試佈局 | root-level test/fixtures | 對齊 `test/providers/` 慣例 |
| Quality tooling | Ruff | 對齊 Black、isort、mypy |
| pytest marker | 新增未註冊的 `grok_cli` marker | 沿用既有 `integration`／`e2e` marker |
| 長 rules | 假設未來可用 rules file | Grok 0.2.93 無 rules file；超限時 fail fast 並明確文件化 |

---

## 2.1 V2.1 additional correction：upstream AgentProfile 沒有 `effort`

本計畫目標是 upstream `awslabs/cli-agent-orchestrator`。目前 upstream
`AgentProfile` 宣告了 `model`，但沒有 `effort`。因此：

- Grok Provider V1 不把 profile-driven effort 視為 release blocker。
- provider 不得直接存取 `profile.effort`。
- command builder 使用 `getattr(profile, "effort", None)`：
  - upstream profile 不會拋出 `AttributeError`；
  - 已自行擴充 effort 欄位的 fork 仍可映射到 Grok `--effort`。
- `getattr()` 只提供執行期相容性，**不代表 upstream profile schema 已支援 effort**。
- upstream 正式支援必須另行擴充 `AgentProfile`、profile parsing tests 與文件，
  並拆成 Optional PR 2B，不阻塞 Grok Provider V1。

---

## 3. 核心架構決策

### 3.1 Provider 模式

第一版採用 persistent interactive TUI：

```bash
grok [flags...]
```

不使用 one-shot prompt mode 作為主要 provider。

理由：

- CAO 需要 multi-turn session。
- `assign`、`handoff`、inbox delivery 需要 terminal 持續存在。
- human operator 必須能 attach terminal。
- status monitor 與 response extraction 依賴持續存在的 CLI process。

`grok agent stdio`／ACP 只列入後續評估，不與第一版 TUI provider 混合。

### 3.2 Prompt 注入

使用：

```bash
--rules "<combined rules>"
```

combined rules 組成：

```text
agent profile system prompt
+ runtime skill catalog
+ restricted profile security prompt
+ startup guard
```

startup guard：

```text
Acknowledge your role briefly, then wait for a concrete task.
Do not inspect, edit, execute, or call tools during startup.
```

不使用 `--system-prompt-override`，避免取代 Grok 內建 system prompt。

#### 長 rules 限制

`grok 0.2.93` 沒有 `--rules-file`；`--prompt-file` 只處理 initial prompt，不能取代 system rules。因此 V1：

1. 在 command builder 計算 `shlex.join(command)` 的長度。
2. 設定一個保守、可測試的 provider limit，並記錄實際 OS `ARG_MAX` 只作 diagnostics。
3. 超過 limit 時使用 `ValueError` fail fast，訊息需指出哪一部分過長：profile prompt、runtime skills 或 security rules。
4. 不截斷 rules，不默默丟棄 skills，也不假設未驗證的 file-based 替代方案。
5. 文件把「超長 agent profile/rules 不支援」列為 V1 known limitation。

### 3.3 Model precedence 與 optional effort extension

Model：

1. agent profile `model`
2. provider constructor `model`
3. Grok user default

Effort：

1. upstream `AgentProfile` 目前沒有 `effort` 欄位，因此 V1 不宣稱
   profile-driven effort 已受 upstream 支援。
2. provider 只做防禦式讀取：

   ```python
   effort = getattr(profile, "effort", None) if profile else None
   ```

3. 沒有 effort 時省略 `--effort`。
4. customized fork 已擴充 effort 欄位時，可沿用相同 command builder。
5. upstream 正式支援需拆成 Optional PR 2B，至少修改：
   - `src/cli_agent_orchestrator/models/agent_profile.py`
   - profile loader/schema tests
   - `docs/agent-profile.md`
   - Grok command-builder tests
6. V1 不在 CAO 內硬編 model 或 effort default。
7. effort schema 未合併不阻塞 lifecycle、permissions、status、extraction 或
   Gate C 的 MCP feasibility 判定。


### 3.4 Permission enforcement

Provider 預設使用：

```bash
--always-approve
```

目的不是取消限制，而是避免 unattended orchestration 卡在每次工具 approval。

restricted profile 同時產生 native deny rules：

```bash
--always-approve
--deny Bash
--deny Edit
...
```

規則：

- `allowed_tools` 為空或包含 `*`：視為 unrestricted。
- restricted profile：使用 Grok native `--allow`／`--deny`。
- `grok_cli` **不加入** `SOFT_ENFORCEMENT_PROVIDERS`。
- security prompt 只作 defense-in-depth，不代替 native enforcement。
- restricted profile 不允許 `execute_bash` 時，必須加：

```bash
--no-subagents
```

原因：subagent 可能透過 delegated shell 或 edit tool 繞過父 agent 的限制。

### 3.5 MCP 與 orchestration

#### V1 不可變原則

Provider 不自動寫入或覆寫：

- `~/.grok/config.toml`
- project `.grok/config.toml`
- project `.mcp.json`
- Grok global plugin registry

Provider 不使用不存在的 `--plugin-dir`，也不以每 terminal 改寫共享 config 的方式注入 literal `CAO_TERMINAL_ID`。

#### 已知基礎設施

CAO 會把：

```bash
CAO_TERMINAL_ID=<terminal-id>
```

設進每個 tmux pane/window environment；`cao-mcp-server` 也以該環境變數識別 caller。

未知邊界只有：

```text
grok process → Grok 啟動的 MCP subprocess
```

Claude Code provider 已記錄「parent shell env 不會自動轉發到 MCP subprocess」的 precedent。Grok 的 CLI permission 介面與 Claude Code 相容，因此 V2 把 **不繼承 parent env** 視為較可能的 base case，而不是例外。

#### Phase 0 候選路徑，依序驗證

**Path A — direct inheritance**

靜態註冊：

```bash
grok mcp add cao-mcp-server -- cao-mcp-server
```

驗證 MCP subprocess 是否直接繼承每個 Grok process 的 `CAO_TERMINAL_ID`。預期成功率偏低，但成本最低，仍先實測。

**Path B — config env expansion**

驗證 Grok MCP config 是否能保留：

```toml
env = { CAO_TERMINAL_ID = "${CAO_TERMINAL_ID}" }
```

並在每個 Grok process 啟動 MCP subprocess 時動態解析。這也是未驗證假說，不得當成保證。

**Path C — forward-by-name**

檢查 `grok mcp add --help` 的 `-e` 語意，實測下列形式是否可只傳 key、由啟動時 parent environment 補值：

```bash
grok mcp add cao-mcp-server \
  -e CAO_TERMINAL_ID \
  -- cao-mcp-server
```

若 CLI 只接受 `KEY=value`，此路徑判定失敗；不得把當下 terminal ID 固定寫進 user/project config。

#### Gate C 結果

- 任一 Path 可在兩個並行 Grok terminals 中穩定傳遞不同 identity：V1 可啟用 orchestration。
- 三條 Path 全部失敗：V1 仍可交付 lifecycle provider，但必須標示：

```text
grok_cli orchestration = NOT SUPPORTED
```

此結果是 V2 的可接受 base case，不視為 provider lifecycle 的 release blocker。

#### MCP preflight

只有 Gate C 通過後才實作 strict orchestration preflight。候選命令：

```bash
grok inspect --json
grok mcp doctor cao-mcp-server --json
```

驗證：

- `cao-mcp-server` 已被載入。
- command 可啟動。
- server origin 可辨識。
- project config 沒有以同名 server 覆蓋安全設定。
- CAO MCP tools 可見。
- MCP caller identity 與當前 terminal 一致。

Provider preflight 只讀，不修改 config。

#### Agent profile `mcpServers`

V1：

- 不自動轉換任意 profile `mcpServers`。
- 若 profile 宣告額外 MCP servers，記錄明確 warning，要求在 Grok 端預先配置。
- Gate C 未通過時，不宣告 `cao-mcp-server` orchestration。
- 任意 MCP 自動隔離延後到有官方 per-process config mechanism 後。

### 3.6 Status detection

狀態判定必須使用 fixture-first calibration，不可單靠推測 regex。

優先序：

1. herdr native status
2. empty buffer → `UNKNOWN`
3. startup／approval／selection dialogs → `WAITING_USER_ANSWER`
4. fatal/auth/process error → `ERROR`
5. live processing marker → `PROCESSING`
6. Grok-specific ready surface：
   - `_turns == 0` → `IDLE`
   - `_turns > 0` → `COMPLETED`
7. 已 initialized 且已 dispatch task，但沒有 ready marker → `PROCESSING`
8. 其他 → `UNKNOWN`

ready surface 不可只匹配：

```text
❯
```

至少需要一個 Grok-specific companion marker，例如實機 fixture 中的 model/mode footer、input box chrome 或其他穩定 surface。

### 3.7 Shell baseline

`initialize()` 在執行 `grok` 前：

1. 等待 shell ready。
2. 取得 pane current command。
3. 設定 `self.shell_baseline`。
4. 再送出 Grok command。

作用：

- 防止 zsh `❯` prompt 被誤判為 Grok ready。
- CLI 結束後可判斷 pane 是否回到 shell。
- server restart 後，`ProviderManager.get_provider()` 可從 DB 恢復 baseline。

### 3.8 Response extraction

Primary path 使用 terminal transcript boundary：

1. strip terminal escapes。
2. 找最後一個「非空 user prompt」。
3. 從該位置向後取內容。
4. 截斷於下一個 empty ready input surface。
5. 過濾：
   - thought/activity chrome
   - tool-call chrome
   - footer/status bar
   - selector hints
   - banner/tips
6. 保留 assistant 的 Markdown、code fence、list 與空行。
7. 空結果或無 boundary 時 raise `ValueError`，交由 CAO extraction retry/fallback 處理。

不要使用單一寬鬆的 `❯` regex 同時判斷 user prompt、shell prompt 與 ready prompt。

---

## 4. 範圍

### 4.1 第一版包含

- `grok_cli` registration。
- binary detection。
- interactive TUI initialization。
- profile rules。
- runtime skill prompt。
- model。
- optional effort compatibility hook（不是 upstream V1 必要功能）。
- native tool restrictions。
- subagent escape mitigation。
- tmux raw-buffer detection。
- pyte screen detection。
- herdr native status。
- response extraction。
- graceful exit。
- Gate C 通過時的 CAO MCP preflight 與 orchestration E2E；未通過時改為 unsupported-path docs/test。
- CLI、API、Web UI provider exposure。
- unit、integration、security、E2E tests。
- provider documentation。

### 4.2 第一版不包含

- 自動登入或管理 xAI API key。
- 自動修改 Grok user/project config。
- 自動安裝或解除安裝 Grok plugins。
- 任意 profile `mcpServers` 自動轉換。
- session resume／fork UI。
- ACP transport。
- 動態 external provider plugin framework。
- 對所有未來 Grok TUI 版本零維護保證。

---

## 5. 檔案修改清單

### 5.1 必要 source files

| 檔案 | 修改 |
|---|---|
| `src/cli_agent_orchestrator/models/provider.py` | 新增 `ProviderType.GROK_CLI = "grok_cli"` |
| `src/cli_agent_orchestrator/providers/grok_cli.py` | 新增 provider implementation |
| `src/cli_agent_orchestrator/providers/manager.py` | import、factory branch、constructor kwargs |
| `src/cli_agent_orchestrator/cli/commands/launch.py` | 加入 workspace-access provider set |
| `src/cli_agent_orchestrator/services/terminal_service.py` | 加入 runtime skill prompt provider；不加入 soft enforcement |
| `src/cli_agent_orchestrator/utils/tool_mapping.py` | 新增 Grok native tool mapping 與 subagent 安全註解 |
| `src/cli_agent_orchestrator/api/main.py` | 加入 provider binary detection：`"grok_cli": "grok"` |

### 5.2 Web UI

| 檔案 | 修改 |
|---|---|
| `web/src/components/AgentPanel.tsx` | 同步 `FALLBACK_PROVIDERS`，加入 `grok_cli`，並清理 stale entries |
| `web/src/test/components.test.tsx` | 更新 provider list assertion |

正常路徑仍應使用 `/agents/providers` API；fallback 只是 API 不可用時的保底。

### 5.3 Tests

對齊 repo 現行 provider test 慣例：

```text
test/providers/test_grok_cli_unit.py
test/providers/fixtures/
  grok_cli_shell_prompt_raw.txt
  grok_cli_shell_prompt_screen.txt
  grok_cli_startup_raw.txt
  grok_cli_startup_screen.txt
  grok_cli_idle_raw.txt
  grok_cli_idle_screen.txt
  grok_cli_processing_raw.txt
  grok_cli_processing_screen.txt
  grok_cli_completed_raw.txt
  grok_cli_completed_screen.txt
  grok_cli_waiting_question_raw.txt
  grok_cli_waiting_question_screen.txt
  grok_cli_waiting_plan_approval_raw.txt
  grok_cli_waiting_plan_approval_screen.txt
  grok_cli_auth_error_raw.txt
  grok_cli_tool_error_raw.txt
  grok_cli_long_response_raw.txt
test/e2e/
  test_grok_cli_e2e.py
```

若 fixture 數量過多，可使用：

```text
test/providers/fixtures/grok_cli/
```

但檔名仍保留 `grok_cli_<state>_<path>.txt` 前綴，避免狀態與來源不清。

既有跨模組測試中補：

- provider manager registration
- API provider binary/reporting
- terminal service runtime skills
- tool mapping
- Web fallback provider list

Live Grok tests 使用既有 `integration` marker；真正 end-to-end cases 使用既有 `e2e` marker。缺 binary/auth 時由 `require_grok` fixture skip。

### 5.4 Docs

| 檔案 | 修改 |
|---|---|
| `docs/grok-cli.md` | 安裝、登入、MCP setup、限制、troubleshooting |
| `README.md` | provider table、valid provider values |
| `docs/tool-restrictions.md` | Grok hard-enforcement 與 subagent 規則 |
| `docs/agent-profile.md` | Grok model／MCP limitations；effort 僅在 Optional PR 2B 合併時補充 |
| `CHANGELOG.md` | 新 provider 說明，依維護者 release flow 決定 |

---

## 6. Provider class 設計

### 6.1 Class state

Grok version probe 使用 module-level process cache，而不是每個 provider instance 各自 spawn：

```python
_GROK_VERSION_CACHE: dict[str, str | None] = {}


class GrokCliProvider(BaseProvider):
    supports_screen_detection = True

    def __init__(...):
        super().__init__(...)
        self._agent_profile = agent_profile
        self._model = model
        self._initialized = False
        self._turns = 0
```

cache key 使用 resolved binary path；測試可清空 cache。

不再需要：

```python
self._tmp_paths
self._plugin_dir
self._mcp_server_names
```

原因：V1 不修改 Grok config，也不建立 plugin directory。

### 6.2 Required properties

```python
@property
def paste_enter_count(self) -> int:
    return 1  # 由 Phase 0 實測確認

@property
def blocks_orchestrated_input_while_waiting_user_answer(self) -> bool:
    return True
```

視實機結果決定是否覆寫：

```python
@property
def paste_submit_delay(self) -> float:
    return 0.3
```

### 6.3 Command builder

目標 command：

```bash
grok \
  --always-approve \
  [--model <model>] \
  [--effort <effort>] \
  [--rules <rules>] \
  [--allow/--deny ...] \
  [--no-subagents]
```

Pseudo-code：

```python
def _build_grok_command(self) -> str:
    binary = shutil.which("grok")
    if not binary:
        raise RuntimeError("Grok CLI not found: 'grok' is not on PATH")

    profile = (
        load_agent_profile(self._agent_profile)
        if self._agent_profile
        else None
    )
    command = [binary, "--always-approve"]

    profile_model = profile.model if profile else None
    model = profile_model or self._model
    if model:
        command.extend(["--model", model])

    # Upstream AgentProfile currently has no `effort` field.
    # getattr keeps customized forks compatible, but does not add
    # upstream profile-schema support by itself.
    effort = getattr(profile, "effort", None) if profile else None
    if effort:
        command.extend(["--effort", effort])

    base_rules = profile.system_prompt if profile else ""
    rules = self._apply_skill_prompt(base_rules or "")

    restricted = bool(
        self._allowed_tools and "*" not in self._allowed_tools
    )
    if restricted:
        rules = f"{rules}\\n\\n{SECURITY_PROMPT}".strip()
        command.extend(
            self._build_permission_args(self._allowed_tools or [])
        )

        if "execute_bash" not in (self._allowed_tools or []):
            command.append("--no-subagents")

    if rules:
        command.extend([
            "--rules",
            self._append_startup_guard(rules),
        ])

    rendered = shlex.join(command)
    self._validate_command_length(rendered)
    return rendered
```

例外類型：

- binary/config contract error：`RuntimeError`
- rules/arguments validation：`ValueError`
- startup wait：`TimeoutError`

不要新增 repo 不存在的通用 `ProviderError`，除非另有全 repo error-model refactor。

### 6.4 MCP preflight helper

Gate C 通過後，private helper：

```python
def _check_cao_mcp_registration(self) -> McpPreflightResult:
    ...
```

`McpPreflightResult` 放在 `providers/grok_cli.py` module level：

```python
@dataclass(frozen=True)
class McpPreflightResult:
    configured: bool
    healthy: bool
    origin: str | None
    identity_verified: bool
    message: str
```

行為：

- read-only，不修改 config。
- Gate C 未通過時不建立「假裝可用」的 preflight；回傳/記錄 unsupported。
- orchestration-required profile 可 hard fail。
- standalone lifecycle worker可 warning 後繼續。
- `grok inspect --json` 或 doctor schema parse 失敗時，訊息需保留 stderr 摘要但移除 secrets。

### 6.5 Initialize sequence

```text
wait_for_shell
  ↓
capture shell_baseline
  ↓
build command
  ↓
status_monitor.notify_input_sent
  ↓
send command
  ↓
handle startup dialogs
  ↓
wait for Grok-specific IDLE/COMPLETED
  ↓
set _initialized = True
```

重要約束：

- `_initialized` 設定前，shell-only fixture 不可回傳 `IDLE`。
- Grok ready 判斷必須需要 Grok-specific marker。
- startup dialog 判斷先於 ready footer。
- timeout 使用 `provider_init_timeout`，不要硬編不同常數，除非實測證明需要 provider override。

### 6.6 mark_input_received

```python
def mark_input_received(self) -> None:
    super().mark_input_received()
    self._turns += 1
```

### 6.7 Status functions

```python
def get_status(self, buffer: str) -> TerminalStatus:
    native = self._resolve_native_status()
    if native is not None:
        return native

    if not buffer:
        return TerminalStatus.UNKNOWN

    clean = strip_terminal_escapes(buffer)
    return self._detect_status(clean, rendered=False)
```

```python
def get_status_from_screen(self, screen_lines: list[str]) -> TerminalStatus:
    rows = [line.rstrip() for line in screen_lines]
    return self._detect_status("\n".join(rows), rendered=True)
```

`_detect_status()` 不保留重複、相同回傳值的 dead branch。

### 6.8 Exit 與 cleanup

```python
def exit_cli(self) -> str:
    return "/quit"

def cleanup(self) -> None:
    # V1 owns no Grok config or plugin resources.
    return None
```

若實測 `/quit` 不穩定，測試 fallback：

1. `/quit`
2. `/exit`
3. Ctrl-D
4. Ctrl-C 後 Ctrl-D

最終只保留一個正常 path，其他由 terminal teardown 負責。

---

## 7. Tool mapping

初始 mapping 必須以 `grok --help`、permission docs 與 E2E 校準為準。

候選：

```python
"grok_cli": {
    "execute_bash": ["Bash"],
    "fs_read": ["Read", "Grep"],
    "fs_write": ["Edit"],
    "fs_list": ["Read", "Grep"],
    "web_fetch": ["WebFetch"],
}
```

注意：

1. 不要用過度寬鬆 wildcard 讓 restricted profile 失效。
2. 不要封鎖整個 `MCPTool`，否則 CAO orchestration tools 也會消失。
3. profile 不允許 `execute_bash` 時加入 `--no-subagents`。
4. profile 允許 Bash 時，即使禁止 Edit，也無法保證 shell 不寫檔；文件需說明這是 permission model 的基本邊界。
5. 所有 native tool names 必須從 `grok inspect`、實際 permission denial message 或官方文件確認。

---

## 8. Phase 0：Blocking calibration

Phase 0 完成前不進入正式 provider implementation PR。

### 8.1 固定版本與環境

記錄：

```text
CAO commit
Python version
tmux version
backend
terminal dimensions
shell
Grok version + build hash
OS
```

基準：

```text
grok 0.2.93 (f00f96316d4b)
```

### 8.1A CAO profile schema baseline

Phase 0 必須保存目標 ref 的 profile schema：

```bash
git show <target-ref>:src/cli_agent_orchestrator/models/agent_profile.py
```

判定：

- 沒有 `AgentProfile.effort`：視為 upstream baseline；V1 只保留 defensive
  compatibility hook。
- 已有 `AgentProfile.effort`：視為 customized fork；可執行 optional effort
  mapping tests。
- 不得因開發機器的 fork 有 effort，就假設 upstream 也有相同欄位。

### 8.2 CLI capability matrix

執行並保存輸出：

```bash
grok version
grok --help
grok inspect --help
grok mcp --help
grok mcp add --help
grok mcp doctor --help
grok agent --help
grok plugin --help
cao --help
cao session --help
cao launch --help
cao shutdown --help
```

確認：

- `--always-approve`
- `--rules`
- `--allow`
- `--deny`
- `--model`
- `--effort`
- `--no-subagents`
- `--session-id`
- `/quit`
- 不存在 `--plugin-dir`

### 8.3 MCP environment inheritance spike

建立只回報 process environment 與 caller identity 的測試 MCP server。

基礎前提：

- CAO pane 已具有正確 `CAO_TERMINAL_ID`。
- `cao-mcp-server` 依賴 `os.environ["CAO_TERMINAL_ID"]`。
- Claude Code 已有 parent env 不自動 forward 到 MCP subprocess 的 precedent。

Phase 0 的預期：

```text
Path A 很可能失敗；
Path B / C 才是大概率的實際候選；
三者全敗則 V1 不支援 orchestration。
```

#### 8.3.1 Path A：direct inheritance

兩個 Grok process 共用同一份靜態 registration：

```bash
CAO_TERMINAL_ID=terminal-a grok
CAO_TERMINAL_ID=terminal-b grok
```

驗證：

```text
Grok A MCP subprocess → terminal-a
Grok B MCP subprocess → terminal-b
```

並行至少 20 回合，不得交叉。

#### 8.3.2 Path B：config env expansion

若 Path A 失敗，測試：

```toml
[mcp_servers.cao-mcp-server]
command = "cao-mcp-server"
env = { CAO_TERMINAL_ID = "${CAO_TERMINAL_ID}" }
```

這是未驗證假說。必須證明 `${...}` 在每次 Grok process 啟動 MCP subprocess 時解析，而不是註冊時保存 literal string。

#### 8.3.3 Path C：`grok mcp add -e` forward-by-name

先保存：

```bash
grok mcp add --help
```

實測 CLI 是否接受只給 key：

```bash
grok mcp add cao-mcp-server \
  -e CAO_TERMINAL_ID \
  -- cao-mcp-server
```

驗證它是否等同 Codex/Kimi 的 `env_keys` forwarding。若只允許 `KEY=value`，此路徑失敗；不可把 terminal-specific value 寫進共享 config。

#### 8.3.4 共通檢查與 ADR

共通檢查：

- `grok inspect --json` 是否顯示 server origin。
- project config 是否覆蓋 user config。
- `grok mcp doctor --json` schema 是否可穩定解析。
- abnormal termination 後是否殘留任何 provider 建立的狀態。
- user與project scope優先順序。
- 兩個 terminals 並行 20 回合無 identity cross-talk。

Phase 0 ADR 必須記錄：

```text
selected_path = A | B | C | none
orchestration_supported = true | false
evidence = fixture/log/test references
```

### 8.4 TUI capture

每個狀態同時收集：

- tmux `pipe-pane` raw bytes
- `get_history()` snapshot
- pyte rendered screen
- terminal dimensions
- Grok version

Fixtures：

```text
shell_prompt
startup
idle
processing
completed
waiting_question
waiting_plan_approval
permission_prompt
auth_error
tool_error
long_response
multiline_code_response
```

### 8.5 Shell false-IDLE spike

至少測試：

- zsh theme 使用 `❯`
- shell prompt 只有 `❯`
- Grok ready prompt 也有 `❯`
- shell prompt 包含 Grok-like文字的極端案例

驗收：

```text
shell-only → UNKNOWN
Grok startup incomplete → UNKNOWN/PROCESSING
Grok ready surface → IDLE
```

### 8.6 Paste behavior

使用 bracketed paste 測試：

- single-line prompt
- multi-line prompt
- code block prompt
- Unicode／中文 prompt

確認：

- `paste_enter_count`
- `paste_submit_delay`
- prompt 不會只進入 editor 而未送出
- prompt 不會被送兩次

### 8.7 Subagent security spike

restricted profile：

```yaml
allowedTools:
  - fs_read
```

測試要求 Grok：

1. 直接執行 shell 寫檔。
2. 直接 Edit 寫檔。
3. spawn subagent 寫檔。
4. spawn subagent 執行 shell。
5. 透過 MCP 非 CAO tool 嘗試寫檔。

驗收：所有寫入均失敗；`--no-subagents` 生效。

### 8.8 Phase 0 exit criteria

Basic-provider 必須完成：

- [ ] Grok-specific ready marker 已確定。
- [ ] raw 與 screen fixtures 已提交。
- [ ] paste 行為已確定。
- [ ] subagent bypass 已封鎖。
- [ ] exit command 已確認。
- [ ] CLI/E2E command names 已由 `cao --help`／`cao session --help` 核實。
- [ ] long-rules limit 與 fail-fast 行為已決定。
- [ ] target branch 的 `AgentProfile` schema 已記錄；effort 是否屬於本次 scope 已定案。
- [ ] unsupported limitations 已寫入 ADR.

MCP Gate C 二擇一：

**Supported**

- [ ] Path A、B 或 C 至少一條通過。
- [ ] 兩 terminal 20 回合 identity 不交叉。
- [ ] provider 不自動修改 Grok config。
- [ ] 可進入 Phase 4 orchestration。

**Unsupported**

- [ ] 三條 Path 失敗已有證據。
- [ ] 標記 `grok_cli orchestration = NOT SUPPORTED`。
- [ ] README、`docs/grok-cli.md`、provider capability/API response 已定義如何呈現。
- [ ] Phase 4 改為 unsupported diagnostics/docs，不做 assign/handoff/send_message E2E。

不得以共享 literal terminal ID config 勉強通過。

---

## 9. Phase 1：Registration 與 basic lifecycle

### Tasks

- [ ] 新增 `ProviderType.GROK_CLI`。
- [ ] 新增 `GrokCliProvider` skeleton。
- [ ] Provider manager factory branch。
- [ ] launch workspace access。
- [ ] API binary detection。
- [ ] binary missing error。
- [ ] shell baseline capture。
- [ ] command launch。
- [ ] startup timeout。
- [ ] graceful exit。
- [ ] cleanup no-op。
- [ ] manager registration tests。
- [ ] API/provider list tests。

### Exit criteria

- `cao launch --provider grok_cli` 可啟動 Grok。
- 初始 terminal 最終到 `IDLE`。
- shell prompt 不會提前完成 initialize。
- `/quit` 後 terminal 回到 captured shell baseline。
- server restart 後 on-demand provider 可辨識 CLI 已退出。

---

## 10. Phase 2：Profile、skills、model、permissions（optional effort hook）

### Tasks

- [ ] `grok_cli` 加入 `RUNTIME_SKILL_PROMPT_PROVIDERS`。
- [ ] 不加入 `SOFT_ENFORCEMENT_PROVIDERS`。
- [ ] profile system prompt → `--rules`。
- [ ] runtime skills append。
- [ ] startup guard。
- [ ] model precedence。
- [ ] 不直接存取 `profile.effort`；使用 `getattr(profile, "effort", None)`。
- [ ] 只有在目標分支已擴充 effort schema 時，才驗證其映射到 `--effort`；upstream V1 不以此為 blocker。
- [ ] native allow/deny mapping。
- [ ] restricted security prompt。
- [ ] `--no-subagents` safety rule。
- [ ] shell quoting tests。
- [ ] long rules test。

### Exit criteria

- profile role 被採用但 startup 不執行工具。
- profile model 優先於 runtime model。
- upstream profile 沒有 effort 欄位時不拋出 `AttributeError`，且 command 不包含 `--effort`。
- 只有在 effort schema extension 存在時，profile effort 才正確傳入 `--effort`。
- read-only profile 無法 shell、edit 或委派 subagent 寫檔。
- unrestricted profile 不被意外限制。

---

## 11. Phase 3：Status detection 與 extraction

### Tasks

- [ ] raw-buffer detector。
- [ ] rendered-screen detector。
- [ ] herdr native path。
- [ ] waiting precedence。
- [ ] error patterns。
- [ ] processing marker。
- [ ] `_turns` IDLE/COMPLETED split。
- [ ] stale marker handling。
- [ ] long-response extraction。
- [ ] Markdown/code fence preservation。
- [ ] extraction retry policy。
- [ ] dead branch removal。

### Exit criteria

狀態轉移：

```text
UNKNOWN
→ IDLE
→ PROCESSING
→ COMPLETED
→ PROCESSING
→ COMPLETED
```

其他：

- approval／question picker → `WAITING_USER_ANSWER`
- stale spinner 不會永久 `PROCESSING`
- stale ready prompt 不會提前 `COMPLETED`
- long response 可完整擷取
- shell output 不會被當 assistant response
- raw 與 screen fixtures 結果一致，除非有明確文件化差異
- herdr empty-buffer 情境仍由 native status 正常運作

---

## 12. Phase 4：MCP 與 orchestration

此 Phase 受 Gate C 控制。

### 12.1 Gate C 通過

Tasks：

- [ ] 實作 read-only MCP preflight。
- [ ] 文件提供一次性 Grok MCP setup。
- [ ] 驗證 `grok inspect --json`。
- [ ] 驗證 `grok mcp doctor`。
- [ ] 驗證 selected forwarding path。
- [ ] `assign` E2E。
- [ ] `handoff` E2E。
- [ ] `send_message` E2E。
- [ ] concurrent workers E2E。
- [ ] project override diagnostic。
- [ ] missing MCP actionable error。

Exit criteria：

- Grok supervisor 可 `assign` Grok worker。
- callback 回正確 supervisor。
- 兩個並行 workers 不交換 terminal identity。
- `handoff` 正確回收結果。
- `send_message` 在 terminal ready 後送達。
- provider 不修改任何 Grok config。

### 12.2 Gate C 未通過

Tasks：

- [ ] provider capability 明確標記 orchestration unsupported。
- [ ] standalone launch、prompt、status、extraction 仍完整支援。
- [ ] profile 宣告 CAO MCP orchestration 時給 actionable warning/error。
- [ ] README provider matrix 區分 lifecycle 與 orchestration。
- [ ] `docs/grok-cli.md` 說明三條候選路徑均未通過的證據。
- [ ] tests 驗證不會誤宣告 `assign`／`handoff`／`send_message` 可用。

Exit criteria：

- 使用者不會把 lifecycle support 誤解成 multi-agent orchestration support。
- 不存在共享 literal ID 或破壞性 config workaround。

## 13. Phase 5：Web UI、docs、CI 與 hardening

### Tasks

- [ ] Web API provider list。
- [ ] `AgentPanel.tsx` fallback list。
- [ ] `components.test.tsx`。
- [ ] `docs/grok-cli.md`。
- [ ] README provider/capability matrix。
- [ ] tool restriction docs。
- [ ] known limitations。
- [ ] fixture-based CI。
- [ ] optional live integration tests。
- [ ] version drift warning。
- [ ] troubleshooting matrix。
- [ ] Gate C supported/unsupported presentation。

### Known limitations 必須包含

1. Grok CLI TUI regex 與 fixtures 以 `0.2.93` 校準。
2. Provider 不自動管理 Grok authentication。
3. Provider 不自動寫 MCP config。
4. 任意 profile `mcpServers` 不會自動同步。
5. Gate C 未通過時，V1 只支援 lifecycle，不支援 CAO `assign`／`handoff`／`send_message`。
6. upstream `AgentProfile` 沒有 `effort` 欄位；V1 的 `getattr()` 只提供 fork 相容性，不代表 upstream profile-driven effort 已受支援。
7. on-demand provider restore 目前不會從 DB 恢復 constructor-only `model`／`skill_prompt`。
8. Bash 被允許時，filesystem write restriction 不能阻止 shell 自行寫檔。
9. Grok 0.2.93 沒有 `--rules-file`；超長 rules 會 fail fast，不自動截斷。
10. session resume／fork 不在第一版範圍。

## 14. Unit test plan

### 14.1 Constructor

- default state。
- allowed tools。
- skill prompt。
- model。
- `_turns == 0`。
- `_initialized is False`。
- `supports_screen_detection is True`。
- `blocks_orchestrated_input_while_waiting_user_answer is True`。

### 14.2 Command builder

- binary missing。
- basic command。
- model from constructor。
- profile model precedence。
- no model omission。
- upstream-like profile 沒有 `effort` attribute：不崩潰且省略 `--effort`。
- customized fork profile 有 `effort` attribute：正確加入 `--effort`。
- 若提交 Optional PR 2B：profile loader 可解析 `effort`。
- rules append。
- startup guard。
- runtime skill append。
- Unicode/shell quoting。
- unrestricted command。
- restricted deny rules。
- no-subagents when Bash disallowed。
- subagents remain enabled when Bash explicitly allowed。
- no use of `--plugin-dir`。
- no writes to Grok config。
- profile is `None` without NPE。
- command length below limit。
- command length above limit raises `ValueError`。
- long rules are never silently truncated。
- version probe cache keyed by binary path。

### 14.3 Initialize

Mock：

- `wait_for_shell`
- backend current command
- `status_monitor.notify_input_sent`
- `send_keys`
- startup dialog handler
- `wait_until_status`

Cases：

- shell timeout。
- binary error。
- ready success。
- Grok startup timeout。
- shell-only `❯` cannot satisfy init。
- shell baseline stored。
- notify occurs before launch。
- `_initialized` only after successful ready。

### 14.4 Status fixtures

每個 fixture 同時測：

```python
get_status(raw)
get_status_from_screen(screen)
```

Cases：

- empty。
- shell prompt。
- startup。
- idle。
- processing。
- completed。
- waiting question。
- plan approval。
- permission prompt。
- auth error。
- tool error。
- stale processing marker。
- stale ready marker。
- long output。
- unknown。

### 14.5 Native/herdr

- `_resolve_native_status()` non-None 時不解析 buffer。
- native `IDLE` pre-dispatch → `IDLE`。
- native `IDLE` post-dispatch → shared base contract。
- native `PROCESSING` → `PROCESSING`。
- native `COMPLETED` → flush-wait contract。
- native `WAITING_USER_ANSWER` passthrough。

### 14.6 Extraction

- single response。
- multi-turn only returns last。
- Markdown。
- code fence。
- nested list。
- Unicode。
- tool calls filtered。
- thought lines filtered。
- footer filtered。
- long response。
- no prompt boundary raises。
- empty response raises。
- shell prompt not returned。

### 14.7 Permission mapping

- every CAO vocabulary maps deterministically。
- unknown CAO tool behavior documented。
- no broad MCP deny。
- no-subagents gate under `execute_bash`。
- deny list stable order，避免 flaky command assertions。

### 14.8 Registration/UI

- enum contains `grok_cli`。
- manager creates correct class。
- API reports binary availability。
- launch accepts provider。
- runtime skills are passed。
- hard-enforcement warning is not emitted。
- frontend fallback contains current providers and `grok_cli`。

---

## 15. Integration test plan

使用 repo 已註冊的 marker：

```python
@pytest.mark.integration
```

不新增 `grok_cli` marker，除非維護者希望修改 `pyproject.toml` marker registry。Grok-specific availability 由 fixture 控制：

```python
@pytest.fixture
def require_grok():
    if shutil.which("grok") is None:
        pytest.skip("Grok CLI is not installed")
    # auth/model readiness checks as appropriate
```

注意 repo `addopts` 預設排除 `e2e`；integration marker 本身不負責 binary/auth skip。

Prerequisites：

- `grok` binary。
- authenticated account。
- optional model access。
- tmux。
- Gate C 通過時才需要 CAO MCP registration。

Cases：

1. launch and idle。
2. simple prompt。
3. second prompt。
4. code modification。
5. read-only restriction。
6. subagent restriction。
7. long answer。
8. waiting question。
9. plan approval。
10. graceful exit。
11. auth failure。
12. `grok inspect --json` parse。
13. two terminals concurrently。
14. restart CAO server and recover provider adapter。
15. Gate C supported path，或 unsupported capability path。

缺少 binary/auth 時 skip，不影響 fixture-based CI。

## 16. E2E test plan

### 16.1 Lifecycle

Phase 0 先保存：

```bash
cao --help
cao session --help
cao launch --help
cao shutdown --help
```

只根據實際 help 使用命令。不要在 PLAN 中假設 `cao session status` 或 `cao session send` 必然存在。

E2E 實作應透過 repo 已存在的 command/API 完成以下動作：

```text
launch grok_cli session
resolve session/terminal identifier
read status
send "Return exactly: GROK_OK"
wait for COMPLETED
extract GROK_OK
shutdown session
```

在測試 source comment 或 ADR 中記錄最終使用的實際 CLI command。

### 16.2 Headless

```bash
cao launch \
  --provider grok_cli \
  --agents developer \
  --headless \
  --async \
  "Inspect the repository and return exactly one sentence."
```

### 16.3 Handoff

Grok supervisor：

```text
handoff a read-only review task to a Grok worker
```

驗證：

- worker created。
- worker reaches processing。
- result returned。
- terminal cleanup correct。

### 16.4 Assign

Grok supervisor 同時 assign 兩個 workers。

驗證：

- tool call立即返回。
- workers 並行。
- callback sender identity 正確。
- result 不會送錯 supervisor。

### 16.5 Send message

在 worker 完成第一輪後送 follow-up。

驗證：

- inbox queued。
- ready 後送達。
- `_turns` 增加。
- 第二輪正確 `COMPLETED`。

### 16.6 Cross-provider

至少測：

```text
Grok supervisor → Claude/Codex worker
Claude/Codex supervisor → Grok worker
```

### 16.7 Security

read-only Grok worker：

- shell write denied。
- Edit denied。
- subagent disabled。
- permitted read succeeds。
- CAO orchestration MCP tools仍可用。

---

## 17. Manual verification runbook

### 17.1 Environment

```bash
grok version
grok models
grok inspect --json
grok mcp list --json
grok mcp doctor cao-mcp-server --json
```

### 17.2 Static MCP setup

```bash
grok mcp add cao-mcp-server -- cao-mcp-server
```

確認 command resolve：

```bash
command -v cao-mcp-server
```

### 17.3 Unit tests

```bash
uv run pytest test/providers/test_grok_cli_unit.py -q
uv run pytest test/providers/ -q
uv run pytest -q
```

### 17.4 Quality

依 repo 現行設定執行：

```bash
uv run black --check src/ test/
uv run isort --check-only src/ test/
uv run mypy src/
```

不使用 Ruff，除非 repo 後續正式加入 Ruff 設定。

若 Makefile／CI 有標準 target，優先使用標準 target，並確認其最終仍覆蓋 Black、isort、mypy。

### 17.5 Frontend

```bash
cd web
npm test
npm run build
```

### 17.6 Live

```bash
uv run pytest -m integration test/e2e/test_grok_cli_e2e.py -q
uv run pytest -m e2e test/e2e/test_grok_cli_e2e.py -q
```

實際路徑依 repo E2E test layout 調整；不使用未註冊的 `grok_cli` marker。

### 17.7 Concurrency

開兩個 terminal，確認：

```text
terminal A → MCP caller id A
terminal B → MCP caller id B
```

重複至少 20 回合。

---

## 18. Observability 與 diagnostics

Provider log 必須包含：

- Grok binary path。
- Grok version。
- command flags，但不得完整記錄含 secret 的 rules/env。
- initialization stage。
- selected model/effort 名稱。
- restricted/unrestricted mode。
- subagents disabled 狀態。
- MCP preflight summary。
- status transition reason。
- extraction boundary failure。
- shell baseline 與 CLI exit detection。

不得記錄：

- xAI API key。
- OAuth token。
- arbitrary secret env values。
- 完整敏感 system prompt。

建議 debug reason：

```text
status=WAITING_USER_ANSWER reason=plan_approval
status=PROCESSING reason=live_footer
status=IDLE reason=ready_surface_no_turn
status=COMPLETED reason=ready_surface_turns_1
status=UNKNOWN reason=shell_prompt_only
```

---

## 19. Compatibility 與 version drift

### 19.1 Calibration version

第一版 regex 與 fixtures 明確標示：

```text
grok 0.2.93 (f00f96316d4b)
```

### 19.2 Runtime warning

Provider/server 對：

```bash
grok version
```

做 process-lifetime cache；同一 server process 只 probe 一次。cache key 至少包含 resolved binary path，方便 binary path 改變時失效。

策略：

- exact calibrated version：debug。
- newer version：info/warning，不阻止啟動。
- older unknown version：warning。
- command 失敗：不阻止啟動，但記錄 unknown。

不做嚴格 version pin，避免 minor update 無法使用。

### 19.3 Fixture update policy

Grok TUI 改版時：

1. 保存新版本 fixtures。
2. 新舊 fixtures同時測試。
3. 只在無法兼容時提高 minimum version。
4. status regex 修改需附 stale-marker regression test。

---

## 20. 風險與對策

| 風險 | 等級 | 對策 |
|---|---:|---|
| Grok MCP subprocess 不 forward parent env | Blocker for orchestration | 預期 Path A 可能失敗；依序驗證 Path B/C；三者全敗則 V1 lifecycle-only |
| config `${VAR}` 不 expansion | High | 明確視為未驗證；不把 literal terminal ID 寫進共享 config |
| `grok mcp add -e` 只接受 `KEY=value` | High | forward-by-name spike；不支援就判定 Path C 失敗 |
| project config 覆蓋 user server | High | `grok inspect --json` 檢查 origin，提供 diagnostic |
| Subagent 繞過 restrictions | High | no-Bash restricted profile 強制 `--no-subagents` |
| Shell `❯` false-IDLE | High | composite ready marker + shell baseline |
| TUI stale redraw marker | High | raw/screen fixtures + herdr contract tests |
| `--always-approve` 擴大影響 | High | native deny + no-subagents + sandbox follow-up |
| long rules 超過 command-line limit | Medium | deterministic length validation + fail fast；無 rules-file fallback |
| arbitrary profile MCP 未注入 | Medium | V1 warning/docs；等待 per-process isolation |
| model/skill metadata restore 不完整 | Medium | known limitation + DB metadata follow-up |
| Grok CLI 更新破壞 regex | Medium | cached version logging、fixtures、compat policy |
| MCP preflight startup latency | Low | process-lifetime cache；strict doctor 只在需要時執行 |
| cleanup 死碼 | Low | V1 cleanup no-op，不建立 temp resources |

## 21. PR 拆分

### PR 1：Phase 0 evidence

只提交：

- capability matrix。
- fixture capture scripts。
- raw/screen fixtures。
- MCP Path A/B/C evidence 與 selected-path ADR。
- subagent security proof。
- architecture decision record。

不得先提交未校準 regex。

### PR 2：Registration + lifecycle + profile

包含：

- enum/factory/API/CLI registration。
- provider launch。
- shell baseline。
- rules/model。
- permission mapping。
- no-subagents。
- defensive `getattr(profile, "effort", None)` compatibility hook。
- lifecycle unit tests。

不包含：

- orchestration 宣告。
- upstream `AgentProfile.effort` schema extension。

### Optional PR 2B：AgentProfile effort schema extension

只有在維護者希望 upstream profile 正式控制 Grok reasoning effort 時提交。

包含：

- `AgentProfile.effort: Optional[str] = None`。
- profile parse/validation tests。
- `docs/agent-profile.md`。
- Grok `--effort` command-builder tests。
- 支援值與未知值處理政策。

此 PR 不阻塞 Grok Provider V1。


### PR 3：Status + extraction

包含：

- raw detector。
- screen detector。
- native status。
- extraction。
- fixture regression suite。
- live lifecycle tests。

### PR 4：MCP + orchestration

前提：Gate C 通過；若未通過，PR 4 改為 unsupported capability/docs/tests。

包含：

- read-only MCP preflight。
- diagnostics。
- assign/handoff/send_message。
- concurrency E2E。
- cross-provider E2E。

### PR 5：UI + docs + CI

包含：

- Web UI。
- README/docs。
- CI 使用既有 `integration`／`e2e` markers。
- troubleshooting。
- changelog。

---

## 22. Definition of Done

### Registration

- [ ] `ProviderType("grok_cli")` 成功。
- [ ] CLI、API、Web UI 都列出 Grok。
- [ ] binary availability 正確。

### Lifecycle

- [ ] initial state 正確到 `IDLE`。
- [ ] shell prompt 不會 false-IDLE。
- [ ] task 可進入 `PROCESSING`。
- [ ] task 完成進入 `COMPLETED`。
- [ ] multi-turn 正常。
- [ ] exit 回到 shell。
- [ ] server restart 後 adapter 可恢復基本狀態。

### Profile

- [ ] rules。
- [ ] skills。
- [ ] model。
- [ ] upstream profile 缺少 effort 欄位時安全省略，不產生 `AttributeError`。
- [ ] optional：Optional PR 2B 合併時，`--effort` mapping 與 profile parsing 測試通過。
- [ ] startup guard。

### Security

- [ ] native deny 生效。
- [ ] no-subagents 生效。
- [ ] read-only E2E 無寫入。
- [ ] Gate C 通過時，CAO MCP orchestration tools 未被誤封。
- [ ] Gate C 未通過時，provider 不誤宣告 MCP orchestration capability。
- [ ] 不記錄 secrets。

### Status/extraction

- [ ] raw fixtures。
- [ ] screen fixtures。
- [ ] herdr native tests。
- [ ] waiting precedence。
- [ ] stale marker regression。
- [ ] long response。
- [ ] Markdown/code preservation。

### MCP/orchestration

Gate C 通過：

- [ ] selected forwarding path 可用。
- [ ] two-terminal concurrency。
- [ ] assign。
- [ ] handoff。
- [ ] send_message。
- [ ] provider 不修改 Grok config。

Gate C 未通過：

- [ ] capability 明確標記 unsupported。
- [ ] docs/UI/API 不誤宣告 orchestration。
- [ ] standalone lifecycle 保持可用。
- [ ] 無不安全 workaround。

### Quality

- [ ] unit suite pass。
- [ ] integration suite pass。
- [ ] frontend test/build pass。
- [ ] lint/type checks pass。
- [ ] docs 完整。
- [ ] known limitations 明確。

---

## 23. Go / No-Go gates

### Gate A：Basic provider

Go：

- TUI ready marker穩定。
- shell false-IDLE已解。
- paste與exit已確認。

No-Go：

- 無法可靠判斷 ready/completed。
- prompt submission不穩定。

### Gate B：Restricted profiles

Go：

- native deny有效。
- subagent path無法繞過。

No-Go：

- restricted agent仍能透過 subagent或內建工具寫檔。

### Gate C：Orchestration

Go：

- Path A、B 或 C 至少一條能 per-process 傳遞 identity。
- 兩 terminal 20 回合 concurrency 無交叉。
- missing/override diagnostics 清楚。
- provider 不修改共享 config。

No-Go for orchestration，但不是 No-Go for lifecycle release：

- 三條 Path 全敗。
- 需要每 terminal 覆寫共享 literal terminal ID。
- identity 有交叉風險。
- provider 必須破壞性修改 user/project config。

No-Go 結果：

```text
grok_cli lifecycle = SUPPORTED
grok_cli orchestration = NOT SUPPORTED
```

文件、API capability 與 Web UI 必須一致呈現。

---

## 24. 後續項目

不阻塞第一版：

1. Optional PR 2B：為 upstream `AgentProfile` 新增 optional `effort` schema。
2. 將 `model`、`skill_prompt`，以及 schema extension 合併後的 `effort` 持久化到 terminal metadata，改善 on-demand adapter restore。
3. 尋找官方 per-process Grok config directory override 或 MCP env-key forwarding。
4. 支援 arbitrary profile `mcpServers` 自動隔離。
5. 評估 `grok agent stdio` ACP backend。
6. 利用 `--session-id` 與 `grok export` 做更可靠 transcript fallback。
7. 評估 `--sandbox` 是否可安全成為 restricted profile default。
8. 支援 Grok session resume／continue／fork。
9. 將 provider registration 重構成集中 registry，減少多檔硬編碼。

---

## 25. 參考資料

### CAO

- Repository: <https://github.com/awslabs/cli-agent-orchestrator>
- Provider implementation skill: <https://github.com/awslabs/cli-agent-orchestrator/blob/main/skills/cao-provider/SKILL.md>
- Base provider: `src/cli_agent_orchestrator/providers/base.py`
- Provider manager: `src/cli_agent_orchestrator/providers/manager.py`
- Terminal service: `src/cli_agent_orchestrator/services/terminal_service.py`
- Tool mapping: `src/cli_agent_orchestrator/utils/tool_mapping.py`

### Grok CLI

- CLI reference: <https://docs.x.ai/build/cli/reference>
- MCP servers: <https://docs.x.ai/build/features/mcp-servers>

### Review baseline

- CAO commit：`32db5a1`
- Grok：`0.2.93 (f00f96316d4b)`
- Review date：2026-07-15

---

## 26. 最終實作順序

```text
Phase 0 evidence
  ↓
TUI / paste / exit / security Gate A-B
  ↓
MCP Path A → Path B → Path C
  ↓
Gate C:
  ├─ pass → lifecycle + orchestration
  └─ fail → lifecycle-only + explicit unsupported capability
  ↓
Registration + lifecycle
  ↓
Profile + hard permissions（optional effort hook）
  ↓
Status + extraction
  ↓
Conditional MCP preflight + orchestration
  ↓
UI + docs + CI
```

最重要的原則：

> Grok MCP subprocess 的 parent-env forwarding 不應被預設成立。V2 以「可能不支援 orchestration」作為正常 base case，先用證據決定 capability。

> 不以修改共享 Grok config 的方式模擬 per-terminal isolation；三條安全 forwarding 路徑均失敗時，V1 明確交付 lifecycle-only provider。

> Restricted profile 的安全模型必須涵蓋 Grok subagents；否則 native Bash/Edit deny 不能視為完整 hard enforcement。
