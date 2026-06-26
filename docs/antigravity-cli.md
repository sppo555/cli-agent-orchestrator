# Antigravity CLI (`agy`) provider

`agy` is Google's successor to the Gemini CLI (Gemini CLI shut down 2026-06-18).
It reuses the `~/.gemini` config tree and shares the Ink-style TUI lineage, so
this provider is modelled on `gemini_cli.py` with agy's actual flags.

## Launch

```
agy --dangerously-skip-permissions [--model <M>] -i "<role ack>"
```

The agent's system prompt is written to a per-terminal `GEMINI.md` inside an
isolated workspace (`~/.cache/cao/agy-workspaces/<terminal_id>/`), and the
launch `cd`s into that workspace so concurrent terminals never clobber each
other's `GEMINI.md` and the user's real file is never touched.

## Status detection — why it does NOT hit the codex false-COMPLETED bug

agy is an Ink/TUI app that repaints in place and keeps an always-present `>`
input box and a spinner — exactly the shape that caused the
[#287](https://github.com/awslabs/cli-agent-orchestrator/issues/287) /
[#293](https://github.com/awslabs/cli-agent-orchestrator/pull/293) class of bug,
where on the **raw pipe-pane stream** the spinner footer gets shredded across
repaints and an always-rendered idle hint reads as COMPLETED ~60-75s into a
task (handoff then returns a half-done result and deletes the terminal).

This provider avoids that by design:

| | codex (pre-fix, raw) | agy (this provider) |
|---|---|---|
| Detection source | raw byte stream | pyte composited screen (`supports_screen_detection = True`) |
| "Working" signal | spinner (shredded on raw stream) | status bar `esc to cancel` and/or `Generating…` spinner, **working wins** |
| "Completed" signal | always-rendered prompt hint (false positive) | status bar `? for shortcuts` **plus** both a query line and a response body |
| ~60-75s false COMPLETED | yes | no (by design) |

The single reliable discriminator on a composited frame is agy's bottom status
bar: `esc to cancel` ⇒ working, `? for shortcuts` ⇒ idle.

## ⚠️ Recalibration caveat

The TUI patterns are **calibrated against agy 1.0.10**. If a future agy release
changes the status-bar strings or spinner text, status detection will break
(false IDLE/COMPLETED or stuck PROCESSING). Re-capture a live agy screen and
update these regexes in `providers/antigravity_cli.py`:

- `AGY_WORKING_FOOTER` — currently `esc to cancel`
- `AGY_IDLE_FOOTER` — currently `? for shortcuts`
- `AGY_SPINNER` — currently `Generating…` / `Generating...`
- `AGY_PROMPT_LINE` / `AGY_QUERY_LINE` — the `>` input box / submitted query

Also note: this detector has not yet been validated end-to-end through a real
supervisor→agy handoff (only against a static screen capture). Confirm with a
real handoff after the first deploy.

## Not yet implemented (MVP scope)

- MCP injection (agy uses `~/.gemini/config/mcp_config.json`; not needed for the
  output-scraping handoff path).
- Policy-Engine tool restriction — agy runs with `--dangerously-skip-permissions`,
  so the `tool_mapping.py` `antigravity_cli` entry exists only to keep
  `get_disallowed_tools` from `KeyError`-ing; it is not enforced.
