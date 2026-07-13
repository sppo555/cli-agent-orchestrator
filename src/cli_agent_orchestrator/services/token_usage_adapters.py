"""Strict native usage adapters for evidence-approved providers.

The adapters only inspect complete JSON objects or JSONL events. They never
search ordinary terminal prose for numbers, so a normal response cannot become
false native usage.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterable, Mapping, Optional

from cli_agent_orchestrator.models.provider import ProviderType
from cli_agent_orchestrator.services.token_usage_contract import NativeUsage

logger = logging.getLogger(__name__)


def _json_objects(raw: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(raw, Mapping):
        yield raw
        return
    if not isinstance(raw, str):
        return
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, Mapping):
        yield parsed
        return
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed_line = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed_line, Mapping):
            yield parsed_line


def _native_usage(value: Any) -> Optional[NativeUsage]:
    if not isinstance(value, Mapping):
        return None
    required = ("input_tokens", "output_tokens")
    if any(key not in value for key in required):
        return None
    counts = {key: value[key] for key in required}
    if any(isinstance(number, bool) or not isinstance(number, int) or number < 0 for number in counts.values()):
        return None
    total = value.get("total_tokens", counts["input_tokens"] + counts["output_tokens"])
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        return None
    if total != counts["input_tokens"] + counts["output_tokens"]:
        return None
    model = value.get("model")
    return NativeUsage(
        input_tokens=counts["input_tokens"],
        output_tokens=counts["output_tokens"],
        total_tokens=total,
        model=model if isinstance(model, str) and model else None,
    )


def extract_claude_code_usage(raw_output: Any) -> Optional[NativeUsage]:
    """Extract the last valid Claude result/assistant usage object."""

    found: Optional[NativeUsage] = None
    for event in _json_objects(raw_output):
        event_type = event.get("type")
        candidates: list[Any] = []
        if event_type == "result":
            candidates.append(event.get("usage"))
        if event_type == "assistant" and isinstance(event.get("message"), Mapping):
            message = event["message"]
            candidates.append(message.get("usage"))
            if isinstance(message.get("model"), str):
                candidates.append({**(message.get("usage") or {}), "model": message["model"]})
        for candidate in candidates:
            usage = _native_usage(candidate)
            if usage is not None:
                found = usage
    return found


def extract_codex_usage(raw_output: Any) -> Optional[NativeUsage]:
    """Extract usage from Codex turn-completed or token-count JSONL events."""

    found: Optional[NativeUsage] = None
    for event in _json_objects(raw_output):
        candidates: list[Any] = []
        if event.get("type") == "turn.completed":
            candidates.append(event.get("usage"))
        if event.get("method") == "turn/completed":
            params = event.get("params")
            if isinstance(params, Mapping) and isinstance(params.get("turn"), Mapping):
                candidates.append(params["turn"].get("usage"))
        payload = event.get("payload")
        if event.get("type") == "event_msg" and isinstance(payload, Mapping) and payload.get("type") == "token_count":
            info = payload.get("info", {})
            if isinstance(info, Mapping):
                candidates.append(info.get("last_token_usage"))
        for candidate in candidates:
            usage = _native_usage(candidate)
            if usage is not None:
                found = usage
    return found


def extract_native_usage(provider: str, raw_output: Any) -> Optional[NativeUsage]:
    if provider == ProviderType.CLAUDE_CODE.value:
        return extract_claude_code_usage(raw_output)
    if provider == ProviderType.CODEX.value:
        return extract_codex_usage(raw_output)
    return None
