"""Grok CLI provider.

This adapter drives Grok's persistent interactive TUI.  It intentionally
supports lifecycle only: Grok 0.2.x has no verified, per-process mechanism for
forwarding ``CAO_TERMINAL_ID`` to MCP subprocesses without mutating shared user
or project configuration.  The provider therefore never writes Grok config or
claims CAO orchestration support.
"""

import logging
import re
import shlex
import shutil
import subprocess
import textwrap
from typing import List, Optional

from cli_agent_orchestrator.backends.registry import get_backend
from cli_agent_orchestrator.constants import SECURITY_PROMPT
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.providers.base import BaseProvider, IncompleteOutputError
from cli_agent_orchestrator.services.settings_service import get_server_settings
from cli_agent_orchestrator.utils.agent_profiles import load_agent_profile
from cli_agent_orchestrator.utils.terminal import wait_for_shell, wait_until_status
from cli_agent_orchestrator.utils.text import strip_terminal_escapes
from cli_agent_orchestrator.utils.tool_mapping import get_disallowed_tools

logger = logging.getLogger(__name__)

_GROK_VERSION_CACHE: dict[str, str | None] = {}

# Keep well below the smallest common ARG_MAX after accounting for the parent
# environment.  Grok 0.2.x has no rules-file option, so oversized inline rules
# must fail rather than be truncated.
MAX_COMMAND_BYTES = 64 * 1024

STARTUP_GUARD = (
    "Acknowledge your role briefly, then wait for a concrete task. "
    "Do not inspect, edit, execute, or call tools during startup."
)

READY_INPUT_COMPACT_PATTERN = r"[│|]❯"
READY_MODEL_COMPACT_PATTERN = r"Grok\d+(?:\.\d+)*(?:\([^)]+\))?"
PROCESSING_PATTERN = (
    r"(?:Starting session|Responding|Thinking|Working|Generating)[^\n]*(?:\.\.\.|…)"
    r"|Ctrl\+c:cancel|\[stop\]"
)
WAITING_PATTERN = (
    r"(?:↑/↓\s*(?:to )?[Nn]avigate)|(?:\[\s*y\s*/\s*n\s*\])"
    r"|(?:Allow once|Allow always|Do you want to (?:allow|run|proceed))"
    r"|(?:enter Toggle|enter Confirm)|(?:Press Enter to continue)"
)
ERROR_PATTERN = (
    r"(?:^|\n)\s*(?:Error:|ERROR:|panic:|Traceback \(most recent call last\):)"
    r"|(?:not logged in|authentication (?:failed|required)|invalid credentials)"
)
QUERY_PATTERN = r"^\s*❯\s+\S"
QUESTION_BEFORE_COMPLETION_PATTERN = r"\?\s*(?:Turn completed in|Worked for)\b"

_THOUGHT_PATTERN = r"^\s*(?:◆\s*Thought|❙\s*◆|◆\s*(?:Run|Read|Write|Edit|Search))"
_COMPLETION_PATTERN = r"^\s*(?:Turn completed in|Worked for)\b"
_INPUT_BOX_PATTERN = r"^\s*[│|]\s*❯\s*(?:[│|]|$)"
_CHROME_PATTERN = (
    r"(?:Shift\+Tab:mode|Ctrl\+[+;xcoq]:|Click here to Upgrade|Grok Build Beta)"
    r"|(?:Starting session|Responding|Thinking|Working|Generating)[^\n]*(?:\.\.\.|…)"
)
_ANSI_PROMPT_BACKGROUND = "\x1b[48;2;36;36;36m"
_ANSI_CODE_BACKGROUND = "\x1b[48;2;28;28;28m"
_ANSI_HEADING_STYLE = "\x1b[1m\x1b[38;2;122;162;247m"


