import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.services.structured_worker import (
    StructuredWorkerError,
    run_structured_worker_step,
)


class _CodexCompletedProcess:
    returncode = 0

    async def communicate(self, input=None):
        assert input is None
        return (
            b'{"type":"item.completed","item":{"type":"agent_message","text":"structured answer"}}\n'
            b'{"type":"turn.completed","usage":{"input_tokens":40,"output_tokens":12}}\n',
            b"",
        )


def test_codex_structured_worker_uses_jsonl_and_native_usage():
    process = _CodexCompletedProcess()
    with (
        patch(
            "cli_agent_orchestrator.services.structured_worker.CodexProvider.build_structured_command",
            return_value=["codex", "exec", "--json", "--ephemeral"],
        ),
        patch(
            "cli_agent_orchestrator.services.structured_worker.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=process),
        ) as spawn,
        patch(
            "cli_agent_orchestrator.services.structured_worker.persist_worker_token_usage"
        ) as persist,
    ):
        result = asyncio.run(run_structured_worker_step("codex", "developer", "do it"))

    assert result.status == TerminalStatus.COMPLETED
    assert result.last_message == "structured answer"
    assert result.token_usage.estimated is False
    assert result.token_usage.total_tokens == 52
    assert spawn.await_args.args[:3] == ("codex", "exec", "--json")
    assert spawn.await_args.args[-1] == "do it"
    assert persist.call_args.kwargs["usage"].estimated is False


class _ClaudeCompletedProcess:
    returncode = 0

    async def communicate(self, input=None):
        assert input is None
        return (
            b'{"type":"result","subtype":"success","result":"claude answer",'
            b'"usage":{"input_tokens":24,"output_tokens":8}}\n',
            b"",
        )


def test_claude_structured_worker_uses_json_result_and_native_usage():
    process = _ClaudeCompletedProcess()
    with (
        patch(
            "cli_agent_orchestrator.services.structured_worker.ClaudeCodeProvider.build_structured_command",
            return_value=["claude", "-p", "--output-format", "json"],
        ),
        patch(
            "cli_agent_orchestrator.services.structured_worker.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=process),
        ) as spawn,
        patch(
            "cli_agent_orchestrator.services.structured_worker.persist_worker_token_usage"
        ) as persist,
    ):
        result = asyncio.run(run_structured_worker_step("claude_code", "developer", "do it"))

    assert result.status == TerminalStatus.COMPLETED
    assert result.last_message == "claude answer"
    assert result.token_usage.estimated is False
    assert result.token_usage.total_tokens == 32
    assert spawn.await_args.args[:4] == ("claude", "-p", "--output-format", "json")
    assert spawn.await_args.args[-1] == "do it"
    assert persist.call_args.kwargs["usage"].estimated is False


def test_structured_worker_rejects_providers_without_a_structured_contract():
    with pytest.raises(StructuredWorkerError, match="not enabled"):
        asyncio.run(run_structured_worker_step("kiro_cli", "developer", "do it"))
