"""Claude Code memory-injection plugin (built-in).

Before provider initialization for a ``claude_code`` terminal, writes the
repo-safe CAO project/global memory context block into
``<cwd>/.claude/CLAUDE.md``, replacing any prior block delimited by the
cao-memory markers. Session and agent-private memory are excluded because the
file is shared by concurrent terminals.

The core terminal lifecycle invokes ``prepare`` as a required security barrier;
plugin discovery is not part of that guarantee. Path, marker, and write failures
propagate and abort provider startup so stale instructions cannot be loaded.
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
from cli_agent_orchestrator.plugins.builtin.memory_markers import strip_managed_blocks
from cli_agent_orchestrator.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

# Delimited section so repeated runs overwrite the same block rather than
# appending forever. Readers of CLAUDE.md can also treat the delimiters as
# a well-known injection boundary.
BEGIN_MARKER = "<!-- cao-memory:begin -->"
END_MARKER = "<!-- cao-memory:end -->"
CLAUDE_FILENAME = "CLAUDE.md"
CLAUDE_DIR = ".claude"


class ClaudeCodeMemoryPlugin(CaoPlugin):
    """Inject repo-safe CAO memory into CLAUDE.md on terminal creation."""

    async def setup(self) -> None:
        """Nothing to configure; plugin is stateless."""

    async def teardown(self) -> None:
        """Nothing to close; plugin holds no resources."""

    async def on_pre_initialize_terminal(self, event: PreInitializeTerminalEvent) -> None:
        """Backward-compatible direct entry point for pre-start preparation."""
        if event.provider != "claude_code":
            return
        working_directory = self._resolve_working_directory(event)
        if not working_directory:
            raise RuntimeError(f"claude_code_memory: no working directory for {event.terminal_id}")
        self.prepare(event.terminal_id, working_directory)

    async def on_post_create_terminal(self, event: PostCreateTerminalEvent) -> None:
        """Backward-compatible observer entry point used by direct callers."""

        if event.provider != "claude_code":
            return

        try:
            working_directory = self._resolve_working_directory(event)
        except Exception as exc:
            logger.warning(
                "claude_code_memory: could not resolve working dir for %s: %s",
                event.terminal_id,
                exc,
            )
            return

        if not working_directory:
            logger.debug(
                "claude_code_memory: no working directory for %s; skipping",
                event.terminal_id,
            )
            return

        try:
            self.prepare(event.terminal_id, working_directory)
        except Exception as exc:
            logger.warning(
                "claude_code_memory: preparation failed for %s: %s",
                working_directory,
                exc,
            )

    # ------------------------------------------------------------------
    # helpers

    def prepare(self, terminal_id: str, working_directory: str) -> None:
        """Synchronize the managed block, scrubbing stale data on empty/error."""
        target = self._validated_target_path(working_directory)
        try:
            context_block = MemoryService().get_provider_file_memory_context(terminal_id)
        except Exception:
            logger.warning("claude_code_memory: memory fetch failed; scrubbing managed block")
            context_block = ""
        self._write_block(target, context_block)

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
        """Return <cwd>/.claude/CLAUDE.md, rejecting paths that escape the cwd.

        Uses realpath for both the base and the final target so symlink
        trickery cannot redirect the write outside the working directory.
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
        target = (base / CLAUDE_DIR / CLAUDE_FILENAME).resolve()
        # relative_to() correctly handles the root-path case (base == "/"),
        # which a string startswith(base + separator) check mishandles ("//").
        try:
            target.relative_to(base)
        except ValueError:
            raise ValueError(f"target {target} escapes working directory {base}")
        return target

    def _write_block(self, target: Path, context_block: str) -> None:
        """Write, replace, or remove the delimited memory section."""

        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        stripped = self._strip_existing_block(existing)

        if not context_block:
            if not target.exists() or stripped == existing:
                return
            new_content = stripped
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            separator = "" if not stripped or stripped.endswith("\n") else "\n"
            new_content = f"{stripped}{separator}{BEGIN_MARKER}\n{context_block}\n{END_MARKER}\n"

        # Atomic temp-file + replace: an interrupted write must never leave a
        # truncated CLAUDE.md behind (same idiom as utils/skill_injection.py).
        temp_path = target.with_suffix(target.suffix + ".tmp")
        try:
            temp_path.write_text(new_content, encoding="utf-8")
            os.replace(temp_path, target)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @staticmethod
    def _strip_existing_block(content: str) -> str:
        """Remove valid blocks and reject malformed marker ownership."""

        return strip_managed_blocks(content, BEGIN_MARKER, END_MARKER)
