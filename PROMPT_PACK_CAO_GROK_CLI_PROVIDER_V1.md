# Prompt Pack：CAO 新增 Grok CLI Provider

> 適用計畫：`PLAN_CAO_ADD_GROK_CLI_PROVIDER_V2_1.md`  
> 建議模式：高推理／high effort  
> 使用方式：每次只執行一個階段；該階段驗收後再開新對話或新工作階段執行下一個提示詞  
> 目標 repository：`awslabs/cli-agent-orchestrator`  
> Provider ID：`grok_cli`  
> Provider binary：`grok`

---

## 1. 使用順序

依下列順序執行：

```text
Prompt 0：工作區與規格預檢
  ↓
Prompt 1：Phase 0 / PR 1 Evidence
  ↓
Prompt 1R：Phase 0 Evidence Review 與 Gate 決策
  ↓
Prompt 2：PR 2 Registration + Lifecycle + Profile
  ↓
Prompt 2R：PR 2 Review/Fix
  ↓
Prompt 2B：Optional AgentProfile effort schema
  ↓
Prompt 3：PR 3 Status + Extraction
  ↓
Prompt 3R：PR 3 Review/Fix
  ↓
Gate C = GO     → Prompt 4A：MCP + Orchestration
Gate C = NO-GO  → Prompt 4B：Lifecycle-only capability path
  ↓
Prompt 5：Web UI + Docs + CI
  ↓
Prompt 6：Final Audit
```

### 不要一次貼全部提示詞

每個 Prompt 都有明確停止點。執行者完成該階段後必須停止，不得自行開始下一階段。

### 建議工作方式

每個 PR 使用獨立 branch：

```text
feat/grok-cli-phase0-evidence
feat/grok-cli-lifecycle
feat/grok-cli-status-extraction
feat/grok-cli-orchestration
docs/grok-cli-provider
```

Optional effort schema 使用獨立 branch：

```text
feat/agent-profile-effort
```

---

# Prompt 0：工作區與規格預檢

## 何時使用

第一次把 repository 與 PLAN 交給 coding agent 時使用。此階段只確認環境與規格，不修改 source code。

## 提示詞

```text
You are the implementation engineer for the Grok CLI provider in
awslabs/cli-agent-orchestrator.

Primary specification:
PLAN_CAO_ADD_GROK_CLI_PROVIDER_V2_1.md

Target provider:
- provider id: grok_cli
- executable: grok
- primary mode: persistent interactive TUI

Your task in this stage is PRE-FLIGHT ONLY.

Do not modify source code, tests, documentation, user configuration, project
configuration, or Grok configuration.

Read the entire PLAN before doing anything else. Then inspect the checked-out
repository and report the actual current state.

Rules:

1. Treat the checked-out repository as the source of truth.
2. Do not assume filenames, APIs, schemas, test conventions, CLI commands, or
   dependencies from the PLAN are still current.
3. Do not use or invent a --plugin-dir flag.
4. Do not modify:
   - ~/.grok/config.toml
   - .grok/config.toml
   - .mcp.json
   - any global plugin registry
5. Do not assume AgentProfile has an effort field.
6. Do not claim a command was validated unless you actually executed it.
7. Do not expose secrets or authentication tokens in the report.
8. Stop after producing the pre-flight report.

Inspect and report:

A. Repository state
- absolute repository path
- current branch
- current commit
- dirty/clean working tree
- configured remotes
- Python version
- package manager and lockfile
- operating system
- shell
- tmux version
- available CAO backends
- whether the checkout matches or differs from the PLAN baseline

B. Repository conventions
- actual AgentProfile schema
- actual ProviderType enum
- BaseProvider constructor and required methods
- ProviderManager factory structure
- terminal service provider sets
- tool mapping structure
- API provider binary detection
- Web provider fallback location
- provider unit-test directory convention
- fixture convention
- e2e directory convention
- registered pytest markers
- lint, format, type-check, and test commands from pyproject/Makefile/CI

C. CLI availability
Run read-only commands where available:
- cao --help
- cao session --help
- grok version
- grok --help
- grok inspect --help
- grok mcp --help
- grok mcp add --help
- grok mcp doctor --help
- grok agent --help
- grok plugin --help

D. Prerequisites
Report whether these are available:
- Grok binary
- Grok authentication
- tmux
- CAO executable
- cao-mcp-server executable
- ability to run integration tests
- ability to create temporary tmux sessions
- ability to run two Grok sessions concurrently

E. PLAN discrepancies
List every discrepancy between the PLAN and the actual checkout.
Classify each as:
- blocker
- required correction
- non-blocking drift
- cosmetic

Required output format:

# Pre-flight Report

## Environment
...

## Repository Baseline
...

## AgentProfile Schema
State explicitly whether effort exists.

## Test and Quality Conventions
...

## CLI Capability Snapshot
...

## Available Prerequisites
...

## PLAN Discrepancies
...

## Recommended Next Action
One of:
- READY_FOR_PHASE_0
- READY_WITH_CORRECTIONS
- BLOCKED

Do not edit files. Stop after the report.
```

## 驗收

- 明確指出 upstream `AgentProfile` 是否有 `effort`。
- 保存真實 `cao session --help`，不能猜 E2E 命令。
- 沒有修改任何檔案。
- 最後只給出一個 pre-flight 判定。

---

# Prompt 1：Phase 0 / PR 1 Evidence

## 何時使用

Prompt 0 判定可進入 Phase 0 後使用。

## 目標

只建立 evidence、fixtures、capture helpers、ADR 與 capability matrix。不得實作正式 provider。

## 提示詞

