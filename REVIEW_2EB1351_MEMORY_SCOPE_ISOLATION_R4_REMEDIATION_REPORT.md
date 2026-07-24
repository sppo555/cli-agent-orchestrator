# R4 Memory Scope Isolation Remediation Report

Date: 2026-07-16

Branch: `custom/4.19-memory-scope-isolation`

Input review: `REVIEW_2EB1351_MEMORY_SCOPE_ISOLATION_R4.md`

Base commit: `2eb1351bfe86ba9a0b84b6595e86f9c32e572613`

## Outcome

The R4 blocker is remediated. Repo-shared provider instruction files can no
longer receive terminal-private session or agent memory. Terminal-specific
first-message injection continues to receive the intended session, project,
and valid global scopes.

No runtime memory wiki, runtime SQLite database, or live provider instruction
file was inspected, modified, quarantined, or scrubbed. All memory and provider
file test data used isolated temporary directories and SQLite fixtures.

## Hard boundary implemented

`MemoryService` now exposes two purpose-specific builders:

| Delivery channel | Builder | Allowed scopes | Explicitly excluded |
|---|---|---|---|
| Terminal first message | `get_memory_context_for_terminal()` | session, project, valid global | agent, federated, invalid global/project |
| Repo-shared provider file | `get_provider_file_memory_context()` | project, valid global | session, agent, federated, invalid global/project |

Both public builders use the same private rendering/budget implementation, but
must pass an explicit scope allowlist. This keeps existing per-scope caps,
ordering, validity filtering, and rendering behavior while preventing a future
caller from accidentally widening the shared-file channel.

Codex, Claude Code, and Kiro CLI provider preparation now call only the
repo-shared builder:

- Codex: `<cwd>/AGENTS.md`
- Claude Code: `<cwd>/.claude/CLAUDE.md`
- Kiro CLI: `<cwd>/.kiro/steering/cao-memory.md`

Project/global duplication between the provider file and first-message channel
is intentional. Session memory is delivered only through the terminal-private
first-message channel.

## Concurrent isolation evidence

Added a deterministic same-repository concurrency matrix covering all required
provider paths:

| Provider | Synchronous initialization | Deferred/parallel initialization |
|---|---:|---:|
| Codex | PASS | PASS |
| Claude Code | PASS | PASS |
| Kiro CLI | PASS | PASS |

Each case creates two terminals with:

- the same repository working directory;
- different terminal IDs and session names;
- distinct session-A and session-B memories;
- common project and valid global memories;
- a controlled interleave in which terminal A pauses before reading the shared
  file, terminal B prepares and reads it, then terminal A resumes.

Assertions prove that both terminals' provider-native startup reads contain the
common project/global context and neither session memory. The subsequent
first-message checks prove terminal A receives only session A and terminal B
receives only session B.

The deferred cases use the real deferred terminal initialization seam used by
parallel assignment, so the test covers the R4 parallel-start overwrite risk
without relying on timing or sleeps.

## Additional regression coverage

- Added a direct builder-boundary test proving same-project provider contexts
  are identical across sessions while terminal contexts remain session-specific.
- Added `memory.enabled=False` coverage for the new provider-file builder; it
  short-circuits to an empty string.
- Updated provider plugin fakes and production-path tests to require the safe
  builder API, preventing silent fallback to the terminal-private builder.
- Updated `docs/memory.md` and provider plugin documentation to record the
  channel-specific scope contract.

## Validation

R4 review suite plus new concurrency and enabled-flag coverage:

```text
199 passed, 23 warnings in 5.29s
```

Formatting and patch integrity:

```text
black --check: 12 files would be left unchanged
git diff --check: clean
```

Full repository suite:

```text
1 failed, 4132 passed, 21 skipped, 93 deselected
```

The single failure is the pre-existing unrelated baseline mismatch:

```text
test/mcp_server/test_workflow_tools.py::TestWorkflowCancel::test_success_envelope
actual timeout: 300.0
expected MCP_REQUEST_TIMEOUT: 30
```

The same failure was present before this R4 remediation. No memory/provider test
failed.

## Files changed

- `src/cli_agent_orchestrator/services/memory_service.py`
- `src/cli_agent_orchestrator/plugins/builtin/codex_memory.py`
- `src/cli_agent_orchestrator/plugins/builtin/claude_code_memory.py`
- `src/cli_agent_orchestrator/plugins/builtin/kiro_cli_memory.py`
- `docs/memory.md`
- `test/services/test_memory_scope_isolation.py`
- `test/services/test_provider_memory_concurrent_isolation.py`
- `test/services/test_memory_enabled_flag.py`
- `test/services/test_provider_memory_production_paths.py`
- `test/services/test_terminal_memory_preinitialize.py`
- `test/plugins/builtin/test_codex_memory.py`
- `test/plugins/builtin/test_claude_code_memory.py`
- `test/plugins/builtin/test_kiro_cli_memory.py`

## R4 disposition

The shared-file concurrency blocker is closed by construction and by
deterministic lifecycle tests. The closed-set invariants from R4 remain intact:
store/read validation, terminal identity fail-closed behavior, core lifecycle
ownership, stale derivative removal, and non-mutation of runtime memory/DB were
not weakened by this change.

Status: ready for R5 re-review.
