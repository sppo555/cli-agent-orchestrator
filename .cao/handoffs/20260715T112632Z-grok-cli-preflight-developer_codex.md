# Handoff — Prompt 0 Pre-flight — grok_cli provider

## Dispatching
- Status: DISPATCHING
- Worker: new_project__developer_codex
- Task file: .cao/tasks/20260715T112632Z-grok-cli-preflight-developer_codex.md
- Expected artifact: .cao/worker-results/20260715T112632Z-grok-cli-preflight-developer_codex.md
- Branch: feat/grok-cli-phase0-evidence

## Current project state
PLAN_CAO_ADD_GROK_CLI_PROVIDER_V2_1.md and PROMPT_PACK_CAO_GROK_CLI_PROVIDER_V1.md
were just added (untracked) to the repo root. PLAN is "Approved for Phase 0".
No planner stage needed — the PLAN + Prompt Pack are already the plan; the
Prompt Pack's Prompt 0 is a read-only pre-flight check, not implementation.
Full pipeline decision: user explicitly requested all stages route to codex
variants (new_project__developer_codex, new_project__reviewer_developer_codex,
new_project__planner_codex, new_project__reviewer_planner_codex), but planner
stage is skipped for this project since the PLAN document already exists and
is approved.

## Why this worker/stage is next
Prompt 0 must run before any Phase 0 evidence work (Prompt 1). It is read-only
and safe to dispatch immediately.

## Next step
After artifact confirmed non-empty, send it to new_project__reviewer_developer_codex
for verification against Prompt 0's 驗收 criteria (no files edited, explicit
effort-field finding, real cao session --help captured, single clear verdict).
Then proceed to Prompt 1 (Phase 0 Evidence) only if verdict is READY_FOR_PHASE_0
or READY_WITH_CORRECTIONS.

## Resume prompt
Resume grok_cli provider work on branch feat/grok-cli-phase0-evidence in
/Users/alex/Developer/cli-agent-orchestrator. Check whether
.cao/worker-results/20260715T112632Z-grok-cli-preflight-developer_codex.md
exists and is non-empty. If yes, review it against Prompt 0's acceptance
criteria (see PROMPT_PACK_CAO_GROK_CLI_PROVIDER_V1.md), then continue the
pipeline (Prompt 1 Phase 0 Evidence dispatched to new_project__developer_codex,
reviewed by new_project__reviewer_developer_codex). If no artifact and the
developer_codex terminal is dead/stuck, follow the ABSOLUTE HALT RULE — do not
implement it yourself, report to the user and wait.