```text
Implement Phase 0 / PR 1 from:

PLAN_CAO_ADD_GROK_CLI_PROVIDER_V2_1.md

Repository:
awslabs/cli-agent-orchestrator

This stage is evidence-first calibration only.

Do not implement GrokCliProvider.
Do not register grok_cli in ProviderType, ProviderManager, CLI, API, or Web UI.
Do not change production provider behavior.
Do not modify user or project Grok configuration.
Do not proceed to PR 2.

Read:
- the complete PLAN
- skills/cao-provider/SKILL.md
- its referenced lessons learned
- existing full-screen providers
- existing provider fixtures and tests
- Claude Code MCP env injection logic
- Codex/Kimi env-key forwarding logic, if present

Core assumptions:

1. Base case: Grok MCP subprocess may NOT inherit the parent process
   CAO_TERMINAL_ID.
2. Direct environment inheritance must be measured, not assumed.
3. Config ${CAO_TERMINAL_ID} expansion is also unverified.
4. `grok mcp add -e` forward-by-name semantics are unverified.
5. If no safe forwarding mechanism exists, Gate C must be NO-GO while the
   lifecycle provider remains deliverable.
6. Never use a shared literal CAO_TERMINAL_ID in Grok config.
7. Never use --plugin-dir.
8. Do not assume AgentProfile.effort exists.
9. Do not claim live evidence when prerequisites are unavailable.

Create the smallest set of evidence artifacts consistent with repository
conventions. Prefer:
- test/providers/fixtures/
- test/e2e/ for live probes where repository convention requires it
- docs or an ADR location already used by the repository
- scripts only when repeatable capture cannot reasonably be documented as
  commands

Required investigations:

A. Baseline capture
Record:
- CAO branch and commit
- Grok version and build hash
- Python version
- tmux version
- OS
- shell
- terminal dimensions
- backend
- target AgentProfile schema
- whether effort exists

B. CLI capability matrix
Actually run and capture:
- grok version
- grok --help
- grok inspect --help
- grok mcp --help
- grok mcp add --help
- grok mcp doctor --help
- grok agent --help
- grok plugin --help
- cao --help
- cao session --help

Confirm the presence or absence of:
- --always-approve
- --rules
- --allow
- --deny
- --model
- --effort or equivalent alias
- --no-subagents
- --session-id
- --plugin-dir
- --mcp-config
- rules-file support
- actual exit commands
- actual E2E CAO subcommands

C. TUI capture
Capture both:
1. raw tmux/pipe-pane representation
2. rendered pyte/screen representation

Capture states:
- shell prompt
- Grok startup
- idle
- processing
- completed
- waiting for question/selection
- plan approval
- permission prompt, if reachable
- authentication error
- tool error
- long response
- Markdown response
- multiline code response

Use repository fixture naming conventions. If raw and rendered fixtures need a
subdirectory, use:
test/providers/fixtures/grok_cli/

Do not create speculative regex implementation in this PR.

D. Shell false-IDLE evidence
Test a shell prompt containing a standalone ❯.
Demonstrate that a bare ❯ is insufficient to identify Grok readiness.
Record the Grok-specific composite ready markers found in actual fixtures.

E. Paste and submit behavior
Test:
- single-line prompt
- multiline prompt
- fenced-code prompt
- Chinese/Unicode prompt

Determine:
- paste_enter_count
- whether submit delay is required
- whether prompts are duplicated
- whether pasted content remains in an editor without submission

F. Exit behavior
Measure:
- /quit
- /exit
- Ctrl-D
- Ctrl-C fallback

Select the least destructive reliable normal exit path.

G. Subagent security evidence
Using a restricted/read-only scenario, test:
- direct shell write
- direct Edit write
- subagent shell write
- subagent Edit write
- non-CAO MCP write path, if available

Verify whether --no-subagents closes the delegated escape path.

H. MCP identity Path A/B/C

Create a minimal temporary MCP test server that reports only:
- process id
- a generated test invocation id
- CAO_TERMINAL_ID presence/value
- a small allowlisted set of non-secret environment metadata

Do not print the whole environment.

Path A:
- use a static MCP registration
- start Grok A with CAO_TERMINAL_ID=terminal-a
- start Grok B with CAO_TERMINAL_ID=terminal-b
- determine whether each MCP subprocess receives the correct value

Path B:
- only if Path A fails
- test config value ${CAO_TERMINAL_ID}
- determine whether expansion occurs at Grok process startup, MCP process
  startup, registration time, or not at all

Path C:
- only if Path B fails
- inspect `grok mcp add -e` behavior
- test whether a key can be forwarded by name without embedding a literal
  terminal id
- do not assume syntax; derive it from actual help/output

Concurrency:
- if any path appears safe, run two concurrent Grok sessions for at least
  20 identity checks
- no cross-terminal identity is allowed

I. ADR and gates
Write an architecture decision record covering:
- selected lifecycle approach
- TUI calibration version
- selected ready markers
- selected paste behavior
- selected exit behavior
- subagent security result
- Path A result
- Path B result
- Path C result
- why shared literal config is prohibited
- Gate A decision
- Gate B decision
- Gate C decision
- supported capability outcome

Gate definitions:

Gate A lifecycle:
GO only if readiness, submission, completion, and exit can be measured
reliably.

Gate B restrictions:
GO only if restricted agents cannot bypass the policy through subagents.

Gate C orchestration:
GO only if per-terminal CAO_TERMINAL_ID reaches the correct MCP subprocess
without rewriting shared config with literal ids.

Allowed final capability outcomes:
1. lifecycle + orchestration
2. lifecycle only
3. no-go for lifecycle release

Required verification:
Run repository-standard formatting/checks/tests applicable to evidence files.
Do not substitute Ruff if the repository uses Black/isort/mypy.

Required final response:

# Phase 0 Evidence Report

## Files Changed
List each file and why.

## Commands Executed
Exact commands, exit status, and concise result.

## Captured Fixtures
State and raw/rendered paths.

## Capability Matrix
...

## Shell and TUI Findings
...

## Paste and Exit Findings
...

## Subagent Security Findings
...

## MCP Path A
...

## MCP Path B
...

## MCP Path C
...

## Concurrency Result
...

## Gate Decisions
- Gate A: GO/NO-GO
- Gate B: GO/NO-GO
- Gate C: GO/NO-GO

## Supported V1 Outcome
Exactly one:
- LIFECYCLE_AND_ORCHESTRATION
- LIFECYCLE_ONLY
- NO_GO_FOR_LIFECYCLE_RELEASE

## Tests
Passed, failed, skipped, and why.

## Blockers
...

## Next Recommended Prompt
State whether Prompt 1R should review the evidence.

Stop after Phase 0. Do not implement PR 2.
```

