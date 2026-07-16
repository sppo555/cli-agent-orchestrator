# `a8019d4` Memory Scope Isolation Review Remediation Report

**Date:** 2026-07-16

**Branch:** `custom/4.19-memory-scope-isolation`

**Codebase base:** `origin/main@8d53e75`

**Reviewed revision:** `a8019d4 fix(memory): isolate project-scoped writes`

**Outcome:** Both review blockers remediated; acceptance criteria covered by regression tests.

## 1. Scope and constraints

This revision addresses the blocking findings in
`REVIEW_A8019D4_MEMORY_SCOPE_ISOLATION.md` without importing code from an integration
branch.

The implementation did not inspect, audit, migrate, quarantine, or otherwise modify the
user's runtime memory directory or runtime SQLite database. All persistence and
quarantine tests used disposable `tmp_path` fixtures with isolated SQLite engines.

## 2. Blocker 1: terminal identity now fails closed

`_get_terminal_context_from_env()` now distinguishes two explicit caller modes:

- No `CAO_TERMINAL_ID`: intentional unbound operator mode; returns `None` and preserves
  existing global administration semantics.
- `CAO_TERMINAL_ID` present: terminal metadata must be verified. Timeout, connection
  refusal, HTTP error, malformed JSON, missing fields, or terminal-ID mismatch raises a
  dedicated `MemoryTerminalContextError` with a constant, content-free message.

The MCP memory tools catch the dedicated failure through their existing structured error
boundary and return:

```json
{
  "success": false,
  "error": "CAO terminal identity could not be verified; memory operation refused"
}
```

A working-directory lookup failure is handled separately. The verified context remains
`caller_scope="project"`, but contains no `cwd`. Consequently:

- global writes remain denied by the caller-scope boundary;
- project writes fail at project-ID resolution instead of falling into a shared location;
- the caller is never promoted to operator.

Logs use constant event markers and do not include response bodies or memory content.

## 3. Blocker 2: legacy global/project reads are isolated

The invalid pairing check is now shared by write and read policy:

```text
scope = global AND memory_type = project
```

The common wiki parser rejects this pairing before constructing a `Memory` object. This
single boundary covers:

- metadata recall;
- BM25 and hybrid result materialization;
- related-memory expansion;
- automatic `<cao-memory>` terminal context injection.

Each skipped legacy topic emits a content-free warning containing only its sanitized
topic key. Legal global `user`, `feedback`, and `reference` memories remain available.

## 4. Audit and explicit quarantine path

Two operator CLI commands were added:

```bash
# Read-only; table output by default
cao memory scope-audit
cao memory scope-audit --format json

# Dry-run by default
cao memory quarantine-global-project KEY

# Explicit mutation
cao memory quarantine-global-project KEY --apply
```

`scope-audit` scans only legacy global wiki headers and reports metadata fields, wiki
paths, index presence, and SQLite metadata presence. It does not return or log memory
bodies.

`quarantine-global-project` validates that the live topic really has the invalid pairing.
Without `--apply`, it creates no directories and changes no wiki, index, or database
state. With `--apply`, it first preserves the topic under:

```text
<memory-base>/quarantine/global-project/<key>.md
```

It then removes the live wiki topic, index entry, and SQLite metadata through the normal
`MemoryService.forget()` path. The command never guesses or assigns a project identity.

## 5. Cross-project regression coverage

The new tests create two distinct working directories and therefore two distinct project
IDs. They prove that:

- project A receives project A memory but not project B memory;
- project B receives project B memory but not project A memory;
- both receive a legal global reference memory;
- neither receives a seeded legacy global/project memory;
- normal global recall excludes the legacy topic;
- audit is read-only;
- quarantine is dry-run by default and removes all live persistence layers only when
  explicitly applied.

Terminal identity coverage includes timeout, refusal, HTTP 404/500, malformed or
incomplete metadata, identity mismatch, working-directory lookup failure, structured MCP
error output, and the explicit no-environment operator case.

## 6. Acceptance matrix

| Review acceptance criterion | Result |
|---|---|
| Declared terminal can never become operator after lookup failure | PASS |
| Timeout, refusal, 404/500, malformed metadata fail closed | PASS |
| Project terminal cannot write any global memory type | PASS |
| No-terminal-ID operator semantics remain available | PASS |
| New global/project writes fail before persistence | PASS |
| Existing global/project topics are excluded from recall and injection | PASS |
| Valid global user/feedback/reference memories remain available | PASS |
| Invalid legacy topics have read-only audit and explicit quarantine paths | PASS |
| Two-project injection preserves project isolation plus valid global context | PASS |

## 7. Validation results

### Isolation and CLI regression set

```bash
.venv/bin/pytest -q \
  test/cli/commands/test_memory.py \
  test/services/test_memory_scope_isolation.py
```

Result: `53 passed`.

### Memory/archive-related suite

```bash
.venv/bin/pytest -q $(rg --files test | rg '(memory|archive)')
```

Result: `398 passed`.

### Full non-E2E suite

```bash
.venv/bin/pytest -q -m 'not e2e'
```

Result: `4075 passed, 21 skipped, 93 deselected, 1 failed`.

The sole failure is the pre-existing baseline mismatch:

```text
test/mcp_server/test_workflow_tools.py::TestWorkflowCancel::test_success_envelope
actual timeout: 300.0
expected timeout: 30
```

It is outside the memory isolation change and was present before this remediation.

Additional checks:

- Black check passed for all modified Python files.
- `git diff --check` passed.
- `cao memory --help` exposes both new maintenance commands.

Existing SQLAlchemy `ResourceWarning` messages remain warnings and did not fail the
targeted suites.

## 8. Final assessment

The two blockers in the `a8019d4` review are closed at central boundaries:

1. declared terminal identity cannot fail open into operator authority;
2. legacy global/project pollution cannot enter normal recall or prompt injection.

Cleanup remains an explicit operator action, with read-only audit and dry-run defaults.
No runtime memory or database migration was performed as part of this implementation.
