# `0df986d` Memory Scope Isolation R3 Remediation Report

**Date:** 2026-07-16

**Branch:** `custom/4.19-memory-scope-isolation`

**Base:** `origin/main@8d53e75`

**Input review:** `REVIEW_0DF986D_MEMORY_SCOPE_ISOLATION_R3.md`

**Runtime memory / DB mutation:** None

## 1. Outcome

Both R3 blockers are remediated:

1. Provider-native memory preparation is now a core `create_terminal()` lifecycle
   requirement for Codex, Claude Code, and Kiro CLI. It no longer depends on an optional
   plugin registry, a matching hook, or successful plugin discovery.
2. Unmatched, nested, and misaligned Codex/Claude CAO markers now fail closed before
   provider construction. The ambiguous file remains byte-identical and lifecycle errors
   contain no instruction-file content.

The provider process cannot be constructed until core preparation has completed.
Synchronous and deferred initialization therefore share the same guarantee.

## 2. Registry-independent core barrier

The protected lifecycle is now:

```text
create session/window
    -> persist terminal metadata
    -> establish output capture
    -> resolve actual pane working directory
    -> core provider-memory prepare/scrub
    -> optional strict plugin extension phase
    -> construct provider
    -> initialize now or schedule deferred initialization
```

`PROTECTED_PROVIDER_MEMORY_PLUGINS` and `prepare_provider_memory_file()` provide the core
mapping for:

| Provider | Managed derivative |
|---|---|
| Codex | `AGENTS.md` managed block |
| Claude Code | `.claude/CLAUDE.md` managed block |
| Kiro CLI | `.kiro/steering/cao-memory.md` managed file |

The optional `PluginRegistry` remains available for third-party pre-initialize
extensions, but it is not part of the built-in memory security boundary. Consequently:

- `registry=None` cannot disable preparation.
- An empty registry cannot disable preparation.
- A registry with no matching memory hook cannot disable preparation.
- Plugin entry-point load failure cannot disable preparation.
- Flow and session creation paths that legitimately have no registry remain protected.

`agent_step.run_agent_step()` now also forwards its registry to `create_terminal()` for
extension lifecycle consistency, while its built-in memory guarantee remains core-owned.

## 3. Malformed marker fail-closed policy

The shared marker parser accepts only flat, ordered BEGIN/END pairs. It rejects:

- BEGIN without END;
- END without a preceding BEGIN;
- nested BEGIN markers;
- END-before-BEGIN or otherwise misaligned layouts.

On rejection:

1. `MalformedMemoryMarkersError("malformed CAO memory markers")` is raised.
2. No temporary file or replacement write is started.
3. The original instruction file remains byte-identical.
4. Core terminal creation enters cleanup before `provider_manager.create_provider()`.
5. The constant error and lifecycle log contain no file body or stale payload.

This deliberately avoids guessing whether trailing bytes are CAO-owned or user-owned.
Well-formed blocks retain the R2 behavior: exact managed spans are removed or replaced,
and all surrounding user-authored bytes remain unchanged.

## 4. Maintenance visibility

`cao memory scrub-provider-files PROJECT_DIR` now reports a content-free `status` for
each derivative:

- `valid`: ownership is unambiguous and `--apply` may scrub it.
- `malformed`: ownership is ambiguous; the file is reported as blocked and left
  unchanged even when `--apply` is present.

The report includes a `blocked` count. Table output explicitly tells the operator that
malformed blocks require manual inspection or repair. The command never prints provider
instruction bodies.

## 5. Production-path lifecycle coverage

The new first-loaded-context matrix executes the real core terminal lifecycle through
every reviewed production entry path:

| Entry path | Codex | Claude Code | Kiro CLI |
|---|---:|---:|---:|
| Direct `create_terminal()` | Covered | Covered | Covered |
| `session_service.create_session()` with no registry | Covered | Covered | Covered |
| `flow_service.execute_flow()` | Covered | Covered | Covered |
| `agent_step.run_agent_step()` with no registry | Covered | Covered | Covered |

The API session and terminal endpoints delegate to the same session/core terminal
functions. The direct and session rows therefore exercise the security boundary those
HTTP entry points reach, without starting an HTTP server.

Each case seeds a temporary provider-native file containing stale content, makes the
mock provider read that file inside its first `initialize()` call, and proves:

- stale content is absent before the first provider read;
- fresh scoped context is present;
- provider construction occurs only after preparation;
- no registry is required.

The earlier three-provider synchronous/deferred test matrix now runs under three registry
states:

| Registry state | Synchronous | Deferred |
|---|---:|---:|
| `None` | Covered | Covered |
| Present but empty | Covered | Covered |
| Entry-point load failure | Covered | Covered |

## 6. Malformed lifecycle coverage

Codex and Claude lifecycle tests cover BEGIN-without-END, nested markers, and misaligned
markers. They assert all of the following together:

- `provider_manager.create_provider()` was never called;
- the file bytes are unchanged;
- the exception is the constant malformed-marker error;
- a seeded secret payload does not appear in captured logs.

Unit tests also cover multiple valid blocks, exact user-byte preservation, and atomic
well-formed replacement. Maintenance tests prove malformed findings are visible but not
automatically mutated.

## 7. Validation results

R3 focused suite, including the production-path matrix:

```text
174 passed, 12 warnings
```

Terminal, flow, session, agent-step, and plugin regression subset:

```text
157 passed
```

The first full repository run exposed four generic herdr inbox unit tests whose mocks did
not provide a working directory. Those tests were explicitly isolated from provider-file
I/O, matching the existing isolation used by generic terminal-service tests. Their
dedicated rerun passed:

```text
6 passed
```

Final full repository suite:

```text
4124 passed, 21 skipped, 93 deselected, 1 failed
```

The sole failure is the known unrelated baseline:

```text
test/mcp_server/test_workflow_tools.py::TestWorkflowCancel::test_success_envelope
actual request timeout: 300.0
test expectation: MCP_REQUEST_TIMEOUT (30)
```

All memory stores and provider files used by these tests were disposable temporary
fixtures. No runtime memory store, runtime database, or live provider instruction file
was inspected, mutated, quarantined, or scrubbed.

## 8. R3 acceptance matrix

| # | Acceptance criterion | Status |
|---:|---|---|
| 1 | Every protected provider creation path prepares before startup | Satisfied |
| 2 | Missing registry cannot disable preparation | Satisfied |
| 3 | Missing matching built-in hook cannot disable preparation | Satisfied |
| 4 | Flow, agent-step, session, direct, sync, and deferred share the guarantee | Satisfied |
| 5 | Correct stale blocks refresh/remove before startup | Satisfied |
| 6 | Empty context removes old managed data without creating files | Satisfied |
| 7 | User bytes outside valid spans remain preserved | Satisfied |
| 8 | Kiro cleanup remains limited to its dedicated file | Satisfied |
| 9 | Malformed markers fail before provider construction | Satisfied |
| 10 | Malformed files remain unchanged | Satisfied |
| 11 | Failure logs and errors remain content-free | Satisfied |
| 12 | First-loaded-context tests cover protected production paths | Satisfied |

## 9. Files added

- `src/cli_agent_orchestrator/plugins/builtin/memory_markers.py`
- `test/services/test_provider_memory_production_paths.py`

## 10. Final assessment

Provider-native memory isolation is now enforced by the terminal core rather than
optional plugin wiring, and ambiguous file ownership cannot fail open. All R3
`CHANGES REQUESTED` criteria are implemented with lifecycle-level regression evidence.

**Remediation status: READY FOR RE-REVIEW**