## 驗收

- 不包含 production provider implementation。
- Gate A/B/C 都有實證。
- Gate C No-Go 不會被誤判為 lifecycle No-Go。
- 沒有改寫共享 Grok config。
- fixtures 可被後續 unit tests 使用。

---

# Prompt 1R：Phase 0 Evidence Review 與 Gate 決策

## 何時使用

Phase 0 完成後，最好開新對話交給同一模型或另一個 reviewer。

## 提示詞

```text
Review Phase 0 / PR 1 for the Grok CLI provider.

Inputs:
- PLAN_CAO_ADD_GROK_CLI_PROVIDER_V2_1.md
- Phase 0 branch or diff
- Phase 0 Evidence Report
- committed fixtures
- ADR
- actual command logs

Do not implement PR 2.
Do not repair code unless explicitly asked after the review.
Do not reinterpret missing live evidence as success.

Review objectives:

1. Verify the PR is evidence-only and did not prematurely implement the
   provider.
2. Verify fixture paths follow repository conventions.
3. Verify raw and rendered fixtures are real captures, not hand-written
   approximations.
4. Verify a shell-only standalone ❯ cannot be classified as Grok ready.
5. Verify ready markers are composite and Grok-specific.
6. Verify paste_enter_count and exit behavior are supported by evidence.
7. Verify subagent escape testing is sufficient for Gate B.
8. Verify MCP Path A/B/C conclusions follow from actual output.
9. Verify no shared literal CAO_TERMINAL_ID was introduced.
10. Verify no user/project Grok config was destructively modified.
11. Verify AgentProfile effort assumptions match the target branch schema.
12. Verify the selected V1 outcome is logically valid:
    - LIFECYCLE_AND_ORCHESTRATION
    - LIFECYCLE_ONLY
    - NO_GO_FOR_LIFECYCLE_RELEASE
13. Verify the ADR is explicit enough for PR 2 and PR 3 to implement without
    inventing behavior.

Required output:

# Phase 0 Review

## Verdict
One:
- APPROVE
- APPROVE_WITH_CORRECTIONS
- REQUEST_CHANGES
- BLOCKED_BY_MISSING_EVIDENCE

## Gate A Assessment
...

## Gate B Assessment
...

## Gate C Assessment
...

## Evidence Integrity
...

## Incorrect Assumptions
...

## Required Corrections
Numbered and ordered by severity.

## Allowed Next Stage
Exactly one:
- PROMPT_2_ALLOWED
- PHASE_0_FIXES_REQUIRED
- STOP_PROJECT

Do not modify files. Stop after the review.
```

---

# Prompt 2：PR 2 Registration + Lifecycle + Profile

## 前置條件

- Gate A = GO
- Gate B = GO
- Prompt 1R 允許進入 PR 2
- Gate C 可為 GO 或 NO-GO；PR 2 不實作 orchestration

## 提示詞

