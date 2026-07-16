# `a8019d4` Memory Scope Isolation Review Report

**Review date:** 2026-07-16  
**Branch:** `custom/4.19-memory-scope-isolation`  
**Base:** `origin/main@8d53e75`  
**Commit:** `a8019d4 fix(memory): isolate project-scoped writes`  
**Verdict:** `CHANGES REQUESTED`

## 1. Executive summary

The patch adds a useful store-boundary rule that rejects the invalid combination
`scope="global"` plus `memory_type="project"`, and it marks verified CAO terminals as
project-bounded callers. The new validation runs before filesystem and SQLite writes,
which is the correct placement.

However, two isolation gaps remain:

1. A CAO terminal becomes an unrestricted global operator when terminal-context lookup
   fails.
2. Existing global/project memories remain readable and injectable across projects.

Because both gaps can defeat the intended hard isolation guarantee, this review does not
approve the commit in its current form.

## 2. Scope and baseline verification

The reviewed branch consists of one commit directly on the declared base:

```text
a8019d4 fix(memory): isolate project-scoped writes
8d53e75 feat(ops-mcp): add read_session_output tool for typed worker-output readback (#422)
```

No direct code overlap with the stated 4.17/4.18 work was found in the reviewed diff.

The commit changes:

- Memory documentation and duplicated CAO Memory skill instructions.
- CAO MCP terminal context construction.
- The central `MemoryService.store()` validation boundary.
- Existing tests that previously stored project-typed memories globally.
- A new project/global isolation regression test module.

## 3. Positive findings

### 3.1 Invalid global/project writes are rejected centrally

File:

```text
src/cli_agent_orchestrator/services/memory_service.py:670-679
```

The patch rejects:

```python
scope == "global" and memory_type == "project"
```

immediately after enum validation and before scope resolution, wiki writes, index writes,
or SQLite metadata writes. This protects both new topics and appends to existing topics.

### 3.2 Rejection does not expose the memory body

The rejection message contains the invalid scope/type combination but not the supplied
content. The new test verifies that sensitive content does not appear in the returned MCP
error.

### 3.3 Verified terminals are assigned a project caller scope

File:

```text
src/cli_agent_orchestrator/mcp_server/server.py:1271-1280
```

When CAO successfully resolves terminal metadata, the context now includes:

```python
"caller_scope": "project"
```

This causes the existing `scope_write_allowed()` boundary to reject global writes made by
normal project workers.

### 3.4 Documentation describes the intended scope policy

The documentation and both copies of the CAO Memory skill now state that project
implementation facts, test results, paths, ports, architecture decisions, slices, and
acceptance results belong in project scope. Global scope is reserved for genuinely
cross-project preferences and operating rules.

## 4. Blocking findings

### Finding 1 — BLOCKER: terminal-context resolution fails open

Affected code:

```text
src/cli_agent_orchestrator/mcp_server/server.py:1261-1294
src/cli_agent_orchestrator/services/memory_service.py:382-407
```

When `CAO_TERMINAL_ID` is present, `_get_terminal_context_from_env()` requests terminal
metadata from the CAO API. If the request times out, receives an HTTP error, returns
malformed JSON, or otherwise raises, the function catches the exception and returns
`None`:

```python
except Exception as e:
    logger.warning(...)
    return None
```

`MemoryService.resolve_caller_scope(None)` then defaults to `global`, which represents an
unrestricted operator:

```python
ctx = terminal_context or {}
...
return "global"
```

The resulting path is:

```text
CAO worker has CAO_TERMINAL_ID
        ↓
CAO terminal API temporarily fails
        ↓
terminal_context becomes None
        ↓
caller_scope defaults to global operator
        ↓
worker can write global user/feedback/reference memories
```

The new `global + project` type rule still rejects project-typed writes, but the stronger
documented guarantee—terminal-bound project workers cannot write global—is no longer true.
A project-specific fact can again enter the global pool if it is mislabeled as `reference`,
`feedback`, or `user` during an API outage.

This is especially relevant because transient CAO server connection failures have already
occurred in the operating environment.

#### Required correction

When `CAO_TERMINAL_ID` exists, terminal-context verification must fail closed. Suitable
implementations include:

