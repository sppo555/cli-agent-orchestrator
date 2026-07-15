"""Minimal allowlisted MCP identity probe for Grok Phase 0 experiments.

This helper is intentionally not registered in any Grok configuration.  It is
available for a later isolated per-process MCP experiment and never dumps the
parent environment.
"""

from __future__ import annotations

import os
import uuid

from fastmcp import FastMCP

mcp = FastMCP("grok-phase0-identity")


@mcp.tool()
def identity_probe() -> dict[str, object]:
    """Return only identity and non-secret terminal metadata."""
    return {
        "pid": os.getpid(),
        "invocation_id": str(uuid.uuid4()),
        "cao_terminal_id_present": "CAO_TERMINAL_ID" in os.environ,
        "cao_terminal_id": os.environ.get("CAO_TERMINAL_ID"),
        "metadata": {
            key: os.environ.get(key)
            for key in ("TERM", "TMUX", "GROK_SANDBOX")
            if key in os.environ
        },
    }


if __name__ == "__main__":
    mcp.run()