```text
Implement PR 2 from:

PLAN_CAO_ADD_GROK_CLI_PROVIDER_V2_1.md

Inputs:
- approved Phase 0 fixtures
- approved Phase 0 ADR
- Gate A = GO
- Gate B = GO
- Gate C may be GO or NO-GO

Scope:
Registration + basic lifecycle + profile/model/rules + native permissions.

Do not implement status regex beyond the minimum startup behavior supported by
approved Phase 0 evidence.
Do not implement final response extraction.
Do not implement assign, handoff, send_message, or automatic MCP setup.
Do not modify Grok user/project configuration.
Do not implement Optional PR 2B.
Do not add AgentProfile.effort to upstream schema in this PR.
Stop after PR 2.

Repository is the source of truth. Re-read actual signatures before editing.

Required source changes, subject to actual checkout structure:

1. Provider registration
- ProviderType.GROK_CLI = "grok_cli"
- ProviderManager factory branch
- CLI workspace-access provider set
- terminal service runtime-skill provider set
- do not add grok_cli to soft-enforcement providers
- API binary detection: grok_cli -> grok

2. Provider class
Create the provider module following existing provider conventions.

Required behavior:
- persistent interactive Grok TUI
- supports_screen_detection = True
- paste behavior exactly as Phase 0 measured
- blocks orchestrated input while waiting for user answer
- capture shell_baseline before launching Grok
- call status monitor input notification before sending launch command where
  the repository contract requires it
- wait for shell
- launch command
- wait for evidence-backed Grok readiness
- set _initialized only after successful readiness
- _turns starts at zero
- mark_input_received increments _turns
- graceful exit uses the Phase 0 selected command
- cleanup is no-op unless this PR owns a resource
- do not add speculative temp directories or plugin cleanup

3. Command builder
Use:
- grok
- --always-approve
- optional --model
- --rules for combined rules
- native --allow/--deny according to repository tool mapping
- --no-subagents when restricted and execute_bash is not allowed

Model precedence:
1. profile model
2. constructor model
3. Grok default

Effort compatibility:
- upstream AgentProfile may not have effort
- never directly access profile.effort
- only use:
  effort = getattr(profile, "effort", None) if profile else None
- add --effort only when a customized target branch actually supplies a value
- this hook does not make effort an upstream supported feature
- do not add profile schema in this PR

Rules:
- profile system prompt, if profile exists
- runtime skill prompt via the existing base/provider helper
- security prompt for restricted profiles
- startup guard
- correct shell quoting
- no silent truncation
- implement evidence-backed deterministic command-length fail-fast
- Grok 0.2.93 has no rules file; do not invent one

4. Tool mapping
Add Grok mappings based only on verified native tool names.
Do not deny the entire MCP tool category if that would remove CAO orchestration
tools.
Document why --no-subagents is required when Bash is disallowed.
Keep output ordering deterministic for test stability.

5. MCP behavior
PR 2 must not auto-configure MCP.
If a profile includes mcpServers:
- preserve current repository behavior where possible
- emit an actionable warning if Grok cannot consume arbitrary profile MCP
  servers automatically
- do not write config

6. Unit tests
Use actual repository layout, expected to be:
- test/providers/test_grok_cli_unit.py
- test/providers/fixtures/...

Test:
- constructor defaults
- properties
- binary missing -> RuntimeError or repository-standard equivalent
- profile None guard
- model precedence
- rules composition
- runtime skill composition
- startup guard
- restricted/unrestricted command
- no-subagents behavior
- deterministic allow/deny ordering
- upstream-like profile without effort
- customized mock profile with effort
- command length fail-fast
- no --plugin-dir
- no config writes
- shell baseline capture
- init timeout
- shell-only ❯ cannot complete init
- _initialized only after actual Grok readiness
- exit command
- cleanup no-op
- registration/factory/API/terminal-service behavior

7. Quality
Use repository-standard commands, expected:
- uv run black --check src/ test/
- uv run isort --check-only src/ test/
- uv run mypy src/
- relevant pytest commands

Do not substitute tooling without confirming repository configuration.

Implementation constraints:
- avoid unrelated refactors
- preserve existing provider behavior
- do not make dynamic plugin architecture changes
- do not mark live tests passed unless executed
- do not begin PR 3

Required final response:

# PR 2 Implementation Report

## Outcome
...

## Files Changed
...

## Design Decisions
...

## AgentProfile Effort Handling
State explicitly that upstream schema was not changed.

## MCP Behavior
State explicitly that no Grok config was modified.

## Tests Added
...

## Commands Executed
...

## Test Results
Passed/failed/skipped.

## Known Limitations
...

## Diff Risks
...

## Stop Point
State: PR 2 COMPLETE; PR 3 NOT STARTED.

Stop after PR 2.
```

---

# Prompt 2R：PR 2 Review/Fix

## 何時使用

PR 2 實作完成後，先 review 再進 PR 3。

## 提示詞

```text
Review and, only where necessary, fix PR 2 for the Grok CLI provider.

Inputs:
- PLAN_CAO_ADD_GROK_CLI_PROVIDER_V2_1.md
- approved Phase 0 ADR and fixtures
- PR 2 diff
- PR 2 test output

Review these invariants:

1. No direct profile.effort access exists.
2. AgentProfile schema was not expanded unless this is explicitly the Optional
   PR 2B branch.
3. --plugin-dir does not appear as an implemented flag.
4. Provider does not write user/project Grok config.
5. shell_baseline is captured before launch.
6. shell-only ❯ cannot produce successful initialization.
7. composite ready detection matches Phase 0 evidence.
8. _initialized is set only after verified readiness.
9. status monitor notification ordering follows repository conventions.
10. --always-approve is paired with native restrictions for restricted
    profiles.
11. --no-subagents is present when execute_bash is disallowed.
12. unrestricted profiles are not accidentally restricted.
13. MCP tools are not broadly denied.
14. rules are never silently truncated.
15. cleanup owns no resources and is therefore a no-op.
16. registration points are complete but unrelated provider lists are not
    damaged.
17. tests follow repository layout and quality tooling.
18. no PR 3 extraction/status implementation has leaked into this PR beyond
    startup readiness.

If defects are found:
- make the smallest focused fixes
- add regression tests
- do not broaden scope

Run relevant unit tests and repository quality commands.

Required final response:

# PR 2 Review Report

## Verdict
- APPROVE
- FIXED_AND_APPROVE
- REQUEST_CHANGES

## Findings
...

## Fixes Applied
...

## Tests
...

## Remaining Risks
...

## Next Stage
State whether Prompt 3 is allowed.

Stop after review/fixes. Do not implement PR 3.
```

---

# Prompt 2B：Optional AgentProfile effort schema

## 何時使用

只有維護者明確要求 upstream profile 正式支援 effort 時使用。此 prompt 不屬於 Grok Provider V1 必要路徑。

## 提示詞

```text
Implement Optional PR 2B only:

Add an optional AgentProfile effort field for upstream
awslabs/cli-agent-orchestrator.

This is a schema-extension PR, separate from the Grok provider lifecycle PR.

Do not modify Grok status detection, extraction, MCP, Web UI provider lists, or
orchestration.
Do not mix this work into PR 2 unless explicitly directed by the maintainer.

Tasks:

1. Inspect the actual AgentProfile model and profile loader.
2. Add an optional field using repository conventions:
   effort: Optional[str] = None
3. Determine whether validation should:
   - accept any non-empty string and defer validation to the provider, or
   - restrict to values documented by supported providers
4. Prefer a compatibility-preserving policy.
5. Ensure existing profiles parse unchanged.
6. Ensure serialization omits or preserves None according to current model
   conventions.
7. Update profile schema/loader tests.
8. Add Grok command-builder tests showing:
   - no effort -> no --effort
   - supported effort string -> --effort value
9. Check whether any other provider already reads effort and add only
   non-breaking coverage needed for that provider.
10. Update docs/agent-profile.md.
11. Do not add a default effort.
12. Do not assume every provider supports effort.

Run:
- targeted tests
- full relevant model/profile tests
- black
- isort
- mypy

Required final response:

# Optional PR 2B Report

## Schema Change
...

## Compatibility
...

## Validation Policy
...

## Providers Affected
...

## Tests
...

## Documentation
...

## Scope Confirmation
State that lifecycle/status/MCP work was not changed.

Stop after Optional PR 2B.
```

