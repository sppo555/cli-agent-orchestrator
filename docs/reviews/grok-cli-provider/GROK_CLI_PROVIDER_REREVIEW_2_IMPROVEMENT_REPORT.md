# Grok CLI Provider Re-review 2 Improvement Report

- Date: 2026-07-16
- Branch: `feat/grok-cli-provider`
- Base: `origin/main@32db5a192d82c7ded5d6e4be270d2a58e9702c3b`
- Review source: `REVIEW_GROK_CLI_PROVIDER_REREVIEW_2.md`
- Scope: lifecycle-only Grok CLI provider; Gate C remains NO-GO

## Outcome

All three findings from the third review have been addressed. Active Grok
output can no longer be converted into a successful public `LAST` payload,
sanitized raw/pyte fixtures are reproducible, and the skills documentation
states the Grok retrieval exception at the point where discovery is introduced.

## Finding Resolution

### P1: public LAST path leaked partial output

Resolved with a shared `IncompleteOutputError(ValueError)` contract. Grok raises
this typed error when the selected turn has no completion boundary or has a
newer processing marker. `terminal_service.get_output()` immediately propagates
the typed error from fixed-tail, escalating-tail, and full-history paths; it is
never converted to `[NO RESPONSE]` or `[PARTIAL RESPONSE]`.

Service-level regressions use the real Phase 0 fixtures:

- active `long_response_completed.ansi` raises `IncompleteOutputError` on the
  first 200-line fetch and never returns `LONG_RESPONSE_MARKER`;
- completed `completed_capture_pane.ansi` returns `CAPTURE_COMPLETED` through
  the same public `OutputMode.LAST` function.

### P2: raw/rendered_pyte divergence

Resolved. All 20 committed `rendered_pyte/*.txt` files were regenerated from
the final sanitized `raw/*.ansi` sources using the repository's
`render_with_pyte.py` at 120 columns by 40 rows. A parametrized parity test
invokes that render function for every pair and requires byte-for-byte equality.
The existing raw/screen status tests pass against the regenerated viewports.

### P3: conflicting load_skill discovery text

Resolved. The discovery section now distinguishes skills being *advertised*
from skills being retrievable. Both the default-catalog and scoped-catalog
paragraphs state up front that Grok lifecycle V1 receives catalog guidance
through `--rules` but cannot use CAO `load_skill` while Gate C is NO-GO.

## Validation

- Public-contract, Grok, parity, and native-status focused suite: `218 passed`.
- Grok unit suite including 20 parity cases and hygiene scan: `72 passed`.
- Provider/service/API/tool-mapping suite: `1159 passed, 7 skipped`.
- Full non-E2E suite, explicitly excluding `test/e2e`: `4097 passed, 14 skipped,
  1 failed`.
  - The only failure is the unchanged main-baseline workflow cancel timeout
    assertion: expected `30`, observed `300.0`.
  - The review's `21 skipped` count used a different collection scope that
    included seven additional E2E/environment skips; the command above excludes
    that directory and validates the Grok E2E separately with collect-only.
- Web unit tests: `61 passed`.
- Web production build: passed; existing jsdom noise and bundle warning remain.
- Grok live E2E collection: one lifecycle case collected.
- Live Grok E2E: not run; `CAO_RUN_GROK_INTEGRATION=1` remains required.
- Black, isort, six changed-source mypy targets, fixture hygiene, and
  `git diff --check`: passed.
- codebase-memory: reindexed; graph-augmented search found the typed error at
  the Grok extractor and all three `get_output()` preservation points.

## Safety Boundary

- No Grok, MCP, user, project, or global plugin configuration was changed.
- No `--plugin-dir` behavior was added.
- Gate C remains NO-GO; CAO orchestration and CAO `load_skill` retrieval remain
  unsupported for Grok lifecycle V1.
- Live lifecycle/restriction probes were not rerun in this pass.

## Recommendation

`READY_FOR_RE_REVIEW`
