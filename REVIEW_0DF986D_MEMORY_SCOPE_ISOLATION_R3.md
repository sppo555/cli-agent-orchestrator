# `0df986d` Memory Scope Isolation Remediation Review — R3

**Review date:** 2026-07-16  
**Branch:** `custom/4.19-memory-scope-isolation`  
**Base:** `origin/main@8d53e75`  
**Original commit:** `a8019d4 fix(memory): isolate project-scoped writes`  
**R1 remediation:** `d433ba8 fix(memory): close legacy scope isolation gaps`  
**R2 remediation:** `0df986d fix(memory): scrub provider context before startup`  
**Reviewed remediation report:** `REVIEW_D433BA8_MEMORY_SCOPE_ISOLATION_R2_REMEDIATION_REPORT.md`  
**Verdict:** `CHANGES REQUESTED`

## 1. Executive summary

The R2 remediation fixes the main provider-native instruction-file lifecycle for terminal
creation paths that supply a populated plugin registry:

- A strict pre-initialization event is awaited before provider construction and startup.
- Stale, correctly delimited CAO memory blocks are refreshed or removed before Codex,
  Claude Code, or Kiro CLI reads them.
- Empty current context removes an existing managed block without creating a new file.
- Codex and Claude user-authored bytes outside the managed span are preserved.
- Kiro's dedicated CAO steering file is removed without touching sibling files.
- Synchronous and deferred initialization are tested against the provider's first file
  read.

However, two fail-open paths remain:

1. Production terminal creation paths that omit the plugin registry silently skip the
   security barrier.
2. A malformed managed block with a BEGIN marker but no valid END marker retains its
   payload and still permits provider startup.

Because either path can allow stale cross-project content into a provider's initial
context, the remediation is not yet approved.

## 2. Review scope

The review covered the delta from `d433ba8` to `0df986d`, including:

- `PreInitializeTerminalEvent` definition and registration.
- Strict plugin event dispatch.
- Terminal lifecycle ordering.
- Codex, Claude Code, and Kiro CLI memory plugins.
- Provider-native memory-file audit and scrub commands.
- Synchronous and deferred lifecycle tests.
- Internal production callers of `create_terminal()`.
- Malformed marker handling.

No source code was modified during review.

## 3. Correctly remediated behavior

### 3.1 Pre-initialization ordering is correct when the registry is present

In `terminal_service.create_terminal()`, terminal metadata and FIFO setup now complete
before a strict, awaited `pre_initialize_terminal` dispatch. Provider construction happens
only after that dispatch returns.

The intended sequence is implemented as:

```text
create tmux session/window
    ↓
persist terminal metadata
    ↓
prepare FIFO/output capture
    ↓
await pre_initialize_terminal
    ↓
refresh/scrub provider-native memory file
    ↓
construct provider
    ↓
initialize synchronously or schedule deferred initialization
```

This ordering protects both synchronous and deferred startup paths when the required hook
is actually registered.

### 3.2 Empty-context cleanup is implemented for normal managed files

For correctly delimited Codex and Claude blocks:

- Target absent plus empty context is a no-op.
- Unmanaged target plus empty context is a byte-identical no-op.
- Managed target plus empty context removes the managed span.
- Non-empty context atomically creates or replaces the managed span.

Kiro's dedicated `.kiro/steering/cao-memory.md` is deleted when current context is empty.

### 3.3 Lifecycle tests inspect the provider's first file read

The new test matrix covers:

| Provider | Synchronous | Deferred |
|---|---:|---:|
| Codex | Covered | Covered |
| Claude Code | Covered | Covered |
| Kiro CLI | Covered | Covered |

The mocked provider initialization reads its native instruction file and verifies that:

- Legacy pollution is absent.
- Valid project memory remains present.
- Valid global reference memory remains present.
- Codex and Claude user prefix/suffix content remains present.

This is materially stronger than testing only the memory-service return value.

### 3.4 Maintenance command is safely scoped

`cao memory scrub-provider-files PROJECT_DIR` is dry-run by default. Apply mode:

- Removes only CAO-managed Codex and Claude spans.
- Deletes only Kiro's dedicated CAO memory file.
- Leaves unmanaged user files unchanged.
- Reuses provider target validation.

## 4. Blocking findings

### Finding 1 — BLOCKER: missing registry silently disables the security barrier

Affected locations:

```text
src/cli_agent_orchestrator/services/plugin_dispatch.py:46-51
src/cli_agent_orchestrator/services/flow_service.py:262-267
src/cli_agent_orchestrator/services/agent_step.py:178-187
src/cli_agent_orchestrator/services/session_service.py:45-70
```

`dispatch_plugin_event_strict()` returns without doing anything when `registry` is
`None`:

```python
if registry is None:
    return
```

This behavior conflicts with the new event's role as a required security barrier.

Several production terminal creation paths can omit the registry:

- `flow_service` calls `create_terminal()` without `registry`.
- `agent_step` accepts a registry in its surrounding API but does not forward it to
  `create_terminal()` in the shown creation call.
- `session_service.create_session()` defines `registry=None` as a valid default and
  forwards that value.
- Direct/internal `create_terminal()` calls can also rely on its optional registry
  default.

The resulting lifecycle is:

```text
flow / workflow / agent-step terminal creation
    ↓
create_terminal(registry=None)
    ↓
strict dispatcher returns successfully without handlers
    ↓
provider starts
    ↓
stale AGENTS.md / CLAUDE.md / Kiro steering may be loaded
```