---

# Prompt 3：PR 3 Status + Extraction

## 前置條件

- PR 2 approved
- Phase 0 raw/rendered fixtures committed
- Gate A = GO

## 提示詞

```text
Implement PR 3 from:

PLAN_CAO_ADD_GROK_CLI_PROVIDER_V2_1.md

Scope:
- full status detection
- response extraction
- raw-buffer path
- rendered-screen path
- herdr/native-status contract
- regression fixtures/tests

Do not implement MCP orchestration.
Do not change Grok configuration.
Do not add AgentProfile effort schema.
Do not proceed to PR 4.
Use committed Phase 0 fixtures as the source of truth.

Status requirements:

1. get_status begins with _resolve_native_status().
2. If native status is available, do not parse the terminal buffer.
3. Empty buffer with no native status -> UNKNOWN.
4. Waiting dialogs must be checked before ready markers.
5. Fatal/auth/process errors must be distinguished from ordinary output.
6. Live processing markers must be evidence-backed.
7. Ready detection must use a composite Grok-specific surface.
8. A bare shell ❯ must never count as Grok ready.
9. Ready with _turns == 0 -> IDLE.
10. Ready with _turns > 0 -> COMPLETED.
11. After dispatch, absence of ready surface may be PROCESSING only when the
    fixture evidence supports it.
12. Stale thought/spinner markers must not keep a completed session in
    PROCESSING.
13. Stale ready markers must not cause premature COMPLETED.
14. Remove redundant branches and dead code.
15. Raw and rendered paths should agree unless the difference is documented and
    tested.

Waiting states:
- question/selection
- plan approval
- permission prompt if supported
- any other fixture-backed dialog

Extraction requirements:

1. Strip terminal escape sequences using repository utilities.
2. Locate the last real non-empty user prompt boundary.
3. Do not confuse:
   - shell prompt
   - empty ready prompt
   - assistant bullet marker
   - terminal decoration
4. Extract only the final assistant response.
5. Stop at the next verified ready input surface.
6. Filter only verified TUI chrome:
   - status/footer
   - thought/activity chrome
   - tool-call chrome
   - selection hints
   - startup banner/tips
7. Preserve:
   - Markdown
   - fenced code
   - indentation
   - lists
   - Unicode
   - meaningful blank lines
8. No boundary or empty result -> ValueError, allowing existing CAO retry or
   fallback logic.
9. Test long output and history expansion behavior.
10. Never return shell output as an assistant response.

Required tests:

A. Status fixtures
- empty
- shell prompt
- startup
- idle
- processing
- completed
- waiting question
- plan approval
- permission prompt
- auth error
- tool error
- stale processing marker
- stale ready marker
- unknown
- long output

Test both:
- get_status(raw)
- get_status_from_screen(rendered)

B. Native/herdr contracts
- native status bypasses parsing
- IDLE
- PROCESSING
- COMPLETED/flush-wait contract
- WAITING_USER_ANSWER
- ERROR where applicable

C. Extraction
- single turn
- multiple turns
- final turn only
- Markdown
- fenced code
- nested lists
- Unicode
- tool output filtered
- thought chrome filtered
- footer filtered
- long response
- empty result
- no prompt boundary
- shell prompt exclusion

D. Transitions
Verify:
UNKNOWN -> IDLE -> PROCESSING -> COMPLETED
and a second turn:
COMPLETED -> PROCESSING -> COMPLETED

Engineering constraints:

- Do not write speculative broad regex.
- Keep regex constants named and documented.
- Every regex change must have a fixture regression test.
- Avoid matching generic words such as "error" without structural context.
- Add status-reason debug logging without logging secrets or full system
  prompts.
- Preserve existing BaseProvider semantics.

Run repository-standard:
- targeted pytest
- broader provider tests
- black
- isort
- mypy

Required final response:

# PR 3 Implementation Report

## Status Model
...

## Fixture-to-Regex Mapping
For every marker, name the fixture supporting it.

## Raw vs Rendered Behavior
...

## Native/herdr Behavior
...

## Extraction Algorithm
...

## Tests Added
...

## Commands and Results
...

## Known TUI Version Dependency
...

## Stop Point
State: PR 3 COMPLETE; PR 4 NOT STARTED.

Stop after PR 3.
```

---

# Prompt 3R：PR 3 Review/Fix

## 提示詞

```text
Review and, where necessary, minimally fix PR 3 for Grok status detection and
response extraction.

Inputs:
- PLAN_CAO_ADD_GROK_CLI_PROVIDER_V2_1.md
- Phase 0 fixtures and ADR
- PR 3 diff
- test output

Review invariants:

1. Every marker is backed by a committed fixture.
2. No bare ❯ readiness detection.
3. Waiting detection precedes ready detection.
4. Native/herdr status bypasses raw parsing.
5. Raw and rendered paths are both tested.
6. Stale processing markers do not override current ready state.
7. Stale ready markers do not prematurely complete an active turn.
8. _turns correctly separates IDLE and COMPLETED.
9. No duplicate or unreachable branch exists.
10. Error patterns are not overly generic.
11. Extraction returns only the final assistant message.
12. Markdown and code fences survive unchanged.
13. TUI chrome filtering is narrow and fixture-backed.
14. Shell output cannot be returned as the answer.
15. No MCP/orchestration work leaked into PR 3.
16. No user config changes occurred.
17. Logging does not expose rules, prompts, keys, or tokens.

If fixes are necessary:
- make minimal changes
- add regression fixtures/tests
- rerun targeted and relevant full tests
- do not start PR 4

Required output:

# PR 3 Review Report

## Verdict
- APPROVE
- FIXED_AND_APPROVE
- REQUEST_CHANGES

## Status Findings
...

## Extraction Findings
...

## Fixes Applied
...

## Regression Tests
...

## Next Stage
State whether Gate C routing may begin.

Stop after review.
```

