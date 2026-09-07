# Grok Phase 0 fixture manifest

All captured states use a 120x40 tmux pane. `raw/*.ansi` is ANSI output and
`rendered/*.txt` is a tmux screen snapshot; where an ANSI stream was available,
`rendered_pyte/*.txt` is the pyte rendering.

| Requested state | Raw capture | Rendered capture | Notes |
| --- | --- | --- | --- |
| shell prompt | `raw/shell_prompt.ansi` | `rendered/shell_prompt.txt` | zsh `❯` only |
| shell Grok-like prompt | `raw/shell_groklike_prompt.ansi` | `rendered/shell_groklike_prompt.txt` | false-IDLE extreme case |
| startup | `raw/startup.ansi` | `rendered/startup.txt` | later live capture; 0.2.101 |
| idle | `raw/idle.ansi` | `rendered/idle.txt` | 0.2.93 capture; pipe-pane |
| processing | `raw/processing_capture_pane.ansi` | `rendered/processing.txt` | `Starting session…` |
| completed | `raw/completed_capture_pane.ansi` | `rendered/completed.txt` | response + completion footer |
| long response | `raw/long_response_completed.ansi` | `rendered/long_response_completed.txt` | historical filename says completed, but the captured viewport still has `Responding…` and `[stop]`; status is processing |
| Markdown | `raw/markdown_completed.ansi` | `rendered/markdown_completed.txt` | heading and fenced code |
| multiline code | `raw/paste_code.ansi` | `rendered/paste_code.txt` | bracketed paste probe |
| question response | `raw/waiting_question_after.ansi` | `rendered/waiting_question_after.txt` | completed question, not native wait |
| plan output | `raw/plan_after.ansi` | `rendered/plan_after.txt` | no approval control reached |
| permission/tool error | `raw/security_direct_shell.ansi` | `rendered/security_direct_shell.txt` | native deny result |
| auth error | `raw/auth_error.SKIP.md` | `rendered/auth_error.SKIP.md` | explicit skip |
| native selection wait | `raw/waiting_selection.SKIP.md` | `rendered/waiting_selection.SKIP.md` | explicit skip |
| native permission prompt | `raw/permission_prompt.SKIP.md` | `rendered/permission_prompt.SKIP.md` | explicit skip |

Paste variants are in paired `paste_single`, `paste_multiline`, `paste_code`,
and `paste_unicode` files. Exit variants are in `rendered/exit_*.txt` with
pane command observations in `spikes/exit_*_pane.txt`.