- Raise a dedicated context-resolution error and return a structured MCP failure.
- Return a constrained context with `caller_scope="project"`, while refusing project-scope
  writes until a trustworthy working directory is available.
- Separate operator invocation from terminal invocation before calling `MemoryService`, so
  a failed terminal lookup can never be interpreted as an operator.

Add tests for at least:

- CAO API connection timeout/refusal.
- Terminal metadata HTTP 404/500.
- Malformed or incomplete terminal metadata JSON.
- Working-directory lookup failure.
- Absence of `CAO_TERMINAL_ID`, which should remain the explicit operator case.

### Finding 2 — BLOCKER: existing polluted global memories remain injectable

Affected code:

```text
src/cli_agent_orchestrator/services/memory_service.py:2291-2303
src/cli_agent_orchestrator/services/memory_service.py:2532-2582
```

The patch prevents new `global + project` writes, but it does not migrate, quarantine, or
filter existing invalid entries.

The search path still always includes the global directory:

```python
global_dir = self.base_dir / "global"
if global_dir.exists():
    dirs.append(global_dir)
```

Terminal context injection also explicitly processes global scope after session and
project scope:

```python
scopes_in_order = [
    MemoryScope.SESSION.value,
    MemoryScope.PROJECT.value,
    MemoryScope.GLOBAL.value,
]
```

The known polluted entry therefore remains eligible for recall and injection:

```text
~/.aws/cli-agent-orchestrator/memory/global/wiki/global/
  slice-a3-e2e-tts-sentinel.md

scope: global
type: project
```

The new test `test_existing_global_project_topic_cannot_be_appended` confirms that such a
legacy file is not modified by a rejected append, but there is no test proving that the
entry is excluded from recall or prompt injection.

Consequently, deploying `a8019d4` alone does not stop the originally reported
cross-project contamination. It prevents one form of new pollution while leaving existing
pollution active.

#### Required correction

At minimum:

1. Exclude `scope="global"` plus `memory_type="project"` entries from recall and automatic
   context injection.
2. Emit a content-free warning or metric when an invalid legacy entry is skipped.
3. Provide an audit command or report listing invalid global/project entries.
4. Provide an explicit migration or quarantine path; do not silently assign an unknown
   project identity.

Add regression tests proving that:

- An existing global/project index entry is not returned by normal recall.
- It is not included in `<cao-memory>` terminal injection.
- Valid global `user`, `feedback`, and `reference` memories remain available.
- Project memories remain available only to terminals resolving to the same project ID.

## 5. Test results

The following targeted test command was run:

```bash
uv run pytest -q \
  test/services/test_memory_scope_isolation.py \
  test/services/test_memory_service.py \
  test/providers/test_memory_injection.py
```

Result:

```text
69 passed, 9 warnings
```

The warnings were `ResourceWarning` reports for unclosed SQLite connections. They did not
fail the targeted test run and are not classified as blockers for this commit.

`git diff --check 8d53e75 a8019d4` also completed successfully.

The passing tests demonstrate that the newly implemented cases work, but neither blocking
scenario above is currently covered.

## 6. Required acceptance criteria for the next revision

The next revision should satisfy all of the following:

1. A process with `CAO_TERMINAL_ID` can never become an operator because terminal metadata
   lookup failed.
2. CAO API timeout, refusal, 404/500, and malformed metadata all fail closed.
3. Project-bound terminals cannot write any global memory type.
4. Operators without `CAO_TERMINAL_ID` retain intentional global administration semantics.
5. `global + project` writes remain rejected before all persistence.
6. Existing `global + project` entries are excluded from recall and terminal injection.
7. Valid global cross-project memories remain recallable.
8. Invalid legacy entries can be audited and explicitly migrated or quarantined.
9. Cross-project injection tests use two distinct project working directories and prove
   that each receives only its own project memories plus valid global memories.

## 7. Final verdict

`a8019d4` establishes the correct central write-time validation for one invalid scope/type
combination, and its documentation direction is sound. It is not yet a complete hard
isolation fix because terminal identity resolution can fail open and legacy polluted data
continues to participate in recall and injection.

**Verdict: `CHANGES REQUESTED`**