---

# Prompt 4A：Gate C = GO，實作 MCP + Orchestration

## 前置條件

只有 Phase 0 ADR 明確判定 Gate C = GO 時使用。

## 提示詞

```text
Implement PR 4A: MCP preflight and CAO orchestration support for grok_cli.

Precondition:
The approved Phase 0 ADR states Gate C = GO and identifies one verified safe
per-terminal CAO_TERMINAL_ID forwarding mechanism.

Do not choose a different forwarding mechanism.
Do not invent a new config layout.
Do not write literal terminal ids into shared configuration.
Do not modify user/project Grok config unless the ADR explicitly proves a
non-destructive, per-process-safe mechanism and the PLAN permits it.
Do not use --plugin-dir.

First, quote the ADR-selected mechanism in your implementation report:
- Path A direct inheritance, or
- Path B runtime config expansion, or
- Path C forward-by-name

Implement only that approved path.

Required behavior:

1. Read-only MCP preflight
Use supported Grok inspection/doctor commands to determine:
- cao-mcp-server is configured
- executable resolves
- server is healthy
- config origin
- project config does not unexpectedly override the intended server
- required CAO MCP tools are visible where inspect output permits it

2. Failure behavior
For missing or unhealthy MCP:
- produce actionable diagnostics
- include exact verified setup/repair command
- distinguish standalone lifecycle use from orchestration-required use
- do not silently claim orchestration support

3. Identity safety
- verify current terminal id reaches the matching MCP subprocess
- never persist a literal terminal id in shared config
- avoid logging the full environment
- test two concurrent terminals

4. Orchestration E2E
Implement and test:
- assign
- handoff
- send_message
- worker callback identity
- inbox delivery after ready
- concurrent Grok workers
- cross-provider direction where test infrastructure supports it:
  - Grok supervisor -> existing provider worker
  - existing provider supervisor -> Grok worker

5. Tool restrictions
Ensure restricted Grok profiles:
- retain CAO orchestration MCP tools
- do not gain shell/edit privileges through MCP or subagents
- still apply --no-subagents when required

6. Tests
Use existing integration/e2e markers only.
Use a require_grok-style fixture for binary/auth prerequisites.
Missing live prerequisites must SKIP, not pass.
Fixture-based unit tests remain mandatory in CI.

7. Capability reporting
Update provider/API capability metadata only if the repository has such a
mechanism.
Do not invent a broad capability framework in this PR.
If capability is represented only in docs, keep production changes minimal.

8. Configuration ownership
Provider cleanup may remove only resources created by this implementation.
If the selected mechanism creates no resource, cleanup remains a no-op.

Run:
- targeted unit tests
- integration tests
- e2e tests where prerequisites are available
- concurrency identity test for at least 20 checks
- black
- isort
- mypy

Required final response:

# PR 4A Orchestration Report

## ADR-Selected MCP Path
...

## Configuration Ownership
...

## MCP Preflight
...

## Identity Safety
...

## Concurrency Evidence
...

## assign
...

## handoff
...

## send_message
...

## Cross-provider Tests
...

## Security Tests
...

## Commands and Results
...

## Skipped Live Tests
Explain prerequisites.

## Gate C Confirmation
State whether evidence still supports GO.

Stop after PR 4A.
```

---

# Prompt 4B：Gate C = NO-GO，實作 Lifecycle-only Capability Path

## 前置條件

Phase 0 ADR 判定 Gate C = NO-GO 時使用。這不是失敗，而是正式支援 lifecycle-only。

## 提示詞

```text
Implement PR 4B: the lifecycle-only capability path for grok_cli.

Precondition:
The approved Phase 0 ADR states:
- Gate A = GO
- Gate B = GO
- Gate C = NO-GO

This is a valid V1 outcome.

Do not implement assign, handoff, send_message, automatic MCP setup, or unsafe
identity forwarding.
Do not write shared literal CAO_TERMINAL_ID values.
Do not modify user/project Grok configuration.
Do not attempt to "make Gate C pass" by weakening the PLAN.

Goals:

1. Make lifecycle-only support explicit and consistent.
2. Ensure launching and using Grok as a standalone CAO-managed terminal works.
3. Ensure orchestration-dependent operations fail early and clearly where the
   repository has an appropriate enforcement point.
4. Avoid broad architecture changes.

Required work:

A. Capability behavior
Inspect how CAO currently represents provider capabilities.
Use an existing mechanism if available.
If no mechanism exists:
- do not introduce a large capability registry solely for this provider
- add the smallest explicit guard or documented limitation consistent with the
  codebase

B. Error messages
When an orchestration operation requires cao-mcp-server identity forwarding:
- state that Grok lifecycle is supported
- state that orchestration is unsupported in this calibrated version/path
- explain that no safe per-terminal MCP identity forwarding was found
- do not suggest shared literal config as a workaround

C. API/UI/docs consistency
Ensure every user-facing surface uses consistent wording:
- lifecycle: supported
- multi-agent orchestration: unsupported
- reason: Gate C identity isolation failed
- no implication that the provider itself is unavailable

D. Tests
Test:
- normal launch still succeeds
- prompt/response lifecycle still succeeds
- restricted profile still works
- attempted orchestration receives the intended unsupported error or is
  omitted from advertised capability
- no config writes
- no MCP setup side effects

E. Future extension
Document which Phase 0 path failed and what new upstream Grok capability would
allow reevaluation:
- parent env forwarding
- config runtime env expansion
- env-key forwarding
- per-process config path

Run:
- targeted tests
- provider tests
- API/UI tests where modified
- black
- isort
- mypy

Required final response:

# PR 4B Lifecycle-only Report

## Capability Outcome
LIFECYCLE_ONLY

## Enforcement Point
...

## User-facing Behavior
...

## Tests
...

## Configuration Safety
...

## Future Gate C Re-evaluation
...

## Scope Confirmation
State that orchestration was not implemented.

Stop after PR 4B.
```

