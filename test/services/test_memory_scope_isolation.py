"""Regression coverage for project/global memory isolation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cli_agent_orchestrator.clients.database import Base, MemoryMetadataModel
from cli_agent_orchestrator.services.memory_service import MemoryService


def _run(coro):
    return asyncio.run(coro)


def _service(tmp_path: Path) -> tuple[MemoryService, object]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'memory.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return MemoryService(base_dir=tmp_path / "memory", db_engine=engine), engine


def _project_context(tmp_path: Path, *, caller_scope: str = "project") -> dict:
    return {
        "terminal_id": "term-project-worker",
        "session_name": "scope-isolation",
        "agent_profile": "developer",
        "provider": "codex",
        "cwd": str(tmp_path / "repo"),
        "caller_scope": caller_scope,
    }


def _metadata_rows(engine) -> list[MemoryMetadataModel]:
    Session = sessionmaker(bind=engine)
    with Session() as db:
        return list(db.query(MemoryMetadataModel).all())


def _seed_legacy_global_project(svc: MemoryService, key: str = "legacy-project") -> Path:
    """Create a pre-boundary polluted topic in an isolated test store."""
    wiki_path = svc.get_wiki_path("global", None, key)
    wiki_path.parent.mkdir(parents=True, exist_ok=True)
    wiki_path.write_text(
        f"# {key}\n"
        "<!-- id: 00000000-0000-0000-0000-000000000001 | scope: global | "
        "type: project | tags: legacy -->\n\n"
        "## 2026-01-01T00:00:00Z\nlegacy private project body\n",
        encoding="utf-8",
    )
    svc._update_index(
        "global",
        None,
        key,
        "project",
        "legacy",
        "legacy private project body",
        "2026-01-01T00:00:00Z",
        "add",
    )
    svc._upsert_metadata(
        key=key,
        memory_type="project",
        scope="global",
        scope_id=None,
        file_path=str(wiki_path),
        tags="legacy",
        source_provider=None,
        source_terminal_id=None,
        token_estimate=4,
    )
    return wiki_path


class TestGlobalProjectBoundary:
    def test_global_project_rejected_before_any_persistence(self, tmp_path: Path) -> None:
        svc, engine = _service(tmp_path)
        body = "private project result must never be logged or persisted"

        with pytest.raises(ValueError, match="use scope='project'") as exc_info:
            _run(
                svc.store(
                    content=body,
                    scope="global",
                    memory_type="project",
                    key="project-result",
                )
            )

        assert body not in str(exc_info.value)
        assert not svc.base_dir.exists()
        assert _metadata_rows(engine) == []

    def test_existing_global_project_topic_cannot_be_appended(self, tmp_path: Path) -> None:
        svc, engine = _service(tmp_path)
        wiki_path = svc.get_wiki_path("global", None, "legacy-project-topic")
        wiki_path.parent.mkdir(parents=True)
        original = (
            "# legacy-project-topic\n"
            "<!-- id: 00000000-0000-0000-0000-000000000000 | scope: global | "
            "type: project | tags: legacy -->\n\n"
            "## 2026-01-01T00:00:00Z\nlegacy body\n"
        )
        wiki_path.write_text(original, encoding="utf-8")

        with pytest.raises(ValueError, match="use scope='project'"):
            _run(
                svc.store(
                    content="attempted append",
                    scope="global",
                    memory_type="project",
                    key="legacy-project-topic",
                )
            )

        assert wiki_path.read_text(encoding="utf-8") == original
        assert not svc.get_index_path("global", None).exists()
        assert _metadata_rows(engine) == []

    def test_project_project_allowed(self, tmp_path: Path) -> None:
        svc, engine = _service(tmp_path)
        ctx = _project_context(tmp_path)

        memory = _run(
            svc.store(
                content="project architecture decision",
                scope="project",
                memory_type="project",
                key="architecture-decision",
                terminal_context=ctx,
            )
        )

        assert Path(memory.file_path).exists()
        assert memory.scope_id
        assert len(_metadata_rows(engine)) == 1

    @pytest.mark.parametrize("memory_type", ["user", "feedback", "reference"])
    def test_operator_global_non_project_types_allowed(
        self, tmp_path: Path, memory_type: str
    ) -> None:
        svc, engine = _service(tmp_path)

        memory = _run(
            svc.store(
                content=f"cross-project {memory_type}",
                scope="global",
                memory_type=memory_type,
                key=f"global-{memory_type}",
            )
        )

        assert Path(memory.file_path).exists()
        assert len(_metadata_rows(engine)) == 1

    def test_project_worker_cannot_write_global_preference(self, tmp_path: Path) -> None:
        svc, engine = _service(tmp_path)

        with pytest.raises(PermissionError, match="may not write target scope 'global'"):
            _run(
                svc.store(
                    content="preference requiring operator elevation",
                    scope="global",
                    memory_type="user",
                    key="operator-only-preference",
                    terminal_context=_project_context(tmp_path),
                )
            )

        assert not svc.base_dir.exists()
        assert _metadata_rows(engine) == []

    def test_archive_import_cannot_bypass_store_boundary(self, tmp_path: Path) -> None:
        svc, engine = _service(tmp_path)
        bundle = tmp_path / "bundle"
        bundle.mkdir()
        (bundle / "imported-project.md").write_text(
            "---\ntype: project\ntitle: imported-project\n---\n\n"
            "# imported-project\n\nproject-only import body\n",
            encoding="utf-8",
        )

        report = svc.import_memories(
            "okf",
            bundle,
            "global",
            conflict_policy="skip",
        )

        assert report.imported == 0
        assert report.rejected == 1
        assert "use scope='project'" in report.errors["imported-project.md"]
        assert not svc.get_wiki_path("global", None, "imported-project").exists()
        assert _metadata_rows(engine) == []

    @patch("cli_agent_orchestrator.mcp_server.server._get_terminal_context_from_env")
    @patch("cli_agent_orchestrator.services.memory_service.MemoryService")
    def test_mcp_returns_structured_rejection_without_body(
        self,
        mock_service_class: Mock,
        mock_context: Mock,
        tmp_path: Path,
    ) -> None:
        from cli_agent_orchestrator.mcp_server.server import memory_store

        svc, engine = _service(tmp_path)
        mock_service_class.return_value = svc
        mock_context.return_value = None
        body = "sensitive project body must not appear in the error"

        result = _run(
            memory_store(
                content=body,
                scope="global",
                memory_type="project",
                key="mcp-project-result",
                tags="project",
            )
        )

        assert result["success"] is False
        assert "use scope='project'" in result["error"]
        assert body not in result["error"]
        assert not svc.base_dir.exists()
        assert _metadata_rows(engine) == []


class TestTerminalCallerScope:
    @patch("cli_agent_orchestrator.mcp_server.server.requests.get")
    @patch.dict("os.environ", {"CAO_TERMINAL_ID": "term-project-worker"}, clear=False)
    def test_verified_terminal_context_is_project_bounded(self, mock_get: Mock) -> None:
        from cli_agent_orchestrator.mcp_server.server import _get_terminal_context_from_env

        terminal_response = Mock()
        terminal_response.raise_for_status.return_value = None
        terminal_response.json.return_value = {
            "id": "term-project-worker",
            "session_name": "scope-isolation",
            "provider": "codex",
            "agent_profile": "developer",
        }
        cwd_response = Mock(status_code=200)
        cwd_response.json.return_value = {"working_directory": "/work/project"}
        mock_get.side_effect = [terminal_response, cwd_response]

        context = _get_terminal_context_from_env()

        assert context is not None
        assert context["caller_scope"] == "project"
        assert context["cwd"] == "/work/project"

    @patch.dict("os.environ", {}, clear=True)
    def test_unbound_operator_context_remains_unset(self) -> None:
        from cli_agent_orchestrator.mcp_server.server import _get_terminal_context_from_env

        assert _get_terminal_context_from_env() is None

    @pytest.mark.parametrize(
        "failure",
        [requests.Timeout("timeout"), requests.ConnectionError("refused")],
    )
    @patch("cli_agent_orchestrator.mcp_server.server.requests.get")
    @patch.dict("os.environ", {"CAO_TERMINAL_ID": "term-project-worker"}, clear=True)
    def test_terminal_lookup_transport_failure_is_fail_closed(
        self, mock_get: Mock, failure: Exception
    ) -> None:
        from cli_agent_orchestrator.mcp_server.server import (
            MEMORY_TERMINAL_CONTEXT_ERROR,
            MemoryTerminalContextError,
            _get_terminal_context_from_env,
        )

        mock_get.side_effect = failure
        with pytest.raises(MemoryTerminalContextError, match=MEMORY_TERMINAL_CONTEXT_ERROR):
            _get_terminal_context_from_env()

    @pytest.mark.parametrize("status", [404, 500])
    @patch("cli_agent_orchestrator.mcp_server.server.requests.get")
    @patch.dict("os.environ", {"CAO_TERMINAL_ID": "term-project-worker"}, clear=True)
    def test_terminal_lookup_http_failure_is_fail_closed(self, mock_get: Mock, status: int) -> None:
        from cli_agent_orchestrator.mcp_server.server import (
            MemoryTerminalContextError,
            _get_terminal_context_from_env,
        )

        response = Mock(status_code=status)
        response.raise_for_status.side_effect = requests.HTTPError(f"status {status}")
        mock_get.return_value = response
        with pytest.raises(MemoryTerminalContextError):
            _get_terminal_context_from_env()

    @pytest.mark.parametrize(
        "metadata",
        [None, [], {}, {"id": "wrong", "session_name": "s", "provider": "codex"}],
    )
    @patch("cli_agent_orchestrator.mcp_server.server.requests.get")
    @patch.dict("os.environ", {"CAO_TERMINAL_ID": "term-project-worker"}, clear=True)
    def test_malformed_or_incomplete_terminal_metadata_is_fail_closed(
        self, mock_get: Mock, metadata: object
    ) -> None:
        from cli_agent_orchestrator.mcp_server.server import (
            MemoryTerminalContextError,
            _get_terminal_context_from_env,
        )

        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = metadata
        mock_get.return_value = response
        with pytest.raises(MemoryTerminalContextError):
            _get_terminal_context_from_env()

    @patch("cli_agent_orchestrator.mcp_server.server.requests.get")
    @patch.dict("os.environ", {"CAO_TERMINAL_ID": "term-project-worker"}, clear=True)
    def test_working_directory_failure_stays_project_bounded(self, mock_get: Mock) -> None:
        from cli_agent_orchestrator.mcp_server.server import _get_terminal_context_from_env

        terminal_response = Mock()
        terminal_response.raise_for_status.return_value = None
        terminal_response.json.return_value = {
            "id": "term-project-worker",
            "session_name": "scope-isolation",
            "provider": "codex",
        }
        mock_get.side_effect = [terminal_response, requests.Timeout("cwd timeout")]

        context = _get_terminal_context_from_env()

        assert context == {
            "terminal_id": "term-project-worker",
            "session_name": "scope-isolation",
            "provider": "codex",
            "agent_profile": None,
            "caller_scope": "project",
        }

    @patch("cli_agent_orchestrator.mcp_server.server.requests.get")
    @patch("cli_agent_orchestrator.services.memory_service.MemoryService")
    @patch.dict("os.environ", {"CAO_TERMINAL_ID": "term-project-worker"}, clear=True)
    def test_mcp_returns_structured_identity_failure_without_storing(
        self, mock_service_class: Mock, mock_get: Mock
    ) -> None:
        from cli_agent_orchestrator.mcp_server.server import (
            MEMORY_TERMINAL_CONTEXT_ERROR,
            memory_store,
        )

        service = mock_service_class.return_value
        service.store = AsyncMock()
        mock_get.side_effect = requests.Timeout("response body must not escape")

        result = _run(
            memory_store(
                content="sensitive project content",
                scope="project",
                memory_type="project",
                key="identity-failure",
            )
        )

        assert result == {"success": False, "error": MEMORY_TERMINAL_CONTEXT_ERROR}
        service.store.assert_not_awaited()


class TestLegacyReadIsolation:
    def test_legacy_global_project_is_filtered_but_valid_global_remains(
        self, tmp_path: Path
    ) -> None:
        svc, _ = _service(tmp_path)
        _seed_legacy_global_project(svc)
        _run(
            svc.store(
                content="valid shared reference",
                scope="global",
                memory_type="reference",
                key="shared-reference",
            )
        )

        memories = _run(svc.recall(scope="global", limit=20, scan_all=True, search_mode="metadata"))

        assert [memory.key for memory in memories] == ["shared-reference"]

    def test_two_projects_receive_only_own_project_and_valid_global(self, tmp_path: Path) -> None:
        svc, _ = _service(tmp_path)
        repo_a = tmp_path / "repo-a"
        repo_b = tmp_path / "repo-b"
        repo_a.mkdir()
        repo_b.mkdir()
        ctx_a = {"cwd": str(repo_a), "caller_scope": "project"}
        ctx_b = {"cwd": str(repo_b), "caller_scope": "project"}

        _run(
            svc.store(
                content="project alpha only",
                scope="project",
                memory_type="project",
                key="alpha",
                terminal_context=ctx_a,
            )
        )
        _run(
            svc.store(
                content="project beta only",
                scope="project",
                memory_type="project",
                key="beta",
                terminal_context=ctx_b,
            )
        )
        _run(
            svc.store(
                content="valid shared reference",
                scope="global",
                memory_type="reference",
                key="shared-reference",
            )
        )
        _seed_legacy_global_project(svc)

        with patch.object(svc, "_get_terminal_context", return_value=ctx_a):
            context_a = svc.get_memory_context_for_terminal("term-a", budget_chars=12000)
        with patch.object(svc, "_get_terminal_context", return_value=ctx_b):
            context_b = svc.get_memory_context_for_terminal("term-b", budget_chars=12000)

        assert "project alpha only" in context_a
        assert "project beta only" not in context_a
        assert "valid shared reference" in context_a
        assert "legacy private project body" not in context_a
        assert "project beta only" in context_b
        assert "project alpha only" not in context_b
        assert "valid shared reference" in context_b
        assert "legacy private project body" not in context_b

    def test_provider_file_context_excludes_session_but_terminal_context_keeps_it(
        self, tmp_path: Path
    ) -> None:
        """Repo-shared and terminal-specific builders enforce different ownership."""

        svc, _ = _service(tmp_path)
        repo = tmp_path / "shared-repo"
        repo.mkdir()
        ctx_a = {
            "cwd": str(repo),
            "session_name": "cao-session-a",
            "agent_profile": "developer",
            "caller_scope": "project",
        }
        ctx_b = {**ctx_a, "session_name": "cao-session-b"}

        _run(
            svc.store(
                content="session alpha private",
                scope="session",
                memory_type="project",
                key="session-alpha",
                terminal_context=ctx_a,
            )
        )
        _run(
            svc.store(
                content="session beta private",
                scope="session",
                memory_type="project",
                key="session-beta",
                terminal_context=ctx_b,
            )
        )
        _run(
            svc.store(
                content="common project context",
                scope="project",
                memory_type="project",
                key="shared-project",
                terminal_context=ctx_a,
            )
        )
        _run(
            svc.store(
                content="common global context",
                scope="global",
                memory_type="reference",
                key="shared-global",
            )
        )

        contexts = {"term-a": ctx_a, "term-b": ctx_b}
        with patch.object(svc, "_get_terminal_context", side_effect=contexts.get):
            provider_a = svc.get_provider_file_memory_context("term-a", budget_chars=12000)
            provider_b = svc.get_provider_file_memory_context("term-b", budget_chars=12000)
            terminal_a = svc.get_memory_context_for_terminal("term-a", budget_chars=12000)
            terminal_b = svc.get_memory_context_for_terminal("term-b", budget_chars=12000)

        assert provider_a == provider_b
        assert "common project context" in provider_a
        assert "common global context" in provider_a
        assert "session alpha private" not in provider_a
        assert "session beta private" not in provider_a
        assert "session alpha private" in terminal_a
        assert "session beta private" not in terminal_a
        assert "session beta private" in terminal_b
        assert "session alpha private" not in terminal_b

    def test_audit_is_read_only_and_quarantine_requires_apply(self, tmp_path: Path) -> None:
        svc, engine = _service(tmp_path)
        source = _seed_legacy_global_project(svc)
        before = source.read_bytes()

        findings = svc.audit_scope_isolation()
        dry_run = _run(svc.quarantine_global_project("legacy-project"))

        assert findings == [
            {
                "key": "legacy-project",
                "scope": "global",
                "scope_id": None,
                "memory_type": "project",
                "wiki_path": str(source),
                "index_present": True,
                "metadata_present": True,
            }
        ]
        assert dry_run["applied"] is False
        assert source.read_bytes() == before
        assert len(_metadata_rows(engine)) == 1
        assert not Path(dry_run["quarantine_path"]).exists()

        applied = _run(svc.quarantine_global_project("legacy-project", apply=True))

        assert applied["applied"] is True
        assert not source.exists()
        assert Path(applied["quarantine_path"]).read_bytes() == before
        assert "legacy-project" not in svc.get_index_path("global", None).read_text()
        assert _metadata_rows(engine) == []
