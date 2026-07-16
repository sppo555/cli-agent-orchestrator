"""Kiro CLI memory-injection plugin (built-in).

Before provider initialization for a ``kiro_cli`` terminal, writes the CAO
memory context to ``<cwd>/.kiro/steering/cao-memory.md``. Kiro CLI natively
loads every ``*.md`` file under ``.kiro/steering/``, so this file is picked
up automatically. The plugin owns this file end-to-end and overwrites it
whole on each run (no in-file markers).

The core terminal lifecycle invokes ``prepare`` as a required security barrier;
plugin discovery is not part of that guarantee. Path and write failures propagate
and abort provider startup so stale steering cannot be loaded.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from cli_agent_orchestrator.clients.database import get_terminal_metadata
from cli_agent_orchestrator.clients.tmux import tmux_client
from cli_agent_orchestrator.plugins import (
    PostCreateTerminalEvent,
    PreInitializeTerminalEvent,
)
from cli_agent_orchestrator.plugins.base import CaoPlugin
from cli_agent_orchestrator.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

STEERING_SUBDIR = ".kiro/steering"
MEMORY_FILENAME = "cao-memory.md"


class KiroCliMemoryPlugin(CaoPlugin):
    """Inject CAO memory into the per-project Kiro steering directory."""

    async def setup(self) -> None:
        """Stateless; nothing to configure."""

    async def teardown(self) -> None:
        """Stateless; nothing to close."""

    async def on_pre_initialize_terminal(self, event: PreInitializeTerminalEvent) -> None:
        """Backward-compatible direct entry point for pre-start preparation."""
        if event.provider != "kiro_cli":
            return
        working_directory = self._resolve_working_directory(event)
        if not working_directory:
            raise RuntimeError(f"kiro_cli_memory: no working directory for {event.terminal_id}")
        self.prepare(event.terminal_id, working_directory)

    async def on_post_create_terminal(self, event: PostCreateTerminalEvent) -> None:
        """Backward-compatible observer entry point used by direct callers."""

        if event.provider != "kiro_cli":
            return

        try:
            working_directory = self._resolve_working_directory(event)
        except Exception as exc:
            logger.warning(
                "kiro_cli_memory: could not resolve working dir for %s: %s",
                event.terminal_id,
                exc,
            )
            return

        if not working_directory:
            logger.debug(
                "kiro_cli_memory: no working directory for %s; skipping",
                event.terminal_id,
            )
            return

        try:
            self.prepare(event.terminal_id, working_directory)
        except Exception as exc:
            logger.warning(
                "kiro_cli_memory: preparation failed for %s: %s",
                working_directory,
                exc,
            )

    # ------------------------------------------------------------------
    # helpers

    def prepare(self, terminal_id: str, working_directory: str) -> None:
        """Synchronize the dedicated steering file, deleting it when empty."""
        target = self._validated_target_path(working_directory)
        try:
            context_block = MemoryService().get_memory_context_for_terminal(terminal_id)
        except Exception:
            logger.warning("kiro_cli_memory: memory fetch failed; removing managed file")
            context_block = ""

        if not context_block:
            target.unlink(missing_ok=True)
            return

        target.parent.mkdir(parents=True, exist_ok=True)
        # Atomic temp-file + replace: Kiro loads every *.md under
        # .kiro/steering/, so a partial file from an interrupted write would
        # still be picked up.
        temp_path = target.with_suffix(target.suffix + ".tmp")
        try:
            temp_path.write_text(context_block + "\n", encoding="utf-8")
            os.replace(temp_path, target)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _resolve_working_directory(self, event: PostCreateTerminalEvent) -> str | None:
        """Look up the tmux pane's working directory for the terminal."""

        metadata = get_terminal_metadata(event.terminal_id)
        if metadata is None:
            return None

        session_name = metadata.get("tmux_session") or event.session_id
        window_name = metadata.get("tmux_window")
        if not session_name or not window_name:
            return None

        return tmux_client.get_pane_working_directory(session_name, window_name)

    def _validated_target_path(self, working_directory: str) -> Path:
        """Return <cwd>/.kiro/steering/cao-memory.md, rejecting escape attempts.

        Uses realpath for both the base and the target so symlink trickery
        cannot redirect the write outside the working directory.
        """

        if "\x00" in working_directory:
            raise ValueError("working directory contains null bytes")

        # resolve(strict=True) raises OSError (e.g. FileNotFoundError) for an
        # ephemeral/missing cwd. Surface it as ValueError so the caller's
        # single ``except ValueError`` reliably catches every validation
        # failure and honours the plugin's log-and-skip contract.
        try:
            base = Path(working_directory).resolve(strict=True)
        except OSError as exc:
            raise ValueError(f"working directory {working_directory!r} is not resolvable: {exc}")
        target = (base / STEERING_SUBDIR / MEMORY_FILENAME).resolve()
        # relative_to() correctly handles the root-path case (base == "/"),
        # which a string startswith(base + separator) check mishandles ("//").
        try:
            target.relative_to(base)
        except ValueError:
            raise ValueError(f"target {target} escapes working directory {base}")
        return target
