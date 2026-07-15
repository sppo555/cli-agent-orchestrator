"""Optional live lifecycle test for the Grok CLI provider.

Grok V1 is lifecycle-only.  This module deliberately does not test CAO MCP
assign/handoff/send_message because Phase 0 found no safe per-terminal MCP
identity-forwarding mechanism.
"""

import time
import uuid

import pytest

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
    finally:
        if terminal_id is not None:
            cleanup_terminal(terminal_id, actual_session)
