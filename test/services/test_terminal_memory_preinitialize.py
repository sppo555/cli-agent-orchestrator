"""Lifecycle regression tests for provider-native memory preparation."""

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine

from cli_agent_orchestrator.clients.database import Base
from cli_agent_orchestrator.models.agent_profile import AgentProfile
from cli_agent_orchestrator.plugins import PluginRegistry
from cli_agent_orchestrator.plugins.builtin.claude_code_memory import (
    BEGIN_MARKER as CLAUDE_BEGIN,
)
from cli_agent_orchestrator.plugins.builtin.claude_code_memory import (
    END_MARKER as CLAUDE_END,
)
from cli_agent_orchestrator.plugins.builtin.codex_memory import BEGIN_MARKER as CODEX_BEGIN
from cli_agent_orchestrator.plugins.builtin.codex_memory import END_MARKER as CODEX_END
from cli_agent_orchestrator.plugins.builtin.memory_markers import (
    MalformedMemoryMarkersError,
)
from cli_agent_orchestrator.services.memory_service import MemoryService
from cli_agent_orchestrator.services.terminal_service import create_terminal


async def _seed_runtime(svc: MemoryService, project_dir: Path) -> dict:
    ctx = {
        "cwd": str(project_dir),
        "session_name": "cao-memory-preinit",
        "agent_profile": "developer",
        "caller_scope": "project",
    }
    await svc.store(
        content="valid project startup context",
        scope="project",
        memory_type="project",
        key="valid-project",
        terminal_context=ctx,
    )
    await svc.store(
        content="valid global startup context",
        scope="global",
        memory_type="reference",
        key="valid-global",
    )
    legacy = svc.get_wiki_path("global", None, "legacy-pollution")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        "# legacy-pollution\n"
        "<!-- id: 00000000-0000-0000-0000-000000000099 | scope: global | "
        "type: project | tags: legacy -->\n\n"
        "## 2026-01-01T00:00:00Z\nlegacy cross-project startup pollution\n",
        encoding="utf-8",
    )
    svc._update_index(
        "global",
        None,
        "legacy-pollution",
        "project",
        "legacy",
        "legacy cross-project startup pollution",
        "2026-01-01T00:00:00Z",
        "add",
    )
    return ctx


