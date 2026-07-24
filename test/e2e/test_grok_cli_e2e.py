"""Optional live lifecycle test for the Grok CLI provider.

Grok V1 is lifecycle-only.  This module deliberately does not test CAO MCP
assign/handoff/send_message because Phase 0 found no safe per-terminal MCP
identity-forwarding mechanism.
"""

import time
import uuid
from pathlib import Path
from urllib.parse import quote

import pytest
import requests

from cli_agent_orchestrator import constants
from cli_agent_orchestrator.services.interactive_token_usage import grok_usage_session_id

from .conftest import cleanup_terminal, create_terminal, extract_output, send_handoff_message


@pytest.mark.e2e
def test_grok_cli_lifecycle(require_grok):
    session_name = f"grok-e2e-{uuid.uuid4().hex[:6]}"
    terminal_id = None
    actual_session = session_name
    try:
        terminal_id, actual_session = create_terminal(
            "grok_cli", "developer", session_name, retries=0
        )
        send_handoff_message(terminal_id, "Return exactly: GROK_OK", "grok_cli")

        deadline = time.time() + 120
        output = ""
        while time.time() < deadline:
            try:
                output = extract_output(terminal_id)
            except AssertionError:
                time.sleep(3)
                continue
            if "GROK_OK" in output:
                break
            time.sleep(3)
        assert "GROK_OK" in output

        terminal = requests.get(f"{constants.API_BASE_URL}/terminals/{terminal_id}")
        assert terminal.status_code == 200
        metadata = terminal.json()
        expected_session_id = grok_usage_session_id(
            terminal_id,
            metadata["session_name"],
            metadata["name"],
        )
        working_directory = requests.get(
            f"{constants.API_BASE_URL}/terminals/{terminal_id}/working-directory"
        )
        assert working_directory.status_code == 200
        expected_source = (
            Path.home()
            / ".grok"
            / "sessions"
            / quote(working_directory.json()["working_directory"], safe="")
            / expected_session_id
            / "updates.jsonl"
        )

        usage_rows = []
        deadline = time.time() + 30
        while time.time() < deadline:
            usage = requests.get(
                f"{constants.API_BASE_URL}/token-usage",
                params={"terminal_id": terminal_id},
            )
            assert usage.status_code == 200
            usage_rows = usage.json()
            if usage_rows:
                break
            time.sleep(1)

        assert len(usage_rows) == 1
        assert usage_rows[0]["provider"] == "grok_cli"
        assert usage_rows[0]["estimated"] is False
        assert usage_rows[0]["total_tokens"] > 0
        assert usage_rows[0]["model"]
        assert expected_source.is_file()
    finally:
        if terminal_id is not None:
            cleanup_terminal(terminal_id, actual_session)
