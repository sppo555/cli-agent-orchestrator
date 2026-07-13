import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.services.structured_worker import (
    StructuredWorkerError,
    run_structured_worker_step,
)


class _CompletedProcess:
    returncode = 0

    async def communicate(self, input=None):
        assert input == b"do it"
        return (
            b'{"type":"item.completed","item":{"type":"agent_message","text":"structured answer"}}\n'
            b'{"type":"turn.completed","usage":{"input_tokens":40,"output_tokens":12}}\n',
            b"",
        )


def test_codex_structured_worker_uses_jsonl_and_native_usage():
    process = _CompletedProcess()
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
    assert persist.call_args.kwargs["usage"].estimated is False


def test_structured_worker_rejects_providers_without_a_structured_contract():
    with pytest.raises(StructuredWorkerError, match="not enabled"):
        asyncio.run(run_structured_worker_step("claude_code", "developer", "do it"))