The current lifecycle tests construct and pass a registry containing the expected memory
plugin, so they do not cover these production paths.

#### Required correction

The provider-memory security preparation must not depend on an optional registry.

Acceptable designs include:

- Move provider memory preparation into the core `create_terminal()` lifecycle for
  protected providers.
- Make registry presence mandatory and thread it through every production caller.
- Require a matching pre-initialize handler for Codex, Claude Code, and Kiro CLI; abort
  startup if the handler is absent.

Merely changing the registry argument from optional to required is insufficient unless
all internal callers and plugin-load failure cases are covered.

Required tests:

- Flow-created Codex/Claude/Kiro terminal.
- Agent-step-created Codex/Claude/Kiro terminal.
- Session-service terminal with no registry.
- Registry present but matching built-in memory plugin absent.
- Built-in plugin load failure.

Every protected-provider case must either prepare the file or refuse startup before the
provider process is constructed.

### Finding 2 — BLOCKER: malformed unclosed BEGIN retains stale payload

Affected locations:

```text
src/cli_agent_orchestrator/plugins/builtin/codex_memory.py:190-202
src/cli_agent_orchestrator/plugins/builtin/claude_code_memory.py
test/plugins/builtin/test_codex_memory.py:435-467
test/plugins/builtin/test_claude_code_memory.py:449-481
```

The managed-block parser handles a BEGIN marker without a valid matching END by deleting
only the BEGIN marker token:

```python
content = content[:begin] + content[begin + len(BEGIN_MARKER):]
```

All bytes after the marker remain in the provider instruction file.

For example:

```text
# User instructions
<!-- cao-memory:begin -->
<cao-memory>
- [global] legacy cross-project pollution
</cao-memory>
```

After the current scrub logic, the result is effectively:

```text
# User instructions
<cao-memory>
- [global] legacy cross-project pollution
</cao-memory>
```

The marker is gone, but the stale payload remains. The pre-initialization hook returns
successfully and the provider is allowed to load the content.

Existing unit tests intentionally preserve all text after an unclosed marker. That policy
was reasonable for a best-effort observer plugin because deleting unknown user content
would be unsafe. It is not sufficient for a security barrier whose guarantee is that stale
managed content cannot enter provider startup.

#### Required correction

An ambiguous malformed block must fail closed during pre-initialization.

Recommended behavior:

- Detect unmatched, nested, or otherwise malformed managed markers.
- Abort protected-provider startup with a content-free error.
- Preserve the file unchanged for explicit operator inspection or repair.
- Provide an explicit repair/scrub command if automatic ownership cannot be determined.

Do not silently delete unknown trailing content, but also do not silently permit provider
startup with that content.

Required tests:

- Codex BEGIN without END aborts before provider construction.
- Claude BEGIN without END aborts before provider construction.
- Nested/misaligned markers abort startup.
- File bytes remain unchanged after rejection.
- Error and log messages do not contain instruction-file content.

## 5. Impact assessment

The normal API path with a correctly loaded registry and well-formed markers is protected.
The remaining failures affect:

- Scheduled flows.
- Workflow or agent-step terminal creation.
- Other internal callers that omit the plugin registry.
- Deployments where the built-in plugin fails to load.
- Projects whose old provider instruction file was interrupted, manually edited, or
  otherwise left with malformed CAO markers.

In those cases, the same cross-project memory content that motivated this remediation can
still reach the provider's first context.

## 6. Validation performed

The following focused command was executed:

```bash
uv run pytest -q \
  test/cli/commands/test_memory.py \
  test/services/test_memory_scope_isolation.py \
  test/services/test_provider_memory_files.py \
  test/services/test_terminal_memory_preinitialize.py \
  test/plugins/builtin/test_codex_memory.py \
  test/plugins/builtin/test_claude_code_memory.py \
  test/plugins/builtin/test_kiro_cli_memory.py \
  test/plugins/test_events.py \
  test/plugins/test_registry.py \
  test/services/test_plugin_event_emission.py
```

Result:

```text
143 passed, 11 warnings
```

The warnings were existing SQLAlchemy `ResourceWarning` messages and did not fail the
test run.

`git diff --check d433ba8 0df986d` passed.

The passing suite confirms the expected normal-path behavior. It does not cover the two
blocking fail-open cases above.

## 7. Updated acceptance criteria

The next revision may be approved when all of the following are satisfied:

1. Every Codex, Claude Code, and Kiro terminal creation path executes provider-memory
   preparation before startup.
2. Missing registry cannot silently disable preparation.
3. Missing matching built-in hook cannot silently disable preparation.
4. Flow, agent-step, session-service, direct API, synchronous, and deferred paths share
   the same guarantee.
5. Correctly delimited stale blocks are refreshed or removed before provider startup.
6. Empty context does not create new files and removes existing managed content.
7. User-authored bytes outside valid managed spans remain preserved.
8. Kiro cleanup remains limited to the dedicated CAO memory steering file.
9. Malformed markers cause startup to fail closed before provider construction.
10. Malformed files remain unchanged for explicit repair.
11. Failure logs and errors remain content-free.
12. First-loaded-context lifecycle tests cover every protected production call path.

## 8. Final verdict

`0df986d` correctly fixes the main lifecycle ordering and normal stale-block cleanup when a
proper plugin registry is supplied and the managed file is well formed. The security
guarantee is still conditional on optional wiring, and malformed blocks retain their
payload while allowing startup.

**Verdict: `CHANGES REQUESTED`**

