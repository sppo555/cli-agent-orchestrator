# Handoff — Prompt 1R Phase 0 Evidence Review — grok_cli provider

## Dispatching
- Status: DISPATCHING
- Worker: new_project__reviewer_developer_codex
- Task file: .cao/tasks/20260715T120329Z-grok-cli-phase0-review-reviewer_developer_codex.md
- Expected artifact: .cao/worker-results/20260715T120329Z-grok-cli-phase0-review-reviewer_developer_codex.md
- Branch: feat/grok-cli-phase0-evidence (uncommitted changes present)

## Current project state
new_project__developer_codex (terminal cfdb9cb6, still alive, not yet reaped)
completed Prompt 1 Phase 0 Evidence: 112 fixture/evidence files under
test/providers/fixtures/grok_cli/, docs/adr-grok-cli-phase0.md, and a 116-line
evidence report. Self-reported: Gate A=GO, Gate B=GO, Gate C=NO-GO
(LIFECYCLE_ONLY), quality checks passed, Grok version drifted 0.2.93->0.2.101
mid-capture. Nothing committed to git yet — supervisor will commit only after
this review approves (or after required corrections are applied).

## Why this worker/stage is next
Prompt Pack mandates Prompt 1R review before any PR 2 (provider implementation)
work may begin, regardless of developer's self-reported success.

## Next step
- If verdict is PROMPT_2_ALLOWED (or APPROVE / APPROVE_WITH_CORRECTIONS with
  only non-blocking notes): supervisor commits the Phase 0 evidence files to
  this branch, then proceeds to Prompt 2 (Registration + Lifecycle + Profile)
  dispatched to new_project__developer_codex.
- If PHASE_0_FIXES_REQUIRED: relay findings back to new_project__developer_codex
  (reuse terminal cfdb9cb6 or fresh dispatch per Dispatch Protocol) for fixes,
  then re-review.
- If STOP_PROJECT: halt and report to the user with the reviewer's reasoning.

## Open issues / risks
- Grok version drift (0.2.93 -> 0.2.101) mid-capture is a first-class risk to
  verify: does the ADR clearly attribute each fixture to a version, and does
  any fixture need recapture under the newer version before PR 2/3 can safely
  rely on it?

## Resume prompt
Resume grok_cli provider work on branch feat/grok-cli-phase0-evidence in
/Users/alex/Developer/cli-agent-orchestrator. Check whether
.cao/worker-results/20260715T120329Z-grok-cli-phase0-review-reviewer_developer_codex.md
exists and is non-empty. Read its verdict and "Allowed Next Stage" field, then
proceed per the Next step section above. If the reviewer terminal is
dead/stuck with no progress after 20+40 minutes, follow the ABSOLUTE HALT
RULE — do not review the code yourself, report to the user and wait.
