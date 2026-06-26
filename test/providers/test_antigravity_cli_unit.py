"""Unit tests for the Antigravity CLI (agy) provider."""

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.providers.antigravity_cli import AntigravityCliProvider


class TestAntigravityCliProvider:
    """Tests for AntigravityCliProvider status classification and initialization."""

    def test_classify_onboarding(self):
        """Test that onboarding screen (query + response + idle footer) classifies as COMPLETED during init."""
        provider = AntigravityCliProvider("term-1", "session-1", "window-1", agent_profile="developer_agy")
        provider._uses_prompt_interactive = True
        assert provider._initialized is False

        # Mock rows matching the onboarding screen
        rows = [
            "> You are the developer_agy. Your instructions are in GEMINI.md. Acknowledge your role in one sentence, then wait for tasks.",
            "I acknowledge my role as developer_agy and am ready for tasks.",
            "────────────────────────────────────────────────────────────────────────────────",
            "> ",
            "?  for shortcuts"
        ]

        status = provider._classify(rows)
        assert status == TerminalStatus.COMPLETED

    def test_classify_post_init_idle(self):
        """Test that onboarding screen classifies as IDLE after initialization is complete, before any task is sent."""
        provider = AntigravityCliProvider("term-1", "session-1", "window-1", agent_profile="developer_agy")
        provider._initialized = True
        provider._uses_prompt_interactive = True
        assert provider._received_input_after_init is False

        rows = [
            "> You are the developer_agy. Your instructions are in GEMINI.md. Acknowledge your role in one sentence, then wait for tasks.",
            "I acknowledge my role as developer_agy and am ready for tasks.",
            "────────────────────────────────────────────────────────────────────────────────",
            "> ",
            "?  for shortcuts"
        ]

        status = provider._classify(rows)
        assert status == TerminalStatus.IDLE

    def test_classify_processing_spinner(self):
        """Test that processing state with spinner classifies as PROCESSING."""
        provider = AntigravityCliProvider("term-1", "session-1", "window-1", agent_profile="developer_agy")
        provider._initialized = True
        provider._uses_prompt_interactive = True
        provider._received_input_after_init = True

        rows = [
            "> Could you check if it is the same problem as ISSUES.md?",
            "Generating...",
            "esc to cancel"
        ]

        status = provider._classify(rows)
        assert status == TerminalStatus.PROCESSING

    def test_classify_task_completed(self):
        """Test that a completed task classifies as COMPLETED."""
        provider = AntigravityCliProvider("term-1", "session-1", "window-1", agent_profile="developer_agy")
        provider._initialized = True
        provider._uses_prompt_interactive = True
        provider._received_input_after_init = True

        rows = [
            "> Could you check if it is the same problem as ISSUES.md?",
            "This is a different problem.",
            "────────────────────────────────────────────────────────────────────────────────",
            "> ",
            "?  for shortcuts"
        ]

        status = provider._classify(rows)
        assert status == TerminalStatus.COMPLETED

    def test_classify_next_task_not_started(self):
        """Test that after sending a new task, we only check below the latest query line.

        If the agent has not responded yet, it must classify as IDLE (not COMPLETED from the previous task's response).
        """
        provider = AntigravityCliProvider("term-1", "session-1", "window-1", agent_profile="developer_agy")
        provider._initialized = True
        provider._uses_prompt_interactive = True
        provider._received_input_after_init = True

        rows = [
            "> Could you check if it is the same problem as ISSUES.md?",
            "This is a different problem.",
            "────────────────────────────────────────────────────────────────────────────────",
            "> Show me the git diff",  # New query line (latest)
            "────────────────────────────────────────────────────────────────────────────────",
            "> ",
            "?  for shortcuts"
        ]

        status = provider._classify(rows)
        # Because we only look below the last query line (which is "> Show me the git diff"),
        # there is no response line yet. Thus, has_response is False, and it evaluates to IDLE.
        assert status == TerminalStatus.IDLE

    @pytest.mark.asyncio
    @patch("cli_agent_orchestrator.providers.antigravity_cli.wait_for_shell", return_value=True)
    @patch("cli_agent_orchestrator.providers.antigravity_cli.get_backend")
    @patch("cli_agent_orchestrator.providers.antigravity_cli.load_agent_profile")
    async def test_initialize_success(self, mock_load_profile, mock_tmux, mock_wait_shell):
        """Test that initialization calls detect_and_apply and successfully completes."""
        profile = MagicMock()
        profile.model = "gemini-2.5-pro"
        profile.system_prompt = "You are developer_agy."
        profile.name = "developer_agy"
        mock_load_profile.return_value = profile

        mock_tmux.return_value.get_history.return_value = "CAO_SHELL_READY"

        provider = AntigravityCliProvider("term-1", "session-1", "window-1", agent_profile="developer_agy")

        mock_monitor = MagicMock()
        mock_monitor.get_status.return_value = TerminalStatus.COMPLETED

        with patch("cli_agent_orchestrator.services.status_monitor.status_monitor", mock_monitor):
            result = await provider.initialize()

        assert result is True
        assert provider._initialized is True
        mock_monitor.detect_and_apply.assert_called_once_with("term-1", force=True)
