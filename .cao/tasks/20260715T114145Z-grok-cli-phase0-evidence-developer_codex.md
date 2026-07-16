# Task: Prompt 1 — Phase 0 / PR 1 Evidence (grok_cli provider)

## Role
new_project__developer_codex, evidence-first calibration only.

## Inputs (read fully before acting)
- /Users/alex/Developer/cli-agent-orchestrator/PLAN_CAO_ADD_GROK_CLI_PROVIDER_V2_1.md
- /Users/alex/Developer/cli-agent-orchestrator/PROMPT_PACK_CAO_GROK_CLI_PROVIDER_V1.md (section "Prompt 1：Phase 0 / PR 1 Evidence")
- Prior pre-flight report: /Users/alex/Developer/cli-agent-orchestrator/.cao/worker-results/20260715T112632Z-grok-cli-preflight-developer_codex.md
  (verdict: READY_WITH_CORRECTIONS — note Grok `mcp add -e` is KEY=value only,
  and `--plugin-dir` must NOT be used per PLAN even though it is exposed by
  `grok agent --help`.)

## Branch
feat/grok-cli-phase0-evidence (already checked out, based on main @ 32db5a1)

## Scope
Execute the full "Prompt 1" prompt text verbatim as given in
PROMPT_PACK_CAO_GROK_CLI_PROVIDER_V1.md (the block starting "Implement Phase 0
/ PR 1 from..." through "Stop after Phase 0. Do not implement PR 2.").

This is evidence-first calibration ONLY:
- Do NOT implement GrokCliProvider.
- Do NOT register grok_cli in ProviderType, ProviderManager, CLI, API, or Web UI.
- Do NOT change production provider behavior.
- Do NOT modify user or project Grok configuration (~/.grok/config.toml,
  .grok/config.toml, .mcp.json, global plugin registry).
- Do NOT use --plugin-dir under any circumstance.
- Do NOT proceed to PR 2.
- Do NOT assume AgentProfile.effort exists (confirmed absent in target checkout).
- Do NOT claim live evidence when prerequisites are unavailable — SKIP and say so.

Required investigations (see Prompt 1 for full detail): baseline capture,
CLI capability matrix, TUI raw+rendered capture across all listed states,
shell false-IDLE spike, paste/submit behavior, exit behavior, subagent
security spike (restricted profile bypass attempts), MCP identity Path A/B/C
(direct inheritance -> config env expansion -> forward-by-name), concurrency
test (>=20 checks) on whichever path looks viable, and a written ADR covering
all Gate A/B/C decisions and the final V1 capability outcome
(LIFECYCLE_AND_ORCHESTRATION / LIFECYCLE_ONLY / NO_GO_FOR_LIFECYCLE_RELEASE).

Use repository conventions for fixture/test locations:
test/providers/fixtures/grok_cli/ (or test/providers/fixtures/ per repo norm),
test/e2e/ for live probes, and an existing docs/ADR location.

Run repository-standard formatting/checks/tests applicable to evidence files
(black --check, isort --check-only, mypy, relevant pytest) — do not substitute
Ruff.

## Deliverable
Write the FULL "# Phase 0 Evidence Report" (exact structure required by
Prompt 1) as the artifact file:
/Users/alex/Developer/cli-agent-orchestrator/.cao/worker-results/20260715T114145Z-grok-cli-phase0-evidence-developer_codex.md

Also commit the actual fixture/ADR files created during this stage to the
current branch (feat/grok-cli-phase0-evidence) as real repo changes — this PR
is expected to add files (fixtures, ADR, capture scripts), just not provider
source code.

## Completion signal
When done, write the artifact file, then call `send_message` (no receiver_id)
to report back to this terminal.
