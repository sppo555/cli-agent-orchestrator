# Handoff — Prompt 1 Phase 0 Evidence — grok_cli provider

## Dispatching
- Status: DISPATCHING
- Worker: new_project__developer_codex
- Task file: .cao/tasks/20260715T114145Z-grok-cli-phase0-evidence-developer_codex.md
- Expected artifact: .cao/worker-results/20260715T114145Z-grok-cli-phase0-evidence-developer_codex.md
- Branch: feat/grok-cli-phase0-evidence (based on main @ 32db5a1)

## Current project state
Prompt 0 pre-flight completed and reviewed informally by supervisor (artifact
non-empty, git status clean of source changes, verdict READY_WITH_CORRECTIONS).
Terminal 9ba1461a (the Prompt 0 worker) was reaped/deleted before this dispatch.
User explicitly instructed to skip further plan-review ping-pong on Prompt 0
and proceed straight into Prompt 1 (Phase 0 Evidence) — this is a deliberate
user override of the normal PLAN REVIEW gate, not a supervisor decision to
skip mandatory review; CODE REVIEW (Prompt 1R equivalent / new_project__reviewer_developer_codex)
still applies after this stage produces evidence.

## Why this worker/stage is next
Per PLAN_CAO_ADD_GROK_CLI_PROVIDER_V2_1.md, PR 2 (real provider implementation)
cannot start until Phase 0 evidence + ADR + Gate A/B/C decisions exist. This
is a large, multi-part task (capability matrix, TUI fixture capture, MCP Path
A/B/C spike, subagent security spike, ADR) — expect it may need more than one
20-minute window; monitor for genuine progress (growing artifact / new
committed fixture files) before treating it as stuck.

## Next step
Once the artifact is non-empty and fixtures/ADR appear as real committed
changes on this branch, dispatch to new_project__reviewer_developer_codex for
Prompt 1R (Phase 0 Evidence Review). Do NOT let the developer proceed to PR 2
even if it claims Phase 0 is complete — reviewer must approve first.

## Open issues / risks
- Live Grok CLI/tmux prerequisites may or may not be available in this sandbox;
  worker must SKIP (not fabricate) any live evidence it cannot actually
  execute, and say so explicitly in the report.
- Gate C (MCP identity forwarding) is expected to plausibly fail (Path A/B/C);
  LIFECYCLE_ONLY is an acceptable, non-blocking outcome per the PLAN.

## Resume prompt
Resume grok_cli provider work on branch feat/grok-cli-phase0-evidence in
/Users/alex/Developer/cli-agent-orchestrator. Check whether
.cao/worker-results/20260715T114145Z-grok-cli-phase0-evidence-developer_codex.md
exists and is non-empty, and whether new fixture/ADR files were committed on
this branch. If yes, dispatch to new_project__reviewer_developer_codex for
Prompt 1R review before allowing any PR 2 (GrokCliProvider implementation)
work. If the developer_codex terminal is dead/stuck with no progress after
20+40 minutes, follow the ABSOLUTE HALT RULE — do not implement it yourself,
report to the user and wait.
