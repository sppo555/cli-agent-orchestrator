# `d433ba8` Memory Scope Isolation R2 Remediation Report

**Date:** 2026-07-16

**Branch:** `custom/4.19-memory-scope-isolation`

**Base:** `origin/main@8d53e75`

**Input review:** `REVIEW_D433BA8_MEMORY_SCOPE_ISOLATION_R2.md`

**Runtime memory / DB mutation:** None

## 1. Outcome

The R2 provider-native instruction-file blocker is remediated. CAO now prepares each
managed provider memory file through a strict, awaited lifecycle barrier before the
provider is initialized or deferred initialization is scheduled. Empty current context
scrubs stale CAO-managed content, while non-empty context is atomically refreshed.

This closes the path where stale cross-project content in `AGENTS.md`,
`.claude/CLAUDE.md`, or `.kiro/steering/cao-memory.md` could be loaded on the provider's
first turn before the former post-create refresh ran.

## 2. Lifecycle correction

A new `PreInitializeTerminalEvent` is dispatched after terminal persistence and FIFO
setup, but before provider construction and initialization:

```text
persist terminal + prepare FIFO
    -> strict pre_initialize_terminal dispatch
    -> prepare/scrub provider-native memory file
    -> create provider
    -> initialize now or schedule deferred initialization
    -> post_create_terminal observer dispatch
```

The pre-initialize dispatch is deliberately strict:

- It is awaited in both synchronous and deferred creation paths.
- Hook failures propagate instead of being isolated as observer failures.
- Provider creation and startup do not proceed when the instruction file cannot be
  safely prepared.
- The existing post-create event remains an observer phase and no longer carries the
  startup ordering guarantee.

Implemented in:

- `src/cli_agent_orchestrator/plugins/events.py`
- `src/cli_agent_orchestrator/plugins/registry.py`
- `src/cli_agent_orchestrator/services/plugin_dispatch.py`
- `src/cli_agent_orchestrator/services/terminal_service.py`
- Codex, Claude Code, and Kiro CLI built-in memory plugins

## 3. Empty-context and preservation behavior

| Current context | Existing target | Result |
|---|---|---|
| Empty | Absent | No file is created |
| Empty | Unmanaged Codex/Claude file | Byte-identical no-op |
| Empty | Codex/Claude file with CAO block | Only the exact CAO-managed span is removed |
| Empty | Kiro CAO memory steering file | The dedicated CAO-managed file is removed |
| Non-empty | Absent | A managed block/file is atomically created |
| Non-empty | Existing managed content | The managed content is atomically replaced |

Codex and Claude block removal no longer applies surrounding `rstrip()`/`lstrip()`
normalization, so user-authored prefix, suffix, whitespace, and line endings outside the
managed span remain byte-preserved. Kiro cleanup removes only
`.kiro/steering/cao-memory.md`; sibling steering files such as `agent-identity.md` are
untouched.

If current memory retrieval fails, the pre-start hook logs a content-free error and
treats the provider derivative as stale: it scrubs the CAO-managed copy rather than
allowing old context to survive into startup.

## 4. Maintenance visibility

The following command now inventories known provider-native CAO memory derivatives for
an explicit project directory without returning their bodies:

```bash
cao memory scrub-provider-files PROJECT_DIR
cao memory scrub-provider-files PROJECT_DIR --format json
```

It is dry-run by default. Applying cleanup requires an explicit flag:

```bash
cao memory scrub-provider-files PROJECT_DIR --apply
```

Apply mode strips only managed Codex/Claude blocks and deletes only Kiro's dedicated CAO
memory file. Target validation and symlink/path-containment protections are shared with
the provider plugins. Runtime memory quarantine and provider-file cleanup are documented
as separate responsibilities in `docs/memory.md`.

## 5. Regression coverage

The new lifecycle test matrix covers all six startup combinations:

| Provider | Synchronous | Deferred |
|---|---:|---:|
| Codex | Covered | Covered |
| Claude Code | Covered | Covered |
| Kiro CLI | Covered | Covered |

Each lifecycle case uses an isolated temporary SQLite memory store and temporary project
directory. It seeds valid project context, valid global reference context, invalid legacy
global/project records, and a stale provider-native file. The provider initialization
mock reads its instruction file as its first loaded context and proves that, before that
read:

- legacy cross-project content is absent;
- valid project and global context is present;
- Codex/Claude user-authored prefix and suffix bytes remain intact;
- synchronous and deferred paths observe the same ordering.

Additional tests cover strict hook failure propagation, event ordering, dry-run and apply
maintenance behavior, unmanaged-file preservation, Kiro sibling-file preservation, and
all empty/non-empty transition cases from the R2 acceptance table.

## 6. Validation results

Focused R2 suite:

```text
143 passed, 11 warnings
```

Additional terminal/plugin regression subset:

```text
62 passed
```

Full repository suite:

```text
4093 passed, 21 skipped, 93 deselected, 1 failed
```

The sole full-suite failure is the pre-existing unrelated baseline:

```text
test/mcp_server/test_workflow_tools.py::TestWorkflowCancel::test_success_envelope
actual request timeout: 300.0
test expectation: MCP_REQUEST_TIMEOUT (30)
```

The same failure existed before this R2 remediation and is outside memory scope
isolation. `git diff --check` passes.

All memory fixtures and databases used by validation were disposable test resources. No
runtime memory store or runtime DB was inspected, modified, quarantined, or scrubbed.

## 7. R2 acceptance matrix

| # | Acceptance criterion | Status |
|---:|---|---|
| 1 | Declared terminal identity cannot fail open | Satisfied by `d433ba8` |
| 2 | New global/project writes fail before persistence | Satisfied by `a8019d4` / `d433ba8` |
| 3 | Legacy runtime entries cannot enter recall/dynamic context | Satisfied by `d433ba8` |
| 4 | Provider-native blocks refresh before startup | Satisfied |
| 5 | Empty context removes stale blocks without creating files | Satisfied |
| 6 | User-authored Codex/Claude content is preserved | Satisfied |
| 7 | Kiro stale CAO steering file is safely removed | Satisfied |
| 8 | Sync/deferred initialization ordering is deterministic | Satisfied |
| 9 | First-loaded-context lifecycle tests exclude stale content | Satisfied |
| 10 | Runtime quarantine and provider cleanup are documented | Satisfied |

## 8. Files added

- `src/cli_agent_orchestrator/services/provider_memory_files.py`
- `test/services/test_provider_memory_files.py`
- `test/services/test_terminal_memory_preinitialize.py`

## 9. Final assessment

All R2 `CHANGES REQUESTED` requirements are implemented and covered by lifecycle-level
regression tests. The provider-native derivative path is now fail-closed before first
provider load, including empty-context cleanup and both startup modes.

**Remediation status: READY FOR RE-REVIEW**
