# `2eb1351` Memory Scope Isolation Remediation Review — R4

**Review date:** 2026-07-16  
**Branch:** `custom/4.19-memory-scope-isolation`  
**Base:** `origin/main@8d53e75`  
**Original commit:** `a8019d4 fix(memory): isolate project-scoped writes`  
**Previous remediations:** `d433ba8`, `0df986d`  
**Reviewed commit:** `2eb1351 fix(memory): enforce core provider preparation`  
**Reviewed remediation report:** `REVIEW_0DF986D_MEMORY_SCOPE_ISOLATION_R3_REMEDIATION_REPORT.md`  
**Verdict:** `CHANGES REQUESTED`

## 1. Executive summary

`2eb1351` successfully closes both blockers from the R3 review:

1. Provider-native memory preparation is now enforced in the core terminal lifecycle and
   no longer depends on an optional plugin registry.
2. Malformed Codex and Claude managed markers now fail closed before provider
   construction, without modifying the ambiguous file or logging its contents.

The remediation also adds production-path coverage for direct terminal creation,
sessions, flows, and agent steps across Codex, Claude Code, and Kiro CLI.

One isolation defect remains. The provider-native instruction files are shared by every
terminal using the same repository, but they are populated with a terminal-specific
memory context containing session scope. Concurrent terminals can therefore overwrite the
shared file and load another terminal's session memory.

This is directly relevant to CAO's multi-supervisor and parallel-worker use case and is a
blocking session-isolation failure.

## 2. Scope of review

The review covered:

- The delta from `0df986d` to `2eb1351`.
- Core provider-memory preparation in `create_terminal()`.
- Optional plugin extension behavior after the core barrier.
- Malformed marker parsing and maintenance visibility.
- Direct, session, flow, and agent-step production paths.
- Synchronous and deferred initialization.
- Registry absent, empty, and plugin-load-failure states.
- Provider-native file ownership and concurrency implications.

No source code or runtime memory data was modified during review.

## 3. R3 findings that are now closed

### 3.1 Core preparation no longer depends on the plugin registry

Affected implementation:

```text
src/cli_agent_orchestrator/services/terminal_service.py
src/cli_agent_orchestrator/services/provider_memory_files.py
```

`create_terminal()` now identifies protected providers directly and invokes
`prepare_provider_memory_file()` before provider construction. The optional strict plugin
dispatch occurs afterward and is correctly described as an extension phase rather than
the built-in security boundary.

The built-in mapping protects:

| Provider | Native derivative |
|---|---|
| Codex | `<repo>/AGENTS.md` managed block |
| Claude Code | `<repo>/.claude/CLAUDE.md` managed block |
| Kiro CLI | `<repo>/.kiro/steering/cao-memory.md` managed file |

The core preparation runs before:

- Provider construction.
- Synchronous initialization.
- Deferred initialization scheduling.

Production tests cover direct, session, flow, and agent-step entry paths without requiring
a registry.

**Status:** Closed.

### 3.2 Malformed managed markers now fail closed

Affected implementation:

```text
src/cli_agent_orchestrator/plugins/builtin/memory_markers.py
src/cli_agent_orchestrator/plugins/builtin/codex_memory.py
src/cli_agent_orchestrator/plugins/builtin/claude_code_memory.py
```

The shared marker parser rejects:

- BEGIN without END.
- END without a preceding BEGIN.
- Nested BEGIN markers.
- Misaligned marker ordering.

The tests verify that malformed input:

- Raises `MalformedMemoryMarkersError`.
- Prevents `provider_manager.create_provider()` from being called.
- Leaves the original instruction file byte-identical.
- Does not expose seeded content in captured logs.

The maintenance scrub command reports malformed derivatives as blocked and does not
automatically mutate them, including in apply mode.

**Status:** Closed.

## 4. Remaining blocking finding

### BLOCKER — Repo-shared provider files contain terminal-specific session memory

Affected implementation:

```text
src/cli_agent_orchestrator/services/memory_service.py:2673-2701
src/cli_agent_orchestrator/plugins/builtin/codex_memory.py:98-109
src/cli_agent_orchestrator/plugins/builtin/claude_code_memory.py:92-100
src/cli_agent_orchestrator/plugins/builtin/kiro_cli_memory.py:88-108
```

`get_memory_context_for_terminal()` intentionally builds a terminal-specific context with
the following precedence:

```python
scopes_in_order = [
    MemoryScope.SESSION.value,
    MemoryScope.PROJECT.value,
    MemoryScope.GLOBAL.value,
]
```

Each provider plugin calls this terminal-specific function and writes the result to a
repository-wide path.

The ownership mismatch is:

| Data | Correct isolation boundary | Actual destination |
|---|---|---|
| Session memory | One CAO session/terminal context | Repo-shared provider file |
| Project memory | One repository | Repo-shared provider file |
| Global memory | All repositories | Repo-shared provider file |

