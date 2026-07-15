# Grok CLI Provider Improvement Report

- Date: 2026-07-16
- Branch: `feat/grok-cli-provider`
- Base: `origin/main@32db5a192d82c7ded5d6e4be270d2a58e9702c3b`
- Review source: `REVIEW_GROK_CLI_PROVIDER.md`
- Scope: lifecycle-only Grok CLI provider; Gate C remains NO-GO

## Outcome

All findings in the review have been addressed and are ready for re-review.
The implementation still does not configure Grok MCP, advertise CAO
orchestration, use `--plugin-dir`, or modify user/project/global configuration.

## Finding Resolution

### P1: real pyte ready and waiting detection

Resolved. Ready detection now treats the input-box marker and Grok model footer
as a composite surface after whitespace normalization, so a 120-column pyte
wrap may split the border, `Grok`, model, and mode across rows. The real Phase 0
raw and pyte captures are tested in pairs. The captured completed assistant
question maps to `WAITING_USER_ANSWER`; a stale question from an older turn no
longer contaminates a newer completed turn.

### P1: stale processing marker

Resolved. Status detection compares the most recent processing/dialog/error
marker with the most recent completion boundary. Historical `Starting
session…`, `Thinking…`, or `Responding…` text before a newer completion no
longer wins. Paired stale-processing and stale-ready regression fixtures cover
both directions.

### P1: response extraction and Markdown preservation

Resolved. The extractor no longer scans ahead for an arbitrary blank line.
ANSI prompt-background evidence is used for wrapped prompts; unstyled ambiguous
boundaries fail with `ValueError`. An assistant/code line beginning with `❯`
cannot silently become the next user boundary. Actual Phase 0 ANSI heading and
code-block styles are reconstructed as a Markdown heading and fenced block.
Tests cover the real Markdown capture, first-paragraph loss, ambiguous `❯`,
nested lists, Unicode, blank lines, long output, and multi-turn selection.

### P2: evidence fixtures

Resolved. The complete sanitized Phase 0 fixture set and ADR are present in the
feature worktree, including raw ANSI, rendered tmux, rendered pyte, CLI
capability evidence, skip ledgers, paste/exit/restriction captures, and the MCP
identity probe that was deliberately never registered. The four hand-written
short screen fixtures were removed.

The historical file `long_response_completed.ansi` actually contains an active
`Responding…`/`[stop]` surface. The manifest and tests now document and classify
that evidence as `PROCESSING` rather than trusting its filename.

### P2: startup guard without profile rules

Resolved. `--rules` and the startup guard are always emitted, including the
default no-profile/no-skill/unrestricted command. Oversize diagnostics report
profile, skill, security, and startup-guard byte contributions.

### P3: Gate C and restart documentation

Resolved. `docs/grok-cli.md` now records the outcomes for direct inheritance,
runtime expansion, and key-only forwarding, plus the conditions that could
justify reevaluating Gate C. It also documents that on-demand reconstruction
does not restore constructor-only `model` or `skill_prompt` overrides.

## Validation

- Grok evidence/unit suite: `48 passed`.
- Provider/service/API/tool-mapping suite: `1132 passed, 7 skipped`.
- Full non-E2E suite: `4071 passed, 14 skipped, 1 failed`.
  - The sole failure is the unchanged main-baseline workflow cancel timeout
    assertion: expected `30`, observed `300.0`.
- Web unit tests: `61 passed`.
- Web production build: passed; existing bundle-size warning remains.
- Black: passed.
- isort: passed.
- mypy for changed Grok registration/provider files: passed.
- Grok E2E collection: one lifecycle case collected.
- Live Grok E2E: not run; it remains opt-in through
  `CAO_RUN_GROK_INTEGRATION=1`.

## Remaining Accepted Limitations

- Gate C is NO-GO; `assign`, `handoff`, and `send_message` are unsupported.
- No Grok authentication or configuration is managed by CAO.
- Phase 0 contains mixed Grok 0.2.93 and 0.2.101 evidence because the CLI
  auto-updated during calibration.
- Native selection, interactive approval, and authentication-error states were
  not safely reachable and remain explicitly documented skips.
- ANSI Markdown reconstruction is calibrated to the captured Grok style and
  must be recalibrated if upstream TUI styling changes.
- Live lifecycle, paste, exit, and native restriction behavior were not rerun
  during this improvement pass.

## Recommendation

`READY_FOR_RE_REVIEW`