def _probe_grok_version(binary: str) -> str | None:
    """Return the Grok version once per resolved binary path."""
    if binary in _GROK_VERSION_CACHE:
        return _GROK_VERSION_CACHE[binary]
    try:
        result = subprocess.run(
            [binary, "version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        version = result.stdout.strip().splitlines()[0] if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        version = None
    _GROK_VERSION_CACHE[binary] = version
    return version


class GrokCliProvider(BaseProvider):
    """Persistent interactive Grok TUI provider (lifecycle-only)."""

    supports_screen_detection = True

    def __init__(
        self,
        terminal_id: str,
        session_name: str,
        window_name: str,
        agent_profile: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
        model: Optional[str] = None,
        skill_prompt: Optional[str] = None,
    ) -> None:
        super().__init__(terminal_id, session_name, window_name, allowed_tools, skill_prompt)
        self._agent_profile = agent_profile
        self._model = model
        self._initialized = False
        self._turns = 0

    @property
    def paste_enter_count(self) -> int:
        """Grok submits bracketed paste with one Enter."""
        return 1

    @property
    def paste_submit_delay(self) -> float:
        """Phase 0 required a longer post-paste settle interval."""
        return 0.8

    @property
    def blocks_orchestrated_input_while_waiting_user_answer(self) -> bool:
        return True

    def _load_profile(self):
        if not self._agent_profile:
            return None
        try:
            return load_agent_profile(self._agent_profile)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load agent profile '{self._agent_profile}': {exc}"
            ) from exc

    def _build_grok_command(self) -> str:
        """Build a shell-escaped Grok TUI command without changing config."""
        binary = shutil.which("grok")
        if not binary:
            raise RuntimeError("Grok CLI not found: 'grok' is not on PATH")

        profile = self._load_profile()
        command = [binary, "--always-approve"]

        profile_model = profile.model if profile is not None else None
        model = profile_model or self._model
        if model:
            command.extend(["--model", model])

        # Upstream AgentProfile at the implementation base has no effort field.
        # Defensive access keeps customized forks compatible.
        effort = getattr(profile, "effort", None) if profile is not None else None
        if effort:
            command.extend(["--effort", effort])

        profile_rules = (profile.system_prompt or "") if profile is not None else ""
        rules = self._apply_skill_prompt(profile_rules)

        restricted = bool(self._allowed_tools and "*" not in self._allowed_tools)
        security_rules_bytes = 0
        if restricted:
            rules = f"{rules}\n\n{SECURITY_PROMPT}".strip()
            security_rules_bytes = len(SECURITY_PROMPT.encode("utf-8"))
            for native_tool in get_disallowed_tools("grok_cli", self._allowed_tools or []):
                command.extend(["--deny", native_tool])
            if "execute_bash" not in (self._allowed_tools or []):
                command.append("--no-subagents")

        if profile is not None and profile.mcpServers:
            logger.warning(
                "grok_cli does not copy profile MCP servers or enable CAO orchestration; "
                "configure non-CAO servers in Grok separately"
            )
        if self._allowed_tools and "@cao-mcp-server" in self._allowed_tools:
            logger.warning(
                "grok_cli lifecycle-only mode ignores the @cao-mcp-server capability marker; "
                "assign, handoff, and send_message are not supported"
            )

        guarded_rules = f"{rules}\n\n{STARTUP_GUARD}".strip()
        command.extend(["--rules", guarded_rules])

        rendered = shlex.join(command)
        rendered_bytes = len(rendered.encode("utf-8"))
        if rendered_bytes > MAX_COMMAND_BYTES:
            raise ValueError(
                "Grok command exceeds the safe inline-rules limit "
                f"({rendered_bytes} > {MAX_COMMAND_BYTES} bytes); "
                f"profile_rules={len(profile_rules.encode('utf-8'))} bytes, "
                f"skill_prompt={len((self._skill_prompt or '').encode('utf-8'))} bytes, "
                f"security_rules={security_rules_bytes} bytes, "
                f"startup_guard={len(STARTUP_GUARD.encode('utf-8'))} bytes"
            )
        return rendered

    async def initialize(self) -> bool:
        """Start Grok after capturing the shell baseline and wait for ready."""
        init_timeout = float(get_server_settings()["provider_init_timeout"])
        if not await wait_for_shell(self.terminal_id, timeout=init_timeout):
            raise TimeoutError(f"Shell initialization timed out after {init_timeout:g}s")

        backend = get_backend()
        self.shell_baseline = backend.get_pane_current_command(self.session_name, self.window_name)
        command = self._build_grok_command()
        binary = shutil.which("grok")
        if binary:
            logger.info("Grok CLI binary=%s version=%s", binary, _probe_grok_version(binary))

        from cli_agent_orchestrator.services.status_monitor import status_monitor

        status_monitor.notify_input_sent(self.terminal_id)
        backend.send_keys(self.session_name, self.window_name, command)
        if not await wait_until_status(
            self.terminal_id,
            {TerminalStatus.IDLE, TerminalStatus.COMPLETED},
            timeout=init_timeout,
        ):
            raise TimeoutError(f"Grok CLI initialization timed out after {init_timeout:g}s")
        self._initialized = True
        return True

    def _shell_is_active(self) -> bool:
        if not self._initialized or not self.shell_baseline:
            return False
        try:
            current = get_backend().get_pane_current_command(self.session_name, self.window_name)
        except Exception:
            return False
        return current == self.shell_baseline

    def _detect_status(self, text: str) -> TerminalStatus:
        if not text.strip():
            return TerminalStatus.UNKNOWN
        tail = text[-16384:]
        compact_tail = re.sub(r"\s+", "", tail)

        completion_matches = list(
            re.finditer(r"(?:Turn completed in|Worked for)\b", tail, re.IGNORECASE)
        )
        processing_matches = list(re.finditer(PROCESSING_PATTERN, tail, re.IGNORECASE))
        waiting_matches = list(re.finditer(WAITING_PATTERN, tail, re.IGNORECASE))
        error_matches = list(re.finditer(ERROR_PATTERN, tail, re.IGNORECASE | re.MULTILINE))
        question_matches = list(
            re.finditer(QUESTION_BEFORE_COMPLETION_PATTERN, tail, re.IGNORECASE)
        )
        last_completion = completion_matches[-1].end() if completion_matches else -1
        last_processing = processing_matches[-1].end() if processing_matches else -1
        last_waiting = waiting_matches[-1].end() if waiting_matches else -1
        last_error = error_matches[-1].end() if error_matches else -1
        last_question = question_matches[-1].end() if question_matches else -1

        # Ignore historical dialog/error/spinner text once a newer completion
        # boundary has been drawn.  Active Grok processing surfaces either have
        # no completion yet or redraw a spinner/cancel marker after the prior
        # turn's completion.
        if last_waiting > last_completion:
            return TerminalStatus.WAITING_USER_ANSWER
        if last_error > last_completion:
            return TerminalStatus.ERROR
        if last_processing > last_completion:
            return TerminalStatus.PROCESSING

        if last_question != -1 and last_question == last_completion:
            return TerminalStatus.WAITING_USER_ANSWER

        ready = bool(
            re.search(READY_INPUT_COMPACT_PATTERN, compact_tail)
            and re.search(READY_MODEL_COMPACT_PATTERN, compact_tail, re.IGNORECASE)
        )
        if ready:
            return TerminalStatus.COMPLETED if self._turns > 0 else TerminalStatus.IDLE
        if self._initialized and self._task_dispatched:
            return TerminalStatus.PROCESSING
        return TerminalStatus.UNKNOWN

    def get_status(self, buffer: str) -> TerminalStatus:
        native = self._resolve_native_status()
        if native is not None:
            return native
        if self._shell_is_active():
            return TerminalStatus.ERROR
        if not buffer:
            return TerminalStatus.UNKNOWN
        return self._detect_status(strip_terminal_escapes(buffer))

    def get_status_from_screen(self, screen_lines: List[str]) -> TerminalStatus:
        native = self._resolve_native_status()
        if native is not None:
            return native
        if self._shell_is_active():
            return TerminalStatus.ERROR
        rows = [line.rstrip() for line in screen_lines]
        return self._detect_status("\n".join(rows))

    def extract_last_message_from_script(self, script_output: str) -> str:
        """Extract the response following the last non-empty Grok prompt."""
        clean = strip_terminal_escapes(script_output)
        lines = clean.splitlines()
        raw_lines = script_output.splitlines()
        query_indices = [
            index for index, line in enumerate(lines) if re.search(QUERY_PATTERN, line)
        ]
        if not query_indices:
            raise ValueError("No Grok CLI user prompt boundary found")

        # A real Grok echoed prompt carries the calibrated input-background
        # style.  If one is present, discard older unstyled candidates such as
        # ``❯ grok --always-approve`` from shell scrollback, while retaining any
        # later candidate so assistant output beginning with ❯ still fails the
        # ambiguity check below.
        ansi_query_indices = [
            index for index in query_indices if _ANSI_PROMPT_BACKGROUND in raw_lines[index]
        ]
        if ansi_query_indices:
            last_ansi_query = ansi_query_indices[-1]
            query_indices = [index for index in query_indices if index >= last_ansi_query]

        # A plain assistant/code line beginning with ❯ is indistinguishable
        # from an unstyled prompt unless the prior turn has already completed.
        # Fail safely instead of silently selecting the wrong boundary.
        for previous, candidate in zip(query_indices, query_indices[1:]):
            between = "\n".join(lines[previous + 1 : candidate])
            if not re.search(_COMPLETION_PATTERN, between, re.MULTILINE):
                raise ValueError("Ambiguous Grok CLI user prompt boundary")

        query_index = query_indices[-1]
        body_start = query_index + 1
        ansi_prompt = _ANSI_PROMPT_BACKGROUND in raw_lines[query_index]

        turn_text = "\n".join(lines[query_index + 1 :])
        completion_matches = list(
            re.finditer(_COMPLETION_PATTERN, turn_text, re.MULTILINE | re.IGNORECASE)
        )
        if not completion_matches:
            raise IncompleteOutputError("Grok CLI response has no completion boundary")
        processing_matches = list(re.finditer(PROCESSING_PATTERN, turn_text, re.IGNORECASE))
        if processing_matches and (processing_matches[-1].end() > completion_matches[-1].end()):
            raise IncompleteOutputError("Grok CLI response is still processing")

        if ansi_prompt:
            while body_start < len(raw_lines) and (
                _ANSI_PROMPT_BACKGROUND in raw_lines[body_start]
            ):
                body_start += 1
            while body_start < len(lines) and not lines[body_start].strip():
                body_start += 1
        elif body_start < len(lines) and not lines[body_start].strip():
            while body_start < len(lines) and not lines[body_start].strip():
                body_start += 1
        elif body_start < len(lines) and not re.search(_THOUGHT_PATTERN, lines[body_start]):
            # A wrapped plain-text prompt is safe to skip only when its blank
            # separator is followed by a recognizable activity boundary.
            separator = next(
                (
                    index
                    for index in range(body_start, min(body_start + 8, len(lines)))
                    if not lines[index].strip()
                ),
                None,
            )
            after_separator = separator + 1 if separator is not None else None
            while (
                after_separator is not None
                and after_separator < len(lines)
                and not lines[after_separator].strip()
            ):
                after_separator += 1
            if (
                after_separator is None
                or after_separator >= len(lines)
                or not re.search(_THOUGHT_PATTERN, lines[after_separator])
            ):
                raise ValueError("Ambiguous wrapped Grok CLI prompt boundary")
            body_start = after_separator

        body: list[str] = []
        in_code_block = False
        for index, line in enumerate(lines[body_start:], start=body_start):
            if re.search(_COMPLETION_PATTERN, line) or re.search(_INPUT_BOX_PATTERN, line):
                break
            if re.search(_THOUGHT_PATTERN, line) or re.search(_CHROME_PATTERN, line):
                continue
            if re.match(r"^\s*[╭╰─]{8,}", line):
                continue
            cleaned = re.sub(r"\s{2,}\d{1,2}:\d{2}\s+[AP]M\s*$", "", line.rstrip())
            cleaned = re.sub(r"\s+█\s*$", "", cleaned)
            raw_line = raw_lines[index] if index < len(raw_lines) else ""
            is_code_line = _ANSI_CODE_BACKGROUND in raw_line
            if is_code_line and not in_code_block:
                body.append("```")
                in_code_block = True
            elif not is_code_line and in_code_block:
                body.append("```")
                in_code_block = False
            if _ANSI_HEADING_STYLE in raw_line and cleaned.strip():
                cleaned = f"## {cleaned.strip()}"
            body.append(cleaned)

        if in_code_block:
            body.append("```")

        response = textwrap.dedent("\n".join(body)).strip()
        response = re.sub(
            r"(```[^\n]*\n)(.*?)(\n```)",
            lambda match: (match.group(1) + textwrap.dedent(match.group(2)) + match.group(3)),
            response,
            flags=re.DOTALL,
        )
        response = response.rstrip()
        if not response:
            raise ValueError("Empty Grok CLI response after user prompt")
        return response

    def exit_cli(self) -> str:
        return "/quit"

    def cleanup(self) -> None:
        self._initialized = False

    def mark_input_received(self) -> None:
        super().mark_input_received()
        self._turns += 1