Project and valid global memory are compatible with a repo-shared derivative. Session
memory is not.

### 4.1 Concurrent startup race

Consider two terminals using the same working directory but different CAO sessions:

```text
Terminal A builds session-A + project + global context
    ↓
Terminal A writes shared AGENTS.md
    ↓
Terminal A awaits or schedules provider initialization

Terminal B builds session-B + project + global context
    ↓
Terminal B overwrites the same AGENTS.md
    ↓
Terminal A provider reads AGENTS.md
    ↓
Terminal A receives session-B memory
```

The same problem applies to `.claude/CLAUDE.md` and Kiro's repository steering file.

The risk is not limited to two manually launched supervisors. CAO explicitly supports
parallel worker assignment. Deferred initialization also creates a window between file
preparation and the provider process actually reading the file.

### 4.2 Already-running provider behavior

Provider-native project instruction files may be re-read after startup, depending on the
provider's behavior and subsequent turns. Even if each terminal reads the expected file
during its first initialization, later terminal preparation can replace the shared block
with another session's context.

Therefore a startup-only ordering barrier cannot make terminal-specific data safe in a
repo-shared file.

### 4.3 Test coverage gap

The new production-path tests are useful but create one terminal at a time. They do not:

- Create two terminals for the same working directory.
- Give the terminals different session memories.
- Interleave preparation with synchronous or deferred initialization.
- Verify that each provider receives only its own session memory.

As a result, the current `174 passed` suite does not exercise the ownership mismatch.

## 5. Required remediation

### 5.1 Separate shared and terminal-specific context builders

Provider-native repo-shared files must contain only scopes compatible with repository
ownership:

```text
project + valid global
```

Session memory must use a terminal-specific delivery mechanism, such as the existing
first-message injection path.

Recommended API separation:

```python
get_provider_file_memory_context(project_identity)
    -> project + global only

get_memory_context_for_terminal(terminal_id)
    -> session + project + global
```

The shared-file builder should still resolve the project from a verified terminal or an
explicit validated project identity, but must never include session or agent-private
content.

### 5.2 Preserve terminal-specific injection

The existing first-message injection path is terminal-specific and may continue to carry:

```text
session + project + global
```

If both provider-native files and first-message injection are enabled, duplicate project
and global context should be considered, but duplication alone is not an isolation
blocker. Session data appearing in the shared file is the blocking condition.

### 5.3 Add concurrent lifecycle tests

Required regression coverage:

1. Create two terminals with the same working directory and different CAO session IDs.
2. Seed distinct session memories for A and B.
3. Seed common project and valid global memory.
4. Interleave preparation and provider initialization deterministically.
5. Verify the repo-shared native file contains no session-scope memory.
6. Verify terminal A's terminal-specific injection contains session A but not session B.
7. Verify terminal B's terminal-specific injection contains session B but not session A.
8. Cover Codex and Claude Code at minimum.
9. Cover synchronous and deferred initialization.
10. Cover parallel worker assignment behavior.

Kiro should follow the same scope ownership rule if its steering file is shared per repo.

## 6. Final closed-set isolation invariants

After the remaining fix, final review should use this closed set of invariants:

| Scope/channel | Required visibility |
|---|---|
| Global memory | All projects, only for valid cross-project types |
| Project memory | Terminals resolving to the same project identity |
| Session memory | Only the matching CAO session |
| Agent memory | Only the matching agent identity |
| Provider-native repo file | Project plus valid global only |
| First-message injection | Session plus project plus valid global |
| Worker inbox | Matching caller and session routing |

Further optional improvements that do not demonstrate a violation of one of these
invariants should be reported as non-blocking observations rather than opening additional
blocking scope.

## 7. Validation performed

The following focused test set was run:

```bash
uv run pytest -q \
  test/cli/commands/test_memory.py \
  test/services/test_memory_scope_isolation.py \
  test/services/test_provider_memory_files.py \
  test/services/test_terminal_memory_preinitialize.py \
  test/services/test_provider_memory_production_paths.py \
  test/plugins/builtin/test_codex_memory.py \
  test/plugins/builtin/test_claude_code_memory.py \
  test/plugins/builtin/test_kiro_cli_memory.py \
  test/plugins/test_events.py \
  test/plugins/test_registry.py \
  test/services/test_plugin_event_emission.py
```

Result:

```text
174 passed, 12 warnings
```

The warnings were existing SQLAlchemy `ResourceWarning` messages and did not fail the
test run.

`git diff --check 0df986d 2eb1351` passed.

## 8. Final verdict

`2eb1351` correctly makes provider-memory preparation core-owned and closes malformed
marker fail-open behavior. It still writes terminal-specific session memory into
repository-shared provider files, allowing concurrent supervisors or workers to overwrite
and potentially ingest one another's session context.

**Verdict: `CHANGES REQUESTED`**

