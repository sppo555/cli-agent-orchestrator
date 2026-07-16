"""Concurrent repo-shared provider file versus terminal-session isolation."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine

from cli_agent_orchestrator.clients.database import Base
from cli_agent_orchestrator.models.agent_profile import AgentProfile
from cli_agent_orchestrator.plugins.builtin.claude_code_memory import (
    BEGIN_MARKER as CLAUDE_BEGIN,
)
from cli_agent_orchestrator.plugins.builtin.claude_code_memory import (
    END_MARKER as CLAUDE_END,
)
from cli_agent_orchestrator.plugins.builtin.codex_memory import BEGIN_MARKER as CODEX_BEGIN
from cli_agent_orchestrator.plugins.builtin.codex_memory import END_MARKER as CODEX_END
from cli_agent_orchestrator.services.memory_service import MemoryService
from cli_agent_orchestrator.services import terminal_service


async def _seed_scoped_contexts(svc: MemoryService, project_dir: Path) -> dict[str, dict[str, str]]:
    contexts = {
        "terminal-a": {
            "cwd": str(project_dir),
            "session_name": "cao-session-a",
            "agent_profile": "developer",
            "caller_scope": "project",
        },
        "terminal-b": {
            "cwd": str(project_dir),
            "session_name": "cao-session-b",
            "agent_profile": "developer",
            "caller_scope": "project",
        },
    }
    await svc.store(
        content="private session alpha",
        scope="session",
        memory_type="project",
        key="session-alpha",
        terminal_context=contexts["terminal-a"],
    )
    await svc.store(
        content="private session beta",
        scope="session",
        memory_type="project",
        key="session-beta",
        terminal_context=contexts["terminal-b"],
    )
    await svc.store(
        content="common project memory",
        scope="project",
        memory_type="project",
        key="common-project",
        terminal_context=contexts["terminal-a"],
    )
    await svc.store(
        content="common global memory",
        scope="global",
        memory_type="reference",
        key="common-global",
    )
    return contexts


@pytest.mark.asyncio
@pytest.mark.parametrize("defer_init", [False, True])
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
async def test_concurrent_same_repo_terminals_never_share_session_memory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    defer_init: bool,
    provider_name: str,
    module_name: str,
    relative_target: Path,
    markers: tuple[str, str] | None,
) -> None:
    """Interleaved sync/assign-style deferred startup keeps session data private."""

    project_dir = tmp_path / "shared-project"
    project_dir.mkdir()
    target = project_dir / relative_target
    target.parent.mkdir(parents=True, exist_ok=True)
    if markers:
        target.write_text(
            f"user instructions\n{markers[0]}\nold shared data\n{markers[1]}\n",
            encoding="utf-8",
        )
    else:
        target.write_text("old shared data\n", encoding="utf-8")

    engine = create_engine(
        f"sqlite:///{tmp_path / 'memory.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    svc = MemoryService(base_dir=tmp_path / "memory", db_engine=engine)
    contexts = await _seed_scoped_contexts(svc, project_dir)
    monkeypatch.setattr(svc, "_get_terminal_context", contexts.get)
    monkeypatch.setattr(svc, "_find_context_manager_terminal", lambda _session: None)
    monkeypatch.setattr(
        f"cli_agent_orchestrator.plugins.builtin.{module_name}.MemoryService",
        lambda: svc,
    )

    backend = MagicMock()
    backend.session_exists.return_value = False
    backend.supports_event_inbox.return_value = True
    backend.get_pane_working_directory.return_value = str(project_dir)
    monkeypatch.setattr("cli_agent_orchestrator.backends.registry._backend", backend)
    terminal_ids = iter(["terminal-a", "terminal-b"])
    monkeypatch.setattr(terminal_service, "generate_terminal_id", lambda: next(terminal_ids))
    monkeypatch.setattr(terminal_service, "generate_window_name", lambda _agent: "developer-window")
    monkeypatch.setattr(
        terminal_service,
        "load_agent_profile",
        lambda _agent: AgentProfile(name="developer", description="Dev"),
    )
    monkeypatch.setattr(terminal_service, "db_create_terminal", lambda *_a, **_k: None)
    monkeypatch.setattr(terminal_service, "db_delete_terminal", lambda *_a, **_k: True)
    monkeypatch.setattr(terminal_service, "get_herdr_inbox_service", lambda: None)

    allow_a_read = asyncio.Event()
    a_initialized = asyncio.Event()
    b_initialized = asyncio.Event()
    first_loaded: dict[str, str] = {}

    def create_provider(_provider: str, terminal_id: str, *_args, **_kwargs):
        provider = MagicMock()
        provider.shell_baseline = None

        async def initialize() -> None:
            if terminal_id == "terminal-a":
                a_initialized.set()
                await allow_a_read.wait()
            first_loaded[terminal_id] = target.read_text(encoding="utf-8")
            if terminal_id == "terminal-b":
                b_initialized.set()

        provider.initialize = AsyncMock(side_effect=initialize)
        return provider

    manager = MagicMock()
    manager.create_provider.side_effect = create_provider
    monkeypatch.setattr(terminal_service, "provider_manager", manager)

    async def launch(terminal: str, deferred: bool):
        return await terminal_service.create_terminal(
            provider=provider_name,
            agent_profile="developer",
            session_name=f"session-{terminal.removeprefix('terminal-')}",
            new_session=True,
            working_directory=str(project_dir),
            allowed_tools=["*"],
            defer_init=deferred,
        )

    if defer_init:
        await launch("terminal-a", True)
        await asyncio.wait_for(a_initialized.wait(), timeout=1)
        await launch("terminal-b", True)
        await asyncio.wait_for(b_initialized.wait(), timeout=1)
        allow_a_read.set()
        await asyncio.wait_for(_wait_for_key(first_loaded, "terminal-a"), timeout=1)
    else:
        task_a = asyncio.create_task(launch("terminal-a", False))
        await asyncio.wait_for(a_initialized.wait(), timeout=1)
        await launch("terminal-b", False)
        allow_a_read.set()
        await task_a

    for loaded in first_loaded.values():
        assert "common project memory" in loaded
        assert "common global memory" in loaded
        assert "private session alpha" not in loaded
        assert "private session beta" not in loaded

    terminal_service._memory_injected_terminals.clear()
    monkeypatch.setattr(terminal_service, "MemoryService", lambda: svc)
    injected_a = terminal_service.inject_memory_context("task a", "terminal-a")
    injected_b = terminal_service.inject_memory_context("task b", "terminal-b")
    terminal_service._memory_injected_terminals.clear()

    assert "private session alpha" in injected_a
    assert "private session beta" not in injected_a
    assert "private session beta" in injected_b
    assert "private session alpha" not in injected_b
    engine.dispose()


async def _wait_for_key(values: dict[str, str], key: str) -> None:
    while key not in values:
        await asyncio.sleep(0)
