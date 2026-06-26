"""Antigravity CLI (``agy``) provider.

Antigravity CLI is Google's successor to Gemini CLI (Gemini CLI shut down
2026-06-18). Command name is ``agy``. This provider is modelled on
``gemini_cli.py`` — agy reuses the ``~/.gemini`` config tree and shares the
Ink-style TUI lineage — but with agy's actual flags and a pyte-calibrated
status detector (see status notes below).

Scope (MVP, calibrated against agy 1.0.10):
  * Launch:  agy --dangerously-skip-permissions [--model M] -i "<role ack>"
             system prompt written to a per-terminal GEMINI.md workspace.
  * Status:  pyte rendered-screen detection. agy's bottom status bar is the
             reliable discriminator — ``esc to cancel`` (working) vs
             ``? for shortcuts`` (idle); a ``Generating…`` spinner also means
             working. This avoids the raw-stream false-COMPLETED class that bit
             codex/gemini.
  * NOT yet: MCP injection (agy uses ~/.gemini/config/mcp_config.json; not
             needed for handoff which scrapes output) and Policy-Engine tool
             restriction (agy runs with --dangerously-skip-permissions).
"""

import asyncio
import logging
import re
import shlex
import time
from pathlib import Path
from typing import List, Optional

from cli_agent_orchestrator.backends.registry import get_backend
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.providers.base import BaseProvider
from cli_agent_orchestrator.utils.agent_profiles import load_agent_profile
from cli_agent_orchestrator.utils.terminal import wait_for_shell
from cli_agent_orchestrator.utils.text import strip_terminal_escapes

logger = logging.getLogger(__name__)

# Per-terminal workspace parent (isolates each terminal's GEMINI.md).
AGY_WORKSPACES_DIR = Path.home() / ".cache" / "cao" / "agy-workspaces"

# --- TUI patterns (calibrated against a live agy 1.0.10 capture) -----------
# Working: status bar shows "esc to cancel", and/or a "Generating…" spinner.
AGY_WORKING_FOOTER = re.compile(r"esc to cancel")
AGY_SPINNER = re.compile(r"Generating\.\.\.|Generating…")
# Idle: status bar shows "? for shortcuts".
AGY_IDLE_FOOTER = re.compile(r"\?\s+for shortcuts")
# Empty input box prompt line ("> " alone between ──── rails).
AGY_PROMPT_LINE = re.compile(r"^\s*>\s*$")
# A submitted query line ("> <text>").
AGY_QUERY_LINE = re.compile(r"^\s*>\s+\S")
ERROR_PATTERN = re.compile(r"^(?:Error:|ERROR:|panic:|Traceback)", re.MULTILINE)
IDLE_TAIL_LINES = 6


class ProviderError(Exception):
    pass


