"""Explicit structured worker execution.

The structured worker is deliberately separate from the interactive tmux
substrate. It launches a provider's machine-readable command, parses only its
stdout contract, and persists usage from that contract. Terminal scrollback,
session files, and rollout logs are not inputs to this path.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Optional

from cli_agent_orchestrator.models.terminal import AgentStepResult, TerminalStatus
from cli_agent_orchestrator.models.token_usage import TokenUsage
from cli_agent_orchestrator.providers.claude_code import ClaudeCodeProvider
from cli_agent_orchestrator.providers.codex import CodexProvider
from cli_agent_orchestrator.services.token_usage import (
    estimate_token_usage,
    persist_worker_token_usage,
    resolve_worker_configuration,
    resolve_worker_progress,
)
from cli_agent_orchestrator.services.token_usage_adapters import (
    extract_claude_code_last_message,
    extract_codex_last_message,
)
from cli_agent_orchestrator.services.token_usage_contract import extract_usage


class StructuredWorkerError(Exception):
    """The structured provider process failed before producing a result."""


def _structured_terminal_id() -> str:
    """Return an 8-hex synthetic id for the existing durable record schema."""

    return uuid.uuid4().hex[:8]


async def run_structured_worker_step(
    provider: str,
    agent: str,
    prompt: str,
    *,
    timeout: float = 600.0,
    working_directory: Optional[str] = None,
    allowed_tools: Optional[list[str]] = None,
    env_vars: Optional[dict[str, str]] = None,
    progress: Optional[str] = None,
) -> AgentStepResult:
    """Run one explicit structured worker step.

    Claude Code and Codex each use their provider-owned machine-readable
    stdout contract. The default interactive run_agent_step path is not called
    or modified.
    """

    if provider not in {"claude_code", "codex"}:
        raise StructuredWorkerError(
            f"structured worker mode is not enabled for provider '{provider}'"
        )
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    terminal_id = _structured_terminal_id()
    if provider == "codex":
        command_builder = CodexProvider(
            terminal_id=terminal_id,
            session_name="structured",
            window_name="structured",
            agent_profile=agent,
            allowed_tools=allowed_tools,
        )
        extract_last_message = extract_codex_last_message
    else:
        command_builder = ClaudeCodeProvider(
            terminal_id=terminal_id,
            session_name="structured",
            window_name="structured",
            agent_profile=agent,
            allowed_tools=allowed_tools,
        )
        extract_last_message = extract_claude_code_last_message

    try:
        command = command_builder.build_structured_command()
    except Exception:
        if isinstance(command_builder, ClaudeCodeProvider):
            command_builder.cleanup()
        raise
    environment = os.environ.copy()
    if env_vars:
        environment.update(env_vars)

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=working_directory,
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        if isinstance(command_builder, ClaudeCodeProvider):
            command_builder.cleanup()
        raise StructuredWorkerError(
            f"failed to start structured {provider} worker: {exc}"
        ) from exc

    try:
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=prompt.encode("utf-8")),
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise TimeoutError(
                f"structured {provider} worker timed out after {timeout}s"
            ) from exc
    finally:
        if isinstance(command_builder, ClaudeCodeProvider):
            command_builder.cleanup()

    raw_output = stdout.decode("utf-8", errors="replace")
    raw_stderr = stderr.decode("utf-8", errors="replace")
    if process.returncode != 0:
        detail = raw_stderr.strip().splitlines()[-1] if raw_stderr.strip() else "no stderr"
        raise StructuredWorkerError(
            f"structured {provider} worker exited with code {process.returncode}: {detail}"
        )

    last_message = extract_last_message(raw_output)
    model, effort = resolve_worker_configuration(provider, agent)
    progress = resolve_worker_progress(progress, prompt, last_message)
    native_usage = extract_usage(provider, raw_output, last_message)
    if native_usage is None:
        usage = estimate_token_usage(
            prompt,
            last_message,
            model=model,
            effort=effort,
            progress=progress,
        )
    else:
        usage = TokenUsage(
            input_tokens=native_usage.input_tokens,
            output_tokens=native_usage.output_tokens,
            total_tokens=native_usage.total_tokens,
            estimated=False,
            model=native_usage.model or model,
            effort=native_usage.effort or effort,
            progress=progress,
        )

    await asyncio.to_thread(
        persist_worker_token_usage,
        terminal_id=terminal_id,
        provider=provider,
        agent=agent,
        usage=usage,
        progress=progress,
        run_id=(env_vars or {}).get("CAO_WORKFLOW_RUN_ID"),
        step_id=(env_vars or {}).get("CAO_WORKFLOW_STEP_ID"),
    )
    return AgentStepResult(
        terminal_id=terminal_id,
        last_message=last_message,
        status=TerminalStatus.COMPLETED,
        token_usage=usage,
    )
