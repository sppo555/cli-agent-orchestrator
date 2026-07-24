"""Token-usage accounting for completed worker steps.

The CLI providers do not expose one stable, machine-readable usage API. The
shared step seam therefore reports an explicit estimate based on the text sent
to the worker and the final text returned by the worker.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

from cli_agent_orchestrator.models.token_usage import TokenUsage

logger = logging.getLogger(__name__)
_WORKER_RESULT_PATH_RE = re.compile(r"(?:\.cao/worker-results|worker-results)/[^\s`\"'<>()[\]]+")


def estimate_tokens(text: str) -> int:
    """Estimate tokens using the project's existing four-chars-per-token rule."""

    if not text:
        return 0
    return (len(text) + 3) // 4


def resolve_worker_configuration(provider: str, agent: str) -> tuple[Optional[str], Optional[str]]:
    """Resolve the configured model and effort for a worker attempt.

    ``None`` means the provider default is active. Claude's effort can also be
    supplied globally through ``CLAUDE_CODE_EFFORT_LEVEL`` when the profile does
    not override it.
    """

    try:
        from cli_agent_orchestrator.utils.agent_profiles import load_agent_profile

        profile = load_agent_profile(agent)
    except (FileNotFoundError, ValueError, OSError):
        profile = None

    model = profile.model if profile is not None else None
    effort = profile.effort if profile is not None else None
    if provider == "claude_code" and not effort:
        effort = os.getenv("CLAUDE_CODE_EFFORT_LEVEL") or None
    return model, effort


def resolve_worker_progress(progress: Optional[str], prompt: str, response: str) -> Optional[str]:
    """Resolve explicit progress, or infer a worker-results artifact path."""

    if progress:
        return progress
    for text in (response, prompt):
        match = _WORKER_RESULT_PATH_RE.search(text or "")
        if match:
            return match.group(0).rstrip(".,;:")
    return None


def estimate_token_usage(
    prompt: str,
    response: str,
    *,
    model: Optional[str] = None,
    effort: Optional[str] = None,
    progress: Optional[str] = None,
) -> TokenUsage:
    """Estimate prompt, final-response, and total token counts."""

    input_tokens = estimate_tokens(prompt)
    output_tokens = estimate_tokens(response)
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        model=model,
        effort=effort,
        progress=progress,
    )


def add_token_usage(left: TokenUsage | None, right: TokenUsage) -> TokenUsage:
    """Add usage from a retry to the usage already collected for a step."""

    if left is None:
        return right
    return TokenUsage(
        input_tokens=left.input_tokens + right.input_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        total_tokens=left.total_tokens + right.total_tokens,
        estimated=left.estimated or right.estimated,
        model=left.model if left.model == right.model else None,
        effort=left.effort if left.effort == right.effort else None,
        progress=right.progress or left.progress,
    )


def persist_worker_token_usage(
    *,
    terminal_id: str,
    provider: str,
    agent: str,
    usage: TokenUsage,
    run_id: Optional[str] = None,
    step_id: Optional[str] = None,
    progress: Optional[str] = None,
) -> Optional[str]:
    """Persist one completed worker attempt without failing the worker.

    SQLite remains the primary store. If it is unavailable, the same
    metadata-only record is durably appended to the token-usage spool for
    replay; prompt, response, and provider transcript data never enter it.

    Returns the stable record id of the persisted attempt (shared by the DB row
    and any spool replay), or ``None`` when the payload could not be built.
    """

    from cli_agent_orchestrator.services.token_usage_spool import (
        append_token_usage_spool,
        build_spool_payload,
    )

    try:
        payload = build_spool_payload(
            terminal_id=terminal_id,
            provider=provider,
            agent=agent,
            usage=usage,
            run_id=run_id,
            step_id=step_id,
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001 — fallback metadata must not break completion
        logger.warning("Failed to build token usage spool payload for worker %s: %s", terminal_id, exc)
        return None

    try:
        from cli_agent_orchestrator.clients.database import record_worker_token_usage

        record_worker_token_usage(
            terminal_id=terminal_id,
            provider=provider,
            agent=agent,
            run_id=run_id,
            step_id=step_id,
            usage=usage,
            progress=progress,
            record_id=payload.record_id,
            recorded_at=payload.recorded_at,
        )
    except Exception as exc:  # noqa: BLE001 — observability must not break worker completion
        logger.warning(
            "Failed to persist token usage for worker %s; queueing durable fallback: %s",
            terminal_id,
            exc,
        )
        try:
            append_token_usage_spool(payload)
        except Exception as spool_exc:  # noqa: BLE001 — worker completion remains primary
            logger.warning("Failed to spool token usage for worker %s: %s", terminal_id, spool_exc)

    return payload.record_id