class AntigravityCliProvider(BaseProvider):
    """Provider for the Antigravity CLI (``agy``) coding agent."""

    # Calibrated pyte detector below — opt into the screen path.
    supports_screen_detection = True

    def __init__(
        self,
        terminal_id: str,
        session_name: str,
        window_name: str,
        agent_profile: Optional[str] = None,
        allowed_tools: Optional[list] = None,
        skill_prompt: Optional[str] = None,
    ):
        super().__init__(terminal_id, session_name, window_name, allowed_tools, skill_prompt)
        self._initialized = False
        self._agent_profile = agent_profile
        # -i produces a first response before accepting input; mirror gemini's
        # post-init handling so handoff (which waits for IDLE) isn't tricked by
        # the init response into thinking a real task already COMPLETED.
        self._uses_prompt_interactive = False
        self._received_input_after_init = False
        self._workspace: Optional[Path] = None

    # ------------------------------------------------------------------ launch
    def _build_command(self) -> str:
        command_parts = ["agy", "--dangerously-skip-permissions"]

        if self._agent_profile is not None:
            try:
                profile = load_agent_profile(self._agent_profile)
            except Exception as e:
                raise ProviderError(f"Failed to load agent profile '{self._agent_profile}': {e}")

            if profile.model:
                command_parts.extend(["--model", profile.model])

            system_prompt = profile.system_prompt or ""
            system_prompt = self._apply_skill_prompt(system_prompt)
            if system_prompt:
                # Isolate per-terminal GEMINI.md so concurrent terminals don't
                # clobber each other and we never touch the user's real file.
                workspace = AGY_WORKSPACES_DIR / self.terminal_id
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "GEMINI.md").write_text(system_prompt, encoding="utf-8")
                self._workspace = workspace

                # Automatically trust this dynamic workspace path in settings.json
                # to bypass agy's per-workspace trust prompt (agy only matches
                # exact paths, and each terminal gets a fresh random workspace).
                try:
                    import json

                    settings_path = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
                    if settings_path.exists():
                        settings_data = json.loads(settings_path.read_text(encoding="utf-8"))
                        settings_data.setdefault("trustedWorkspaces", [])
                        ws_path_str = str(workspace)
                        if ws_path_str not in settings_data["trustedWorkspaces"]:
                            settings_data["trustedWorkspaces"].append(ws_path_str)
                            settings_path.write_text(
                                json.dumps(settings_data, indent=2), encoding="utf-8"
                            )
                except Exception as e:
                    logger.warning(f"Failed to auto-trust workspace: {e}")

                role_name = profile.name or "agent"
                command_parts.extend(
                    [
                        "-i",
                        f"You are the {role_name}. Your instructions are in GEMINI.md. "
                        "Acknowledge your role in one sentence, then wait for tasks.",
                    ]
                )
                self._uses_prompt_interactive = True

        launch = shlex.join(command_parts)
        if self._workspace is not None:
            return f"cd {shlex.quote(str(self._workspace))} && {launch}"
        return launch

    async def initialize(self) -> bool:
        from cli_agent_orchestrator.services.status_monitor import status_monitor

        if not await wait_for_shell(self.terminal_id, timeout=10.0):
            raise TimeoutError("Shell initialization timed out after 10 seconds")

        # Shell warm-up echo (same reason as gemini: Ink TUIs can exit silently
        # in a not-yet-settled tmux shell).
        marker = "CAO_SHELL_READY"
        status_monitor.notify_input_sent(self.terminal_id)
        get_backend().send_keys(self.session_name, self.window_name, f"echo {marker}")
        t0 = time.time()
        while time.time() - t0 < 15.0:
            out = get_backend().get_history(self.session_name, self.window_name)
            if out and marker in out:
                break
            await asyncio.sleep(0.5)
        await asyncio.sleep(2)

        command = self._build_command()
        status_monitor.notify_input_sent(self.terminal_id)
        get_backend().send_keys(self.session_name, self.window_name, command)

        target = (
            (TerminalStatus.COMPLETED,)
            if self._uses_prompt_interactive
            else (TerminalStatus.IDLE, TerminalStatus.COMPLETED)
        )
        t0 = time.time()
        status = TerminalStatus.UNKNOWN
        while time.time() - t0 < 240.0:
            status = status_monitor.get_status(self.terminal_id)
            if status in target:
                break
            await asyncio.sleep(1.0)
        else:
            raise TimeoutError(f"Antigravity CLI init timed out (last status: {status})")

        self._initialized = True
        return True

    def mark_input_received(self) -> None:
        self._received_input_after_init = True

    # ------------------------------------------------------------------ status
    def _classify(self, rows: List[str]) -> TerminalStatus:
        """Shared classification over clean (escape-free) non-empty rows."""
        if not rows:
            return TerminalStatus.UNKNOWN
        bottom = "\n".join(rows[-IDLE_TAIL_LINES:])
        wide = "\n".join(rows[-12:])

        # Working wins: status bar "esc to cancel" or a live "Generating…".
        if AGY_WORKING_FOOTER.search(bottom) or AGY_SPINNER.search(wide):
            return TerminalStatus.PROCESSING

        if AGY_IDLE_FOOTER.search(bottom):
            has_query = any(AGY_QUERY_LINE.search(ln) for ln in rows)
            # Body content between the query and the input box ⇒ a response.
            has_response = any(
                ln.strip()
                and not AGY_QUERY_LINE.search(ln)
                and not AGY_PROMPT_LINE.search(ln)
                and not re.search(r"─{8,}", ln)
                and not AGY_IDLE_FOOTER.search(ln)
                and "for shortcuts" not in ln
                for ln in rows[1:]
            )
            if has_query and has_response:
                # Post-init -i response is not a task completion — keep IDLE so
                # handoff (waits for IDLE) can send the real task.
                if (
                    self._initialized
                    and self._uses_prompt_interactive
                    and not self._received_input_after_init
                ):
                    return TerminalStatus.IDLE
                return TerminalStatus.COMPLETED
            return TerminalStatus.IDLE

        if ERROR_PATTERN.search("\n".join(rows)):
            return TerminalStatus.ERROR
        # No idle footer and not clearly working: assume still producing.
        return TerminalStatus.PROCESSING

    def get_status(self, output: str) -> TerminalStatus:
        if not output:
            return TerminalStatus.UNKNOWN
        clean = strip_terminal_escapes(output)
        rows = [ln.rstrip() for ln in clean.splitlines() if ln.strip()]
        return self._classify(rows)

    def get_status_from_screen(self, screen_lines: List[str]) -> TerminalStatus:
        """Detect status from a pyte-composited viewport (escape-free rows).

        agy's bottom status bar is the reliable discriminator on a composited
        frame: ``esc to cancel`` ⇒ working, ``? for shortcuts`` ⇒ idle. Same
        classification as get_status but on the clean rendered screen.
        """
        rows = [ln.rstrip() for ln in screen_lines if ln.strip()]
        return self._classify(rows)

    # -------------------------------------------------------------- extraction
    @property
    def extraction_retries(self) -> int:
        return 3

    def extract_last_message_from_script(self, script_output: str) -> str:
        """Best-effort: text between the last submitted query and the input box."""
        clean = strip_terminal_escapes(script_output)
        lines = clean.splitlines()
        # find last query line
        last_q = None
        for i, ln in enumerate(lines):
            if AGY_QUERY_LINE.search(ln):
                last_q = i
        if last_q is None:
            return ""
        body = []
        for ln in lines[last_q + 1:]:
            s = ln.rstrip()
            if not s.strip():
                continue
            if AGY_PROMPT_LINE.search(s) or re.search(r"─{8,}", s):
                break
            if AGY_IDLE_FOOTER.search(s) or AGY_WORKING_FOOTER.search(s) or "for shortcuts" in s:
                continue
            body.append(s.strip())
        return "\n".join(body).strip()

    def exit_cli(self) -> str:
        return "/quit"

    def cleanup(self) -> None:
        if self._workspace is not None:
            try:
                import shutil

                shutil.rmtree(self._workspace, ignore_errors=True)
            except Exception:
                pass

            # Remove the auto-trusted path from settings.json to prevent bloat.
            try:
                import json

                settings_path = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
                if settings_path.exists():
                    settings_data = json.loads(settings_path.read_text(encoding="utf-8"))
                    ws_path_str = str(self._workspace)
                    if (
                        "trustedWorkspaces" in settings_data
                        and ws_path_str in settings_data["trustedWorkspaces"]
                    ):
                        settings_data["trustedWorkspaces"].remove(ws_path_str)
                        settings_path.write_text(
                            json.dumps(settings_data, indent=2), encoding="utf-8"
                        )
            except Exception:
                pass
