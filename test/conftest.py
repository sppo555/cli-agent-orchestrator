"""Repo-wide test fixtures."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _no_llm_compile_in_tests(monkeypatch):
    """Default memory wiki compilation to append mode for every test.

    The production default is "llm", which drives whichever coding-agent CLI
    (claude / codex / kiro-cli) is installed on the developer's machine — each
    invocation cold-starts for tens of seconds and would make the suite both
    slow and non-hermetic. Tests that exercise the LLM path override this env
    var themselves or stub the ``wiki_compiler`` seams.
    """
    monkeypatch.setenv("CAO_MEMORY_COMPILE_MODE", "append")


@pytest.fixture(autouse=True)
def _isolate_agent_step_usage_persistence():
    """Never let synthetic agent-step attempts write to the user's live DB."""

    with patch("cli_agent_orchestrator.services.agent_step.persist_worker_token_usage"):
        yield