@pytest.mark.asyncio
@pytest.mark.parametrize("defer_init", [False, True])
@pytest.mark.parametrize("registry_kind", ["none", "empty", "load-failed"])
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
        (
            "kiro_cli",
            "kiro_cli_memory",
            Path(".kiro/steering/cao-memory.md"),
            None,
        ),
    ],
)
async def test_stale_provider_file_is_clean_before_first_provider_load(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    defer_init: bool,
    registry_kind: str,
    provider_name: str,
    module_name: str,
    relative_target: Path,
    markers: tuple[str, str] | None,
) -> None:
    """Both lifecycle modes scrub legacy content before initialize reads files."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    target = project_dir / relative_target
    target.parent.mkdir(parents=True, exist_ok=True)
    user_prefix = "# User-authored instructions\nkeep-before\n"
    user_suffix = "\nkeep-after\n"
    if markers:
        target.write_text(
            user_prefix
            + f"{markers[0]}\nlegacy cross-project startup pollution\n{markers[1]}"
            + user_suffix,
            encoding="utf-8",
        )
    else:
        target.write_text("legacy cross-project startup pollution\n", encoding="utf-8")

    engine = create_engine(
        f"sqlite:///{tmp_path / 'memory.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    svc = MemoryService(base_dir=tmp_path / "memory", db_engine=engine)
    terminal_context = await _seed_runtime(svc, project_dir)
    monkeypatch.setattr(svc, "_get_terminal_context", lambda _terminal_id: terminal_context)

    plugin_module = f"cli_agent_orchestrator.plugins.builtin.{module_name}"
    monkeypatch.setattr(f"{plugin_module}.MemoryService", lambda: svc)
    monkeypatch.setattr(
        f"{plugin_module}.get_terminal_metadata",
        lambda terminal_id: {
            "id": terminal_id,
            "tmux_session": "cao-memory-preinit",
            "tmux_window": "developer-abcd",
        },
    )
    monkeypatch.setattr(
        f"{plugin_module}.tmux_client.get_pane_working_directory",
        lambda _session, _window: str(project_dir),
    )

    backend = MagicMock()
    backend.session_exists.return_value = False
    backend.supports_event_inbox.return_value = True
    monkeypatch.setattr("cli_agent_orchestrator.backends.registry._backend", backend)
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.generate_terminal_id",
        lambda: "terminal-preinit",
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.generate_window_name",
        lambda _agent: "developer-abcd",
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.load_agent_profile",
        lambda _agent: AgentProfile(name="developer", description="Dev"),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.build_skill_catalog", lambda _skills: ""
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.db_create_terminal",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.db_delete_terminal",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.get_herdr_inbox_service", lambda: None
    )

    first_loaded: list[str] = []
    initialized = asyncio.Event()

    async def initialize() -> None:
        first_loaded.append(target.read_text(encoding="utf-8"))
        initialized.set()

    provider = MagicMock()
    provider.initialize = AsyncMock(side_effect=initialize)
    provider.shell_baseline = None
    manager = MagicMock()
    manager.create_provider.return_value = provider
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.provider_manager", manager
    )

    registry = None
    if registry_kind != "none":
        registry = PluginRegistry()
    if registry_kind == "load-failed":
        broken_entry_point = MagicMock()
        broken_entry_point.name = "broken-memory-plugin"
        broken_entry_point.load.side_effect = RuntimeError("synthetic load failure")
        monkeypatch.setattr(
            "cli_agent_orchestrator.plugins.registry.importlib.metadata.entry_points",
            lambda **_kwargs: [broken_entry_point],
        )
        await registry.load()

    await create_terminal(
        provider=provider_name,
        agent_profile="developer",
        session_name="memory-preinit",
        new_session=True,
        working_directory=str(project_dir),
        allowed_tools=["*"],
        registry=registry,
        defer_init=defer_init,
    )
    await asyncio.wait_for(initialized.wait(), timeout=1)

    startup_content = first_loaded[0]
    assert "legacy cross-project startup pollution" not in startup_content
    assert "valid project startup context" in startup_content
    assert "valid global startup context" in startup_content
    if markers:
        assert startup_content.startswith(user_prefix + user_suffix)
    engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_name", "module_name", "relative_target", "begin", "end"),
    [
        ("codex", "codex_memory", Path("AGENTS.md"), CODEX_BEGIN, CODEX_END),
        (
            "claude_code",
            "claude_code_memory",
            Path(".claude/CLAUDE.md"),
            CLAUDE_BEGIN,
            CLAUDE_END,
        ),
    ],
)
@pytest.mark.parametrize("layout", ["unclosed", "nested", "misaligned"])
async def test_malformed_provider_markers_abort_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    provider_name: str,
    module_name: str,
    relative_target: Path,
    begin: str,
    end: str,
    layout: str,
) -> None:
    """Ambiguous ownership is content-free, byte-preserving, and fail-closed."""

    project_dir = tmp_path / "project"
    target = project_dir / relative_target
    target.parent.mkdir(parents=True, exist_ok=True)
    secret = "legacy-secret-cross-project-payload"
    malformed = {
        "unclosed": f"user-prefix\n{begin}\n{secret}\n",
        "nested": f"user-prefix\n{begin}\n{secret}\n{begin}\n{end}\n",
        "misaligned": f"user-prefix\n{end}\n{secret}\n{begin}\n{end}\n",
    }[layout]
    target.write_text(malformed, encoding="utf-8")
    original = target.read_bytes()

    memory = MagicMock()
    memory.get_memory_context_for_terminal.return_value = ""
    monkeypatch.setattr(
        f"cli_agent_orchestrator.plugins.builtin.{module_name}.MemoryService",
        lambda: memory,
    )

    backend = MagicMock()
    backend.session_exists.return_value = False
    backend.supports_event_inbox.return_value = True
    backend.get_pane_working_directory.return_value = str(project_dir)
    monkeypatch.setattr("cli_agent_orchestrator.backends.registry._backend", backend)
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.generate_terminal_id",
        lambda: "terminal-malformed",
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.generate_window_name",
        lambda _agent: "developer-malformed",
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.load_agent_profile",
        lambda _agent: AgentProfile(name="developer", description="Dev"),
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.db_create_terminal",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.db_delete_terminal",
        lambda *_a, **_k: True,
    )
    manager = MagicMock()
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.terminal_service.provider_manager", manager
    )

    caplog.set_level(logging.ERROR)
    with pytest.raises(MalformedMemoryMarkersError, match="malformed CAO memory markers"):
        await create_terminal(
            provider=provider_name,
            agent_profile="developer",
            session_name="malformed",
            new_session=True,
            working_directory=str(project_dir),
            allowed_tools=["*"],
        )

    manager.create_provider.assert_not_called()
    assert target.read_bytes() == original
    assert secret not in caplog.text