---

# Prompt 5：Web UI + Docs + CI

## 前置條件

- PR 2/3 approved
- Prompt 4A 或 4B 已完成
- 最終 capability outcome 已固定

## 提示詞

```text
Implement PR 5: Web UI, documentation, CI integration, and release hardening for
grok_cli.

Inputs:
- PLAN_CAO_ADD_GROK_CLI_PROVIDER_V2_1.md
- approved implementation PRs
- final capability outcome:
  - LIFECYCLE_AND_ORCHESTRATION, or
  - LIFECYCLE_ONLY
- final Gate A/B/C decisions
- calibrated Grok version

Do not change core provider behavior unless a documentation/UI test exposes a
small defect.
Do not reopen Gate C.
Do not add Optional PR 2B unless separately requested.

Tasks:

1. Web UI
Inspect actual current files.
Expected locations may include:
- web/src/components/AgentPanel.tsx
- web/src/test/components.test.tsx

Update:
- fallback provider list
- stale provider entries where safe and directly related
- tests

Normal provider discovery should remain API-driven.
Do not replace dynamic discovery with hard-coded UI behavior.

2. README/provider table
Add grok_cli with precise capability wording.

If Gate C = GO:
- lifecycle supported
- orchestration supported
- mention required static MCP registration/preflight

If Gate C = NO-GO:
- lifecycle supported
- orchestration unsupported
- do not describe the whole provider as unsupported

3. docs/grok-cli.md
Include:
- installation
- binary detection
- authentication is user-managed
- calibrated Grok version/build
- launch examples using verified CAO commands
- model behavior
- rules/system prompt behavior
- optional effort compatibility:
  - upstream AgentProfile may not contain effort
  - V1 does not claim profile-driven effort unless Optional PR 2B is present
- native permission enforcement
- --no-subagents security rule
- startup behavior
- status detection caveat
- long-rules fail-fast limitation
- graceful exit
- MCP setup only if Gate C = GO
- lifecycle-only explanation if Gate C = NO-GO
- troubleshooting
- version drift policy
- known limitations

4. Agent profile docs
Do not document effort as upstream-supported unless Optional PR 2B is actually
merged.
Document arbitrary mcpServers behavior accurately.

5. Tool restriction docs
Explain:
- hard enforcement
- Bash and filesystem boundary
- subagent escape mitigation
- CAO MCP tools behavior

6. API/help text
Update provider lists and help text only where actual repo conventions require
it.

7. CI/tests
- keep live Grok tests optional
- use existing integration/e2e markers
- use require_grok-style prerequisite skip
- fixture unit tests run by default
- no unregistered marker
- frontend test/build
- black/isort/mypy
- repository-standard pytest

8. Changelog
Follow repository release convention.
Do not add changelog if the project does not use one for unreleased changes.

Required final response:

# PR 5 Documentation and UI Report

## Final Capability Outcome
...

## Web Changes
...

## Documentation Changes
...

## Effort Documentation Status
...

## MCP Documentation Status
...

## CI and Test Changes
...

## Commands and Results
...

## User-visible Known Limitations
...

Stop after PR 5.
```

---

# Prompt 6：Final Audit

## 何時使用

所有實作與文件完成後，開新對話進行最終驗收。

## 提示詞

```text
Perform the final audit for the grok_cli provider implementation.

Primary specification:
PLAN_CAO_ADD_GROK_CLI_PROVIDER_V2_1.md

Inputs:
- all implementation branches or final combined diff
- Phase 0 ADR and fixtures
- PR 2/3/4/5 reports
- test outputs
- final Gate A/B/C decisions

Do not add features.
Do not refactor unrelated code.
Only make minimal correctness fixes if explicitly permitted.
Otherwise produce a review report.

Audit categories:

A. Scope integrity
- provider id is grok_cli
- persistent TUI mode
- no dynamic provider framework refactor
- no automatic auth management
- no --plugin-dir
- no unsafe Grok config mutation
- no hidden Optional PR 2B schema change

B. Registration completeness
- enum
- manager
- CLI
- terminal service
- API binary detection
- Web fallback
- tests/docs

C. Lifecycle
- shell baseline
- startup notification ordering
- false-IDLE defense
- initialization timeout
- multi-turn behavior
- exit
- cleanup ownership

D. Profile and command
- model precedence
- profile None guard
- getattr effort compatibility
- no upstream effort claim without schema PR
- rules composition
- startup guard
- command-length fail-fast
- correct quoting

E. Security
- native hard enforcement
- not soft-enforcement provider
- --no-subagents when Bash disallowed
- no broad MCP deny
- read-only E2E
- no secret logging

F. Status
- native/herdr first
- raw fixtures
- rendered fixtures
- waiting precedence
- composite ready marker
- stale marker regression
- no dead code

G. Extraction
- final response only
- Markdown/code preserved
- shell output excluded
- long response
- correct failure behavior

H. MCP and capability
If Gate C = GO:
- approved forwarding path only
- concurrency identity evidence
- assign/handoff/send_message
- config ownership safe

If Gate C = NO-GO:
- no orchestration implementation
- lifecycle remains supported
- API/UI/docs consistently state lifecycle-only
- no unsafe workaround

I. Tests and tooling
- test layout follows repo
- no unregistered pytest marker
- black
- isort
- mypy
- unit tests
- frontend tests/build
- live tests honestly skipped or passed

J. Documentation
- actual commands verified
- calibrated version stated
- known limitations accurate
- effort wording accurate
- no capability overclaim

Required output:

# Final Audit Report

## Overall Verdict
One:
- RELEASE_READY
- RELEASE_READY_WITH_NON_BLOCKING_NOTES
- CHANGES_REQUIRED
- NO_GO

## Gate Summary
- Gate A:
- Gate B:
- Gate C:
- Final capability:

## Blocking Findings
...

## Non-blocking Findings
...

## Test Evidence
...

## Security Assessment
...

## Capability Accuracy
...

## Documentation Accuracy
...

## Minimal Required Fixes
Numbered.

## Release Checklist
Use checkboxes.

Do not claim RELEASE_READY if:
- live evidence is fabricated
- shell false-IDLE remains
- subagent bypass remains
- Gate C is overclaimed
- profile.effort is directly accessed on upstream
- shared literal terminal ids are written to config
- tests or docs contradict final capability

Stop after the audit.
```

