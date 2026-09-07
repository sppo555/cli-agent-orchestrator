# Phase 0 state availability ledger

The following states were requested by Prompt 1 but were not reachable without
changing Grok configuration or accepting a destructive action:

| State | Result | Evidence / reason |
| --- | --- | --- |
| waiting for native question/selection | SKIP | A prompt asking Grok to ask one question produced a completed assistant question, not a native input-selection surface. See `raw/waiting_question_after.ansi` and `rendered/waiting_question_after.txt`. |
| plan approval | SKIP as approval; CAPTURED as plan output | `--permission-mode plan` rendered a plan, but no approval control appeared because the request explicitly prohibited writes. See `raw/plan_after.ansi` and `rendered/plan_after.txt`. |
| interactive permission prompt | SKIP | `--deny Bash --deny Edit` produced an immediate policy-denied tool result rather than an approval prompt; no approval was accepted. |
| authentication error | SKIP | Authentication was available and no safe logout/credential-invalidating experiment was authorized. |
| non-CAO MCP write | SKIP | Read-only `grok mcp doctor --json` showed two healthy project servers, generalized as `project-server-a` and `project-server-b`; neither was a file-write probe. No MCP config was changed. |

The policy-denied shell result is retained as `tool_error` evidence in
`raw/security_direct_shell.ansi` and `rendered/security_direct_shell.txt`.
