# Task: Prompt 0 — Pre-flight Report (grok_cli provider)

## Role
new_project__developer_codex acting as implementation engineer for PRE-FLIGHT ONLY.

## Inputs (read fully before acting)
- /Users/alex/Developer/cli-agent-orchestrator/PLAN_CAO_ADD_GROK_CLI_PROVIDER_V2_1.md
- /Users/alex/Developer/cli-agent-orchestrator/PROMPT_PACK_CAO_GROK_CLI_PROVIDER_V1.md (section "Prompt 0")

## Scope
This stage is PRE-FLIGHT ONLY. Do NOT modify source code, tests, documentation,
user configuration, project configuration, or Grok configuration. Do not
implement GrokCliProvider or register grok_cli anywhere. Do not use or invent
a --plugin-dir flag. Do not modify ~/.grok/config.toml, .grok/config.toml,
.mcp.json, or any global plugin registry. Do not assume AgentProfile has an
effort field — verify from the actual checkout. Do not claim a command was
validated unless you actually executed it. Do not expose secrets/tokens.

## Exact task
Execute the full "Prompt 0" prompt text verbatim as given in
PROMPT_PACK_CAO_GROK_CLI_PROVIDER_V1.md (the block starting "You are the
implementation engineer for the Grok CLI provider..." through "Do not edit
files. Stop after the report."). Treat the checked-out repository at
/Users/alex/Developer/cli-agent-orchestrator (branch: feat/grok-cli-phase0-evidence)
as the source of truth, not the PLAN's assumptions.

Produce the required "# Pre-flight Report" output format exactly as specified
in Prompt 0 (Environment, Repository Baseline, AgentProfile Schema, Test and
Quality Conventions, CLI Capability Snapshot, Available Prerequisites, PLAN
Discrepancies, Recommended Next Action).

## Deliverable
Write the FULL report as the artifact file:
/Users/alex/Developer/cli-agent-orchestrator/.cao/worker-results/20260715T112632Z-grok-cli-preflight-developer_codex.md

## Completion signal
When done, write the artifact file, then call `send_message` (no receiver_id)
to report back to this terminal.
