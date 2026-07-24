# Grok CLI Provider Re-review Improvement Report

- Date: 2026-07-16
- Branch: `feat/grok-cli-provider`
- Base: `origin/main@32db5a192d82c7ded5d6e4be270d2a58e9702c3b`
- Review source: `REVIEW_GROK_CLI_PROVIDER_REREVIEW.md`
- Scope: lifecycle-only Grok CLI provider; Gate C remains NO-GO

## Outcome

All four re-review findings have been addressed and are ready for another
review. No Grok, MCP, user, project, or global plugin configuration was changed.
The implementation does not use `--plugin-dir` or advertise CAO orchestration.

## Finding Resolution

### P1: partial processing output returned as final

Resolved. Response extraction now requires a completion boundary after the
selected Grok prompt. It also compares the latest completion and processing
markers and raises `ValueError` when a newer `Responding…`, `[stop]`, or other
processing surface exists. The historically named
`long_response_completed.ansi`, whose actual viewport is still active, is now
rejected by extraction. The real completed `plan_after.ansi` capture exercises
successful extraction of a long-form response.

### P2: shell prompt before ANSI Grok prompt

Resolved. Calibrated ANSI Grok prompt-background evidence now takes precedence
over older unstyled candidates such as `❯ grok --always-approve` in shell
scrollback. Candidates after the latest ANSI Grok prompt are retained for the
ambiguity guard, so assistant/code output beginning with `❯` still fails safely.
A regression combines a shell prompt with the real completed ANSI capture.

### P2: fixture sanitization

Resolved. Personal usernames, hostnames, home paths, project paths, and local
executable paths were replaced with stable placeholders across the complete
fixture tree. The inspect and MCP doctor JSON fixtures were reduced to the
minimum fields needed for Gate C evidence; server names and unrelated skill
inventory are generalized. A test scans every fixture and rejects personal
absolute paths, hostnames, and local executable prefixes.

### P2: security and skills documentation

Resolved. `SECURITY.md` now records Grok's native `--deny` enforcement,
conditional `--no-subagents`, and lifecycle-only orchestration boundary.
`docs/skills.md` includes Grok in all runtime-prompt provider locations and
states that V1 injects the catalog through `--rules` but cannot claim CAO
`load_skill` retrieval while Gate C is NO-GO.

### P3: ADR decision state

Resolved. The Phase 0 ADR is accepted for lifecycle-only V1 implementation and
production registration. It continues to reject Gate C orchestration and
configuration writes, records the implementation-review acceptance date, and
reframes mixed-version calibration requirements for future version updates.

## Validation

- Grok provider plus shared native-status suite: `152 passed`.
- Provider/service/API/tool-mapping suite: `1137 passed, 7 skipped`.
- Full non-E2E suite: `4075 passed, 14 skipped, 1 failed`.
  - The only failure is the unchanged main-baseline workflow cancel timeout
    assertion: expected `30`, observed `300.0`.
- Fixture hygiene scan: passed with no personal path/hostname matches.
- Web unit tests: `61 passed`.
- Web production build: passed; the existing bundle-size warning remains.
- Black, isort, changed-source mypy, and `git diff --check`: passed.
- Grok live E2E collection: one lifecycle case collected.
- Live Grok E2E: not run; it remains opt-in through
  `CAO_RUN_GROK_INTEGRATION=1`.
- codebase-memory: repository reindexed and the new extraction boundary was
  found in the provider method graph/search result.

## Remaining Accepted Limitations

- Gate C is NO-GO; `assign`, `handoff`, `send_message`, and CAO `load_skill`
  retrieval are unsupported for Grok V1.
- Phase 0 contains mixed Grok 0.2.93 and 0.2.101 evidence because Grok
  auto-updated during calibration.
- Native selection, interactive approval, and authentication-error states were
  not safely reachable and remain explicit skips.
- Live lifecycle, paste, exit, and restriction probes were not rerun in this
  pass.

## Recommendation

`READY_FOR_RE_REVIEW`
