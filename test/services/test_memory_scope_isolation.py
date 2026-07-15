"""Regression coverage for project/global memory isolation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
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
