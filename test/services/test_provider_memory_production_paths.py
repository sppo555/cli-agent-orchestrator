"""Production call-path coverage for core-owned provider memory preparation."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from cli_agent_orchestrator.models.agent_profile import AgentProfile
from cli_agent_orchestrator.models.flow import Flow
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.plugins.builtin.claude_code_memory import (
    BEGIN_MARKER as CLAUDE_BEGIN,
)
from cli_agent_orchestrator.plugins.builtin.claude_code_memory import (
    END_MARKER as CLAUDE_END,
)
from cli_agent_orchestrator.plugins.builtin.codex_memory import BEGIN_MARKER as CODEX_BEGIN
from cli_agent_orchestrator.plugins.builtin.codex_memory import END_MARKER as CODEX_END
from cli_agent_orchestrator.services import agent_step, flow_service, session_service
from cli_agent_orchestrator.services import terminal_service


@pytest.mark.asyncio
@pytest.mark.parametrize("call_path", ["direct", "session", "flow", "agent-step"])
@pytest.mark.parametrize(
    ("provider_name", "module_name", "relative_target", "markers"),
    [
        ("codex", "codex_memory", Path("AGENTS.md"), (CODEX_BEGIN, CODEX_END)),
        (
            "claude_code",
            "claude_code_memory",
            Path(".claude/CLAUDE.md"),
            (CLAUDE_BEGIN, CLAUDE_END),
        ),
        ("kiro_cli", "kiro_cli_memory", Path(".kiro/steering/cao-memory.md"), None),
    ],
)
async def test_protected_production_path_prepares_before_first_provider_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    call_path: str,
    provider_name: str,
    module_name: str,
    relative_target: Path,
    markers: tuple[str, str] | None,
) -> None:
    """All production entry paths share the registry-independent core barrier."""

    project_dir = tmp_path / "project"
    target = project_dir / relative_target
    target.parent.mkdir(parents=True, exist_ok=True)
    stale = "legacy production-path pollution"
    if markers:
        target.write_text(
            f"user-before\n{markers[0]}\n{stale}\n{markers[1]}\nuser-after\n",
            encoding="utf-8",
        )
    else:
        target.write_text(stale, encoding="utf-8")

    memory = MagicMock()
    memory.get_memory_context_for_terminal.return_value = (
        "<cao-memory>fresh scoped context</cao-memory>"
    )
    monkeypatch.setattr(
        f"cli_agent_orchestrator.plugins.builtin.{module_name}.MemoryService",
        lambda: memory,
    )

    backend = MagicMock()
    backend.session_exists.return_value = False
    backend.supports_event_inbox.return_value = True
    backend.get_pane_working_directory.return_value = str(project_dir)
    monkeypatch.setattr("cli_agent_orchestrator.backends.registry._backend", backend)
    monkeypatch.setattr(terminal_service, "generate_terminal_id", lambda: "terminal-production")
    monkeypatch.setattr(
        terminal_service, "generate_window_name", lambda _agent: "developer-production"
    )
    monkeypatch.setattr(
        terminal_service,
        "load_agent_profile",
        lambda _agent: AgentProfile(name="developer", description="Dev"),
    )
    monkeypatch.setattr(terminal_service, "db_create_terminal", lambda *_a, **_k: None)
    monkeypatch.setattr(terminal_service, "db_delete_terminal", lambda *_a, **_k: True)
    monkeypatch.setattr(terminal_service, "get_herdr_inbox_service", lambda: None)

    first_loaded: list[str] = []

    async def initialize() -> None:
        first_loaded.append(target.read_text(encoding="utf-8"))

    provider = MagicMock()
    provider.initialize = AsyncMock(side_effect=initialize)
    provider.shell_baseline = None
    manager = MagicMock()
    manager.create_provider.return_value = provider
    monkeypatch.setattr(terminal_service, "provider_manager", manager)

    if call_path == "direct":
        await terminal_service.create_terminal(
            provider=provider_name,
            agent_profile="developer",
            session_name="direct-production",
            new_session=True,
            working_directory=str(project_dir),
            allowed_tools=["*"],
        )
    elif call_path == "session":
        await session_service.create_session(
            provider=provider_name,
            agent_profile="developer",
            session_name="session-production",
            working_directory=str(project_dir),
            allowed_tools=["*"],
            registry=None,
        )
    elif call_path == "flow":
        flow_file = project_dir / "flow.md"
        flow_file.write_text("---\n---\nflow prompt\n", encoding="utf-8")
        flow = Flow(
            name="memory-production",
            file_path=str(flow_file),
            schedule="* * * * *",
            agent_profile="developer",
            provider=provider_name,
            script="",
            enabled=True,
        )
        monkeypatch.setattr(flow_service, "get_flow", lambda _name: flow)
        monkeypatch.setattr(flow_service, "db_update_flow_run_times", lambda *_a, **_k: None)
        monkeypatch.setattr(flow_service, "send_input", lambda *_a, **_k: None)
        assert await flow_service.execute_flow(flow.name) is True
    else:
        monkeypatch.setattr(agent_step, "wait_until_status", AsyncMock(return_value=True))
        monkeypatch.setattr(terminal_service, "send_input", lambda *_a, **_k: None)
        monkeypatch.setattr(terminal_service, "get_output", lambda *_a, **_k: "done")
        monkeypatch.setattr(
            agent_step.status_monitor, "get_status", lambda _terminal_id: TerminalStatus.COMPLETED
        )
        await agent_step.run_agent_step(
            provider=provider_name,
            agent="developer",
            prompt="work",
            working_directory=str(project_dir),
            allowed_tools=["*"],
            registry=None,
            teardown=False,
        )

    manager.create_provider.assert_called_once()
    assert len(first_loaded) == 1
    assert stale not in first_loaded[0]
    assert "fresh scoped context" in first_loaded[0]