---

# Prompt 7：根據 Review 修正，但禁止擴大 Scope

## 何時使用

任何 PR 收到 review 後，把 review 內容與此提示詞一起交給 agent。

## 提示詞

```text
Apply the attached review findings to the current Grok CLI provider branch.

Inputs:
- PLAN_CAO_ADD_GROK_CLI_PROVIDER_V2_1.md
- current branch/diff
- attached review
- prior test report

Rules:

1. Validate each review finding against the actual checkout before changing
   code.
2. Classify every finding:
   - valid blocker
   - valid non-blocker
   - already fixed
   - not applicable
   - incorrect
3. Fix only valid findings.
4. Add or update regression tests for every behavior change.
5. Do not broaden the current PR phase.
6. Do not begin the next PLAN phase.
7. Do not change Gate C outcome without new reproducible Phase 0 evidence.
8. Do not add AgentProfile.effort unless this is explicitly Optional PR 2B.
9. Keep `getattr(profile, "effort", None)` for upstream compatibility.
10. Do not introduce --plugin-dir or shared literal terminal id config.
11. Use repository-standard Black/isort/mypy/pytest tooling.
12. Preserve unrelated user changes.

Required response:

# Review Fix Report

## Finding Triage
For each review item:
- classification
- evidence
- action

## Files Changed
...

## Regression Tests
...

## Commands and Results
...

## Scope Confirmation
State the current PR phase and confirm no next phase was started.

## Remaining Review Items
...

Stop after review fixes.
```

---

# Prompt 8：中斷後恢復工作

## 何時使用

前一個 coding agent session 中斷、context 不完整或需要換 agent 時。

## 提示詞

```text
Resume the Grok CLI provider work safely.

Primary specification:
PLAN_CAO_ADD_GROK_CLI_PROVIDER_V2_1.md

Do not assume the previous session completed correctly.

First inspect:
- current branch
- current commit
- working tree
- staged and unstaged diff
- untracked files
- latest implementation report
- latest review report
- Phase 0 ADR
- Gate A/B/C decisions
- tests previously run

Determine the current phase:
- PRE_FLIGHT
- PHASE_0
- PR_2
- OPTIONAL_PR_2B
- PR_3
- PR_4A
- PR_4B
- PR_5
- FINAL_AUDIT

Then report:
1. completed work supported by diff/tests
2. incomplete work
3. suspicious or out-of-scope changes
4. next exact task
5. which Prompt Pack stage should be used

Do not modify files during this assessment.
Do not continue implementation automatically.
Stop after the recovery report.
```

---

# 快速選擇表

| 現在狀態 | 使用提示詞 |
|---|---|
| 剛拿到 repo，還沒確認環境 | Prompt 0 |
| 尚未有真實 Grok fixtures／MCP evidence | Prompt 1 |
| Phase 0 做完，需要獨立審核 | Prompt 1R |
| Gate A/B 通過，要做 provider registration/lifecycle | Prompt 2 |
| PR 2 做完，需要修正或審核 | Prompt 2R |
| 維護者要求 upstream 正式支援 profile effort | Prompt 2B |
| lifecycle 已完成，要做完整 status/extraction | Prompt 3 |
| PR 3 做完，需要審核 | Prompt 3R |
| Gate C = GO | Prompt 4A |
| Gate C = NO-GO，但 lifecycle 可交付 | Prompt 4B |
| 核心實作完成，要補 UI/docs/CI | Prompt 5 |
| 全部完成，要做 release audit | Prompt 6 |
| 收到任何 review | Prompt 7 |
| session 中斷或換 agent | Prompt 8 |

---

# 執行時固定附上的資料

每次使用 Prompt 1 之後的提示詞，建議一併附上：

```text
1. PLAN_CAO_ADD_GROK_CLI_PROVIDER_V2_1.md
2. Phase 0 ADR
3. Gate A/B/C 結果
4. 前一階段 implementation report
5. 前一階段 review report
6. 當前 git diff
7. 最新 test output
```

---

# 最重要的停止條件

Coding agent 遇到以下情況必須停止並回報，不可自行設計 workaround：

1. 無法用實證區分 shell `❯` 與 Grok ready。
2. restricted agent 可透過 subagent 寫檔。
3. MCP identity 在兩個 terminal 間交叉。
4. 唯一 MCP 解法需要把 literal `CAO_TERMINAL_ID` 寫入共享 config。
5. 需要使用不存在的 `--plugin-dir` 或 `--mcp-config`。
6. 需要直接讀取 upstream 不存在的 `profile.effort`。
7. 需要默默截斷 system rules。
8. 缺少 Grok credentials 卻無法執行 live test。
9. repository 現況與 PLAN 有 blocker 級差異。
10. 正在執行的工作超出當前 Prompt 所屬 PR phase。

遇到 Gate C 問題時，正確結論可以是：

```text
grok_cli lifecycle: supported
grok_cli orchestration: not supported
```

這是 PLAN 定義的合法交付結果，不得為了宣稱完整支援而降低隔離或安全要求。
