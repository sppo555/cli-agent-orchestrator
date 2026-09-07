# Grok CLI Phase 0 capability matrix

Commands were executed from CAO commit `32db5a192d82c7ded5d6e4be270d2a58e9702c3b`.
Full stdout/stderr captures are in this directory. The first version capture
is 0.2.93; the later live binary reported 0.2.101 after Grok auto-updated.

| Capability | Result | Source |
| --- | --- | --- |
| `--always-approve` | PRESENT | `grok_help.txt` |
| `--rules` | PRESENT | `grok_help.txt` |
| `--allow` / `--deny` | PRESENT | `grok_help.txt` |
| `--model` | PRESENT | `grok_help.txt` |
| `--effort` | PRESENT as alias of `--reasoning-effort` | `grok_help.txt`, `grok_agent_help.txt` |
| `--no-subagents` | PRESENT | `grok_help.txt` |
| `--session-id` | PRESENT | `grok_help.txt` |
| `--plugin-dir` | PRESENT only under `grok agent`; PROHIBITED by this task | `grok_agent_help.txt` |
| `--mcp-config` | ABSENT from captured root/agent help | `grok_help.txt`, `grok_agent_help.txt` |
| rules-file support | ABSENT; `--rules` accepts inline rules and `--prompt-file` is single-turn | `grok_help.txt` |
| `/quit` | WORKS; returned to zsh | `rendered/exit_quit.txt`, `spikes/exit_quit_pane.txt` |
| `/exit` | WORKS; returned to zsh | `rendered/exit_exit.txt`, `spikes/exit_exit_pane.txt` |
| Ctrl-D | DID NOT exit in 3 seconds | `spikes/exit_ctrl_d_pane.txt` |
| Ctrl-C / Ctrl-C twice | DID NOT exit in 3 seconds | `spikes/exit_ctrl_c_pane.txt`, `spikes/exit_ctrl_c_twice_pane.txt` |
| Ctrl-Q | DID NOT exit in 3 seconds despite welcome footer | `spikes/exit_ctrl_q_pane.txt` |
| actual CAO E2E surface | `cao launch`; session operations are `cao session list/status/send`; no invented `cao session run` | `cao_help.txt`, `cao_launch_help.txt`, `cao_session_help.txt` |

The root TUI help also exposes `--permission-mode` values including `plan`,
and `--no-alt-screen`; these are recorded in the raw help capture for later
implementation decisions.
